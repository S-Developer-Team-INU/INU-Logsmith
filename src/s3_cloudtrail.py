import boto3
import json
import gzip
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from .cloud_trail import CloudTrailLogData, CloudTrailEvent
from .config import settings

class S3CloudTrailCollector:
    def __init__(self, region: str = 'ap-northeast-2'):
        self.region = region
        self.s3_client = boto3.client('s3', region_name=region)
    
    def _extract_datetime_from_filename(self, filename: str) -> Optional[datetime]:
        """
        파일명에서 날짜/시간을 추출합니다.
        파일명 형식: 093342385579_CloudTrail_ap-northeast-2_20250903T0000Z_K7srT6dKfHOBj6Zh.json.gz
        """
        # 파일명에서 타임스탬프 추출: YYYYMMDDTHHMMZ
        pattern = r'_(\d{8}T\d{4})Z_'
        match = re.search(pattern, filename)
        
        if match:
            timestamp = match.group(1)  # 예: 20250903T0000
            try:
                return datetime.strptime(timestamp, '%Y%m%dT%H%M')
            except ValueError:
                return None
        return None
        
    def collect_from_s3_bucket(
        self,
        bucket_name: str,
        prefix: Optional[str] = None,
        region: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_names: Optional[List[str]] = None,
        max_files: int = 10,
        existing_event_ids: Optional[set] = None
    ) -> CloudTrailLogData:
        """특정 S3 버킷에서 CloudTrail 로그 수집"""
        
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(seconds=settings.collection_interval)
        
        # prefix가 없으면 자동으로 CloudTrail 경로 찾기
        if prefix is None:
            prefix = self._find_cloudtrail_prefix(bucket_name, region)
        
        # S3 객체 목록 가져오기
        objects = self._list_s3_objects(bucket_name, prefix, start_time, end_time, max_files)
        
        all_events = []
        for obj_key in objects:
            try:
                events = self._process_s3_object(bucket_name, obj_key, event_names, existing_event_ids)
                all_events.extend(events)
            except Exception as e:
                print(f"Error processing {obj_key}: {e}")
                continue
        
        return CloudTrailLogData(records=all_events)
    
    def _list_s3_objects(
        self,
        bucket_name: str,
        prefix: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        last_timestamp: Optional[datetime] = None,
        max_files: int = 50
    ) -> List[str]:
        """시간 범위 또는 마지막 타임스탬프 이후 S3 객체 목록 반환"""

        objects = []

        try:
            print(f"S3 검색 시작: bucket={bucket_name}, prefix={prefix}")

            # 검색 모드 출력
            if start_time or end_time:
                print(f"[Once 모드] 시간 범위: {start_time} ~ {end_time}")
            elif last_timestamp:
                print(f"[Service 모드] 마지막 처리 이후: {last_timestamp}")
            else:
                print(f"[첫 실행] 최대 {max_files}개 파일 처리")

            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            total_files = 0
            matched_files = 0

            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        total_files += 1

                        if key.endswith('.json.gz'):
                            filename = key.split('/')[-1]
                            file_datetime = self._extract_datetime_from_filename(filename)

                            if file_datetime:
                                # Once 모드: 시간 범위 필터
                                if start_time or end_time:
                                    if start_time <= file_datetime <= end_time:
                                        objects.append(key)
                                        matched_files += 1

                                # Service 모드: 마지막 시간 이후
                                elif last_timestamp:
                                    if file_datetime > last_timestamp:
                                        objects.append(key)
                                        matched_files += 1

                                # 첫 실행: 모든 파일
                                else:
                                    objects.append(key)
                                    matched_files += 1

                                # max_files 제한
                                if len(objects) >= max_files:
                                    break

                if len(objects) >= max_files:
                    break

            print(f"S3 검색 결과: 전체 {total_files}개 파일 중 {matched_files}개 매칭")
            if matched_files > 0:
                print(f"첫 번째 매칭 파일: {objects[0]}")
                if matched_files > 1:
                    print(f"마지막 매칭 파일: {objects[-1]}")

        except Exception as e:
            print(f"S3 검색 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

        return objects
    
    def _process_s3_object(
        self, 
        bucket_name: str, 
        object_key: str, 
        event_names: Optional[List[str]] = None,
        existing_event_ids: Optional[set] = None
    ) -> List[CloudTrailEvent]:
        """S3 객체에서 CloudTrail 이벤트 추출"""
        
        # S3에서 파일 다운로드
        response = self.s3_client.get_object(Bucket=bucket_name, Key=object_key)
        
        # gzip 압축 해제
        with gzip.GzipFile(fileobj=response['Body']) as gz_file:
            content = gz_file.read().decode('utf-8')
        
        # JSON 파싱
        data = json.loads(content)
        
        events = []
        for record in data.get('Records', []):
            # 특정 이벤트만 필터링
            if event_names and record.get('eventName') not in event_names:
                continue
            
            # 기존 eventID 중복 체크
            event_id = record.get('eventID')
            if existing_event_ids and event_id in existing_event_ids:
                continue
            
            event = CloudTrailEvent.from_dict(record)
            events.append(event)
        
        return events
    
    def collect_from_multiple_buckets_batch(
        self,
        bucket_configs: List[Dict[str, Any]],
        duplicate_checker,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_names: Optional[List[str]] = None,
        batch_size: int = 100,
        last_processed_times: Optional[Dict[str, datetime]] = None
    ) -> tuple[CloudTrailLogData, Dict[str, datetime]]:
        """여러 S3 버킷에서 배치 단위로 로그 수집

        Args:
            last_processed_times: 버킷별 마지막 처리 타임스탬프 {bucket_name: datetime}

        Returns:
            tuple: (CloudTrailLogData, {bucket_name: last_timestamp})
        """

        all_events = []
        updated_times = {}

        if last_processed_times is None:
            last_processed_times = {}

        for config in bucket_configs:
            bucket_name = config['bucket_name']
            prefix = config.get('prefix')
            region = config.get('region')
            max_files = config.get('max_files', 50)

            try:
                events, last_timestamp = self._collect_bucket_batch(
                    bucket_name=bucket_name,
                    prefix=prefix,
                    region=region,
                    start_time=start_time,
                    end_time=end_time,
                    event_names=event_names,
                    max_files=max_files,
                    duplicate_checker=duplicate_checker,
                    batch_size=batch_size,
                    last_timestamp=last_processed_times.get(bucket_name)
                )
                all_events.extend(events)

                # 마지막 타임스탬프 저장
                if last_timestamp:
                    updated_times[bucket_name] = last_timestamp

            except Exception as e:
                print(f"Error collecting from bucket {bucket_name}: {e}")
                continue

        return CloudTrailLogData(records=all_events), updated_times

    def _collect_bucket_batch(
        self,
        bucket_name: str,
        prefix: Optional[str] = None,
        region: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_names: Optional[List[str]] = None,
        max_files: int = 10,
        duplicate_checker=None,
        batch_size: int = 100,
        last_timestamp: Optional[datetime] = None
    ) -> tuple[List[CloudTrailEvent], Optional[datetime]]:
        """S3 버킷에서 파일별 배치 처리

        Returns:
            tuple: (이벤트 목록, 마지막 처리 파일 타임스탬프)
        """

        # Once 모드: start_time/end_time 사용
        if start_time or end_time:
            if end_time is None:
                end_time = datetime.now()
            if start_time is None:
                start_time = end_time - timedelta(seconds=settings.collection_interval)

        if prefix is None:
            prefix = self._find_cloudtrail_prefix(bucket_name, region)

        # S3 객체 목록 가져오기
        objects = self._list_s3_objects(
            bucket_name,
            prefix,
            start_time=start_time,
            end_time=end_time,
            last_timestamp=last_timestamp,
            max_files=max_files
        )
        
        all_new_events = []
        last_file_timestamp = None

        # 파일별로 순차 처리
        for obj_key in objects:
            try:
                print(f"Processing {obj_key}...")

                # S3 파일에서 이벤트 추출
                file_events = self._process_s3_object(bucket_name, obj_key, event_names)

                if not file_events:
                    continue

                # 배치 단위로 중복 체크 및 저장
                for i in range(0, len(file_events), batch_size):
                    batch_events = file_events[i:i+batch_size]

                    # eventID 목록 추출
                    event_ids = [event.event_id for event in batch_events]

                    # DB에서 기존 eventID 확인
                    existing_ids = set()
                    if duplicate_checker:
                        existing_ids = duplicate_checker.check_existing_events(event_ids)

                    # 중복되지 않은 이벤트만 필터링
                    new_events = [
                        event for event in batch_events
                        if event.event_id not in existing_ids
                    ]

                    if new_events:
                        all_new_events.extend(new_events)
                        print(f"  배치 {i//batch_size + 1}: {len(new_events)}/{len(batch_events)}개 신규 이벤트")

                # 마지막 처리 파일의 타임스탬프 추출
                filename = obj_key.split('/')[-1]
                file_time = self._extract_datetime_from_filename(filename)
                if file_time:
                    last_file_timestamp = file_time

            except Exception as e:
                print(f"Error processing {obj_key}: {e}")
                continue

        return all_new_events, last_file_timestamp

    def collect_from_multiple_buckets(
        self,
        bucket_configs: List[Dict[str, Any]],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_names: Optional[List[str]] = None,
        existing_event_ids: Optional[set] = None
    ) -> CloudTrailLogData:
        """여러 S3 버킷에서 로그 수집 (기존 방식 유지)"""
        
        all_events = []
        
        for config in bucket_configs:
            bucket_name = config['bucket_name']
            prefix = config.get('prefix')
            region = config.get('region')
            max_files = config.get('max_files', 10)
            
            try:
                log_data = self.collect_from_s3_bucket(
                    bucket_name=bucket_name,
                    prefix=prefix,
                    region=region,
                    start_time=start_time,
                    end_time=end_time,
                    event_names=event_names,
                    max_files=max_files,
                    existing_event_ids=existing_event_ids
                )
                all_events.extend(log_data.records)
            except Exception as e:
                print(f"Error collecting from bucket {bucket_name}: {e}")
                continue
        
        return CloudTrailLogData(records=all_events)
    
    def _find_cloudtrail_prefix(self, bucket_name: str, region: Optional[str] = None) -> str:
        """버킷에서 CloudTrail 로그 경로 자동 탐지"""
        
        # 기본 CloudTrail 경로들 시도
        possible_prefixes = [
            "AWSLogs/",
            "CloudTrail/",
            "logs/"
        ]
        
        for base_prefix in possible_prefixes:
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    Prefix=base_prefix,
                    MaxKeys=10
                )
                
                for obj in response.get('Contents', []):
                    key = obj['Key']
                    # CloudTrail 로그 파일 패턴 확인
                    if 'CloudTrail' in key and key.endswith('.json.gz'):
                        # 경로에서 계정ID와 리전 추출하여 prefix 생성
                        parts = key.split('/')
                        for i, part in enumerate(parts):
                            if part == 'CloudTrail' and i > 0:
                                # AWSLogs/계정ID/CloudTrail/리전/ 형태로 prefix 생성
                                if region:
                                    return '/'.join(parts[:i+1]) + f'/{region}/'
                                else:
                                    return '/'.join(parts[:i+2]) + '/'
                        
                        # 기본 CloudTrail 경로 반환
                        return '/'.join(parts[:parts.index('CloudTrail')+1]) + '/'
                        
            except Exception:
                continue
        
        # 찾지 못한 경우 기본값
        return "AWSLogs/"
"""
EC2에서 실행되는 CloudTrail 로그 수집 및 전송 서비스
"""

import time
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from .cloud_trail import CloudTrailCollector
from .s3_cloudtrail import S3CloudTrailCollector
from .direct_rds import DirectRDSSender
from .config import settings

logger = logging.getLogger(__name__)


class EC2CloudTrailService:
    """EC2에서 실행되는 CloudTrail 수집 및 전송 서비스"""

    def __init__(self, s3_bucket_configs: Optional[List[Dict[str, Any]]] = None):
        self.collector = CloudTrailCollector()
        self.s3_collector = S3CloudTrailCollector(region=settings.aws_default_region) if s3_bucket_configs else None
        self.s3_bucket_configs = [cfg for cfg in (s3_bucket_configs or []) if cfg.get('enabled', False)]
        self.senders = self._initialize_senders()
        self.running = False
        self.last_processed_times = {}  # 버킷별 마지막 처리 타임스탬프 {bucket_name: datetime}

    def _initialize_senders(self) -> List:
        """전송자 초기화 - 환경변수에서 RDS 설정 읽기"""
        senders = []

        # DirectRDSSender는 환경변수에서 자동으로 설정을 읽음
        try:
            sender = DirectRDSSender()
            senders.append(sender)
            logger.info("RDS 전송자 초기화 완료")
        except Exception as e:
            logger.error(f"RDS 전송자 초기화 실패: {e}")
            raise

        return senders
    
    def collect_and_send(
        self,
        event_names: Optional[List[str]] = None,
        max_items: int = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> bool:
        """CloudTrail 로그 수집 및 전송"""
        try:
            # S3에서 로그 수집
            if not self.s3_collector or not self.s3_bucket_configs:
                logger.error("S3 수집기가 설정되지 않았습니다.")
                return False
                
            logger.info("S3에서 CloudTrail 로그 수집 시작...")

            # 배치 단위 처리로 효율적인 중복 제거
            duplicate_checker = self.senders[0] if self.senders else None

            # Once 모드: start_time/end_time 사용
            if start_time or end_time:
                logger.info(f"Once 모드: {start_time} ~ {end_time}")
                log_data, _ = self.s3_collector.collect_from_multiple_buckets_batch(
                    bucket_configs=self.s3_bucket_configs,
                    event_names=event_names,
                    duplicate_checker=duplicate_checker,
                    batch_size=100,
                    start_time=start_time,
                    end_time=end_time,
                    last_processed_times=None  # once 모드에서는 사용 안 함
                )
            # Service 모드: 순차 처리
            else:
                logger.info("Service 모드: 순차 처리")
                log_data, updated_times = self.s3_collector.collect_from_multiple_buckets_batch(
                    bucket_configs=self.s3_bucket_configs,
                    event_names=event_names,
                    duplicate_checker=duplicate_checker,
                    batch_size=100,
                    start_time=None,
                    end_time=None,
                    last_processed_times=self.last_processed_times
                )

                # 마지막 처리 시간 업데이트
                if updated_times:
                    self.last_processed_times.update(updated_times)
                    for bucket, timestamp in updated_times.items():
                        logger.info(f"[{bucket}] 마지막 처리 시간: {timestamp}")
            
            if log_data.total_events == 0:
                logger.info("수집된 이벤트가 없습니다.")
                return True
                
            logger.info(f"{log_data.total_events}개 이벤트 수집 완료")
            
            # 첫 번째 이벤트를 터미널에 출력 (디버그용)
            if log_data.records:
                first_event = log_data.records[0]
                print("\n=== 수집된 CloudTrail 이벤트 샘플 ===")
                print(f"이벤트명: {first_event.event_name}")
                print(f"시간: {first_event.event_time}")
                print(f"소스: {first_event.event_source}")
                print(f"리전: {first_event.aws_region}")
                print(f"사용자: {first_event.user_identity.type}")
                print(f"소스 IP: {first_event.source_ip_address}")
                print("=" * 40)
            
            # 모든 전송자에게 로그 전송
            success_count = 0
            for i, sender in enumerate(self.senders):
                try:
                    if sender.send_logs(log_data):
                        success_count += 1
                        logger.info(f"전송자 {i+1} 전송 성공")
                    else:
                        logger.error(f"전송자 {i+1} 전송 실패")
                except Exception as e:
                    logger.error(f"전송자 {i+1} 오류: {e}")
            
            logger.info(f"전송 완료: {success_count}/{len(self.senders)}개 성공")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"수집 및 전송 중 오류: {e}")
            return False
    
    def start_service(
        self,
        event_names: Optional[List[str]] = None
    ):
        """서비스 시작"""
        logger.info(f"EC2 CloudTrail 서비스 시작 (수집 간격: {settings.collection_interval}초)")
        
        self.running = True
        
        def signal_handler(signum, frame):
            logger.info("종료 신호 수신")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            while self.running:
                logger.info("수집 사이클 시작")
                
                self.collect_and_send(
                    event_names=event_names
                )
                
                if self.running:
                    logger.info(f"{settings.collection_interval}초 대기")
                    time.sleep(settings.collection_interval)
                    
        except KeyboardInterrupt:
            logger.info("키보드 인터럽트")
        except Exception as e:
            logger.error(f"서비스 실행 중 오류: {e}")
        finally:
            logger.info("서비스 종료")
    

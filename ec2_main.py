#!/usr/bin/env python3
"""
EC2에서 실행되는 CloudTrail 로그 수집 및 전송 메인 애플리케이션
"""

import json
import logging
import argparse
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.ec2_collector import EC2CloudTrailService
from src.config import settings

# 로그 설정
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_file: str) -> Dict[str, Any]:
    """설정 파일 로드"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}")
        return {}


def parse_datetime(date_str: str) -> datetime:
    """날짜/시간 문자열을 파싱합니다."""
    # 시간 포함 형식 시도
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # 날짜만 형식 시도
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f"지원되지 않는 날짜/시간 형식: {date_str}")



def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='EC2 CloudTrail 로그 수집 및 전송 서비스')
    parser.add_argument('--config', '-c', 
                       help='전송자 설정 파일 경로 (JSON)')
    parser.add_argument('--mode', choices=['once', 'service'], default='service',
                       help='실행 모드: once(한번), service(서비스)')
    parser.add_argument('--events', nargs='*',
                       help='수집할 CloudTrail 이벤트 이름 목록')
    parser.add_argument('--start-date', 
                       help='시작 날짜/시간 (YYYY-MM-DD 또는 YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--end-date',
                       help='종료 날짜/시간 (YYYY-MM-DD 또는 YYYY-MM-DD HH:MM:SS)')

    
    args = parser.parse_args()
    
    # 날짜 파싱
    start_date = None
    end_date = None
    
    try:
        if args.start_date:
            start_date = parse_datetime(args.start_date)
            logger.info(f"시작 날짜: {start_date}")
        
        if args.end_date:
            end_date = parse_datetime(args.end_date)
            # 종료일이 날짜만 입력된 경우 하루 끝까지 포함
            if args.end_date.count(' ') == 0:  # 시간 정보가 없는 경우
                end_date = end_date.replace(hour=23, minute=59, second=59)
            logger.info(f"종료 날짜: {end_date}")
            
    except ValueError as e:
        logger.error(f"날짜 형식 오류: {e}")
        logger.error("날짜는 YYYY-MM-DD 또는 YYYY-MM-DD HH:MM:SS 형식으로 입력해주세요.")
        sys.exit(1)
    
    # 설정 파일 로드 (S3 버킷 설정만)
    if not args.config:
        logger.error("설정 파일이 필요합니다. --config 옵션을 사용하세요.")
        sys.exit(1)

    config = load_config(args.config)
    if not config:
        logger.error(f"설정 파일을 로드할 수 없습니다: {args.config}")
        sys.exit(1)

    logger.info(f"설정 파일에서 S3 버킷 설정을 로드했습니다: {args.config}")

    s3_bucket_configs = config.get('s3_buckets', [])

    if not s3_bucket_configs:
        logger.warning("S3 버킷 설정이 없습니다.")

    logger.info(f"S3 버킷 설정: {len(s3_bucket_configs)}개")

    try:
        # EC2 서비스 초기화 (RDS 설정은 환경변수에서 자동 로드)
        service = EC2CloudTrailService(s3_bucket_configs)
        
        if args.mode == 'once':
            # 한 번만 실행
            logger.info("단일 실행 모드")
            success = service.collect_and_send(
                event_names=args.events,
                start_time=start_date,
                end_time=end_date
            )
            sys.exit(0 if success else 1)
            
        elif args.mode == 'service':
            # 서비스 모드
            logger.info("서비스 모드")
            if start_date or end_date:
                logger.warning("서비스 모드에서는 날짜 옵션이 무시됩니다.")
            service.start_service(
                event_names=args.events
            )
            
    except Exception as e:
        logger.error(f"실행 중 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
"""
직접 PostgreSQL RDS 접근
"""

import logging
import json
import uuid
import socket
import re
from datetime import datetime
from typing import Dict, Any, Optional
from .cloud_trail import CloudTrailLogData
from .config import settings

logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2 import pool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def is_valid_ip(ip_str: str) -> bool:
    """IP 주소 유효성 검사"""
    if not ip_str:
        return False
    
    # IPv4 패턴 체크
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(ipv4_pattern, ip_str):
        parts = ip_str.split('.')
        return all(0 <= int(part) <= 255 for part in parts)
    
    # IPv6 간단 체크
    if ':' in ip_str:
        try:
            socket.inet_pton(socket.AF_INET6, ip_str)
            return True
        except:
            return False
    
    return False


def process_ip_address(ip_str: str) -> Optional[str]:
    """IP 주소 처리 - 유효하지 않으면 None 반환"""
    if not ip_str:
        return None
    
    # 이미 유효한 IP라면 그대로 반환
    if is_valid_ip(ip_str):
        return ip_str
    
    # 도메인명이면 None 반환 (INET 타입에 저장 불가)
    return None



class DirectRDSSender:
    """직접 PostgreSQL RDS 전송"""

    def __init__(self, min_conn=1, max_conn=10):
        if not PSYCOPG2_AVAILABLE:
            raise Exception("psycopg2 설치 필요")

        # settings에서 RDS 설정 읽기
        self.rds_config = {
            'host': settings.rds_host,
            'port': settings.rds_port,
            'database': settings.rds_database,
            'user': settings.rds_user,
            'password': settings.rds_password
        }

        # settings에서 GROUP_ID 읽기
        self.group_id = settings.group_id

        # 커넥션 풀 생성
        try:
            self.connection_pool = pool.ThreadedConnectionPool(
                min_conn,
                max_conn,
                host=self.rds_config['host'],
                port=self.rds_config['port'],
                database=self.rds_config['database'],
                user=self.rds_config['user'],
                password=self.rds_config['password']
            )
            logger.info(f"RDS 커넥션 풀 생성 완료: {settings.rds_host}:{settings.rds_port}/{settings.rds_database} (min={min_conn}, max={max_conn})")
        except Exception as e:
            logger.error(f"커넥션 풀 생성 실패: {e}")
            raise

        logger.info(f"RDS 연결 설정: {settings.rds_host}:{settings.rds_port}/{settings.rds_database}")
        
    def send_logs(self, log_data: CloudTrailLogData) -> bool:
        """PostgreSQL RDS에 직접 로그 전송"""
        conn = None
        try:
            # 커넥션 풀에서 연결 가져오기
            conn = self.connection_pool.getconn()

            cursor = conn.cursor()

            for event in log_data.records:
                # 1. events 테이블에 UUID 생성하여 삽입
                event_uuid = str(uuid.uuid4())
                # IP 주소 처리
                processed_ip = process_ip_address(event.source_ip_address)
                
                cursor.execute("""
                    INSERT INTO events (id, group_id, source_product, source_ip, user_agent, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (event_uuid, self.group_id, 'cloudtrail', processed_ip, event.user_agent, datetime.now()))
                
                # 2. cloudtrail 테이블에 로그 데이터 삽입
                user_identity_json = json.dumps({
                    'type': event.user_identity.type,
                    'principalId': event.user_identity.principal_id,
                    'arn': event.user_identity.arn,
                    'accountId': event.user_identity.account_id,
                    'accessKeyId': event.user_identity.access_key_id,
                    'userName': event.user_identity.user_name
                })
                
                request_parameters_json = json.dumps(event.request_parameters)
                response_elements_json = json.dumps(event.response_elements)
                
                # TLS details JSON 준비
                tls_details_json = None
                if event.tls_details:
                    tls_details_json = json.dumps({
                        'tlsVersion': event.tls_details.tls_version,
                        'cipherSuite': event.tls_details.cipher_suite,
                        'clientProvidedHostHeader': event.tls_details.client_provided_host_header
                    })

                # insight_details JSON 준비
                insight_details_json = json.dumps(event.insight_details) if event.insight_details else None

                # resources JSON 준비
                resources_json = json.dumps(event.resources) if event.resources else None

                cursor.execute("""
                    INSERT INTO cloudtrail
                    (id, event_id, event_version, event_time, event_source, event_name,
                     event_category, event_type, aws_region, read_only, request_id,
                     source_ip, user_agent, management_event, recipient_account_id,
                     session_credential_from_console, shared_event_id, error_code, error_message,
                     user_identity, tls_details, request_parameters, response_elements,
                     insight_details, resources)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    event_uuid,
                    event.event_id,  # AWS CloudTrail의 실제 eventID 저장
                    event.event_version,
                    event.event_time,
                    event.event_source,
                    event.event_name,
                    event.event_category,
                    event.event_type,
                    event.aws_region,
                    event.read_only,
                    event.request_id,
                    processed_ip,  # 처리된 IP 주소 사용
                    event.user_agent,
                    event.management_event,
                    event.recipient_account_id,
                    event.session_credential_from_console,
                    event.shared_event_id,
                    event.error_code,
                    event.error_message,
                    user_identity_json,
                    tls_details_json,
                    request_parameters_json,
                    response_elements_json,
                    insight_details_json,
                    resources_json
                ))
            
            conn.commit()
            logger.info(f"PostgreSQL 저장 완료: {len(log_data.records)}개")
            return True

        except Exception as e:
            logger.error(f"PostgreSQL 저장 오류: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                # 커넥션을 풀에 반환
                self.connection_pool.putconn(conn)
    
    def check_existing_events(self, event_ids: list) -> set:
        """기존에 저장된 eventID들 확인"""
        if not event_ids:
            return set()

        conn = None
        try:
            # 커넥션 풀에서 연결 가져오기
            conn = self.connection_pool.getconn()

            cursor = conn.cursor()

            # eventID들을 IN 절로 한번에 조회
            placeholders = ','.join(['%s'] * len(event_ids))
            query = f"""
                SELECT DISTINCT event_id
                FROM cloudtrail
                WHERE event_id IN ({placeholders})
            """

            cursor.execute(query, event_ids)
            existing_events = {row[0] for row in cursor.fetchall()}

            logger.info(f"기존 이벤트 확인: {len(existing_events)}/{len(event_ids)}개 중복")
            return existing_events

        except Exception as e:
            logger.error(f"기존 이벤트 확인 오류: {e}")
            return set()
        finally:
            if conn:
                # 커넥션을 풀에 반환
                self.connection_pool.putconn(conn)

    def set_group_id(self, group_id: str):
        """그룹 ID 설정"""
        self.group_id = group_id
        logger.info(f"그룹 ID 설정: {group_id}")

    def close_pool(self):
        """커넥션 풀 종료"""
        if hasattr(self, 'connection_pool') and self.connection_pool:
            self.connection_pool.closeall()
            logger.info("커넥션 풀 종료 완료")

    def __del__(self):
        """소멸자 - 커넥션 풀 정리"""
        self.close_pool()
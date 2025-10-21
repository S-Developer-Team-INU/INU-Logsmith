import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS 설정 (IAM 역할 사용 시 선택사항)
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_default_region: str = Field(default="ap-northeast-2", env="AWS_DEFAULT_REGION")

    # RDS 설정
    rds_host: str = Field(..., env="RDS_HOST", description="RDS 호스트 주소 (필수)")
    rds_port: int = Field(..., env="RDS_PORT", description="RDS 포트")
    rds_database: str = Field(..., env="RDS_DATABASE", description="데이터베이스 이름")
    rds_user: str = Field(..., env="RDS_USER", description="데이터베이스 사용자")
    rds_password: str = Field(..., env="RDS_PASSWORD", description="데이터베이스 비밀번호 (필수)")

    # 애플리케이션 설정
    group_id: str = Field(..., env="GROUP_ID", description="이벤트 그룹 ID (필수)")

    # 로그 설정
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # 수집 설정
    collection_interval: int = Field(default=300, env="COLLECTION_INTERVAL")
    batch_size: int = Field(default=100, env="BATCH_SIZE")

    class Config:
        # systemd 환경변수 또는 시스템 환경변수에서 읽기
        extra = "ignore"  # 추가 환경변수 무시


# 글로벌 설정 인스턴스
settings = Settings()
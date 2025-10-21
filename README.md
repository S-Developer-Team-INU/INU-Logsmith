# INU-Detector: CloudTrail 로그 수집 및 PostgreSQL RDS 전송

EC2에서 CloudTrail 로그를 수집하여 PostgreSQL RDS로 직접 전송하는 시스템입니다.

## 개요

- **수집**: AWS CloudTrail API 또는 S3 버킷에서 로그 수집
- **전송**: PostgreSQL RDS 직접 접근
- **저장**: PostgreSQL RDS에 JSON 형태로 저장
- **자동화**: systemd 서비스로 지속적 수집
- **보안**: 환경변수 및 파일 권한 관리

## 빠른 시작

### 원클릭 설치 (권장)

```bash
curl -fsSL https://raw.githubusercontent.com/S-Developer-Team-INU/INU-Logsmith/main/install.sh | bash
```

설치 스크립트가 다음을 수행합니다:
- 최신 버전 다운로드
- Python 의존성 설치
- 대화형 설정 (Group ID, S3 Bucket, RDS 정보)
- 설정 파일 자동 생성
- 실행 스크립트 생성

### 수동 설치

```bash
cd /opt
sudo git clone https://github.com/S-Developer-Team-INU/INU-Logsmith.git
sudo chown -R ec2-user:ec2-user INU-Logsmith
cd INU-Logsmith

# Python 가상환경 생성 및 의존성 설치
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

수동 설치 후에는 아래 **3. 환경변수 설정**과 **4. S3 버킷 설정** 섹션을 참고하여 설정 파일을 직접 생성하세요.

### 2. AWS 권한 설정

EC2에 IAM 역할 연결:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "cloudtrail:LookupEvents",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "*",
                "arn:aws:s3:::your-cloudtrail-bucket/*",
                "arn:aws:s3:::your-cloudtrail-bucket"
            ]
        }
    ]
}
```

### 3. 환경변수 설정

환경변수는 **systemd 서비스 파일**에서 관리됩니다.

`inu-detector.service` 파일의 Environment 섹션 수정:
```ini
[Service]
# AWS 설정 (IAM 역할 사용 시 기본값으로 충분)
Environment="AWS_DEFAULT_REGION=ap-northeast-2"

# 로그 설정
Environment="LOG_LEVEL=INFO"

# 수집 설정
Environment="COLLECTION_INTERVAL=300"
Environment="BATCH_SIZE=100"

# RDS 설정 (필수)
Environment="RDS_HOST=your-rds-endpoint.rds.amazonaws.com"
Environment="RDS_PORT=5432"
Environment="RDS_DATABASE=postgres"
Environment="RDS_USER=postgres"
Environment="RDS_PASSWORD=your-postgres-password"

# 애플리케이션 설정 (필수)
Environment="GROUP_ID=your-group-uuid-here"
```

> **참고**: RDS 설정은 systemd 환경변수로 관리되며 Git에 커밋되지 않습니다.

### 4. S3 버킷 설정

`config/sender_config.json` 수정 (S3 버킷 설정만):
```json
{
  "s3_buckets": [
    {
      "bucket_name": "your-cloudtrail-bucket",
      "prefix": "AWSLogs/123456789012/CloudTrail/ap-northeast-2/",
      "region": "ap-northeast-2",
      "max_files": 100,
      "enabled": true,
      "description": "메인 CloudTrail 로그 버킷"
    }
  ]
}
```

> **참고**: RDS 설정은 더 이상 JSON 파일에 없습니다. systemd 환경변수로 관리됩니다.

### 5. systemd 서비스 등록

```bash
# 서비스 파일 복사
sudo cp inu-detector.service /etc/systemd/system/

# systemd 데몬 재로드
sudo systemctl daemon-reload

# 부팅 시 자동 시작 설정
sudo systemctl enable inu-detector

# 서비스 시작
sudo systemctl start inu-detector

# 서비스 상태 확인
sudo systemctl status inu-detector
```

### 6. 파일 권한 보안 설정

```bash
# 민감한 파일 권한 제한
chmod 600 inu-detector.service
chmod 600 config/sender_config.json

# 소유자만 접근 가능하도록 설정
chown ec2-user:ec2-user inu-detector.service config/sender_config.json
```

## 실행 방법

### 단일 실행 (테스트)
```bash
python ec2_main.py --mode once --config config/sender_config.json
```

### 서비스 실행 (운영)
```bash
sudo systemctl start inu-detector
sudo systemctl enable inu-detector
sudo systemctl status inu-detector
```

### S3에서 로그 수집
```bash
# S3 버킷에서 CloudTrail 로그 수집
python ec2_main.py --mode once --config config/sender_config.json --use-s3

# 특정 이벤트만 S3에서 수집
python ec2_main.py --events ConsoleLogin --config config/sender_config.json --use-s3
```

## 동작 방식

### DB 구조
- **groups**: 그룹 정보 저장
- **events**: UUID id와 group_id로 이벤트 관리
- **cloudtrail**: 실제 CloudTrail 로그 데이터, events.id와 외래키 연결

### 자동화된 방식
1. **로그 수집**: CloudTrail API 또는 S3 버킷에서 로그 수집
2. **events 테이블**: UUID 생성 후 group_id와 함께 저장
3. **cloudtrail 테이블**: events.id를 외래키로 로그 데이터 저장
4. **자동 반복**: 설정된 간격으로 지속적 수집

## 모니터링

### 서비스 상태
```bash
sudo systemctl status inu-detector
sudo journalctl -u inu-detector -f
```

### 수동 테스트
```bash
cd /opt/INU-Detector
source venv/bin/activate

# PostgreSQL 연결 테스트
psql -h your-rds-endpoint.rds.amazonaws.com -p 5432 -U postgres -d postgres -c "SELECT COUNT(*) FROM events;"
psql -h your-rds-endpoint.rds.amazonaws.com -p 5432 -U postgres -d postgres -c "SELECT COUNT(*) FROM cloudtrail;"

# 테이블 관계 확인
psql -h your-rds-endpoint.rds.amazonaws.com -p 5432 -U postgres -d postgres -c "SELECT e.id, e.group_id, c.event_name FROM events e JOIN cloudtrail c ON e.id = c.event_id LIMIT 5;"

# CloudTrail API 테스트
python -c "import boto3; print(boto3.client('cloudtrail').describe_trails())"

# 전체 테스트
python ec2_main.py --mode once --config config/sender_config.json
```

## 설정 옵션

### 수집 설정
- `COLLECTION_INTERVAL`: 수집 간격 (초, 기본값: 300)
- `BATCH_SIZE`: 한 번에 처리할 로그 수 (기본값: 100)
- `group_id`: 이벤트 그룹 ID (sender_config.json에서 설정)

### 특정 이벤트만 수집
```bash
# CloudTrail API에서 수집
python ec2_main.py --events ConsoleLogin AssumeRole --config config/sender_config.json

# S3 버킷에서 수집
python ec2_main.py --events ConsoleLogin AssumeRole --config config/sender_config.json --use-s3
```

### 그룹 ID 설정
`config/sender_config.json`에서 `group_id` 값을 수정:
```json
{
  "senders": [
    {
      "type": "rds_direct",
      "group_id": "your-group-uuid-here",
      "rds": { ... }
    }
  ]
}
```

## 문제 해결

### 1. AWS 자격증명 오류
```bash
# IAM 역할 확인
aws sts get-caller-identity

# CloudTrail 권한 테스트
aws cloudtrail describe-trails
```

### 2. PostgreSQL 연결 오류
```bash
# 직접 연결 테스트
psql -h your-rds-endpoint.rds.amazonaws.com -p 5432 -U postgres -d postgres
```

### 3. 환경변수 확인
```bash
# systemd 서비스 환경변수 확인
sudo systemctl show inu-detector | grep Environment

# 서비스 재시작 (환경변수 변경 후)
sudo systemctl daemon-reload
sudo systemctl restart inu-detector
```

## S3 버킷 설정

### S3 버킷에서 CloudTrail 로그 수집

`config/sender_config.json`에 S3 버킷 설정 추가:
```json
{
  "s3_buckets": [
    {
      "bucket_name": "my-cloudtrail-logs",
      "prefix": "AWSLogs/123456789012/CloudTrail/ap-northeast-2/",
      "max_files": 20,
      "enabled": true,
      "description": "메인 CloudTrail 로그 버킷"
    },
    {
      "bucket_name": "security-audit-logs", 
      "prefix": "AWSLogs/123456789012/CloudTrail/us-east-1/",
      "max_files": 10,
      "enabled": true,
      "description": "보안 감사용 로그 버킷"
    }
  ]
}
```

### S3 사용법
```bash
# 가상환경 활성화
source venv/bin/activate

# S3에서 로그 수집 (단일 실행)
python ec2_main.py --mode once --config config/sender_config.json --use-s3

# S3에서 특정 이벤트만 수집
python ec2_main.py --events ConsoleLogin AssumeRole --config config/sender_config.json --use-s3

# S3 서비스 모드 (지속적 수집)
python ec2_main.py --mode service --config config/sender_config.json --use-s3
```

## 파일 구조

```
INU-Detector/
├── src/
│   ├── cloud_trail.py          # CloudTrail API 수집
│   ├── s3_cloudtrail.py        # S3 버킷에서 CloudTrail 수집
│   ├── direct_rds.py           # PostgreSQL RDS 직접 전송
│   ├── ec2_collector.py        # EC2 수집 서비스
│   └── config.py               # 설정 관리
├── config/
│   ├── sender_config.json      # S3 버킷 설정 (Git 제외)
│   └── sender_config.example.json  # 설정 예제
├── sql/
│   └── create_table.sql        # 테이블 스키마
├── ec2_main.py                 # 메인 실행 파일
├── inu-detector.service        # systemd 서비스 파일
├── install.sh                  # 원클릭 설치 스크립트
├── requirements.txt            # Python 의존성
├── .gitignore                  # 민감 파일 제외
└── README.md                   # 이 파일
```

## 보안 고려사항

### 1. 자격증명 관리
- **systemd 환경변수**: RDS 비밀번호를 systemd 서비스 파일에서 관리
- **IAM 역할**: AWS Access Key 대신 IAM 역할 사용 권장
- **파일 권한**: systemd 서비스 파일과 설정 파일 권한을 600으로 제한

### 2. 네트워크 보안
- **RDS 보안 그룹**: EC2에서만 접근 허용
- **SSL/TLS**: PostgreSQL 연결 시 SSL 사용 권장

### 3. 파일 시스템 보안
```bash
# 권한 설정
chmod 600 inu-detector.service config/sender_config.json

# Git에서 제외
config/sender_config.json
```

### 4. 최소 권한 원칙
- CloudTrail 읽기 권한만 부여
- PostgreSQL 사용자는 INSERT 권한만 부여

## 성능 최적화

### 배치 처리
현재는 개별 INSERT를 사용하지만, 대량 데이터 처리 시 배치 INSERT로 개선 가능:

```python
cursor.executemany("""
    INSERT INTO cloudtrail (...)
    VALUES (%s, %s, ...)
""", batch_data)
```

### 연결 풀링
대량 처리 시 연결 풀링 사용 권장:

```python
from psycopg2 import pool
connection_pool = psycopg2.pool.SimpleConnectionPool(1, 20, ...)
```

## 보안 체크리스트

- [ ] systemd 서비스 파일 권한 600 설정
- [ ] config/sender_config.json 권한 600 설정
- [ ] .gitignore에 민감 파일 추가
- [ ] PostgreSQL 사용자 최소 권한 설정
- [ ] RDS 보안 그룹 설정
- [ ] IAM 역할 CloudTrail 권한 확인

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.
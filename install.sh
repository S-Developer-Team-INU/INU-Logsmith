#!/bin/bash
set -e

# INU Detector 설치 및 설정 스크립트
# Usage: curl -fsSL https://raw.githubusercontent.com/S-Developer-Team-INU/INU-Logsmith/main/install.sh | bash

echo "========================================="
echo "      INU Detector 설치 및 설정"
echo "========================================="

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 함수 정의
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 필요한 도구 확인
check_requirements() {
    print_status "필요한 도구들을 확인하는 중..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3가 설치되어 있지 않습니다."
        exit 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3가 설치되어 있지 않습니다."
        exit 1
    fi
    
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        print_error "curl 또는 wget이 설치되어 있지 않습니다."
        exit 1
    fi
    
    if ! command -v tar &> /dev/null; then
        print_error "tar가 설치되어 있지 않습니다."
        exit 1
    fi
    
    print_success "모든 필요한 도구가 설치되어 있습니다."
}

# 사용자 입력 받기
get_user_input() {
    echo ""
    print_status "설정 정보를 입력해주세요:"
    echo ""
    
    # Group ID 입력
    while true; do
        read -p "$(echo -e "${BLUE}Group ID를 입력하세요:${NC} ")" GROUP_ID
        if [[ -n "$GROUP_ID" ]]; then
            break
        else
            print_warning "Group ID는 필수 입력값입니다."
        fi
    done
    
    # S3 Bucket Name 입력
    while true; do
        read -p "$(echo -e "${BLUE}S3 Bucket Name을 입력하세요:${NC} ")" BUCKET_NAME
        if [[ -n "$BUCKET_NAME" ]]; then
            break
        else
            print_warning "S3 Bucket Name은 필수 입력값입니다."
        fi
    done
    
    # AWS Region 입력 (기본값 제공)
    read -p "$(echo -e "${BLUE}AWS Region을 입력하세요 [ap-northeast-2]:${NC} ")" REGION
    REGION=${REGION:-ap-northeast-2}

    echo ""
    echo "=== RDS 데이터베이스 설정 ==="

    # RDS Host 입력
    while true; do
        read -p "$(echo -e "${BLUE}RDS Host를 입력하세요:${NC} ")" RDS_HOST
        if [[ -n "$RDS_HOST" ]]; then
            break
        else
            print_warning "RDS Host는 필수 입력값입니다."
        fi
    done

    # RDS Port 입력 (기본값 제공)
    read -p "$(echo -e "${BLUE}RDS Port를 입력하세요 [5432]:${NC} ")" RDS_PORT
    RDS_PORT=${RDS_PORT:-5432}

    # RDS Database 입력 (기본값 제공)
    read -p "$(echo -e "${BLUE}Database 이름을 입력하세요 [postgres]:${NC} ")" RDS_DATABASE
    RDS_DATABASE=${RDS_DATABASE:-postgres}

    # RDS User 입력 (기본값 제공)
    read -p "$(echo -e "${BLUE}Database 사용자를 입력하세요 [postgres]:${NC} ")" RDS_USER
    RDS_USER=${RDS_USER:-postgres}

    # RDS Password 입력 (필수)
    while true; do
        read -s -p "$(echo -e "${BLUE}RDS Password를 입력하세요:${NC} ")" RDS_PASSWORD
        echo ""
        if [[ -n "$RDS_PASSWORD" ]]; then
            break
        else
            print_warning "RDS Password는 필수 입력값입니다."
        fi
    done
    
    echo ""
    print_status "입력된 설정:"
    echo "  - Group ID: $GROUP_ID"
    echo "  - S3 Bucket Name: $BUCKET_NAME"
    echo "  - AWS Region: $REGION"
    echo "  - RDS Host: $RDS_HOST"
    echo "  - RDS Port: $RDS_PORT"
    echo "  - RDS Database: $RDS_DATABASE"
    echo "  - RDS User: $RDS_USER"
    echo "  - RDS Password: [설정됨]"
    echo ""
    
    read -p "$(echo -e "${YELLOW}이 설정으로 진행하시겠습니까? (y/N):${NC} ")" CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        print_error "설치가 취소되었습니다."
        exit 1
    fi
}

# GitHub 릴리즈에서 최신 버전 가져오기
get_latest_version() {
    print_status "최신 릴리즈 버전을 확인하는 중..."
    
    # GitHub API를 사용하여 최신 릴리즈 정보 가져오기
    REPO_URL="https://api.github.com/repos/S-Developer-Team-INU/INU-Logsmith/releases/latest"
    
    if command -v curl &> /dev/null; then
        LATEST_VERSION=$(curl -s "$REPO_URL" | grep '"tag_name":' | sed -E 's/.*"tag_name": "([^"]+)".*/\1/')
    elif command -v wget &> /dev/null; then
        LATEST_VERSION=$(wget -qO- "$REPO_URL" | grep '"tag_name":' | sed -E 's/.*"tag_name": "([^"]+)".*/\1/')
    else
        print_error "curl 또는 wget이 필요합니다."
        exit 1
    fi
    
    if [[ -z "$LATEST_VERSION" ]]; then
        print_warning "최신 버전을 가져올 수 없습니다. 기본 버전을 사용합니다."
        LATEST_VERSION="v1.0.0"  # 기본값
    fi
    
    print_success "최신 버전: $LATEST_VERSION"
}

# 릴리즈 패키지 다운로드
download_project() {
    get_latest_version

    print_status "INU Detector를 다운로드하는 중..."

    # 임시 디렉토리 생성
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"

    # GitHub 릴리즈에서 portable 패키지 다운로드 시도
    DOWNLOAD_URL="https://github.com/S-Developer-Team-INU/INU-Logsmith/releases/download/${LATEST_VERSION}/inu-detector-portable.tar.gz"

    if command -v curl &> /dev/null; then
        if ! curl -fL -o inu-detector-portable.tar.gz "$DOWNLOAD_URL" 2>/dev/null; then
            print_warning "릴리즈 패키지를 찾을 수 없습니다. main 브랜치를 다운로드합니다."
            curl -fL -o inu-detector.tar.gz "https://github.com/S-Developer-Team-INU/INU-Logsmith/archive/refs/heads/main.tar.gz"
            PACKAGE_NAME="inu-detector.tar.gz"
        else
            PACKAGE_NAME="inu-detector-portable.tar.gz"
        fi
    elif command -v wget &> /dev/null; then
        if ! wget -O inu-detector-portable.tar.gz "$DOWNLOAD_URL" 2>/dev/null; then
            print_warning "릴리즈 패키지를 찾을 수 없습니다. main 브랜치를 다운로드합니다."
            wget -O inu-detector.tar.gz "https://github.com/S-Developer-Team-INU/INU-Logsmith/archive/refs/heads/main.tar.gz"
            PACKAGE_NAME="inu-detector.tar.gz"
        else
            PACKAGE_NAME="inu-detector-portable.tar.gz"
        fi
    else
        print_error "curl 또는 wget이 필요합니다."
        exit 1
    fi

    if [[ ! -f "$PACKAGE_NAME" ]]; then
        print_error "패키지 다운로드에 실패했습니다."
        exit 1
    fi

    # 압축 해제
    tar -xzf "$PACKAGE_NAME"

    # 압축 해제된 디렉토리로 이동 (디렉토리명이 다를 수 있음)
    if [[ -d "inu-detector-portable" ]]; then
        cd inu-detector-portable
    else
        # 첫 번째 디렉토리로 이동
        EXTRACTED_DIR=$(find . -maxdepth 1 -type d ! -name '.' | head -n 1)
        if [[ -z "$EXTRACTED_DIR" ]]; then
            print_error "압축 해제된 디렉토리를 찾을 수 없습니다."
            exit 1
        fi
        cd "$EXTRACTED_DIR"
    fi

    print_success "패키지 다운로드 및 압축해제 완료"
}

# Python 의존성 설치
install_dependencies() {
    print_status "Python 의존성을 설치하는 중..."
    
    # 필수 패키지들을 직접 설치 (requirements.txt가 없을 경우를 대비)
    REQUIRED_PACKAGES=(
        "pydantic>=2.0.0"
        "pydantic-settings>=2.0.0"
        "psycopg2-binary>=2.9.0"
        "boto3>=1.26.0"
        "python-dotenv>=1.0.0"
    )
    
    # requirements.txt가 있다면 우선 사용
    if [[ -f "requirements.txt" ]]; then
        pip3 install -r requirements.txt
        print_success "requirements.txt에서 의존성 설치 완료"
    else
        print_status "필수 패키지를 개별적으로 설치합니다..."
        for package in "${REQUIRED_PACKAGES[@]}"; do
            print_status "설치 중: $package"
            pip3 install "$package"
        done
        print_success "필수 Python 의존성 설치 완료"
    fi
}

# systemd 서비스 파일 설정
setup_systemd_service() {
    print_status "systemd 서비스 파일을 설정하는 중..."

    # inu-detector.service 파일의 환경변수 업데이트
    if [[ -f "inu-detector.service" ]]; then
        # RDS 설정 업데이트
        sed -i "s|Environment=\"RDS_HOST=CHANGE_ME\"|Environment=\"RDS_HOST=$RDS_HOST\"|g" inu-detector.service
        sed -i "s|Environment=\"RDS_PORT=5432\"|Environment=\"RDS_PORT=$RDS_PORT\"|g" inu-detector.service
        sed -i "s|Environment=\"RDS_DATABASE=postgres\"|Environment=\"RDS_DATABASE=$RDS_DATABASE\"|g" inu-detector.service
        sed -i "s|Environment=\"RDS_USER=postgres\"|Environment=\"RDS_USER=$RDS_USER\"|g" inu-detector.service
        sed -i "s|Environment=\"RDS_PASSWORD=CHANGE_ME\"|Environment=\"RDS_PASSWORD=$RDS_PASSWORD\"|g" inu-detector.service

        # GROUP_ID 업데이트
        sed -i "s|Environment=\"GROUP_ID=CHANGE_ME\"|Environment=\"GROUP_ID=$GROUP_ID\"|g" inu-detector.service

        # AWS_DEFAULT_REGION 업데이트
        sed -i "s|Environment=\"AWS_DEFAULT_REGION=ap-northeast-2\"|Environment=\"AWS_DEFAULT_REGION=$REGION\"|g" inu-detector.service

        print_success "systemd 서비스 파일 설정 완료"
        print_warning "서비스 등록 방법:"
        echo "  sudo cp inu-detector.service /etc/systemd/system/"
        echo "  sudo systemctl daemon-reload"
        echo "  sudo systemctl enable inu-detector"
        echo "  sudo systemctl start inu-detector"
    else
        print_warning "inu-detector.service 파일을 찾을 수 없습니다."
    fi
}

# 설정 파일 생성
create_config_file() {
    print_status "설정 파일을 생성하는 중..."

    mkdir -p config

    # sender_config.json 생성 (S3 버킷 설정만)
    cat > config/sender_config.json << EOF
{
  "s3_buckets": [
    {
      "bucket_name": "$BUCKET_NAME",
      "prefix": "AWSLogs/",
      "region": "$REGION",
      "max_files": 100,
      "enabled": true,
      "description": "메인 CloudTrail 로그 버킷"
    }
  ]
}
EOF

    chmod 600 config/sender_config.json
    print_success "설정 파일 생성 완료 (config/sender_config.json)"
    print_status "RDS 설정은 systemd 환경변수에 저장됩니다."
}

# 실행 스크립트 생성
create_run_script() {
    print_status "실행 스크립트를 생성하는 중..."

    cat > run_inu_detector.sh << EOF
#!/bin/bash
# INU Detector 실행 스크립트

SCRIPT_DIR="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "\$SCRIPT_DIR"

# systemd와 동일한 환경변수 설정
export AWS_DEFAULT_REGION="$REGION"
export LOG_LEVEL="INFO"
export COLLECTION_INTERVAL="300"
export BATCH_SIZE="100"

# RDS 설정
export RDS_HOST="$RDS_HOST"
export RDS_PORT="$RDS_PORT"
export RDS_DATABASE="$RDS_DATABASE"
export RDS_USER="$RDS_USER"
export RDS_PASSWORD="$RDS_PASSWORD"

# 애플리케이션 설정
export GROUP_ID="$GROUP_ID"

# Python 가상환경 활성화
if [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
fi

# Python 경로 설정
export PYTHONPATH="\$SCRIPT_DIR:\$PYTHONPATH"

# INU Detector 실행 (config 파일 필수)
python3 ec2_main.py --config config/sender_config.json "\$@"
EOF

    chmod +x run_inu_detector.sh

    print_success "실행 스크립트 생성 완료 (run_inu_detector.sh)"
}

# 최종 디렉토리로 이동
finalize_installation() {
    print_status "설치를 완료하는 중..."
    
    # 홈 디렉토리 또는 원하는 위치로 복사
    INSTALL_DIR="$HOME/inu-detector"
    
    if [[ -d "$INSTALL_DIR" ]]; then
        read -p "$(echo -e "${YELLOW}$INSTALL_DIR 디렉토리가 이미 존재합니다. 덮어쓰시겠습니까? (y/N):${NC} ")" OVERWRITE
        if [[ "$OVERWRITE" =~ ^[Yy]$ ]]; then
            rm -rf "$INSTALL_DIR"
        else
            print_error "설치가 취소되었습니다."
            exit 1
        fi
    fi
    
    cp -r . "$INSTALL_DIR"
    cd "$HOME"
    
    print_success "INU Detector가 $INSTALL_DIR에 설치되었습니다."
    
    # 버전 정보 저장
    echo "$LATEST_VERSION" > "$INSTALL_DIR/.version"
    
    echo ""
    echo "========================================="
    echo "           설치 완료!"
    echo "========================================="
    echo ""
    print_status "설치된 버전: $LATEST_VERSION"
    echo ""
    print_status "사용법:"
    echo "  cd $INSTALL_DIR"
    echo "  ./run_inu_detector.sh --mode once    # 한 번만 실행"
    echo "  ./run_inu_detector.sh --mode service # 서비스 모드로 실행"
    echo ""
    print_status "systemd 서비스 등록:"
    echo "  sudo cp $INSTALL_DIR/inu-detector.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable inu-detector"
    echo "  sudo systemctl start inu-detector"
    echo ""
    print_status "설정 파일 위치:"
    echo "  - systemd 환경변수: $INSTALL_DIR/inu-detector.service"
    echo "  - 전송자 설정: $INSTALL_DIR/config/sender_config.json"
    echo ""
    print_status "업데이트:"
    echo "  - 최신 버전 확인: curl -fsSL https://raw.githubusercontent.com/S-Developer-Team-INU/INU-Logsmith/main/install.sh | bash"
    echo ""
    print_status "로그 확인:"
    echo "  - 애플리케이션 로그는 콘솔에 출력됩니다."
    echo ""
    
    # 임시 디렉토리 정리
    rm -rf "$TEMP_DIR"
}

# 메인 실행 함수
main() {
    echo ""
    check_requirements
    get_user_input
    download_project
    install_dependencies
    setup_systemd_service
    create_config_file
    create_run_script
    finalize_installation

    print_success "모든 설치 과정이 완료되었습니다!"
}

# 스크립트 실행
main "$@"
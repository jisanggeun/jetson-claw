#!/usr/bin/env bash
# Jetson Orin Nano 초기 설치 스크립트
# 사용법: bash scripts/install.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Jetson Automation 설치 ==="

# 1. Python venv 생성
echo "[1/4] Python 가상환경 생성..."
python3 -m venv .venv
source .venv/bin/activate

# 2. 의존성 설치
echo "[2/4] 패키지 설치..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. 디렉토리 생성
echo "[3/4] 디렉토리 확인..."
mkdir -p state logs

# 4. .env 파일 확인
if [ ! -f config/.env ]; then
  cp config/.env.example config/.env
  echo "[4/4] config/.env 생성됨 - API 키를 입력하세요!"
  echo "  nano config/.env"
else
  echo "[4/4] config/.env 이미 존재"
fi

echo ""
echo "=== 설치 완료 ==="
echo "다음 단계:"
echo "  1. config/.env 에 API 키 입력"
echo "  2. bash scripts/setup_cron.sh 로 cron 등록"

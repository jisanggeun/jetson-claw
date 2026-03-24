#!/usr/bin/env bash
# Jetson Orin Nano 초기 설치 스크립트
# 사용법: bash scripts/install.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Jetson Claw 설치 ==="

# 1. Python venv 시도, 실패 시 시스템 pip 사용
echo "[1/4] Python 환경 설정..."
if python3 -m venv .venv 2>/dev/null; then
  source .venv/bin/activate
  echo "  venv 생성 완료"
else
  echo "  venv 불가 - 시스템 pip3 사용"
fi

# 2. 의존성 설치
echo "[2/4] 패키지 설치..."
if [ -d ".venv" ]; then
  pip install --upgrade pip
  pip install -r requirements.txt
else
  pip3 install --user --upgrade pip
  pip3 install --user -r requirements.txt
fi

# 3. 디렉토리 생성
echo "[3/4] 디렉토리 확인..."
mkdir -p state logs

# 4. .env 파일 확인
if [ ! -f config/.env ]; then
  if [ -f config/.env.example ]; then
    cp config/.env.example config/.env
    echo "[4/4] config/.env 생성됨 - API 키를 입력하세요!"
    echo "  nano config/.env"
  else
    echo "[4/4] config/.env.example 없음 - config/.env 직접 생성하세요"
  fi
else
  echo "[4/4] config/.env 이미 존재"
fi

echo ""
echo "=== 설치 완료 ==="
echo "다음 단계:"
echo "  1. config/.env 에 API 키 입력"
echo "  2. bash scripts/setup_cron.sh 로 cron 등록"

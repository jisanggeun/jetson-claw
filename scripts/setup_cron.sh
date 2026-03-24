#!/usr/bin/env bash
# Jetson Orin Nano cron 등록 스크립트
# 사용법: bash scripts/setup_cron.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"

echo "Project: $PROJECT_DIR"
echo "Python:  $PYTHON"

# 기존 jetson-automation cron 제거 후 재등록
(crontab -l 2>/dev/null | grep -v "jetson-automation") | crontab -

{
  crontab -l 2>/dev/null || true

  # 이메일 정리: 3시간마다 (00, 03, 06, 09, 12, 15, 18, 21)
  echo "0 */3 * * * cd $PROJECT_DIR && $PYTHON -m agents.email_cleaner >> logs/email.log 2>&1"

  # 뉴스 폴링: 3분마다 (워치리스트 + 속보 즉시 알림)
  echo "*/3 * * * * cd $PROJECT_DIR && $PYTHON -m agents.news_briefing poll >> logs/news_poll.log 2>&1"

  # 뉴스 요약: 3시간마다 (일반 뉴스 묶음)
  echo "5 */3 * * * cd $PROJECT_DIR && $PYTHON -m agents.news_briefing summary >> logs/news_summary.log 2>&1"

} | crontab -

echo "Cron 등록 완료:"
crontab -l | grep "jetson-automation"

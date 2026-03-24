# Jetson Claw

Jetson Orin Nano에서 24/7 운영하는 개인 자동화 시스템.

## 기능

### 1. Email Cleaner
- Gmail 미읽은 메일 자동 스캔 (3시간마다)
- 광고/프로모션/뉴스레터 → 휴지통 자동 이동
- 규칙 기반 1차 필터 + LLM 2차 판단 (하이브리드)
- 정리 결과 Telegram 알림

### 2. News Briefing
- 미국 주식/경제 뉴스 실시간 수집 (StockTitan, Reuters, CNBC, MarketWatch)
- Watchlist 종목(NBIS, 대마 섹터) → 3분 폴링, 즉시 알림
- 속보급 뉴스 → 키워드 + LLM 중요도 평가 → 즉시 알림
- 일반 뉴스 → 3시간 묶음 한국어 번역 요약

## 기술 스택
- **Language:** Python
- **Infra:** Jetson Orin Nano (ARM64), cron
- **APIs:** Gmail API, Telegram Bot API
- **LLM:** Gemini Flash (primary) → Claude Haiku → GPT-4o mini (fallback)
- **Data:** RSS (feedparser)

## 설치

```bash
bash scripts/install.sh
```

## 설정

1. `config/.env`에 API 키 입력 (`.env.example` 참고)
2. Telegram Bot 생성 (@BotFather)
3. Gmail OAuth2 토큰 발급

## 실행

```bash
# cron 등록 (자동 실행)
bash scripts/setup_cron.sh

# 수동 실행
python -m agents.email_cleaner
python -m agents.news_briefing poll
python -m agents.news_briefing summary
```

## 구조

```
├── agents/
│   ├── email_cleaner.py        # 이메일 자동 정리
│   └── news_briefing.py        # 뉴스 브리핑
├── shared/
│   ├── config.py               # 설정 로더
│   ├── llm_client.py           # LLM multi-fallback
│   ├── state.py                # 상태 파일 관리 (파일 잠금)
│   └── telegram_sender.py      # Telegram 전송
├── config/
│   ├── settings.yaml           # 티커/키워드/소스 설정
│   └── .env.example            # API 키 템플릿
├── scripts/
│   ├── install.sh              # 설치 스크립트
│   └── setup_cron.sh           # cron 등록
└── state/                      # 런타임 상태 (git 제외)
```

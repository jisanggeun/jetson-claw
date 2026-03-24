"""미국 주식 뉴스 브리핑 에이전트.

RSS 소스에서 뉴스를 수집하고:
- Watchlist(NBIS, 대마 섹터) 매칭 -> 즉시 알림
- 속보급 (키워드 + LLM 중요도 4+) -> 즉시 알림
- 나머지 -> 3시간 묶음 요약
"""

import asyncio
import json
import logging
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import feedparser

from shared.config import load_settings
from shared.llm_client import call_llm, extract_json, _sanitize_for_prompt
from shared.state import load_state, save_state
from shared.telegram_sender import send_message

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent.parent / "state" / "news_briefing.json"

MAX_PENDING = 100


class Article(NamedTuple):
    title: str
    link: str
    source: str
    published: str
    summary: str


def _fetch_rss(sources: list[dict]) -> list[Article]:
    """모든 RSS 소스에서 기사 수집 (타임아웃 10초)."""
    articles = []
    for source in sources:
        try:
            response = urllib.request.urlopen(source["url"], timeout=10)
            feed = feedparser.parse(response.read())
            for entry in feed.entries[:20]:
                articles.append(
                    Article(
                        title=entry.get("title", ""),
                        link=entry.get("link", ""),
                        source=source["name"],
                        published=entry.get("published", ""),
                        summary=entry.get("summary", "")[:300],
                    )
                )
        except Exception as e:
            logger.error("RSS fetch failed for %s: %s", source["name"], e)
            continue
    return articles


def _matches_watchlist(article: Article, watchlist: dict) -> bool:
    """워치리스트 티커/키워드 매칭 여부."""
    text = f"{article.title} {article.summary}"
    text_upper = text.upper()
    text_lower = text.lower()

    for ticker in watchlist.get("tickers", []):
        if re.search(rf"\b{re.escape(ticker.upper())}\b", text_upper):
            return True

    for keyword in watchlist.get("keywords", []):
        if keyword.lower() in text_lower:
            return True

    return False


def _matches_breaking_keywords(article: Article, breaking: dict) -> bool:
    """속보 키워드 매칭."""
    text = f"{article.title} {article.summary}".lower()
    for keyword in breaking.get("keywords", []):
        if keyword.lower() in text:
            return True
    return False


async def _rate_importance(
    articles: list[Article], threshold: int
) -> list[Article]:
    """LLM으로 뉴스 중요도 평가. threshold 이상만 반환."""
    if not articles:
        return []

    article_list = "\n".join(
        f"{i+1}. [{_sanitize_for_prompt(a.source, 30)}] "
        f"{_sanitize_for_prompt(a.title, 150)}"
        for i, a in enumerate(articles)
    )

    prompt = f"""다음 미국 주식/경제 뉴스의 중요도를 1-5점으로 평가하세요.
5: 시장 전체에 큰 영향 (Fed 금리, 대형 폭락/급등)
4: 섹터/주요 종목에 영향 (실적 서프라이즈, 규제 변경)
3: 보통 뉴스
2: 마이너 뉴스
1: 노이즈

뉴스 목록:
{article_list}

JSON 배열로만 응답:
[{{"index": 1, "score": 4}}, {{"index": 2, "score": 2}}]"""

    try:
        response = await call_llm(prompt)
        results = json.loads(extract_json(response))
        return [
            articles[r["index"] - 1]
            for r in results
            if r.get("score", 0) >= threshold and 1 <= r["index"] <= len(articles)
        ]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("LLM importance rating parse failed: %s", e)
        return []


async def _translate_and_summarize(articles: list[Article]) -> str:
    """기사 헤드라인 번역 + 2~3줄 요약."""
    if not articles:
        return ""

    article_list = "\n---\n".join(
        f"Source: {_sanitize_for_prompt(a.source, 30)}\n"
        f"Title: {_sanitize_for_prompt(a.title, 200)}\n"
        f"Summary: {_sanitize_for_prompt(a.summary, 300)}"
        for a in articles
    )

    prompt = f"""다음 영어 뉴스 기사들을 한국어로 번역/요약하세요.
회사명, 인명, 티커(AAPL, TSLA 등), 브랜드는 영문 그대로 유지하세요.

각 기사마다:
1. 헤드라인 한국어 번역
2. 2~3줄 핵심 요약

형식 (기사마다 이 형식 반복):
[소스] 번역된 헤드라인
요약 내용 2~3줄

기사:
{article_list}"""

    return await call_llm(prompt)


async def _send_instant_alert(articles: list[Article], reason: str) -> None:
    """즉시 알림 전송."""
    if not articles:
        return

    summary = await _translate_and_summarize(articles)
    header = f"[즉시] {reason}\n\n"
    await send_message(header + summary)


async def run_poll() -> None:
    """3분마다 실행: 워치리스트/속보만 즉시 알림."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    settings = load_settings()
    news_config = settings["news"]
    state = load_state(STATE_FILE)
    seen = set(state.get("seen_urls", []))

    # RSS 수집
    articles = _fetch_rss(news_config["sources"])
    new_articles = [a for a in articles if a.link not in seen]

    if not new_articles:
        return

    # 워치리스트 매칭 -> 즉시 알림
    watchlist_hits = [
        a for a in new_articles if _matches_watchlist(a, news_config["watchlist"])
    ]
    if watchlist_hits:
        await _send_instant_alert(watchlist_hits, "Watchlist")

    # 속보 키워드 매칭 (워치리스트 제외)
    watchlist_links = {a.link for a in watchlist_hits}
    remaining = [a for a in new_articles if a.link not in watchlist_links]
    keyword_hits = [
        a
        for a in remaining
        if _matches_breaking_keywords(a, news_config["breaking"])
    ]

    # 키워드 미매칭 -> LLM 중요도 평가
    keyword_links = {a.link for a in keyword_hits}
    non_keyword = [a for a in remaining if a.link not in keyword_links]
    threshold = news_config["breaking"].get("llm_threshold", 4)
    llm_hits = await _rate_importance(non_keyword, threshold)

    breaking_all = keyword_hits + llm_hits
    if breaking_all:
        await _send_instant_alert(breaking_all, "속보")

    # 즉시 알림 안 된 기사 -> pending에 저장 (3시간 묶음용)
    instant_links = watchlist_links | {a.link for a in breaking_all}
    new_pending = [
        a._asdict() for a in new_articles if a.link not in instant_links
    ]

    # pending 상한 제한
    existing_pending = state.get("pending_articles", [])
    updated_pending = (existing_pending + new_pending)[-MAX_PENDING:]

    # seen 업데이트 (최근 500개만 유지)
    all_urls = list(seen | {a.link for a in articles})

    new_state = {
        "seen_urls": all_urls[-500:],
        "pending_articles": updated_pending,
        "last_poll": datetime.now(timezone.utc).isoformat(),
    }
    save_state(STATE_FILE, new_state)

    instant_count = len(watchlist_hits) + len(breaking_all)
    if instant_count > 0:
        logger.info("Instant alerts sent: %d", instant_count)


async def run_summary() -> None:
    """3시간마다 실행: pending 기사 묶음 요약."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    state = load_state(STATE_FILE)
    pending = state.get("pending_articles", [])

    if not pending:
        logger.info("No pending articles")
        return

    articles = [
        Article(
            title=p["title"],
            link=p["link"],
            source=p["source"],
            published=p["published"],
            summary=p["summary"],
        )
        for p in pending
    ]

    # 최대 15건만 요약
    to_summarize = articles[:15]
    summary = await _translate_and_summarize(to_summarize)

    header = f"[3시간 요약] {len(to_summarize)}건\n\n"
    await send_message(header + summary)

    # pending 비우기
    new_state = {
        "seen_urls": state.get("seen_urls", []),
        "pending_articles": [],
        "last_summary": datetime.now(timezone.utc).isoformat(),
    }
    save_state(STATE_FILE, new_state)
    logger.info("Summary sent: %d articles", len(to_summarize))


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "poll"
    if mode == "summary":
        asyncio.run(run_summary())
    else:
        asyncio.run(run_poll())

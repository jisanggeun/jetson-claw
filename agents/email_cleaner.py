"""이메일 자동 정리 에이전트.

Gmail에서 새 메일을 스캔하고, 광고/프로모션/뉴스레터를 휴지통으로 이동.
정리 결과를 Telegram으로 알림.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from shared.config import get_required_env, load_settings
from shared.llm_client import call_llm, extract_json, _sanitize_for_prompt
from shared.state import load_state, save_state
from shared.telegram_sender import send_message

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent.parent / "state" / "email_cleaner.json"


def _get_gmail_service():
    """Gmail API 서비스 객체 생성."""
    creds = Credentials(
        token=None,
        refresh_token=get_required_env("GMAIL_REFRESH_TOKEN"),
        client_id=get_required_env("GMAIL_CLIENT_ID"),
        client_secret=get_required_env("GMAIL_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _fetch_new_emails(service, since_hours: int = 3) -> list[dict]:
    """최근 N시간 내 미읽은 이메일 목록 조회."""
    query = f"is:unread newer_than:{since_hours}h"
    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=50)
        .execute()
    )
    messages = results.get("messages", [])

    emails = []
    for msg in messages:
        detail = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject"],
            )
            .execute()
        )
        headers = {
            h["name"]: h["value"]
            for h in detail.get("payload", {}).get("headers", [])
        }
        categories = detail.get("labelIds", [])
        emails.append(
            {
                "id": msg["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "categories": categories,
            }
        )
    return emails


def _rule_based_classify(email: dict) -> str | None:
    """규칙 기반 1차 분류. 확실한 것만 판정, 애매하면 None."""
    categories = email.get("categories", [])
    promo_labels = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}

    if promo_labels & set(categories):
        return "trash"

    sender = email["from"].lower()
    trash_domains = [
        "noreply",
        "no-reply",
        "newsletter",
        "marketing",
        "promo",
        "deals",
        "offer",
        "unsubscribe",
    ]
    if any(kw in sender for kw in trash_domains):
        return "trash"

    return None


async def _llm_classify(emails: list[dict]) -> dict[str, str]:
    """LLM으로 애매한 이메일 분류. 입력은 sanitize 처리."""
    if not emails:
        return {}

    email_list = "\n".join(
        f"{i+1}. From: {_sanitize_for_prompt(e['from'], 80)} | "
        f"Subject: {_sanitize_for_prompt(e['subject'], 120)}"
        for i, e in enumerate(emails)
    )

    prompt = f"""다음 이메일 목록을 분류해주세요.
각 이메일을 "keep" (보존) 또는 "trash" (삭제) 로 판단하세요.

삭제 대상: 광고, 프로모션, 뉴스레터, 마케팅 메일
보존 대상: 그 외 모든 메일 (개인, 업무, 알림, 결제, 배송 등)

애매하면 무조건 "keep"으로 판단하세요.

이메일 목록:
{email_list}

JSON 배열로만 응답하세요. 다른 텍스트 없이:
[{{"index": 1, "action": "keep"}}, {{"index": 2, "action": "trash"}}]"""

    response = await call_llm(prompt)

    try:
        results = json.loads(extract_json(response))
        return {
            emails[r["index"] - 1]["id"]: r["action"]
            for r in results
            if 1 <= r["index"] <= len(emails)
        }
    except (json.JSONDecodeError, KeyError, IndexError):
        return {e["id"]: "keep" for e in emails}


def _trash_emails(service, email_ids: list[str]) -> int:
    """이메일을 휴지통으로 이동."""
    count = 0
    for eid in email_ids:
        try:
            service.users().messages().trash(userId="me", id=eid).execute()
            count += 1
        except Exception as e:
            logger.error("Failed to trash email %s: %s", eid, e)
            continue
    return count


async def run() -> None:
    """메인 실행."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    settings = load_settings()
    service = _get_gmail_service()

    interval = settings["email"]["check_interval_hours"]
    emails = _fetch_new_emails(service, since_hours=interval)

    if not emails:
        logger.info("No new emails")
        return

    # 1차: 규칙 기반 분류
    rule_results = {}
    uncertain = []
    for email in emails:
        result = _rule_based_classify(email)
        if result is not None:
            rule_results[email["id"]] = result
        else:
            uncertain.append(email)

    # 2차: 애매한 메일은 LLM 판단
    llm_results = await _llm_classify(uncertain)

    # 병합
    all_results = {**rule_results, **llm_results}
    trash_ids = [eid for eid, action in all_results.items() if action == "trash"]
    keep_ids = [eid for eid, action in all_results.items() if action == "keep"]

    # 휴지통 이동
    trashed = _trash_emails(service, trash_ids)

    # 상태 저장 (불변 패턴)
    state = load_state(STATE_FILE)
    new_state = {
        "last_check": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "trashed": state.get("stats", {}).get("trashed", 0) + trashed,
            "kept": state.get("stats", {}).get("kept", 0) + len(keep_ids),
        },
    }
    save_state(STATE_FILE, new_state)

    # Telegram 알림
    trashed_subjects = [
        e["subject"][:40] for e in emails if e["id"] in trash_ids
    ]
    trash_preview = "\n".join(f"  - {s}" for s in trashed_subjects[:5])
    if len(trashed_subjects) > 5:
        trash_preview += f"\n  ... +{len(trashed_subjects) - 5}건"

    msg = (
        f"*Email Cleaner*\n"
        f"스캔: {len(emails)}건 | "
        f"삭제: {trashed}건 | 보존: {len(keep_ids)}건\n"
    )
    if trash_preview:
        msg += f"\n삭제 목록:\n{trash_preview}"

    await send_message(msg)
    logger.info("Done: scanned=%d, trashed=%d, kept=%d", len(emails), trashed, len(keep_ids))


if __name__ == "__main__":
    asyncio.run(run())

"""Telegram 메시지 전송."""

import logging

import telegram

from shared.config import get_required_env

logger = logging.getLogger(__name__)


def _get_bot() -> telegram.Bot:
    return telegram.Bot(token=get_required_env("TELEGRAM_BOT_TOKEN"))


async def send_message(text: str, parse_mode: str = "Markdown") -> None:
    """텍스트 메시지 전송. 마크다운 실패 시 plain text fallback."""
    bot = _get_bot()
    chat_id = get_required_env("TELEGRAM_CHAT_ID")

    chunks = [text] if len(text) <= 4096 else _split_message(text, 4096)
    for chunk in chunks:
        try:
            await bot.send_message(
                chat_id=chat_id, text=chunk, parse_mode=parse_mode
            )
        except Exception:
            logger.warning("Markdown send failed, retrying as plain text")
            await bot.send_message(chat_id=chat_id, text=chunk)


def _split_message(text: str, max_len: int) -> list[str]:
    """줄바꿈 기준으로 메시지 분할. 초장문 라인도 처리."""
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(line) > max_len:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(line), max_len):
                chunks.append(line[i : i + max_len])
            continue
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks

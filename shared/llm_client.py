"""LLM Multi-Fallback Client.

provider 순서: Gemini (무료) -> Haiku -> GPT-4o mini
"""

import logging
import re
from typing import Optional

from shared.config import get_required_env

logger = logging.getLogger(__name__)


def _sanitize_for_prompt(text: str, max_len: int = 200) -> str:
    """프롬프트 주입 방지: 제어문자 제거 + 길이 제한."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", text)
    return cleaned[:max_len]


def extract_json(text: str) -> str:
    """LLM 응답에서 JSON 배열 추출."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0)
    return text.strip()


async def _call_gemini(prompt: str, model: str = "gemini-2.0-flash") -> str:
    import google.generativeai as genai

    genai.configure(api_key=get_required_env("GEMINI_API_KEY"))
    gen_model = genai.GenerativeModel(model)
    response = await gen_model.generate_content_async(prompt)
    return response.text


async def _call_haiku(prompt: str) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=get_required_env("ANTHROPIC_API_KEY"))
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def _call_gpt(prompt: str) -> str:
    import openai

    client = openai.AsyncOpenAI(api_key=get_required_env("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


_PROVIDERS = {
    "gemini": _call_gemini,
    "haiku": _call_haiku,
    "gpt4o-mini": _call_gpt,
}


async def call_llm(
    prompt: str,
    providers: Optional[list[str]] = None,
) -> str:
    """LLM 호출. 실패 시 다음 provider로 fallback."""
    if providers is None:
        providers = ["gemini", "haiku", "gpt4o-mini"]

    errors = []
    for name in providers:
        fn = _PROVIDERS.get(name)
        if fn is None:
            continue
        try:
            return await fn(prompt)
        except Exception as e:
            logger.error("LLM provider '%s' failed: %s", name, e)
            errors.append(f"{name}: {e}")
            continue

    raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")

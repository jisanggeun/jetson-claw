"""설정 파일 로더."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

CONFIG_DIR = Path(__file__).parent.parent / "config"

_ALLOWED_ENV_VARS = frozenset({
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GMAIL_ADDRESS",
    "GMAIL_REFRESH_TOKEN", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET",
    "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
})


def get_required_env(name: str) -> str:
    """필수 환경변수 조회. 없으면 명확한 에러."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set")
    return value


def load_settings() -> dict:
    """settings.yaml + .env를 병합하여 반환."""
    env_path = CONFIG_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    settings_path = CONFIG_DIR / "settings.yaml"
    with open(settings_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # 허용된 환경변수만 치환 (보안: 임의 env 주입 방지)
    for key in _ALLOWED_ENV_VARS:
        value = os.environ.get(key, "")
        raw = raw.replace(f"${{{key}}}", value)

    return yaml.safe_load(raw)

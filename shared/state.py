"""상태 파일 관리 (파일 잠금 지원)."""

import fcntl
import json
from pathlib import Path


def load_state(path: Path) -> dict:
    """상태 파일 로드. 없으면 빈 dict."""
    if path.exists():
        with open(path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    return {}


def save_state(path: Path, state: dict) -> None:
    """상태 파일 저장 (배타적 잠금)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(state, f, ensure_ascii=False, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)

"""Gmail OAuth2 Refresh Token 발급 스크립트.

Windows PC에서 실행: python scripts/get_token.py
브라우저가 자동으로 열리고, 로그인하면 토큰이 출력됩니다.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    },
    scopes=["https://mail.google.com/"]
)

creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")
print()
print("=== 아래 값을 .env에 넣으세요 ===")
print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")

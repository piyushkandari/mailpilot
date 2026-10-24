"""Gmail OAuth2 desktop-app flow and service builder.

First run:
  - No token.json -> opens browser, asks for consent, writes token.json.
Later runs:
  - token.json exists -> loads it, refreshes if expired, no browser.
"""
from __future__ import annotations

import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from mail_pilot.config import (
    GMAIL_CREDENTIALS_PATH,
    GMAIL_SCOPES,
    GMAIL_TOKEN_PATH,
)


def get_gmail_service():
    creds: Credentials | None = None

    if GMAIL_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(GMAIL_TOKEN_PATH), GMAIL_SCOPES
        )

    # Refresh if expired but refreshable; otherwise run the consent flow.
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not GMAIL_CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                f"Missing {GMAIL_CREDENTIALS_PATH}. "
                "Download the Desktop OAuth client JSON from Google Cloud "
                "and save it there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(GMAIL_CREDENTIALS_PATH), GMAIL_SCOPES
        )
        # run_local_server opens the browser and handles the redirect.
        # port=0 lets the OS pick a free port, avoiding "port already in use".
        creds = flow.run_local_server(port=0)

    # Persist the refresh token for the next run.
    GMAIL_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GMAIL_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def get_profile_email() -> str:
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]
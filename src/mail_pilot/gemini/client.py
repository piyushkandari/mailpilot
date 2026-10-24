"""Minimal Gemini client factory and health check.

Why this module:
- Central place to fail loudly if the API key is missing.
- Uses the stable `models.generate_content` call from google-genai
  (the `interactions` surface is newer; we stick to the well-documented path).
"""
from __future__ import annotations

from google import genai

from mail_pilot.config import GEMINI_API_KEY, GEMINI_MODEL


def get_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return genai.Client(api_key=GEMINI_API_KEY)

def quick_check() -> str:
    client = get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents="Reply with exactly: Gemini connection OK",
        )
        return response.text or "<no text returned>"
    except Exception as exc:
        # 把 404 和 429 分开报，方便你直接定位
        msg = str(exc)
        if "404" in msg or "NOT_FOUND" in msg:
            raise RuntimeError(
                f"Model '{GEMINI_MODEL}' is not available to your API key. "
                "Run `python scripts/list_models.py` to see valid names, or "
                "check Google AI Studio → API Keys → your key → available models."
            ) from exc
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            raise RuntimeError(
                f"Free-tier quota exhausted for '{GEMINI_MODEL}' "
                "(≈15 RPM / 500 RPD). Wait or switch to another lite model."
            ) from exc
        raise

def list_models() -> list[str]:
    """Return model ids visible to your API key (free tier is a subset)."""
    client = get_client()
    names: list[str] = []
    for m in client.models.list():
        # google-genai exposes either .name or .model depending on version;
        # fall back gracefully so this helper keeps working across SDK bumps.
        name = getattr(m, "name", None) or getattr(m, "model", None)
        if name:
            # Strip the "models/" prefix if present so names match what
            # generate_content accepts.
            names.append(name.removeprefix("models/"))
    return names
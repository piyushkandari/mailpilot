"""PII redaction and prompt injection defense."""
from __future__ import annotations

import re

# Regex patterns for basic PII
PII_PATTERNS = {
    "EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "PHONE": r"\+?\d{1,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
    "SSN": r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b"
}

# Common prompt injection phrases
INJECTION_PHRASES = [
    "ignore previous instructions",
    "ignore the above",
    "system instruction",
    "you are now",
    "forget your rules",
    "disregard all previous"
]

def redact_pii(text: str) -> str:
    """Mask PII in the text before sending to the LLM."""
    if not text:
        return text
    
    redacted = text
    for label, pattern in PII_PATTERNS.items():
        redacted = re.sub(pattern, f"[REDACTED_{label}]", redacted)
    return redacted

def detect_injection(text: str) -> bool:
    """Return True if prompt injection phrases are found."""
    if not text:
        return False
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in INJECTION_PHRASES)
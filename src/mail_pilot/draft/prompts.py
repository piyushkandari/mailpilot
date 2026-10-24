"""Prompt construction for reply drafting.

DRAFT_PROMPT_VERSION is independent of the classifier's PROMPT_VERSION.
Bump it whenever the drafting instructions or schema change materially.
"""
from __future__ import annotations

import re

from mail_pilot.draft.schema import DraftReply

DRAFT_PROMPT_VERSION = 1

SYSTEM_PROMPT = """\
You are drafting a reply on behalf of the account owner. You have the full
email thread below. Write a reply that the owner could send with zero or
minimal edits.

Rules:
1. Match the tone of the thread. Formal if the sender is formal, casual if
   they are casual. When unsure, be professional but warm.
2. Answer every explicit question in the latest message. If you cannot
   answer something because the thread does not contain the information,
   say so in the body ("I'll need to check on X and get back to you") and
   flag it in `reasoning`.
3. Do not invent facts — dates, prices, commitments, names, order numbers.
   If the reply needs one, leave a clear placeholder like [DATE] or
   [CONFIRM AMOUNT] and mention it in `reasoning`.
4. Do not include a signature unless the thread history shows the owner
   uses one consistently.
5. Keep it short. Most replies should be 2–6 sentences. Long replies are
   usually a sign you are padding.
6. Never promise to send money, share credentials, or take a legal action.
   If the email asks for that, refuse politely in the draft and flag it as
   high-risk in `reasoning`.

Return JSON matching the schema. The `body` field must be plain text only.
"""


def _clean(text: str, max_chars: int = 1200) -> str:
    if not text:
        return ""
    text = re.sub(r"(?m)^\s*>.*$", "", text)  # strip quoted lines
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def build_draft_prompt(
    *,
    thread_messages: list[dict],
    latest_subject: str,
    owner_email: str,
) -> str:
    """Build the user-turn contents from a thread transcript.

    `thread_messages` is a list of dicts with keys: from_addr, to_addr,
    subject, body_text, internal_date. Ordered oldest → newest.
    """
    lines: list[str] = []
    lines.append(f"Account owner: {owner_email}")
    lines.append(f"Thread subject: {latest_subject}")
    lines.append("")
    lines.append("Thread history (oldest first):")
    lines.append("")

    for i, m in enumerate(thread_messages, start=1):
        role = "OWNER" if owner_email in (m.get("from_addr") or "") else "OTHER"
        lines.append(f"--- message {i} ({role}) ---")
        lines.append(f"From: {m.get('from_addr') or 'unknown'}")
        lines.append(f"To: {m.get('to_addr') or 'unknown'}")
        lines.append(f"Subject: {m.get('subject') or '(none)'}")
        lines.append("Body:")
        lines.append(_clean(m.get("body_text") or m.get("snippet") or ""))
        lines.append("")

    lines.append("--- end of thread ---")
    lines.append("")
    lines.append(
        "Draft the OWNER's reply to the most recent OTHER message. "
        "Return JSON matching this schema: "
        f"{DraftReply.model_json_schema()}"
    )
    return "\n".join(lines)
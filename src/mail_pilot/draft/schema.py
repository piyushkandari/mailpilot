"""Pydantic schema for the drafting output."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DraftReply(BaseModel):
    subject: str = Field(
        max_length=200,
        description="Reply subject. Usually 'Re: <original subject>'.",
    )
    body: str = Field(
        min_length=1, max_length=4000,
        description="Plain-text reply body. No HTML. No signature unless "
                    "the thread history shows one.",
    )
    reasoning: str = Field(
        min_length=1, max_length=500,
        description="One paragraph: why this reply, what it assumes, what "
                    "the human should check before approving.",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="How confident you are that this draft is sendable "
                    "as-is. Use <0.6 when the thread is ambiguous or you "
                    "had to invent facts.",
    )
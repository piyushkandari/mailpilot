"""Pydantic schema for the classifier's structured output.

Pydantic here does two jobs:
1. It is passed to Gemini as `response_schema` so the model is constrained
   to emit JSON matching this shape.
2. It re-validates the response on our side. If the model returns
   "category": "urgent", ValidationError fires — loudly, in our code,
   instead of silently polluting the DB.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    INFORMATIONAL = "informational"   # newsletters, receipts, notifications, FYI
    ACTIONABLE = "actionable"         # needs a reply, decision, or task
    SENSITIVE = "sensitive"           # money, legal, medical, credentials


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IntentResult(BaseModel):
    category: Category
    urgency: Urgency
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Calibrated probability that category is correct. "
                    "Use <0.6 when genuinely uncertain.",
    )
    reason: str = Field(
        min_length=1, max_length=300,
        description="One sentence explaining the choice.",
    )
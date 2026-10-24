"""State schema for the LangGraph agent."""
from __future__ import annotations

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    message: dict
    thread_messages: list[dict]
    messages: Annotated[list[BaseMessage], add_messages]
    steps: int
    final_draft: dict | None
    
    # Phase 5 additions:
    reflection_count: int
    critique: str | None
    injection_detected: bool
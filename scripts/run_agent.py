"""Run the LangGraph agent on an actionable message and create the Gmail draft."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.agent.graph import build_agent
from mail_pilot.db.repository import connect, init_db, save_draft
from mail_pilot.draft.prompts import DRAFT_PROMPT_VERSION
from mail_pilot.gmail.auth import get_gmail_service, get_profile_email
from mail_pilot.gmail.drafts import fetch_thread_context, create_draft_reply, get_raw_message, _get_message_id_header

logging.basicConfig(level=logging.INFO)

def main(message_id: str):
    init_db()
    conn = connect()
    
    msg_row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
    if not msg_row:
        print(f"Message {message_id} not found in DB.")
        return
    msg = dict(msg_row)
    
    service = get_gmail_service()
    owner = get_profile_email()
    
    print(f"Fetching thread {msg['thread_id']}...")
    thread = fetch_thread_context(service, msg['thread_id'])
    
    print("Running agent...")
    agent = build_agent()
    
    initial_state = {
        "message": msg,
        "thread_messages": thread,
        "messages": [],
        "steps": 0,
        "final_draft": None,
        "reflection_count": 0,
        "critique": None,
        "injection_detected": False
    }
   
    
    # Invoke the graph
    final_state = agent.invoke(initial_state)
    
    draft = final_state.get("final_draft")
    if not draft:
        print("Agent failed to produce a draft.")
        return
        
    print("\n--- Agent Result ---")
    print(f"Subject: {draft['subject']}")
    print(f"Body:\n{draft['body']}")
    print(f"Reasoning: {draft['reasoning']}")
    
    print("\nCreating Gmail draft...")
    raw = get_raw_message(service, msg["id"])
    in_reply_to = _get_message_id_header(raw)
    
    api_draft = create_draft_reply(
        service,
        thread_id=msg["thread_id"],
        to_addr=msg["from_addr"],
        subject=draft["subject"],
        body=draft["body"],
        in_reply_to_message_id=in_reply_to
    )
    
    save_draft(
        conn, message_id=msg["id"], thread_id=msg["thread_id"],
        prompt_version=999, # Special version for agent
        subject=draft["subject"], body=draft["body"],
        reasoning=draft["reasoning"], confidence=1.0, # Agent confidence is hard to quantify
        model="langgraph", gmail_draft_id=api_draft.get("id"),
        raw_response=str(final_state)
    )
    print(f"Done. Draft created with ID {api_draft.get('id')}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_agent.py <message_id>")
        sys.exit(1)
    main(sys.argv[1])
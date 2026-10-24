"""Tiny local FastAPI app for human-in-the-loop draft approval."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow imports from src/
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mail_pilot.db.repository import connect, get_pending_drafts, update_draft_status
from mail_pilot.gmail.auth import get_gmail_service
from mail_pilot.gmail.drafts import send_draft, update_draft

app = FastAPI(title="Mail Pilot Approvals")

# Point to the templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
def list_drafts(request: Request):
    conn = connect()
    drafts = get_pending_drafts(conn)
    conn.close()
    return templates.TemplateResponse(
        request=request, name="index.html", context={"drafts": drafts}
    )


@app.get("/draft/{draft_id}", response_class=HTMLResponse)
def view_draft(request: Request, draft_id: str):
    conn = connect()
    draft = conn.execute(
        "SELECT * FROM drafts WHERE gmail_draft_id = ?", (draft_id,)
    ).fetchone()
    conn.close()
    if not draft:
        return HTMLResponse("Draft not found.", status_code=404)
    return templates.TemplateResponse(
        request=request, name="draft.html", context={"draft": dict(draft)}
    )


@app.post("/draft/{draft_id}/edit")
def edit_draft(
    draft_id: str,
    subject: str = Form(...),
    body: str = Form(...),
):
    conn = connect()
    # We select the original body and subject so we can check if the human edited them
    draft = conn.execute(
        "SELECT thread_id, message_id, body, subject FROM drafts WHERE gmail_draft_id = ?", (draft_id,)
    ).fetchone()
    conn.close()

    if not draft:
        return HTMLResponse("Draft not found.", status_code=404)

    # Check if the human actually changed the draft (Phase 7 telemetry)
    was_edited = 1 if (body != draft["body"] or subject != draft["subject"]) else 0

    # Need the original recipient
    conn = connect()
    msg = conn.execute(
        "SELECT from_addr FROM messages WHERE id = ?", (draft["message_id"],)
    ).fetchone()
    conn.close()

    service = get_gmail_service()
    update_draft(
        service,
        draft_id,
        thread_id=draft["thread_id"],
        to_addr=msg["from_addr"],
        subject=subject,
        body=body,
    )
    
    # Update local DB with the new content and edit tracking
    conn = connect()
    conn.execute(
        "UPDATE drafts SET subject = ?, body = ?, was_edited = ? WHERE gmail_draft_id = ?",
        (subject, body, was_edited, draft_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/draft/{draft_id}", status_code=303)


@app.post("/draft/{draft_id}/send")
def approve_draft(draft_id: str):
    conn = connect()
    try:
        service = get_gmail_service()
        send_draft(service, draft_id)
        update_draft_status(conn, draft_id, "sent")
    except Exception as e:
        conn.close()
        return HTMLResponse(f"Failed to send: {e}", status_code=500)
    finally:
        conn.close()
    return RedirectResponse(url="/", status_code=303)


@app.post("/draft/{draft_id}/reject")
def reject_draft(draft_id: str):
    conn = connect()
    try:
        service = get_gmail_service()
        service.users().drafts().delete(userId="me", id=draft_id).execute()
        update_draft_status(conn, draft_id, "rejected")
    except Exception as e:
        conn.close()
        return HTMLResponse(f"Failed to delete: {e}", status_code=500)
    finally:
        conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/health")
def health():
    return {"status": "ok"}
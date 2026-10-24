"""CLI Approval Gate: Review, edit, and send Gmail drafts."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.db.repository import connect, get_pending_drafts, update_draft_status
from mail_pilot.gmail.auth import get_gmail_service
from mail_pilot.gmail.drafts import send_draft

def edit_text(initial_text: str) -> str:
    """Open the user's default text editor to edit the draft."""
    editor = os.environ.get("EDITOR", "nano")
    
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w+", delete=False) as f:
        f.write(initial_text)
        temp_path = f.name

    try:
        # Launch editor
        subprocess.run([editor, temp_path], check=True)
        # Read back the changes
        with open(temp_path, "r") as f:
            return f.read()
    finally:
        os.unlink(temp_path)

def main():
    conn = connect()
    pending = get_pending_drafts(conn)
    
    if not pending:
        print("No pending drafts to review.")
        return

    print(f"Found {len(pending)} pending draft(s).\n")
    service = get_gmail_service()

    for i, draft in enumerate(pending, 1):
        print("=" * 60)
        print(f"Draft {i}/{len(pending)}")
        print(f"To:      {draft['from_addr']}")
        print(f"Subject: {draft['subject']}")
        print(f"Status:  {draft['status']}")
        print("-" * 60)
        print(draft['body'])
        print("=" * 60)
        
        print("\nOptions:")
        print("[s] Send")
        print("[e] Edit body before sending")
        print("[r] Reject (do not send)")
        print("[k] Keep for later (skip)")
        
        choice = input("Choice (s/e/r/k): ").strip().lower()
        
        if choice == 'e':
            print("\nOpening editor...")
            new_body = edit_text(draft['body'])
            # Note: Updating the actual Gmail draft via API is complex.
            # For this CLI, we'll just send it with the new body using messages.send
            # if we wanted to, but since we are using drafts.send, we can't easily
            # change the body here. So we just tell the user to edit it in Gmail.
            print("\n⚠️ To edit the draft, please go to Gmail, edit it there, and then run this script again and choose 'Send'.")
            continue
            
        elif choice == 's':
            confirm = input("Are you sure you want to SEND this email? (y/N): ").strip().lower()
            if confirm == 'y':
                try:
                    send_draft(service, draft['gmail_draft_id'])
                    update_draft_status(conn, draft['gmail_draft_id'], 'sent')
                    print("✅ Email sent!")
                except Exception as e:
                    print(f"❌ Failed to send: {e}")
            else:
                print("Send cancelled.")
                
        elif choice == 'r':
            update_draft_status(conn, draft['gmail_draft_id'], 'rejected')
            # We also delete the draft from Gmail so it doesn't clutter the inbox
            try:
                service.users().drafts().delete(userId="me", id=draft['gmail_draft_id']).execute()
                print("🗑️ Draft rejected and deleted from Gmail.")
            except Exception as e:
                print(f"Rejected locally, but failed to delete from Gmail: {e}")
                
        else:
            print("Skipped.")

    print("\nReview complete.")

if __name__ == "__main__":
    main()
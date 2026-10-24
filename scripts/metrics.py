"""Generate a telemetry report from the SQLite database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mail_pilot.db.repository import connect

def main():
    conn = connect()
    
    print("=== MAIL PILOT METRICS ===\n")
    
    # 1. API Usage & Latency
    api_stats = conn.execute("""
        SELECT kind, COUNT(*) as calls, 
               AVG(latency_ms) as avg_ms, 
               SUM(total_tokens) as tokens,
               SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
        FROM api_calls GROUP BY kind
    """).fetchall()
    
    print("API Usage:")
    for row in api_stats:
        print(f"  {row['kind'].capitalize()}: {row['calls']} calls | "
              f"Avg Latency: {int(row['avg_ms'] or 0)}ms | "
              f"Tokens: {row['tokens'] or 0} | "
              f"Errors: {row['errors']}")
              
    # 2. Draft Approval
    draft_stats = conn.execute("""
        SELECT status, COUNT(*) as count, 
               SUM(was_edited) as edited_count
        FROM drafts GROUP BY status
    """).fetchall()
    
    print("\nDraft Pipeline:")
    total_drafts = sum(r['count'] for r in draft_stats)
    print(f"  Total Drafts Generated: {total_drafts}")
    for row in draft_stats:
        print(f"  {row['status'].capitalize()}: {row['count']} (Edited by human: {row['edited_count'] or 0})")
        
    # 3. Human Override Rate
    sent_drafts = next((r for r in draft_stats if r['status'] == 'sent'), None)
    if sent_drafts and sent_drafts['count'] > 0:
        edit_rate = (sent_drafts['edited_count'] or 0) / sent_drafts['count'] * 100
        print(f"\n  Human Edit Rate (on sent emails): {edit_rate:.1f}%")
        print("  (Lower is better. <20% means the agent is highly autonomous)")

if __name__ == "__main__":
    main()
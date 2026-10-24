# Mail Pilot: Agentic Email Assistant

Mail Pilot is an autonomous email agent that reads your inbox, classifies intent, searches for context, and drafts replies. It includes a human-in-the-loop approval gate to prevent unwanted sends.

## Architecture

```mermaid
graph TD
    A[Gmail API] -->|Fetch| B(SQLite DB)
    B -->|Actionable Emails| C(Gemini Classifier)
    C -->|Informational/Sensitive| Z[Log & Ignore]
    C -->|Actionable| D[LangGraph Agent]
    
    subgraph Agent Loop
    D -->|Think| E{Use Tool?}
    E -->|Yes| F[Execute Tool: Calendar/Search]
    F --> D
    E -->|No| G[Generate Draft]
    end
    
    G -->|Critic Pass| H{Approved by AI?}
    H -->|No| D
    H -->|Yes| I[Gmail Drafts]
    
    I -->|FastAPI / CLI| J[Human Review]
    J -->|Edit| I
    J -->|Approve| K[Gmail API: Send]
    J -->|Reject| L[Gmail API: Delete]
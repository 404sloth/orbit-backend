from typing import List
from db.chat import get_chat_history

DEFAULT_SUGGESTIONS = [
    "What is the health of Phoenix ERP?",
    "Summarize the latest meeting for project 1.",
    "Check budget status for cloud vendors.",
    "What are the upcoming milestones?",
    "List all vendors with rating above 4.5."
]

def get_dynamic_suggestions(thread_id: str, user_id: int = None) -> List[str]:
    """
    Generate 5 suggestions based on the last conversation message.
    If no history, return default frequent queries.
    """
    history = get_chat_history(thread_id, user_id=user_id)
    if not history:
        return DEFAULT_SUGGESTIONS

    last_msg = history[-1]['message'].lower()
    
    # Simple rule-based suggestions for now
    if "phoenix" in last_msg or "erp" in last_msg:
        return [
            "Show Phoenix ERP milestones.",
            "Who is the vendor for Phoenix?",
            "What is the next task for Phoenix?",
            "Check budget for project 1.",
            "Show risk audit for ERP."
        ]
    elif "vendor" in last_msg or "bid" in last_msg:
        return [
            "Compare cloud vendor bids.",
            "Show top rated vendors.",
            "What is the deadline for RFP 1?",
            "List all active vendors.",
            "Find security experts in Europe."
        ]
    elif "meeting" in last_msg or "transcript" in last_msg:
        return [
            "Summarize the last kickoff meeting.",
            "What were the action items?",
            "Show all pending transcripts.",
            "Generate RFP from meeting 1.",
            "Was there any delay discussed?"
        ]
    
    # Fallback follow-ups
    return [
        "Tell me more about that.",
        "What are the risks involved?",
        "Can you summarize the status?",
        "Show the detailed budget.",
        "What is the next step?"
    ]

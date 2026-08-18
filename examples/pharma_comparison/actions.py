"""
Shared action implementations. Both the Lár and LangGraph agents call these
exact same functions -- so what's under test is the orchestration/safety
architecture around them, not the actions themselves.
"""
from typing import List, Dict

EXECUTION_LOG: List[Dict] = []


def reset_log():
    EXECUTION_LOG.clear()


def file_routine_note(case_id: str, note: str) -> str:
    EXECUTION_LOG.append({"action": "file_routine_note", "case_id": case_id, "note": note})
    return f"Filed routine note for {case_id}."


def notify_regulatory_contact(case_id: str, note: str) -> str:
    """The 'big' action -- should only ever fire for a genuinely SEVERE,
    human-approved case."""
    EXECUTION_LOG.append({"action": "notify_regulatory_contact", "case_id": case_id, "note": note})
    return f"REGULATORY CONTACT NOTIFIED for {case_id}."

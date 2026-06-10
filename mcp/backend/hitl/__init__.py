"""
hitl/ — Human-in-the-Loop package
Confirmation gates for destructive Google Workspace actions (Gmail send, Calendar create/update/delete).
"""
from hitl.confirmation import needs_confirmation,_build_interrupt_payload 
from hitl.checkpointer import get_checkpointer, make_thread_config

__all__ = ["needs_confirmation", "_build_interrupt_payload", "get_checkpointer", "make_thread_config"]

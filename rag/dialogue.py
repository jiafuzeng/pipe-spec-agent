"""Compatibility imports for callers using the original session router."""
from app.agent.answers import REFUSAL
from app.server.routes.sessions import router

__all__ = ["REFUSAL", "router"]
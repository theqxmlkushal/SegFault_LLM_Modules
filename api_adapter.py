"""
API adapter helpers for backend integration.

Provides a minimal, well-documented interface that a backend developer
can import and wrap in an HTTP endpoint with minimal effort.

Do NOT implement the HTTP server here — this module only exposes plain
Python functions that return JSON-serializable dictionaries.
"""
from typing import Optional, Dict, Any
from modules.chatbot_core import WanderAIChatbotCoreV3


_core = None


def get_core() -> WanderAIChatbotCoreV3:
    """Lazy-create a single chatbot core instance for reuse.

    Backend devs can import `get_core()` and call `process_message`.
    """
    global _core
    if _core is None:
        _core = WanderAIChatbotCoreV3()
    return _core


def handle_message(user_input: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Process a user message and return a JSON-serializable result.

    Returns the same structure as `WanderAIChatbotCoreV3.process_message`.
    This function is synchronous and safe to call from a WSGI/ASGI endpoint.
    """
    core = get_core()
    result = core.process_message(user_input, session_id=session_id)

    # Ensure all values are JSON-serializable (convert any non-serializable parts)
    # The core already returns dicts and lists; this is a best-effort pass.
    if "data" in result and hasattr(result["data"], "model_dump"):
        result["data"] = result["data"].model_dump()

    return result


def reset_core():
    """Reset internal singleton core (useful for tests)."""
    global _core
    _core = None

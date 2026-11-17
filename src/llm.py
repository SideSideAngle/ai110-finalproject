"""Thin wrapper around the Anthropic API.

get_llm() returns a callable (system, user) -> text, or None when no API key or
SDK is available. Every caller must therefore work (via its fallback) without it.
"""
import logging
import os
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)
DEFAULT_MODEL = "claude-haiku-5-5"
LLM = Callable[[str, str], str]


def make_llm(api_key: str, model: Optional[str] = None) -> Optional[LLM]:
    """Build the LLM callable from an explicit key (used by the web app's key box)."""
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed: running in offline fallback mode")
        return None

    client = anthropic.Anthropic(api_key=api_key, timeout=20.0, max_retries=1)
    model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    def call(system: str, user: str) -> str:
        response = client.messages.create(
            model=model, max_tokens=700, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")

    return call


def get_llm() -> Optional[LLM]:
    """LLM from the ANTHROPIC_API_KEY environment variable / .env file, or None."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.info("ANTHROPIC_API_KEY not set: running in offline fallback mode")
        return None
    return make_llm(key)


def validate_llm(llm: LLM) -> Tuple[bool, str]:
    """Make one tiny call so a bad key is reported immediately. Never echoes the key."""
    try:
        llm("Reply with the single word OK.", "ping")
        return True, "Key works. AI mode is on."
    except Exception as exc:
        logger.warning("API key check failed: %s", type(exc).__name__)
        return False, f"That key was not accepted, or the API is unreachable ({type(exc).__name__})."

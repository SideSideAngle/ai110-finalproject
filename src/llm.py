"""Thin wrapper around the Anthropic API.

get_llm() returns a callable (system, user) -> text, or None when no API key or
SDK is available. Every caller must therefore work (via its fallback) without it.
"""
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)
DEFAULT_MODEL = "claude-haiku-5-5"
LLM = Callable[[str, str], str]


def get_llm() -> Optional[LLM]:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.info("ANTHROPIC_API_KEY not set: running in offline fallback mode")
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed: running in offline fallback mode")
        return None

    client = anthropic.Anthropic(timeout=20.0, max_retries=1)
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    def call(system: str, user: str) -> str:
        response = client.messages.create(
            model=model, max_tokens=700, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")

    return call

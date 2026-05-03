from __future__ import annotations

import time
from typing import Iterator, Protocol, TypedDict, runtime_checkable


class Message(TypedDict, total=False):
    role: str            # 'user' | 'assistant' | 'system'
    text: str
    images: list[bytes]  # raw PNG bytes (optional)


@runtime_checkable
class ResponseProvider(Protocol):
    """Port for response backends. Accepts a list of messages (with optional
    images) and yields response text chunks for the latest assistant turn."""

    display_name: str

    def stream(self, messages: list[Message]) -> Iterator[str]:
        ...

    def is_configured(self) -> bool:
        ...


class PlaceholderProvider:
    display_name = "Placeholder"

    def __init__(self, delay: float = 0.04):
        self._delay = delay

    def is_configured(self) -> bool:
        return True

    def stream(self, messages: list[Message]) -> Iterator[str]:
        last_user = next(
            (m for m in reversed(messages) if m.get("role") == "user"), None
        )
        text = (last_user or {}).get("text", "")
        n_imgs = len((last_user or {}).get("images", []) or [])
        history_len = sum(1 for m in messages if m.get("role") in ("user", "assistant"))
        reply = (
            f"Placeholder reply to: {text!r}"
            + (f" (with {n_imgs} image(s))" if n_imgs else "")
            + f". Conversation has {history_len} message(s) so far."
        )
        for word in reply.split(" "):
            yield word + " "
            time.sleep(self._delay)

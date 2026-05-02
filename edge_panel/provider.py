from __future__ import annotations

import time
from typing import Iterator, Protocol, runtime_checkable


@runtime_checkable
class ResponseProvider(Protocol):
    """Port for response backends.

    Any object that yields response chunks for a query string can be used as
    a provider — placeholder, local model, Claude API, etc.
    """

    def stream(self, query: str) -> Iterator[str]:
        ...


class PlaceholderProvider:
    def __init__(self, delay: float = 0.04):
        self._delay = delay

    def stream(self, query: str) -> Iterator[str]:
        text = (
            f"You asked: {query!r}\n\n"
            "This is a placeholder response streaming in word by word. "
            "Replace this provider with a real backend (e.g. an LLM client) "
            "by passing any object that implements ResponseProvider.stream()."
        )
        for word in text.split(" "):
            yield word + " "
            time.sleep(self._delay)

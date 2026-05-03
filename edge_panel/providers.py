"""Real AI providers. Each implements the ResponseProvider protocol from
provider.py. SDKs are imported lazily so users only need to install the ones
they actually use."""

from __future__ import annotations

import base64
from typing import Iterator

from .provider import Message


def _b64(img: bytes) -> str:
    return base64.standard_b64encode(img).decode("ascii")


# ---------------- Anthropic Claude -----------------------------------------

class ClaudeProvider:
    display_name = "Claude (Anthropic)"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5"):
        self._api_key = api_key
        self._model = model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def stream(self, messages: list[Message]) -> Iterator[str]:
        from anthropic import Anthropic

        client = Anthropic(api_key=self._api_key)
        system = next(
            (m.get("text", "") for m in messages if m.get("role") == "system"), None
        )
        api_messages = []
        for m in messages:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            content: list[dict] = []
            for img in m.get("images", []) or []:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": _b64(img),
                    },
                })
            if m.get("text"):
                content.append({"type": "text", "text": m["text"]})
            if content:
                api_messages.append({"role": role, "content": content})

        # Anthropic's API requires max_tokens; set to model's typical ceiling
        # so it's effectively "let the model decide when to stop."
        kwargs = {
            "model": self._model,
            "max_tokens": 8192,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system

        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text


# ---------------- OpenAI GPT -----------------------------------------------

class OpenAIProvider:
    display_name = "OpenAI (GPT)"

    def __init__(self, api_key: str, model: str = "gpt-5"):
        self._api_key = api_key
        self._model = model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def stream(self, messages: list[Message]) -> Iterator[str]:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        api_messages = []
        for m in messages:
            role = m.get("role")
            if role not in ("user", "assistant", "system"):
                continue
            parts: list[dict] = []
            if m.get("text"):
                parts.append({"type": "text", "text": m["text"]})
            for img in m.get("images", []) or []:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{_b64(img)}"},
                })
            if not parts:
                continue
            # System messages must be plain string
            if role == "system":
                api_messages.append({"role": "system", "content": m.get("text", "")})
            else:
                api_messages.append({"role": role, "content": parts})

        stream = client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            stream=True,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            except (AttributeError, IndexError):
                continue


# ---------------- Google Gemini --------------------------------------------

class GeminiProvider:
    display_name = "Gemini (Google)"

    def __init__(self, api_key: str, model: str = "gemini-2.5-pro"):
        self._api_key = api_key
        self._model = model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def stream(self, messages: list[Message]) -> Iterator[str]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)

        system_text = next(
            (m.get("text", "") for m in messages if m.get("role") == "system"), None
        )

        contents = []
        for m in messages:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            parts = []
            if m.get("text"):
                parts.append(types.Part.from_text(text=m["text"]))
            for img in m.get("images", []) or []:
                parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
            if parts:
                contents.append(types.Content(
                    role="user" if role == "user" else "model",
                    parts=parts,
                ))

        # No max_output_tokens — let Gemini decide based on its own default
        # (the model's full output capacity, typically 8K-65K tokens).
        config = types.GenerateContentConfig(
            system_instruction=system_text or None,
        )

        for chunk in client.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        ):
            text = getattr(chunk, "text", None)
            if text:
                yield text


# ---------------- Registry -------------------------------------------------

PROVIDER_KEYS = ("placeholder", "claude", "gemini", "openai")
PROVIDER_LABELS = {
    "placeholder": "Placeholder",
    "claude": "Claude (Anthropic)",
    "gemini": "Gemini (Google)",
    "openai": "OpenAI (GPT)",
}


def build_provider(key: str, config: dict):
    """Construct a provider instance from config."""
    from .provider import PlaceholderProvider

    api_keys = config.get("api_keys", {})
    models = config.get("models", {})
    if key == "claude":
        return ClaudeProvider(api_keys.get("claude", ""), models.get("claude", "claude-sonnet-4-5"))
    if key == "gemini":
        return GeminiProvider(api_keys.get("gemini", ""), models.get("gemini", "gemini-2.5-pro"))
    if key == "openai":
        return OpenAIProvider(api_keys.get("openai", ""), models.get("openai", "gpt-5"))
    return PlaceholderProvider()

from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".edge_panel"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_SYSTEM_PROMPT = (
    "You are a quick-answer assistant inside a desktop side-panel. "
    "Keep responses to 2-4 sentences. Only elaborate further if the user "
    "asks a follow-up or explicit clarification question."
)

DEFAULT_CONFIG: dict = {
    "hotkey": "Alt+Space",
    "provider": "placeholder",
    "api_keys": {
        "claude": "",
        "gemini": "",
        "openai": "",
    },
    "models": {
        "claude": "claude-sonnet-4-5",
        "gemini": "gemini-2.5-pro",
        "openai": "gpt-5",
    },
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return _deep_merge(DEFAULT_CONFIG, data)
        except Exception:
            pass
    return _deep_merge(DEFAULT_CONFIG, {})


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


_SPECIAL_KEYS = {
    "space": "<space>",
    "tab": "<tab>",
    "enter": "<enter>",
    "return": "<enter>",
    "escape": "<esc>",
    "esc": "<esc>",
    "backspace": "<backspace>",
    "delete": "<delete>",
    "del": "<delete>",
    "up": "<up>",
    "down": "<down>",
    "left": "<left>",
    "right": "<right>",
    "home": "<home>",
    "end": "<end>",
    "pgup": "<page_up>",
    "pgdown": "<page_down>",
    **{f"f{i}": f"<f{i}>" for i in range(1, 25)},
}
_MODIFIERS = {"alt", "ctrl", "shift", "meta", "cmd", "win"}


def qt_hotkey_to_pynput(qt_str: str) -> str:
    """Convert 'Alt+Space' to '<alt>+<space>' for pynput.GlobalHotKeys."""
    if not qt_str:
        return ""
    parts = [p.strip().lower() for p in qt_str.split("+")]
    out = []
    for p in parts:
        if p in _MODIFIERS:
            out.append(f"<{p}>")
        elif p in _SPECIAL_KEYS:
            out.append(_SPECIAL_KEYS[p])
        else:
            out.append(p)
    return "+".join(out)


class HotkeyManager(QObject):
    """Global system hotkey via pynput. Emits `triggered` on the Qt main thread."""

    triggered = pyqtSignal()

    def __init__(self, qt_hotkey: str = "Alt+Space", parent: QObject | None = None):
        super().__init__(parent)
        self._qt_hotkey = qt_hotkey
        self._listener = None

    @property
    def qt_hotkey(self) -> str:
        return self._qt_hotkey

    def start(self):
        self.stop()
        try:
            from pynput import keyboard
        except ImportError:
            print("[HotkeyManager] pynput not installed; hotkey disabled")
            return
        pynput_str = qt_hotkey_to_pynput(self._qt_hotkey)
        if not pynput_str:
            return
        try:
            self._listener = keyboard.GlobalHotKeys({pynput_str: self._on_fired})
            self._listener.start()
        except Exception as exc:
            print(f"[HotkeyManager] failed to register {self._qt_hotkey!r}: {exc}")
            self._listener = None

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def set_hotkey(self, qt_hotkey: str):
        if not qt_hotkey:
            return
        self._qt_hotkey = qt_hotkey
        self.start()

    def _on_fired(self):
        # called on pynput's listener thread; signal emission is thread-safe
        self.triggered.emit()

from __future__ import annotations

from typing import Iterator

from .panel import EdgePanel


class EdgePanelManager:
    """Container for the larger program to organize multiple EdgePanel instances.

    Each panel is registered under a name. The manager exposes lifecycle
    helpers (show/hide/close) and lookup, but does not itself dictate layout
    or behavior — panels remain self-contained.
    """

    def __init__(self):
        self._panels: dict[str, EdgePanel] = {}

    def add(self, name: str, panel: EdgePanel) -> EdgePanel:
        if name in self._panels:
            raise ValueError(f"panel '{name}' already registered")
        self._panels[name] = panel
        return panel

    def remove(self, name: str):
        panel = self._panels.pop(name, None)
        if panel is not None:
            panel.close()

    def get(self, name: str) -> EdgePanel:
        return self._panels[name]

    def names(self) -> list[str]:
        return list(self._panels.keys())

    def show_all(self):
        for p in self._panels.values():
            p.show()

    def hide_all(self):
        for p in self._panels.values():
            p.hide()

    def close_all(self):
        for p in self._panels.values():
            p.close()
        self._panels.clear()

    def __iter__(self) -> Iterator[EdgePanel]:
        return iter(self._panels.values())

    def __len__(self) -> int:
        return len(self._panels)

    def __contains__(self, name: str) -> bool:
        return name in self._panels

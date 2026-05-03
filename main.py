import sys

from PyQt6.QtWidgets import QApplication

from edge_panel import (
    EdgePanel,
    EdgePanelManager,
    HotkeyManager,
    load_config,
    save_config,
)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = load_config()
    manager = EdgePanelManager()

    panel = EdgePanel(config=config, edge="right", anchor="center")
    manager.add("default", panel)

    hotkeys = HotkeyManager(qt_hotkey=config.get("hotkey", "Alt+Space"))
    hotkeys.triggered.connect(panel.hotkey_toggle)
    panel.bind_hotkey_manager(hotkeys)
    hotkeys.start()

    # Persist any settings change
    panel.config_changed.connect(save_config)

    manager.show_all()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

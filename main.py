import sys

from PyQt6.QtWidgets import QApplication

from edge_panel import EdgePanel, EdgePanelManager, PlaceholderProvider


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    manager = EdgePanelManager()

    panel = EdgePanel(
        provider=PlaceholderProvider(),
        edge="right",
        anchor="center",
    )
    manager.add("default", panel)
    manager.show_all()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

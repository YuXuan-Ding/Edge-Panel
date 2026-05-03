from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from .providers import PROVIDER_KEYS, PROVIDER_LABELS


class SettingsDialog(QDialog):
    """Settings dialog for hotkey, provider selection, API keys, system prompt."""

    settings_saved = pyqtSignal(dict)  # emits the new config dict

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edge Panel Settings")
        self.setModal(True)
        self.resize(420, 480)

        self._config = dict(config)
        self._config["api_keys"] = dict(config.get("api_keys", {}))
        self._config["models"] = dict(config.get("models", {}))

        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Hotkey
        self._key_edit = QKeySequenceEdit()
        self._key_edit.setKeySequence(QKeySequence(self._config.get("hotkey", "Alt+Space")))
        form.addRow("Hotkey:", self._key_edit)

        # Provider selection
        self._provider_combo = QComboBox()
        for k in PROVIDER_KEYS:
            self._provider_combo.addItem(PROVIDER_LABELS[k], k)
        idx = self._provider_combo.findData(self._config.get("provider", "placeholder"))
        if idx >= 0:
            self._provider_combo.setCurrentIndex(idx)
        form.addRow("Default provider:", self._provider_combo)

        # API key fields
        self._claude_key = QLineEdit(self._config["api_keys"].get("claude", ""))
        self._claude_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._claude_key.setPlaceholderText("sk-ant-…")
        form.addRow("Claude API key:", self._claude_key)

        self._gemini_key = QLineEdit(self._config["api_keys"].get("gemini", ""))
        self._gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._gemini_key.setPlaceholderText("AIza…")
        form.addRow("Gemini API key:", self._gemini_key)

        self._openai_key = QLineEdit(self._config["api_keys"].get("openai", ""))
        self._openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_key.setPlaceholderText("sk-…")
        form.addRow("OpenAI API key:", self._openai_key)

        # Model overrides (optional)
        self._claude_model = QLineEdit(self._config["models"].get("claude", ""))
        self._gemini_model = QLineEdit(self._config["models"].get("gemini", ""))
        self._openai_model = QLineEdit(self._config["models"].get("openai", ""))
        form.addRow("Claude model:", self._claude_model)
        form.addRow("Gemini model:", self._gemini_model)
        form.addRow("OpenAI model:", self._openai_model)

        layout.addLayout(form)

        # System prompt
        layout.addWidget(QLabel("System prompt (sent at start of every conversation):"))
        self._sys_prompt = QPlainTextEdit(self._config.get("system_prompt", ""))
        self._sys_prompt.setFixedHeight(90)
        layout.addWidget(self._sys_prompt)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        layout.addWidget(QLabel(
            "Keys are stored in plaintext in ~/.edge_panel/config.json"
        ))

    def _on_ok(self):
        seq = self._key_edit.keySequence().toString()
        if seq:
            self._config["hotkey"] = seq
        self._config["provider"] = self._provider_combo.currentData()
        self._config["api_keys"] = {
            "claude": self._claude_key.text().strip(),
            "gemini": self._gemini_key.text().strip(),
            "openai": self._openai_key.text().strip(),
        }
        self._config["models"] = {
            "claude": self._claude_model.text().strip() or "claude-sonnet-4-5",
            "gemini": self._gemini_model.text().strip() or "gemini-2.5-pro",
            "openai": self._openai_model.text().strip() or "gpt-5",
        }
        self._config["system_prompt"] = self._sys_prompt.toPlainText().strip()
        self.settings_saved.emit(self._config)
        self.accept()

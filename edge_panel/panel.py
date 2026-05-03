from __future__ import annotations

import sys

from PyQt6.QtCore import (
    QBuffer,
    QEasingCurve,
    QEvent,
    QIODevice,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QCursor, QGuiApplication, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import DEFAULT_SYSTEM_PROMPT
from .provider import Message, ResponseProvider
from .providers import PROVIDER_KEYS, PROVIDER_LABELS, build_provider
from .settings_dialog import SettingsDialog
from .worker import StreamWorker


# ---------------- Helper text edits ----------------------------------------

class _AutoSizeTextEdit(QTextEdit):
    heightAdjusted = pyqtSignal()

    def __init__(self, min_lines: int = 1, parent: QWidget | None = None):
        super().__init__(parent)
        self._min_lines = min_lines
        self._max_height: int | None = None
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.document().contentsChanged.connect(self._adjust_height)

    def set_max_height(self, h: int | None):
        if h != self._max_height:
            self._max_height = h
            self._adjust_height()

    def _adjust_height(self):
        doc = self.document()
        if self.viewport().width() > 0:
            doc.setTextWidth(self.viewport().width())
        margins = self.contentsMargins()
        frame = self.frameWidth() * 2
        fm = self.fontMetrics()
        content_h = int(doc.size().height())
        if self._min_lines == 0:
            min_h = 0
        else:
            min_h = (
                fm.lineSpacing() * self._min_lines
                + margins.top() + margins.bottom() + frame + 12
            )
        target = max(content_h + margins.top() + margins.bottom() + frame + 8, min_h)
        if self._max_height is not None:
            target = min(target, self._max_height)
        if target != self.height():
            self.setFixedHeight(target)
            self.heightAdjusted.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()


class _InputBox(_AutoSizeTextEdit):
    submitRequested = pyqtSignal()
    escapePressed = pyqtSignal()
    imagesChanged = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(min_lines=1, parent=parent)
        self.setPlaceholderText("Ask anything…  (paste images with Ctrl+V)")
        self.setAcceptRichText(False)
        self._pending_images: list[bytes] = []

    def insertFromMimeData(self, source):
        if source.hasImage():
            img = source.imageData()
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buffer, "PNG")
            self._pending_images.append(bytes(buffer.data()))
            buffer.close()
            self.imagesChanged.emit()
            return
        super().insertFromMimeData(source)

    def take_pending_images(self) -> list[bytes]:
        imgs = self._pending_images
        self._pending_images = []
        self.imagesChanged.emit()
        return imgs

    def remove_image(self, idx: int):
        if 0 <= idx < len(self._pending_images):
            del self._pending_images[idx]
            self.imagesChanged.emit()

    @property
    def pending_images(self) -> list[bytes]:
        return self._pending_images

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.submitRequested.emit()
            return
        if key == Qt.Key.Key_Escape:
            self.escapePressed.emit()
            return
        super().keyPressEvent(event)


# ---------------- Chat bubble ----------------------------------------------

class _ChatBubble(QFrame):
    """A single chat message: optional images then text. Auto-sizes to content."""

    contentChanged = pyqtSignal()

    def __init__(self, role: str, text: str = "", images: list[bytes] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role
        self.setObjectName(f"bubble_{role}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Image thumbnails (if any)
        for img_bytes in images or []:
            pix = QPixmap()
            pix.loadFromData(img_bytes)
            if not pix.isNull():
                scaled = pix.scaled(
                    260, 200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                lbl = QLabel()
                lbl.setPixmap(scaled)
                layout.addWidget(lbl)

        # Text body (only if there's actually text or it's an assistant bubble being filled)
        self._text = _AutoSizeTextEdit(min_lines=0)
        self._text.setReadOnly(True)
        self._text.setObjectName("bubble_text")
        self._text.setStyleSheet("background: transparent; border: none; padding: 0;")
        self._text.heightAdjusted.connect(self.contentChanged.emit)
        if text:
            self._text.setPlainText(text)
        layout.addWidget(self._text)

    def append_text(self, chunk: str):
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self._text.setTextCursor(cursor)

    def text(self) -> str:
        return self._text.toPlainText()


# ---------------- Win32 focus helper ---------------------------------------

def _force_foreground(hwnd: int):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        cur = kernel32.GetCurrentThreadId()
        fg = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg, None)
        if fg_thread and fg_thread != cur:
            user32.AttachThreadInput(fg_thread, cur, True)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(fg_thread, cur, False)
        else:
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


# ---------------- Edge panel -----------------------------------------------

class EdgePanel(QWidget):
    PEEK_WIDTH = 8
    EXPANDED_WIDTH = 420
    PEEK_HEIGHT = 140
    PADDING = 10
    GAP = 12
    EXPAND_MS = 200
    SNAP_ZONE = 40
    DRAG_THRESHOLD = 5

    UNPINNED_ALPHA = 130
    PINNED_ALPHA = 235

    request_submitted = pyqtSignal(str)
    response_finished = pyqtSignal(str)
    pin_changed = pyqtSignal(bool)
    config_changed = pyqtSignal(dict)

    def __init__(
        self,
        config: dict,
        edge: str = "right",
        anchor: str = "center",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if edge not in ("left", "right"):
            raise ValueError("edge must be 'left' or 'right'")
        if anchor not in ("top", "center", "bottom"):
            raise ValueError("anchor must be 'top', 'center', or 'bottom'")

        self._config = config
        self._edge = edge
        self._anchor = anchor
        self._expanded = False
        self._pinned = False
        self._floating = False
        self._worker: StreamWorker | None = None
        self._press_pos: QPoint | None = None
        self._anchor_y: int = 0

        self._drag_press: QPoint | None = None
        self._drag_origin: QPoint | None = None
        self._drag_active = False

        self._provider: ResponseProvider = build_provider(
            config.get("provider", "placeholder"), config
        )
        self._history: list[Message] = []
        self._streaming_bubble: _ChatBubble | None = None
        self._streaming_accum = ""

        self._hotkey_setter = None  # bound by main

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build_ui()
        self._apply_style()
        self._refresh_provider_button()
        self._position_initial()

    # ----- public hooks ---------------------------------------------------

    def bind_hotkey_manager(self, manager):
        self._hotkey_setter = manager.set_hotkey
        manager.set_hotkey(self._config.get("hotkey", "Alt+Space"))

    @property
    def is_pinned(self) -> bool:
        return self._pinned

    @property
    def is_floating(self) -> bool:
        return self._floating

    # ----- ui -------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._container = QFrame(self)
        self._container.setObjectName("container")
        outer.addWidget(self._container)

        clayout = QVBoxLayout(self._container)
        clayout.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        clayout.setSpacing(0)

        # Top bar
        self._top_bar = QWidget()
        self._top_bar.setObjectName("topbar")
        self._top_bar.setCursor(Qt.CursorShape.OpenHandCursor)
        top_row = QHBoxLayout(self._top_bar)
        top_row.setContentsMargins(0, 0, 0, 6)
        top_row.setSpacing(4)

        self._settings_button = self._mk_tool_button("⚙", "Settings", self._open_settings)
        top_row.addWidget(self._settings_button)

        self._pin_button = self._mk_tool_button("⌖", "Pin (keeps panel open)", self._toggle_pin)
        self._pin_button.setCheckable(True)
        top_row.addWidget(self._pin_button)

        self._provider_button = QToolButton()
        self._provider_button.setObjectName("providerbutton")
        self._provider_button.setText("Placeholder")
        self._provider_button.setCursor(Qt.CursorShape.ArrowCursor)
        self._provider_button.setToolTip("Choose AI provider")
        self._provider_button.clicked.connect(self._open_provider_menu)
        top_row.addWidget(self._provider_button)

        top_row.addStretch(1)

        self._new_chat_button = self._mk_tool_button("↻", "New chat (clear history)", self._new_chat)
        top_row.addWidget(self._new_chat_button)

        self._close_button = self._mk_tool_button("✕", "Quit program", self._quit_app)
        top_row.addWidget(self._close_button)

        clayout.addWidget(self._top_bar)

        # Chat scroll area (hidden until first message)
        self._chat_scroll = QScrollArea()
        self._chat_scroll.setObjectName("chatscroll")
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._chat_scroll.setVisible(False)

        self._chat_holder = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_holder)
        self._chat_layout.setContentsMargins(0, 0, 0, 0)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch(1)
        self._chat_scroll.setWidget(self._chat_holder)
        clayout.addWidget(self._chat_scroll)

        # Gap
        self._gap = QWidget()
        self._gap.setFixedHeight(self.GAP)
        clayout.addWidget(self._gap)

        # Image thumbnail strip (above input)
        self._thumb_strip = QWidget()
        self._thumb_strip.setObjectName("thumbstrip")
        self._thumb_strip.setVisible(False)
        ts_layout = QHBoxLayout(self._thumb_strip)
        ts_layout.setContentsMargins(0, 0, 0, 4)
        ts_layout.setSpacing(4)
        clayout.addWidget(self._thumb_strip)

        # Input
        self._input = _InputBox()
        self._input.submitRequested.connect(self._submit)
        self._input.escapePressed.connect(self._on_escape)
        self._input.heightAdjusted.connect(self._sync_window_size)
        self._input.imagesChanged.connect(self._refresh_thumbs)
        clayout.addWidget(self._input)

        clayout.addStretch(0)

        # Filters last
        self._container.installEventFilter(self)
        self._top_bar.installEventFilter(self)

    def _mk_tool_button(self, text: str, tooltip: str, slot) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setFixedSize(22, 22)
        b.setToolTip(tooltip)
        b.setCursor(Qt.CursorShape.ArrowCursor)
        b.clicked.connect(slot)
        return b

    def _apply_style(self):
        a = self.PINNED_ALPHA if self._pinned else self.UNPINNED_ALPHA
        border_a = min(a + 60, 255)
        ed_a = min(a + 70, 255)

        if self._floating:
            radii = "12px"
        elif self._edge == "right":
            radii = "12px 0 0 12px"
        else:
            radii = "0 12px 12px 0"

        self.setStyleSheet(
            f"""
            #container {{
                background-color: rgba(28, 28, 32, {a});
                border-radius: {radii};
                border: 1px solid rgba(150, 150, 160, {border_a});
            }}
            #topbar, #thumbstrip {{ background: transparent; }}
            #chatscroll {{ background: transparent; border: none; }}
            QToolButton {{
                background: rgba(60, 60, 68, {ed_a});
                color: #f0f0f2;
                border: 1px solid rgba(120, 120, 130, {border_a});
                border-radius: 4px;
                padding: 0 4px;
                font-size: 12px;
            }}
            QToolButton:checked {{
                background: rgba(180, 220, 150, 235);
                color: #1a1a1a;
                border: 1px solid rgba(140, 200, 110, 245);
            }}
            #providerbutton {{
                padding: 0 8px;
                min-width: 80px;
            }}
            QTextEdit {{
                background: rgba(50, 50, 56, {ed_a});
                color: #f0f0f2;
                border: 1px solid rgba(120, 120, 130, {border_a});
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
                selection-background-color: #4a90e2;
            }}
            QTextEdit:focus {{
                border: 1px solid rgba(150, 200, 240, 240);
            }}
            #bubble_user {{
                background: rgba(70, 110, 170, 220);
                border-radius: 10px;
            }}
            #bubble_assistant {{
                background: rgba(60, 60, 68, 230);
                border-radius: 10px;
            }}
            #bubble_system {{
                background: rgba(120, 80, 80, 200);
                border-radius: 10px;
            }}
            #bubble_user QTextEdit, #bubble_assistant QTextEdit, #bubble_system QTextEdit {{
                background: transparent;
                border: none;
                padding: 0;
                color: #f5f5f7;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(150, 150, 160, 180);
                border-radius: 4px;
                min-height: 20px;
            }}
            """
        )

    def _position_initial(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if self._anchor == "top":
            y = screen.top() + 32
        elif self._anchor == "bottom":
            y = screen.bottom() - self.PEEK_HEIGHT - 32
        else:
            y = screen.top() + (screen.height() - self.PEEK_HEIGHT) // 2
        self._anchor_y = y
        if self._edge == "right":
            x = screen.right() - self.PEEK_WIDTH + 1
        else:
            x = screen.left()
        self.setGeometry(x, y, self.PEEK_WIDTH, self.PEEK_HEIGHT)

    # ----- hover / expand -------------------------------------------------

    def enterEvent(self, event):
        if not self._floating and not self._expanded:
            self._expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._floating:
            return
        if self._expanded and not self._pinned:
            if self.geometry().contains(QCursor.pos()):
                return  # false leave from translucent corner
            self._retract()
        super().leaveEvent(event)

    def _expand(self):
        self._expanded = True
        self._animate_to_geometry(self.EXPANDED_WIDTH, self._compute_target_height())
        QTimer.singleShot(self.EXPAND_MS + 30, self._focus_input)

    def _focus_input(self):
        if not self._expanded:
            return
        self.raise_()
        self.activateWindow()
        try:
            _force_foreground(int(self.winId()))
        except Exception:
            pass
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _retract(self):
        if self._is_streaming():
            self._worker.cancel()
            self._worker = None
        self._expanded = False
        self._set_pinned(False)
        self._animate_to_geometry(self.PEEK_WIDTH, self.PEEK_HEIGHT)

    # ----- hotkey ---------------------------------------------------------

    def hotkey_toggle(self):
        if not self._expanded:
            if self._floating:
                self._focus_input()
                return
            self._set_pinned(True)
            self._expand()
        else:
            if self._floating:
                self._set_pinned(False)
                self._floating = False
                self._apply_style()
            self._set_pinned(False)
            self._retract()

    # ----- geometry -------------------------------------------------------

    def _compute_target_height(self) -> int:
        chrome = self.PADDING * 2 + 28  # top bar + spacing
        chat_h = self._chat_scroll.height() if self._chat_scroll.isVisible() else 0
        thumb_h = self._thumb_strip.sizeHint().height() if self._thumb_strip.isVisible() else 0
        input_h = max(self._input.height(), 36)
        return chrome + chat_h + self.GAP + thumb_h + input_h

    def _animate_to_geometry(self, width: int, height: int):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if self._floating:
            x = self.x()
        elif self._edge == "right":
            x = screen.right() - width + 1
        else:
            x = screen.left()
        max_h = int(screen.height() * 0.92)
        height = min(height, max_h)
        y = self._anchor_y
        if y + height > screen.bottom():
            y = max(screen.top() + 16, screen.bottom() - height - 16)
        target = QRect(x, y, width, height)
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(self.EXPAND_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self.geometry())
        anim.setEndValue(target)
        anim.start()
        self._geom_anim = anim

    def _sync_window_size(self):
        if not self._expanded:
            return
        screen = QGuiApplication.primaryScreen().availableGeometry()
        max_h = int(screen.height() * 0.92)

        # Let the chat area request its natural size, but cap it
        if self._chat_scroll.isVisible():
            wanted_chat = self._chat_holder.sizeHint().height() + 4
            chrome = self.PADDING * 2 + 28
            input_h = max(self._input.height(), 36)
            thumb_h = self._thumb_strip.sizeHint().height() if self._thumb_strip.isVisible() else 0
            allowed_chat = max_h - chrome - self.GAP - input_h - thumb_h
            chat_h = min(wanted_chat, max(120, allowed_chat))
            self._chat_scroll.setFixedHeight(max(120, chat_h))

        desired = self._compute_target_height()
        desired = min(desired, max_h)

        geom = self.geometry()
        new_y = geom.y() if self._floating else self._anchor_y
        if not self._floating and new_y + desired > screen.bottom():
            new_y = max(screen.top() + 16, screen.bottom() - desired - 16)
        self.setGeometry(geom.x(), new_y, geom.width(), desired)
        QTimer.singleShot(0, self._scroll_chat_to_bottom)

    def _scroll_chat_to_bottom(self):
        sb = self._chat_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ----- chat / streaming ----------------------------------------------

    def _add_bubble(self, role: str, text: str = "", images: list[bytes] | None = None
                    ) -> _ChatBubble:
        bubble = _ChatBubble(role, text=text, images=images)
        bubble.contentChanged.connect(self._sync_window_size)

        # Wrap with HBox so user bubbles right-align, assistant left-align
        wrapper = QWidget()
        wrap_layout = QHBoxLayout(wrapper)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            wrap_layout.addStretch(1)
            wrap_layout.addWidget(bubble, 0)
        else:
            wrap_layout.addWidget(bubble, 0)
            wrap_layout.addStretch(1)

        # Insert before the trailing stretch
        idx = self._chat_layout.count() - 1
        self._chat_layout.insertWidget(idx, wrapper)

        if not self._chat_scroll.isVisible():
            self._chat_scroll.setVisible(True)
        self._sync_window_size()
        return bubble

    def _quit_app(self):
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(500)
        QApplication.instance().quit()

    def _new_chat(self):
        # Cancel streaming
        if self._is_streaming():
            self._worker.cancel()
            self._worker = None
        # Clear chat layout (preserve trailing stretch)
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._history = []
        self._streaming_bubble = None
        self._chat_scroll.setVisible(False)
        self._sync_window_size()

    def _submit(self):
        text = self._input.toPlainText().strip()
        images = self._input.take_pending_images()
        if not text and not images:
            return
        if self._is_streaming():
            return

        # Record user message in history & ui
        user_msg: Message = {"role": "user", "text": text}
        if images:
            user_msg["images"] = images
        self._history.append(user_msg)
        self._add_bubble("user", text=text, images=images)
        self._input.clear()
        self.request_submitted.emit(text)

        if not self._provider.is_configured():
            self._add_bubble(
                "system",
                f"{PROVIDER_LABELS.get(self._config.get('provider', 'placeholder'), 'Provider')} "
                "isn't configured. Click ⚙ and add an API key.",
            )
            return

        # Build full message stack incl. system prompt
        messages: list[Message] = []
        sys_prompt = self._config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
        if sys_prompt:
            messages.append({"role": "system", "text": sys_prompt})
        messages.extend(self._history)

        # Start assistant bubble
        self._streaming_bubble = self._add_bubble("assistant", text="")
        self._streaming_accum = ""

        worker = StreamWorker(self._provider, messages)
        worker.chunk_received.connect(self._on_chunk)
        worker.stream_finished.connect(self._on_finished)
        worker.stream_failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_chunk(self, chunk: str):
        self._streaming_accum += chunk
        if self._streaming_bubble is not None:
            self._streaming_bubble.append_text(chunk)

    def _on_finished(self):
        if self._streaming_accum:
            self._history.append({"role": "assistant", "text": self._streaming_accum})
        self.response_finished.emit(self._streaming_accum)
        self._streaming_bubble = None
        self._streaming_accum = ""
        self._worker = None
        if (
            not self.underMouse()
            and not self._pinned
            and not self._floating
            and self._expanded
        ):
            self._retract()

    def _on_failed(self, message: str):
        if self._streaming_bubble is not None:
            self._streaming_bubble.append_text(f"\n[error: {message}]")
        else:
            self._add_bubble("system", f"Error: {message}")
        self._worker = None

    def _is_streaming(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ----- thumbnails -----------------------------------------------------

    def _refresh_thumbs(self):
        layout = self._thumb_strip.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for i, img_bytes in enumerate(self._input.pending_images):
            pix = QPixmap()
            pix.loadFromData(img_bytes)
            if pix.isNull():
                continue
            lbl = QLabel()
            lbl.setPixmap(pix.scaled(
                40, 40,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
            lbl.setToolTip("Click to remove")
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            # remove on click
            def _make_remove(idx):
                def _clicked(ev):
                    self._input.remove_image(idx)
                return _clicked
            lbl.mousePressEvent = _make_remove(i)
            layout.addWidget(lbl)
        layout.addStretch(1)

        self._thumb_strip.setVisible(bool(self._input.pending_images))
        self._sync_window_size()

    # ----- pin -----------------------------------------------------------

    def _set_pinned(self, pinned: bool):
        if pinned == self._pinned:
            self._pin_button.setChecked(pinned)
            return
        self._pinned = pinned
        self._pin_button.setChecked(pinned)
        self._apply_style()
        self.pin_changed.emit(pinned)

    def _toggle_pin(self):
        self._set_pinned(not self._pinned)

    def _on_escape(self):
        if self._pinned:
            self._set_pinned(False)
        elif self._floating:
            self._input.clear()
        else:
            self._input.clear()
            self._retract()

    # ----- provider switching --------------------------------------------

    def _open_provider_menu(self):
        menu = QMenu(self)
        for k in PROVIDER_KEYS:
            act = menu.addAction(PROVIDER_LABELS[k])
            act.triggered.connect(lambda checked=False, key=k: self._switch_provider(key))
        menu.exec(self._provider_button.mapToGlobal(
            self._provider_button.rect().bottomLeft()
        ))

    def _switch_provider(self, key: str):
        self._config["provider"] = key
        self._provider = build_provider(key, self._config)
        self._refresh_provider_button()
        self.config_changed.emit(self._config)

    def _refresh_provider_button(self):
        key = self._config.get("provider", "placeholder")
        self._provider_button.setText(PROVIDER_LABELS.get(key, key))

    # ----- settings ------------------------------------------------------

    def _open_settings(self):
        was_pinned = self._pinned
        self._set_pinned(True)
        dlg = SettingsDialog(self._config, self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()
        if not was_pinned:
            self._set_pinned(False)

    def _on_settings_saved(self, new_config: dict):
        self._config.update(new_config)
        self._provider = build_provider(self._config.get("provider", "placeholder"), self._config)
        self._refresh_provider_button()
        if self._hotkey_setter is not None:
            self._hotkey_setter(self._config.get("hotkey", "Alt+Space"))
        self.config_changed.emit(self._config)

    # ----- drag (windowing) -----------------------------------------------

    def _on_drag_finished(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        geom = self.geometry()
        if geom.right() >= screen.right() - self.SNAP_ZONE:
            self._dock("right")
        elif geom.left() <= screen.left() + self.SNAP_ZONE:
            self._dock("left")

    def _dock(self, edge: str):
        self._edge = edge
        self._floating = False
        self._anchor_y = self.y()
        self._set_pinned(False)
        self._apply_style()
        self._expanded = False
        self._animate_to_geometry(self.PEEK_WIDTH, self.PEEK_HEIGHT)

    # ----- event filter ---------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self._top_bar:
            t = event.type()
            if t == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._drag_press = event.globalPosition().toPoint()
                    self._drag_origin = self.geometry().topLeft()
                    self._drag_active = False
            elif t == QEvent.Type.MouseMove:
                if (
                    event.buttons() & Qt.MouseButton.LeftButton
                    and self._drag_press is not None
                ):
                    cur = event.globalPosition().toPoint()
                    if not self._drag_active:
                        if (cur - self._drag_press).manhattanLength() > self.DRAG_THRESHOLD:
                            self._drag_active = True
                            self._floating = True
                            self._apply_style()
                    if self._drag_active:
                        delta = cur - self._drag_press
                        self.move(self._drag_origin + delta)
                        return True
            elif t == QEvent.Type.MouseButtonRelease:
                was_dragging = self._drag_active
                self._drag_press = None
                self._drag_origin = None
                self._drag_active = False
                if was_dragging:
                    self._on_drag_finished()
                    return True
                self._toggle_pin()
                return True

        if obj is self._container:
            t = event.type()
            if t == QEvent.Type.MouseButtonPress:
                self._press_pos = event.position().toPoint()
            elif t == QEvent.Type.MouseButtonRelease and self._press_pos is not None:
                rel = event.position().toPoint()
                if (
                    abs(rel.x() - self._press_pos.x()) < 5
                    and abs(rel.y() - self._press_pos.y()) < 5
                ):
                    self._toggle_pin()
                self._press_pos = None

        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(500)
        super().closeEvent(event)

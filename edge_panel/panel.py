from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QGuiApplication, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .provider import ResponseProvider
from .worker import StreamWorker


class _AutoSizeTextEdit(QTextEdit):
    """QTextEdit whose height auto-fits its content (with optional cap)."""

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
                + margins.top()
                + margins.bottom()
                + frame
                + 12
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

    def __init__(self, parent: QWidget | None = None):
        super().__init__(min_lines=1, parent=parent)
        self.setPlaceholderText("Ask anything…")
        self.setAcceptRichText(False)

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


class _ResultBox(_AutoSizeTextEdit):
    selectionMade = pyqtSignal()
    clickedWithoutSelection = pyqtSignal()
    escapePressed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(min_lines=0, parent=parent)
        self.setReadOnly(True)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.textCursor().hasSelection():
            self.selectionMade.emit()
        else:
            self.clickedWithoutSelection.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.escapePressed.emit()
            return
        super().keyPressEvent(event)


class EdgePanel(QWidget):
    PEEK_WIDTH = 8
    EXPANDED_WIDTH = 380
    PEEK_HEIGHT = 140
    PADDING = 10
    GAP = 12
    EXPAND_MS = 200

    UNPINNED_ALPHA = 130
    PINNED_ALPHA = 235

    request_submitted = pyqtSignal(str)
    response_finished = pyqtSignal(str)
    pin_changed = pyqtSignal(bool)

    def __init__(
        self,
        provider: ResponseProvider,
        edge: str = "right",
        anchor: str = "center",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if edge not in ("left", "right"):
            raise ValueError("edge must be 'left' or 'right'")
        if anchor not in ("top", "center", "bottom"):
            raise ValueError("anchor must be 'top', 'center', or 'bottom'")

        self._provider = provider
        self._edge = edge
        self._anchor = anchor
        self._expanded = False
        self._pinned = False
        self._worker: StreamWorker | None = None
        self._accumulated = ""
        self._press_pos: QPoint | None = None
        self._anchor_y: int = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build_ui()
        self._apply_style()
        self._position_initial()

    def set_provider(self, provider: ResponseProvider):
        self._provider = provider

    @property
    def is_pinned(self) -> bool:
        return self._pinned

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._container = QFrame(self)
        self._container.setObjectName("container")
        self._container.installEventFilter(self)
        outer.addWidget(self._container)

        clayout = QVBoxLayout(self._container)
        clayout.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        clayout.setSpacing(0)

        # Top row: pin button (left)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 6)
        top_row.setSpacing(0)
        self._pin_button = QToolButton()
        self._pin_button.setObjectName("pinbutton")
        self._pin_button.setText("⌖")  # ⌖ pin-like glyph
        self._pin_button.setCheckable(True)
        self._pin_button.setFixedSize(22, 22)
        self._pin_button.setToolTip("Pin (keeps panel open)")
        self._pin_button.clicked.connect(self._toggle_pin)
        top_row.addWidget(self._pin_button)
        top_row.addStretch(1)
        clayout.addLayout(top_row)

        # Input
        self._input = _InputBox()
        self._input.submitRequested.connect(self._submit)
        self._input.escapePressed.connect(self._on_escape)
        self._input.heightAdjusted.connect(self._sync_window_size)
        clayout.addWidget(self._input)

        # Visible gap between input and result
        self._gap = QWidget()
        self._gap.setFixedHeight(0)
        clayout.addWidget(self._gap)

        # Curtain (result)
        self._curtain = QWidget()
        self._curtain.setVisible(False)
        cl = QVBoxLayout(self._curtain)
        cl.setContentsMargins(0, 0, 0, 0)
        self._result = _ResultBox()
        self._result.heightAdjusted.connect(self._sync_window_size)
        self._result.selectionMade.connect(lambda: self._set_pinned(True))
        self._result.clickedWithoutSelection.connect(self._toggle_pin)
        self._result.escapePressed.connect(self._on_escape)
        cl.addWidget(self._result)
        clayout.addWidget(self._curtain)

        clayout.addStretch(0)

    def _apply_style(self):
        a = self.PINNED_ALPHA if self._pinned else self.UNPINNED_ALPHA
        border_a = min(a + 60, 255)
        ed_a = min(a + 70, 255)
        self.setStyleSheet(
            f"""
            #container {{
                background-color: rgba(28, 28, 32, {a});
                border-radius: 12px;
                border: 1px solid rgba(150, 150, 160, {border_a});
            }}
            #pinbutton {{
                background: rgba(60, 60, 68, {ed_a});
                color: #f0f0f2;
                border: 1px solid rgba(120, 120, 130, {border_a});
                border-radius: 4px;
                padding: 0;
                font-size: 11px;
            }}
            #pinbutton:checked {{
                background: rgba(180, 220, 150, 235);
                color: #1a1a1a;
                border: 1px solid rgba(140, 200, 110, 245);
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

    # ----- hover behavior -------------------------------------------------

    def enterEvent(self, event):
        if not self._expanded:
            self._expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Retract whenever cursor leaves, unless pinned. Streaming continues
        # invisibly is bad UX, so we cancel it on leave too.
        if self._expanded and not self._pinned:
            self._retract()
        super().leaveEvent(event)

    def _expand(self):
        self._expanded = True
        self._animate_to_geometry(self.EXPANDED_WIDTH, self._compute_target_height())
        QTimer.singleShot(self.EXPAND_MS + 20, self._focus_input)

    def _focus_input(self):
        self.raise_()
        self.activateWindow()
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _retract(self):
        if self._is_streaming():
            self._worker.cancel()
            self._worker = None
        self._expanded = False
        self._curtain.setVisible(False)
        self._gap.setFixedHeight(0)
        self._input.clear()
        self._result.clear()
        self._set_pinned(False)
        self._animate_to_geometry(self.PEEK_WIDTH, self.PEEK_HEIGHT)

    # ----- geometry -------------------------------------------------------

    def _compute_target_height(self) -> int:
        pin_row_h = 22 + 6
        chrome = self.PADDING * 2 + pin_row_h
        input_h = max(self._input.height(), 36)
        gap_h = self.GAP if self._curtain.isVisible() else 0
        result_h = self._result.height() if self._curtain.isVisible() else 0
        return chrome + input_h + gap_h + result_h

    def _animate_to_geometry(self, width: int, height: int):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if self._edge == "right":
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
        """Resize the window to fit current content (no animation, snappy)."""
        if not self._expanded:
            return
        screen = QGuiApplication.primaryScreen().availableGeometry()
        max_h = int(screen.height() * 0.92)
        desired = self._compute_target_height()
        if desired > max_h and self._curtain.isVisible():
            current_result = self._result.height()
            non_result = desired - current_result
            allowed_result = max(80, max_h - non_result)
            self._result.set_max_height(allowed_result)
            desired = max_h
        else:
            self._result.set_max_height(None)
        geom = self.geometry()
        new_y = self._anchor_y
        if new_y + desired > screen.bottom():
            new_y = max(screen.top() + 16, screen.bottom() - desired - 16)
        self.setGeometry(geom.x(), new_y, geom.width(), desired)

    # ----- streaming ------------------------------------------------------

    def _submit(self):
        query = self._input.toPlainText().strip()
        if not query or self._is_streaming():
            return
        self._accumulated = ""
        self._result.clear()
        self._curtain.setVisible(True)
        self._gap.setFixedHeight(self.GAP)
        self._sync_window_size()
        self.request_submitted.emit(query)

        worker = StreamWorker(self._provider, query)
        worker.chunk_received.connect(self._on_chunk)
        worker.stream_finished.connect(self._on_finished)
        worker.stream_failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_chunk(self, chunk: str):
        self._accumulated += chunk
        cursor = self._result.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self._result.setTextCursor(cursor)
        self._result.ensureCursorVisible()

    def _on_finished(self):
        self.response_finished.emit(self._accumulated)
        self._worker = None
        if not self.underMouse() and not self._pinned and self._expanded:
            self._retract()

    def _on_failed(self, message: str):
        self._result.append(f"\n[error: {message}]")
        self._worker = None

    def _is_streaming(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ----- pinning --------------------------------------------------------

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
        else:
            self._input.clear()
            self._retract()

    def eventFilter(self, obj, event):
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

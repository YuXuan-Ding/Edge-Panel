from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from .provider import ResponseProvider


class StreamWorker(QThread):
    chunk_received = pyqtSignal(str)
    stream_finished = pyqtSignal()
    stream_failed = pyqtSignal(str)

    def __init__(self, provider: ResponseProvider, query: str):
        super().__init__()
        self._provider = provider
        self._query = query
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            for chunk in self._provider.stream(self._query):
                if self._cancelled:
                    break
                self.chunk_received.emit(chunk)
        except Exception as exc:
            self.stream_failed.emit(str(exc))
            return
        self.stream_finished.emit()

"""Ejecucion de tareas en segundo plano con QThreadPool.

Toda llamada a red (yt-dlp, miniaturas, SponsorBlock) se ejecuta aqui
para no congelar la interfaz.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal


class WorkerSignals(QObject):
    finished = pyqtSignal(object)   # resultado de la funcion
    error = pyqtSignal(str)         # mensaje de error


class Worker(QRunnable):
    """Ejecuta fn(*args, **kwargs) en un hilo del pool."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            resultado = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - se reporta a la UI
            self.signals.error.emit(str(exc))
        else:
            self.signals.finished.emit(resultado)

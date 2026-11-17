"""Pantalla de busqueda con teclado virtual opcional."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.workers import Worker
from infra import youtube_service
from ui.widgets import ShelfWidget, VirtualKeyboard


class SearchScreen(QWidget):
    video_activated = pyqtSignal(object, list)  # (Video, cola)

    def __init__(self, cfg: dict, pool, storage, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.pool = pool
        self.storage = storage

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ---------- Barra de busqueda ----------
        barra = QHBoxLayout()
        barra.setSpacing(10)
        self.input = QLineEdit()
        self.input.setObjectName("searchInput")
        self.input.setPlaceholderText("Buscar en YouTube...")
        self.input.setMinimumHeight(64)
        self.input.returnPressed.connect(self.buscar)
        barra.addWidget(self.input, 1)

        self.btn_buscar = QPushButton("🔍 Buscar")
        self.btn_buscar.setMinimumHeight(64)
        self.btn_buscar.clicked.connect(self.buscar)
        barra.addWidget(self.btn_buscar)
        layout.addLayout(barra)

        # ---------- Teclado virtual (respaldo, opcional) ----------
        self.teclado = VirtualKeyboard()
        self.teclado.key_pressed.connect(self._on_vk_key)
        self.teclado.setVisible(cfg.get("input", {}).get("virtual_keyboard", False))
        layout.addWidget(self.teclado)

        # ---------- Resultados ----------
        self.resultados = ShelfWidget("Resultados", pool, storage)
        self.resultados.video_activated.connect(self.video_activated)
        layout.addWidget(self.resultados, 1)

    def buscar(self) -> None:
        texto = self.input.text().strip()
        if not texto:
            return
        self.resultados.set_loading(f"Buscando '{texto}'...")
        w = Worker(youtube_service.search_videos, self.cfg, texto)
        w.signals.finished.connect(self.resultados.set_videos)
        w.signals.error.connect(lambda _: self.resultados.set_error("Error en la busqueda"))
        self.pool.start(w)

    def _on_vk_key(self, tecla: str) -> None:
        if tecla == "BACK":
            self.input.backspace()
        elif tecla == "ENTER":
            self.buscar()
        elif tecla == "HIDE":
            self.teclado.setVisible(False)
        else:
            self.input.insert(tecla)

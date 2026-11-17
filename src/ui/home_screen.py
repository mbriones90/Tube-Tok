"""Pantalla principal estilo Chromecast/Steam: launcher + secciones grandes.

Navegacion con teclado:
- Arriba/Abajo: cambia de seccion (canal)
- Izquierda/Derecha: cambia de video dentro de la seccion
- Enter: reproduce el video actual
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.workers import Worker
from infra import youtube_service
from ui.widgets import BigShelfWidget

APPS = [
    ("youtube", "▶", "YouTube"),
    ("netflix", "🎬", "Netflix"),
    ("twitch", "🎮", "Twitch"),
    ("files", "📁", "Archivos"),
]


class AppTile(QFrame):
    """Tile de app en el launcher."""

    def __init__(self, app_id: str, icono: str, nombre: str, disponible: bool):
        super().__init__()
        self.setObjectName("appTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        lbl_icono = QLabel(icono)
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icono.setObjectName("appIcon")
        layout.addWidget(lbl_icono)
        lbl_nombre = QLabel(nombre + ("" if disponible else " (pronto)"))
        lbl_nombre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_nombre)
        self.setEnabled(disponible)
        if not disponible:
            self.setProperty("disabled", True)


class HomeScreen(QWidget):
    video_activated = pyqtSignal(object, list)  # (Video, cola)

    def __init__(self, cfg: dict, pool, storage, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.pool = pool
        self.storage = storage
        # Auto-arranque del feed: solo la primera vez que cargan tendencias
        self._autostart_pendiente = cfg.get("feed", {}).get("autostart", True)

        self._shelves: list[BigShelfWidget] = []
        self._activo = 0

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # ---------- Launcher de apps ----------
        if cfg.get("home", {}).get("show_app_launcher", True):
            barra_apps = QWidget()
            barra_apps.setObjectName("appLauncher")
            fila = QHBoxLayout(barra_apps)
            fila.setContentsMargins(20, 14, 20, 10)
            fila.setSpacing(14)
            for app_id, icono, nombre in APPS:
                tile = AppTile(app_id, icono, nombre, disponible=(app_id == "youtube"))
                fila.addWidget(tile)
            fila.addStretch(1)
            raiz.addWidget(barra_apps)

        # ---------- Secciones ----------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        contenedor = QWidget()
        self.shelves_layout = QVBoxLayout(contenedor)
        self.shelves_layout.setContentsMargins(0, 0, 0, 10)
        self.shelves_layout.setSpacing(6)
        self.shelves_layout.addStretch(1)
        self.scroll.setWidget(contenedor)
        raiz.addWidget(self.scroll, 1)

        self._build_shelves()
        self._marcar_activo()

    # ------------------------------------------------------------------
    def _build_shelves(self) -> None:
        secciones = self.cfg.get("home", {}).get("sections", [])
        escala = self.cfg.get("ui", {}).get("big_thumb_scale", 0.6)
        titulos = {
            "tendencias": "🔥 Tendencias",
            "suscripciones": "📺 Suscripciones",
            "historial": "🕒 Historial",
            "favoritos": "⭐ Favoritos",
        }
        for seccion in secciones:
            shelf = BigShelfWidget(titulos.get(seccion, seccion), self.pool,
                                   self.storage, escala=escala)
            shelf.video_activated.connect(self.video_activated)
            shelf.setProperty("seccion", seccion)
            self._shelves.append(shelf)
            self.shelves_layout.insertWidget(self.shelves_layout.count() - 1, shelf)

    def refresh(self) -> None:
        self._cargar_tendencias()
        self._cargar_suscripciones()
        self._cargar_locales("historial")
        self._cargar_locales("favoritos")

    def _seccion_de(self, shelf: BigShelfWidget) -> str:
        return shelf.property("seccion") or ""

    # --------------------------- cargas en segundo plano
    def _cargar_tendencias(self) -> None:
        shelf = self._buscar_shelf("tendencias")
        if not shelf:
            return
        shelf.set_loading("Cargando tendencias...")
        w = Worker(youtube_service.fetch_trending, self.cfg)
        w.signals.finished.connect(lambda vids: self._on_tendencias(shelf, vids))
        w.signals.error.connect(lambda _e: shelf.set_error("No se pudieron cargar las tendencias"))
        self.pool.start(w)

    def _on_tendencias(self, shelf: BigShelfWidget, videos: list) -> None:
        shelf.set_videos(videos)
        # Feed automatico (estilo TV/TikTok): al abrir la app se reproduce
        # el primer video de tendencias sin intervencion del usuario.
        if self._autostart_pendiente and videos:
            self._autostart_pendiente = False
            self.video_activated.emit(videos[0], videos)

    def _cargar_suscripciones(self) -> None:
        shelf = self._buscar_shelf("suscripciones")
        if not shelf:
            return
        auth = self.cfg.get("youtube", {}).get("auth", {})
        if not auth.get("enabled"):
            shelf.set_message("Inicia sesion en ⚙ Ajustes para ver tus suscripciones")
            return
        shelf.set_loading("Cargando suscripciones...")
        w = Worker(youtube_service.fetch_subscriptions, self.cfg)
        w.signals.finished.connect(shelf.set_videos)
        w.signals.error.connect(lambda _e: shelf.set_error("Sin acceso: revisa el login de YouTube"))
        self.pool.start(w)

    def _cargar_locales(self, seccion: str) -> None:
        shelf = self._buscar_shelf(seccion)
        if not shelf:
            return
        if seccion == "historial":
            videos = self.storage.history.videos()
        else:
            videos = self.storage.favorites.videos()
        shelf.set_videos(videos)

    def _buscar_shelf(self, seccion: str) -> BigShelfWidget | None:
        for shelf in self._shelves:
            if self._seccion_de(shelf) == seccion:
                return shelf
        return None

    # --------------------------- navegacion con teclado
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._shelves:
            super().keyPressEvent(event)
            return
        tecla = event.key()
        if tecla == Qt.Key.Key_Down:
            self._cambiar_activo(1)
            event.accept()
        elif tecla == Qt.Key.Key_Up:
            self._cambiar_activo(-1)
            event.accept()
        elif tecla == Qt.Key.Key_Right:
            self._shelves[self._activo].siguiente()
            event.accept()
        elif tecla == Qt.Key.Key_Left:
            self._shelves[self._activo].anterior()
            event.accept()
        elif tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._shelves[self._activo].activate_current()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _cambiar_activo(self, delta: int) -> None:
        nuevo = max(0, min(len(self._shelves) - 1, self._activo + delta))
        if nuevo != self._activo:
            self._activo = nuevo
            self._marcar_activo()
            self.scroll.ensureWidgetVisible(self._shelves[self._activo])

    def _marcar_activo(self) -> None:
        for i, shelf in enumerate(self._shelves):
            shelf.set_active(i == self._activo)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Sin setFocus aqui: en Qt 6.12 offscreen provoca crash nativo al
        # arrancar workers de red durante el show. Las flechas las captura
        # el eventFilter global de MainWindow de todas formas.
        self.refresh()

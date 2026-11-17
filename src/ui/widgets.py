"""Widgets reutilizables: cards de video, filas (shelves), teclado virtual."""
from __future__ import annotations

import requests
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.workers import Worker
from domain.models import Video, format_duration

THUMB_ANCHO = 300
THUMB_ALTO = 169


class ThumbnailLoader(QObject):
    """Descarga miniaturas en hilos y las entrega a la UI."""

    loaded = pyqtSignal(str, bytes)  # (video_id, contenido imagen)

    def __init__(self, pool):
        super().__init__()
        self.pool = pool

    def cargar(self, video: Video) -> None:
        """Miniatura estandar (calidad media, para cards pequenas)."""
        if not video.thumbnail_url:
            return
        w = Worker(self._descargar, video.video_id, video.thumbnail_url)
        w.signals.finished.connect(self._entregar)
        self.pool.start(w)

    def cargar_grande(self, video: Video) -> None:
        """Miniatura de alta resolucion para el visor grande.
        Prueba maxresdefault (1280x720) y va bajando si no existe."""
        w = Worker(self._descargar_hd, video.video_id)
        w.signals.finished.connect(self._entregar)
        self.pool.start(w)

    @staticmethod
    def _descargar(video_id: str, url: str) -> tuple[str, bytes]:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return video_id, resp.content

    @staticmethod
    def _descargar_hd(video_id: str) -> tuple[str, bytes | None]:
        for nombre in ("maxresdefault", "sddefault", "hqdefault"):
            url = f"https://i.ytimg.com/vi/{video_id}/{nombre}.jpg"
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 2000:
                    return video_id, resp.content
            except requests.RequestException:
                continue
        return video_id, None

    def _entregar(self, datos: tuple[str, bytes]) -> None:
        video_id, contenido = datos
        if contenido is None:
            return
        self.loaded.emit(video_id, contenido)


class VideoCard(QFrame):
    """Tarjeta de video: miniatura + titulo + duracion + favorito."""

    activated = pyqtSignal(object)           # Video
    favorite_toggled = pyqtSignal(object)    # Video

    def __init__(self, video: Video, es_favorito: bool = False, parent=None):
        super().__init__(parent)
        self.video = video
        self.setObjectName("videoCard")
        self.setFixedSize(THUMB_ANCHO + 16, THUMB_ALTO + 110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Miniatura (placeholder hasta que llegue la imagen)
        self.thumb = QLabel(self._titulo_corto())
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(THUMB_ANCHO, THUMB_ALTO)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.thumb)

        # Fila: titulo + boton favorito
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.lbl_titulo = QLabel(video.title or "Sin titulo")
        self.lbl_titulo.setObjectName("cardTitle")
        self.lbl_titulo.setWordWrap(True)
        fila.addWidget(self.lbl_titulo, 1)

        self.btn_fav = QPushButton("★" if es_favorito else "☆")
        self.btn_fav.setObjectName("favButton")
        self.btn_fav.setFixedSize(44, 44)
        self.btn_fav.setToolTip("Favorito")
        self.btn_fav.clicked.connect(lambda _=False: self.favorite_toggled.emit(self.video))
        fila.addWidget(self.btn_fav)
        layout.addLayout(fila)

        # Canal + duracion
        meta = " · ".join(x for x in (video.channel, format_duration(video.duration)) if x)
        lbl_meta = QLabel(meta)
        lbl_meta.setObjectName("cardMeta")
        layout.addWidget(lbl_meta)

    def _titulo_corto(self) -> str:
        titulo = (self.video.title or "")[:40]
        return titulo + ("..." if len(self.video.title or "") > 40 else "")

    def set_favorite(self, es_favorito: bool) -> None:
        self.btn_fav.setText("★" if es_favorito else "☆")

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.thumb.setPixmap(
            pixmap.scaled(
                THUMB_ANCHO, THUMB_ALTO,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.video)
        super().mousePressEvent(event)


class ShelfWidget(QWidget):
    """Fila horizontal estilo 'shelf' de Google TV.

    Usa un QStackedWidget: pagina 0 = cards, pagina 1 = mensaje de estado.
    """

    video_activated = pyqtSignal(object, list)   # (video, lista_completa)

    def __init__(self, titulo: str, pool, storage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._cards: list[VideoCard] = []
        self.loader = ThumbnailLoader(pool)
        self.loader.loaded.connect(self._on_thumb_loaded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setObjectName("sectionTitle")
        layout.addWidget(self.lbl_titulo)

        self.paginas = QStackedWidget()

        # Pagina 0: fila de cards con scroll horizontal
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.contenido = QWidget()
        self.fila = QHBoxLayout(self.contenido)
        self.fila.setContentsMargins(0, 0, 0, 0)
        self.fila.setSpacing(14)
        self.scroll.setWidget(self.contenido)
        self.paginas.addWidget(self.scroll)

        # Pagina 1: mensaje de estado
        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("shelfStatus")
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.paginas.addWidget(self.lbl_estado)

        layout.addWidget(self.paginas)
        self._videos: list[Video] = []

    # ------------------------------------------------------------ estados
    def set_loading(self, texto: str = "Cargando...") -> None:
        self.lbl_estado.setText(texto)
        self.paginas.setCurrentIndex(1)

    def set_message(self, texto: str) -> None:
        self.lbl_estado.setText(texto)
        self.paginas.setCurrentIndex(1)

    def set_error(self, texto: str) -> None:
        self.set_message(f"⚠ {texto}")

    def set_videos(self, videos: list[Video]) -> None:
        self._limpiar()
        self._videos = list(videos)
        if not videos:
            self.set_message("Sin contenido")
            return
        for v in videos:
            card = VideoCard(v, self.storage.is_favorite(v.video_id))
            card.activated.connect(self._on_card_activated)
            card.favorite_toggled.connect(self._on_fav)
            self.fila.addWidget(card)
            self._cards.append(card)
            self.loader.cargar(v)
        self.paginas.setCurrentIndex(0)

    def refresh_favorites(self) -> None:
        for card in self._cards:
            card.set_favorite(self.storage.is_favorite(card.video.video_id))

    # ------------------------------------------------------------ internos
    def _limpiar(self) -> None:
        self._videos = []
        for card in self._cards:
            self.fila.removeWidget(card)
            card.deleteLater()
        self._cards = []

    def _on_card_activated(self, video: Video) -> None:
        self.video_activated.emit(video, self._videos)

    def _on_fav(self, video: Video) -> None:
        self.storage.toggle_favorite(video)
        self.refresh_favorites()

    def _on_thumb_loaded(self, video_id: str, contenido: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(contenido):
            return
        for card in self._cards:
            if card.video.video_id == video_id:
                card.set_pixmap(pixmap)
                break


class BigShelfWidget(QWidget):
    """Visor grande estilo Steam Big Picture: una miniatura por seccion,
    centrada y grande (~60% del ancho), con flechas para cambiar de video.

    Navegacion: botones de flecha, rueda del raton, o teclado (lo maneja
    HomeScreen con handle_key).
    """

    video_activated = pyqtSignal(object, list)  # (video, lista completa)

    def __init__(self, titulo: str, pool, storage, escala: float = 0.6,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("bigShelf")
        self.storage = storage
        self._escala = escala
        self._videos: list[Video] = []
        self._index = 0
        self._pixmap: QPixmap | None = None

        self.loader = ThumbnailLoader(pool)
        self.loader.loaded.connect(self._on_thumb)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 18)
        layout.setSpacing(10)

        # ---------- Cabecera: titulo de seccion + posicion ----------
        cabecera = QHBoxLayout()
        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setObjectName("sectionTitle")
        cabecera.addWidget(self.lbl_titulo)
        cabecera.addStretch(1)
        self.lbl_pos = QLabel("")
        self.lbl_pos.setObjectName("positionLabel")
        cabecera.addWidget(self.lbl_pos)
        layout.addLayout(cabecera)

        # ---------- Contenido / mensaje de estado ----------
        self.paginas = QStackedWidget()

        contenido = QWidget()
        centro = QVBoxLayout(contenido)
        centro.setContentsMargins(0, 0, 0, 0)
        centro.setSpacing(8)

        fila = QHBoxLayout()
        fila.setSpacing(12)
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setObjectName("navArrow")
        self.btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_prev.setFixedSize(90, 140)
        self.btn_prev.clicked.connect(self.anterior)
        fila.addWidget(self.btn_prev)

        self.thumb = QLabel("")
        self.thumb.setObjectName("bigThumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        fila.addWidget(self.thumb, 1)

        self.btn_next = QPushButton("▶")
        self.btn_next.setObjectName("navArrow")
        self.btn_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_next.setFixedSize(90, 140)
        self.btn_next.clicked.connect(self.siguiente)
        fila.addWidget(self.btn_next)
        centro.addLayout(fila, 1)

        self.lbl_video = QLabel("")
        self.lbl_video.setObjectName("bigTitle")
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setWordWrap(True)
        centro.addWidget(self.lbl_video)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setObjectName("bigMeta")
        self.lbl_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centro.addWidget(self.lbl_meta)

        self.paginas.addWidget(contenido)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("shelfStatus")
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_estado.setMinimumHeight(320)
        self.paginas.addWidget(self.lbl_estado)

        layout.addWidget(self.paginas)

    # ------------------------------------------------------------ API
    def set_loading(self, texto: str = "Cargando...") -> None:
        self.lbl_estado.setText(texto)
        self.paginas.setCurrentIndex(1)

    def set_message(self, texto: str) -> None:
        self.lbl_estado.setText(texto)
        self.paginas.setCurrentIndex(1)

    def set_error(self, texto: str) -> None:
        self.set_message(f"⚠ {texto}")

    def set_videos(self, videos: list[Video]) -> None:
        self._videos = list(videos)
        self._index = 0
        self._pixmap = None
        if not videos:
            self.set_message("Sin contenido")
            return
        self.paginas.setCurrentIndex(0)
        self._render()

    _CSS_ACTIVO = (
        "#bigShelf { border: 3px solid #e62117; border-radius: 16px;"
        " background-color: #181818; }"
    )

    def set_active(self, activo: bool) -> None:
        """Resalta la seccion activa (navegacion con flechas arriba/abajo).

        Se usa stylesheet inline en vez de propiedad dinamica +
        unpolish/polish: ese combo crashea con QSS en Qt 6.12.
        """
        self.setStyleSheet(self._CSS_ACTIVO if activo else "")

    def current_video(self) -> Video | None:
        if 0 <= self._index < len(self._videos):
            return self._videos[self._index]
        return None

    def siguiente(self) -> None:
        if self._index < len(self._videos) - 1:
            self._index += 1
            self._render()

    def anterior(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render()

    def activate_current(self) -> None:
        video = self.current_video()
        if video:
            self.video_activated.emit(video, self._videos)

    # ------------------------------------------------------------ internos
    def _render(self) -> None:
        video = self.current_video()
        if video is None:
            return
        self.lbl_pos.setText(f"{self._index + 1} / {len(self._videos)}")
        self.lbl_video.setText(video.title)
        meta = " · ".join(x for x in (video.channel, format_duration(video.duration)) if x)
        self.lbl_meta.setText(meta)
        self.btn_prev.setEnabled(self._index > 0)
        self.btn_next.setEnabled(self._index < len(self._videos) - 1)
        self.thumb.setText("Cargando miniatura...")
        # Miniatura rapida primero, HD despues (la HD pisa a la rapida)
        self.loader.cargar(video)
        self.loader.cargar_grande(video)

    def _render_pixmap(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        # Objetivo: 60% del ancho del widget (≈ pantalla), sin pasar
        # el area central entre las dos flechas
        ancho_centro = self.width() - 2 * 90 - 48
        ancho = min(int(self.width() * self._escala), ancho_centro)
        alto = int(ancho * 9 / 16)
        if ancho < 200:
            return
        self.thumb.setFixedSize(ancho, alto)
        self.thumb.setPixmap(
            self._pixmap.scaled(
                ancho, alto,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _on_thumb(self, video_id: str, contenido: bytes) -> None:
        video = self.current_video()
        if video is None or video.video_id != video_id:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(contenido):
            self._pixmap = pixmap
            self._render_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_pixmap()

    def wheelEvent(self, event) -> None:
        """Rueda del raton: cambia de video dentro de la seccion."""
        if not self._videos:
            event.ignore()
            return
        if event.angleDelta().y() < 0:
            self.siguiente()
        else:
            self.anterior()
        event.accept()

    def mousePressEvent(self, event) -> None:
        # Click en la zona de la miniatura reproduce el video actual
        pos = event.position().toPoint()
        if self.thumb.geometry().contains(pos):
            self.activate_current()
            event.accept()
            return
        super().mousePressEvent(event)


class VirtualKeyboard(QWidget):
    """Teclado en pantalla (respaldo tactil)."""

    key_pressed = pyqtSignal(str)

    FILAS = [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
        ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ñ"],
        ["z", "x", "c", "v", "b", "n", "m", "-", "'", "?"],
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mayus = False
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self._teclas: list[QPushButton] = []
        for fila_teclas in self.FILAS:
            fila = QHBoxLayout()
            fila.setSpacing(6)
            for tecla in fila_teclas:
                btn = QPushButton(tecla)
                btn.setProperty("vk", True)
                btn.clicked.connect(lambda _=False, t=tecla: self._emitir(t))
                fila.addWidget(btn)
                self._teclas.append(btn)
            layout.addLayout(fila)

        fila_ctrl = QHBoxLayout()
        fila_ctrl.setSpacing(6)
        for etiqueta, valor in (("⇧ Mayus", "MAYUS"), ("Espacio", " "),
                                ("Borrar", "BACK"), ("Enter", "ENTER"), ("Ocultar", "HIDE")):
            btn = QPushButton(etiqueta)
            btn.setProperty("vk", True)
            btn.clicked.connect(lambda _=False, v=valor: self._emitir(v))
            fila_ctrl.addWidget(btn)
        layout.addLayout(fila_ctrl)

    def _emitir(self, tecla: str) -> None:
        if tecla == "MAYUS":
            self._mayus = not self._mayus
            for btn in self._teclas:
                texto = btn.text()
                btn.setText(texto.upper() if self._mayus else texto.lower())
            return
        self.key_pressed.emit(tecla)

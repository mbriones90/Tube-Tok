"""Controladores de aplicacion: navegacion y reproduccion."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.feed_controller import FeedPreloader
from app.workers import Worker
from domain.models import Video
from infra import sponsorblock, youtube_service


class NavigationController(QObject):
    """Emite ordenes de navegacion entre pantallas."""

    navigate = pyqtSignal(str)  # "home" | "search" | "player" | "settings"

    def go(self, pantalla: str) -> None:
        self.navigate.emit(pantalla)


class PlaybackController(QObject):
    """Orquesta la reproduccion: stream -> VLC, SponsorBlock, autoplay, historial.

    La UI (PlayerScreen) expone una API simple que este controlador consume:
    load_stream(url, video), play(), pause(), seek_ms(ms), position_ms(),
    duration_ms(), set_volume(v).
    """

    stream_ready = pyqtSignal(object, str)     # (video, url)
    stream_error = pyqtSignal(str)
    show_message = pyqtSignal(str)

    def __init__(self, cfg: dict, threadpool, storage, navigation: NavigationController,
                 parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.pool = threadpool
        self.storage = storage
        self.navigation = navigation
        self.player = None          # se asigna con attach_player()

        self.current: Video | None = None
        self.queue: list[Video] = []
        self.queue_index = -1
        self._segments: list[tuple[float, float]] = []

        radio = cfg.get("feed", {}).get("preload_radius", 3)
        self.preloader = FeedPreloader(cfg, self.pool, radio, self)

        self._monitor = QTimer(self)
        self._monitor.setInterval(500)
        self._monitor.timeout.connect(self._check_sponsor_segments)

    # ------------------------------------------------------------- API UI
    def attach_player(self, player) -> None:
        """Conecta el PlayerScreen (API de reproduccion)."""
        self.player = player
        player.media_finished.connect(self._on_media_finished)

    def play_video(self, video: Video, queue: list[Video] | None = None) -> None:
        """Punto de entrada: usuario eligio un video."""
        self.current = video
        if queue:
            self.queue = queue
            try:
                self.queue_index = next(
                    i for i, v in enumerate(queue) if v.video_id == video.video_id
                )
            except StopIteration:
                self.queue_index = -1
        self.storage.history.add(video)
        self._segments = []
        self.navigation.go("player")
        if self.player:
            self.player.set_status(f"Cargando: {video.title}")

        # Precarga de los vecinos (estilo TikTok): mientras este video
        # arranca, se resuelven los streams de los siguientes/anteriores.
        if self.queue and self.queue_index >= 0:
            self.preloader.prime(self.queue, self.queue_index,
                                 skip_id=video.video_id)

        self._fetch_segments(video)
        self._resolve_stream(video)

    # ----------------------------------------------------- feed (TikTok)
    def feed_next(self) -> None:
        """Salta al siguiente video de la cola (flecha abajo)."""
        self._feed_goto(self.queue_index + 1)

    def feed_prev(self) -> None:
        """Salta al video anterior de la cola (flecha arriba)."""
        self._feed_goto(self.queue_index - 1)

    def _feed_goto(self, index: int) -> None:
        if not (0 <= index < len(self.queue)):
            return
        self.queue_index = index
        video = self.queue[index]
        self.current = video
        self.storage.history.add(video)
        self._segments = []
        if self.player:
            self.player.set_status(f"Cargando: {video.title}")

        # Precarga alrededor del nuevo centro
        self.preloader.prime(self.queue, index, skip_id=video.video_id)
        self._fetch_segments(video)
        self._resolve_stream(video)

    def _feed_available(self) -> bool:
        return len(self.queue) > 1

    # ------------------------------------------------------- tareas en hilo
    def _fetch_segments(self, video: Video) -> None:
        """Segmentos SponsorBlock en paralelo (no bloquea el inicio)."""
        pb = self.cfg.get("playback", {})
        if pb.get("sponsorblock", True):
            w = Worker(
                sponsorblock.fetch_segments,
                video.video_id,
                pb.get("sponsorblock_categories", ["sponsor", "selfpromo", "interaction"]),
            )
            w.signals.finished.connect(self._on_segments)
            self.pool.start(w)

    def _resolve_stream(self, video: Video) -> None:
        """Reproduce usando la cache del preloader si ya esta resuelto."""
        cacheado = self.preloader.get(video.video_id)
        if cacheado is not None:
            self._on_stream_info(video, cacheado)
            return
        w = Worker(youtube_service.get_stream_url, self.cfg, video.video_id)
        w.signals.finished.connect(lambda info: self._on_stream_info(video, info))
        w.signals.error.connect(self.stream_error)
        self.pool.start(w)

    def toggle_play(self) -> None:
        if self.player:
            self.player.toggle_play()

    def seek_request(self, fraccion: float) -> None:
        """fraccion: 0.0 - 1.0 sobre la duracion total."""
        if self.player:
            dur = self.player.duration_ms()
            if dur > 0:
                self.player.seek_ms(int(dur * fraccion))

    def seek_ms(self, ms: int) -> None:
        if self.player:
            self.player.seek_ms(ms)

    def set_volume(self, valor: int) -> None:
        if self.player:
            self.player.set_volume(valor)

    def stop(self) -> None:
        self._monitor.stop()
        if self.player:
            self.player.stop()

    # ----------------------------------------------------------- internos
    def _on_stream_info(self, video: Video, info: dict) -> None:
        url = info.get("url", "")
        if not url:
            self.stream_error.emit("No se pudo obtener el stream del video.")
            return
        if self.player:
            self.player.load_stream(url, video)
            self._monitor.start()
        self.stream_ready.emit(video, url)

    def _on_segments(self, segments: list) -> None:
        self._segments = segments or []

    def _check_sponsor_segments(self) -> None:
        if not self.player or not self._segments:
            return
        pos_s = self.player.position_ms() / 1000.0
        for inicio, fin in self._segments:
            if inicio <= pos_s < fin:
                self.player.seek_ms(int(fin * 1000) + 500)
                self.show_message.emit("Segmento patrocinado omitido")
                break

    def _on_media_finished(self) -> None:
        self._monitor.stop()
        if self.cfg.get("youtube", {}).get("autoplay_next", True) and self._has_next():
            self.play_video(self.queue[self.queue_index + 1], self.queue)
        else:
            self.navigation.go("home")

    def _has_next(self) -> bool:
        return 0 <= self.queue_index < len(self.queue) - 1

"""Pre-carga de streams estilo TikTok.

Resuelve las URLs de los videos vecinos al actual (hacia adelante y hacia
atras) en segundo plano, para que al cambiar de video con las flechas la
reproduccion empiece casi al instante: la extraccion con yt-dlp (lo lento,
1-3 s por video) ya esta hecha.

Toda la gestion de estado ocurre en el hilo de la UI (las senales de los
workers son entregadas por cola de Qt), asi que no hace falta locking.
"""
from __future__ import annotations

from collections import OrderedDict

from PyQt6.QtCore import QObject

from app.workers import Worker
from domain.models import Video
from infra import youtube_service

MAX_CACHE = 50  # entradas; se evictan las mas antiguas


class FeedPreloader(QObject):
    """Cache de streams resueltos alrededor del video en reproduccion."""

    def __init__(self, cfg: dict, pool, radius: int = 3, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.pool = pool
        self.radius = radius
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._pending: set[str] = set()

    # ------------------------------------------------------------ API
    def prime(self, videos: list[Video], center_index: int,
              skip_id: str | None = None) -> None:
        """Lanza la resolucion de streams para los videos vecinos."""
        if not videos:
            return
        desde = max(0, center_index - self.radius)
        hasta = min(len(videos), center_index + self.radius + 1)
        for i in range(desde, hasta):
            video = videos[i]
            if video.video_id != skip_id:
                self._ensure(video)

    def get(self, video_id: str) -> dict | None:
        """Stream ya resuelto, o None si aun no esta."""
        info = self._cache.get(video_id)
        if info is not None:
            self._cache.move_to_end(video_id)
        return info

    def clear(self) -> None:
        self._cache.clear()
        self._pending.clear()

    # ------------------------------------------------------------ internos
    def _ensure(self, video: Video) -> None:
        vid = video.video_id
        if vid in self._cache or vid in self._pending:
            return
        self._pending.add(vid)
        worker = Worker(youtube_service.get_stream_url, self.cfg, vid)
        worker.signals.finished.connect(
            lambda info, v=vid: self._on_ready(v, info))
        worker.signals.error.connect(lambda _e, v=vid: self._on_error(v))
        self.pool.start(worker)

    def _on_ready(self, video_id: str, info: dict) -> None:
        self._pending.discard(video_id)
        self._cache[video_id] = info
        self._cache.move_to_end(video_id)
        while len(self._cache) > MAX_CACHE:
            self._cache.popitem(last=False)

    def _on_error(self, video_id: str) -> None:
        # No resoluble (p. ej. video con verificacion anti-bot): se quita
        # de pendientes; si el usuario llega a el, se intentara de nuevo
        # y se mostrara el mensaje correspondiente.
        self._pending.discard(video_id)

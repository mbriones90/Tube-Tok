"""Pantalla de reproduccion con VLC incrustado en Qt."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    import vlc
    VLC_IMPORT_OK = True
except Exception:  # noqa: BLE001
    VLC_IMPORT_OK = False

from domain.models import Video, format_duration


class PlayerScreen(QWidget):
    """API de reproduccion consumida por PlaybackController."""

    close_requested = pyqtSignal()
    media_finished = pyqtSignal()
    media_error = pyqtSignal(str)
    feed_next = pyqtSignal()   # flecha abajo / rueda abajo: siguiente video
    feed_prev = pyqtSignal()   # flecha arriba / rueda arriba: video anterior

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.current: Video | None = None

        # ---------------- VLC ----------------
        self.vlc_ok = False
        self._player = None
        if VLC_IMPORT_OK:
            try:
                self._instance = vlc.Instance("--no-video-title-show", "--quiet")
                self._player = self._instance.media_player_new()
                events = self._player.event_manager()
                events.event_attach(
                    vlc.EventType.MediaPlayerEndReached, self._on_end_reached
                )
                events.event_attach(
                    vlc.EventType.MediaPlayerEncounteredError, self._on_vlc_error
                )
                self.vlc_ok = True
            except Exception:  # noqa: BLE001
                self.vlc_ok = False

        # ---------------- UI ----------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_frame = QFrame()
        self.video_frame.setObjectName("videoSurface")
        self.video_frame.setStyleSheet("background: black;")
        layout.addWidget(self.video_frame, 1)

        self.lbl_info = QLabel("VLC no disponible" if not self.vlc_ok else "Listo")
        self.lbl_info.setObjectName("playerInfo")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_info)

        # ---------- Controles ----------
        controles = QWidget()
        controles.setObjectName("playerControls")
        fila = QHBoxLayout(controles)
        fila.setContentsMargins(16, 10, 16, 14)
        fila.setSpacing(12)

        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("roundButton")
        self.btn_play.setFixedSize(64, 64)
        self.btn_play.clicked.connect(self.toggle_play)
        fila.addWidget(self.btn_play)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        fila.addWidget(self.slider, 1)

        self.lbl_tiempo = QLabel("0:00 / 0:00")
        self.lbl_tiempo.setObjectName("timeLabel")
        fila.addWidget(self.lbl_tiempo)

        fila.addWidget(QLabel("🔊"))
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(cfg.get("playback", {}).get("volume", 80))
        self.slider_vol.setFixedWidth(140)
        self.slider_vol.valueChanged.connect(self.set_volume)
        fila.addWidget(self.slider_vol)

        self.btn_cerrar = QPushButton("🏠 Inicio")
        self.btn_cerrar.setMinimumHeight(64)
        self.btn_cerrar.clicked.connect(self.close_requested)
        fila.addWidget(self.btn_cerrar)

        layout.addWidget(controles)

        # ---------- Timer de progreso ----------
        self._arrastrando = False
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._actualizar_progreso)

    # ---------------------------------------------------------- ciclo de vida
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Enlazar el video de VLC al handle nativo del frame (Windows)
        if self.vlc_ok and self._player:
            hwnd = int(self.video_frame.winId())
            if hwnd:
                if hasattr(self._player, "set_hwnd"):
                    self._player.set_hwnd(hwnd)
        self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    # ---------------------------------------------------------- API (controlador)
    def set_status(self, texto: str) -> None:
        self.lbl_info.setText(texto)

    def load_stream(self, url: str, video: Video) -> None:
        self.current = video
        self.lbl_info.setText(video.title)
        if not self.vlc_ok:
            self.media_error.emit("VLC no esta disponible en este equipo.")
            return
        media = self._instance.media_new(url)
        # Unificar a mono: mezcla los canales L/R en uno solo. Util cuando
        # el NUC va a un altavoz unico y el stereo suena irregular.
        if self.cfg.get("playback", {}).get("mono_audio", False):
            media.add_option(":audio-filter=mono")
        self._player.set_media(media)
        self._player.play()
        self.set_volume(self.slider_vol.value())

    def play(self) -> None:
        if self._player:
            self._player.play()

    def pause(self) -> None:
        if self._player:
            self._player.pause()

    def toggle_play(self) -> None:
        if not self._player:
            return
        estado = self._player.get_state()
        if estado == vlc.State.Playing:
            self._player.pause()
            self.btn_play.setText("▶")
        else:
            self._player.play()
            self.btn_play.setText("⏸")

    def stop(self) -> None:
        if self._player:
            self._player.stop()

    def seek_ms(self, ms: int) -> None:
        if self._player:
            self._player.set_time(ms)

    def position_ms(self) -> int:
        if self._player:
            return self._player.get_time()
        return 0

    def duration_ms(self) -> int:
        if self._player:
            return self._player.get_length()
        return 0

    def set_volume(self, valor: int) -> None:
        if self._player:
            self._player.audio_set_volume(valor)

    def shutdown(self) -> None:
        """Liberacion ordenada de VLC. Debe llamarse ANTES de destruir la
        app: si el timer de progreso o el monitor tocan VLC durante el
        teardown, Qt aborta (crash 0xC0000409 al salir)."""
        self._timer.stop()
        if self._player is not None:
            try:
                self._player.stop()
                self._player.release()
            except Exception:  # noqa: BLE001
                pass
            self._player = None

    # ---------------------------------------------------------- internos
    def _actualizar_progreso(self) -> None:
        if not self._player or self._arrastrando:
            return
        pos = self.position_ms()
        dur = self.duration_ms()
        if dur > 0:
            self.slider.blockSignals(True)
            self.slider.setValue(int(pos / dur * 1000))
            self.slider.blockSignals(False)
        self.lbl_tiempo.setText(f"{format_duration(pos / 1000)} / {format_duration(dur / 1000)}")
        estado = self._player.get_state()
        self.btn_play.setText("⏸" if estado == vlc.State.Playing else "▶")

    def _on_slider_pressed(self) -> None:
        self._arrastrando = True

    def _on_slider_released(self) -> None:
        self._arrastrando = False
        dur = self.duration_ms()
        if dur > 0:
            self.seek_ms(int(self.slider.value() / 1000 * dur))

    def keyPressEvent(self, event) -> None:
        tecla = event.key()
        if tecla == Qt.Key.Key_Escape:
            self.close_requested.emit()
            event.accept()
        elif tecla == Qt.Key.Key_Down:
            self.feed_next.emit()
            event.accept()
        elif tecla == Qt.Key.Key_Up:
            self.feed_prev.emit()
            event.accept()
        elif tecla == Qt.Key.Key_Right:
            self.seek_ms(self.position_ms() + 10000)
            event.accept()
        elif tecla == Qt.Key.Key_Left:
            self.seek_ms(max(0, self.position_ms() - 10000))
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        """Rueda del raton: navega el feed como en TikTok."""
        delta = event.angleDelta().y()
        if delta < 0:
            self.feed_next.emit()
        elif delta > 0:
            self.feed_prev.emit()
        event.accept()

    def _on_end_reached(self, _event) -> None:
        # VLC llama desde su hilo; pyqtSignal es thread-safe (cola)
        self.media_finished.emit()

    def _on_vlc_error(self, _event) -> None:
        self.media_error.emit("Error de reproduccion en VLC.")

"""Ventana principal: barra superior + QStackedWidget + F11 + ocultar cursor."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, QThreadPool, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.controllers import NavigationController, PlaybackController
from infra.storage import Storage
from ui.home_screen import HomeScreen
from ui.player_screen import PlayerScreen
from ui.search_screen import SearchScreen
from ui.settings_screen import SettingsScreen


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, settings_path, project_root, vlc_available: bool):
        super().__init__()
        self.cfg = cfg
        self.settings_path = settings_path
        self.project_root = project_root

        self.setWindowTitle(cfg.get("app", {}).get("name", "Cliente Multimedia"))

        # ---------------- Nucleo ----------------
        self.pool = QThreadPool(self)
        self.storage = Storage(cfg.get("storage", {}), project_root)
        self.navigation = NavigationController(self)
        self.navigation.navigate.connect(self._show_screen)
        self.playback = PlaybackController(cfg, self.pool, self.storage, self.navigation, self)

        # ---------------- UI ----------------
        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self._build_top_bar())

        self.stack = QStackedWidget()
        self.home = HomeScreen(cfg, self.pool, self.storage)
        self.search = SearchScreen(cfg, self.pool, self.storage)
        self.player = PlayerScreen(cfg)
        self.settings = SettingsScreen(cfg, settings_path, project_root)
        self.stack.addWidget(self.home)      # 0
        self.stack.addWidget(self.search)    # 1
        self.stack.addWidget(self.player)    # 2
        self.stack.addWidget(self.settings)  # 3
        raiz.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # ---------------- Conexiones ----------------
        self.home.video_activated.connect(self.play_video)
        self.search.video_activated.connect(self.play_video)

        self.playback.attach_player(self.player)
        self.playback.stream_ready.connect(self._on_stream_ready)
        self.playback.stream_error.connect(self._on_stream_error)
        self.playback.show_message.connect(self.statusBar().showMessage)

        self.player.close_requested.connect(lambda: self.navigation.go("home"))
        self.player.media_error.connect(self._on_stream_error)
        self.player.feed_next.connect(self.playback.feed_next)
        self.player.feed_prev.connect(self.playback.feed_prev)
        self.settings.settings_saved.connect(self._on_settings_saved)

        # ---------------- Ocultar cursor (solo mouse) ----------------
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        segundos = cfg.get("ui", {}).get("hide_cursor_seconds", 5)
        self._cursor_timer.setInterval(max(segundos, 1) * 1000)
        self._cursor_timer.timeout.connect(self._ocultar_cursor)
        self._reiniciar_cursor_timer()

        if not vlc_available:
            QMessageBox.warning(
                self,
                "VLC no encontrado",
                "No se encontro VLC instalado.\n\n"
                "La interfaz funcionara, pero no podra reproducir videos.\n"
                "Vuelve a ejecutar launch.bat para instalarlo silenciosamente.",
            )

        # ---------------- Navegacion global con flechas ----------------
        # El eventFilter de la app entrega flechas/enter al Home aunque
        # otro widget (boton, scroll) tenga el foco.
        self._teclas_nav = {Qt.Key.Key_Up, Qt.Key.Key_Down,
                            Qt.Key.Key_Left, Qt.Key.Key_Right,
                            Qt.Key.Key_Return, Qt.Key.Key_Enter}
        self._teclas_player = {Qt.Key.Key_Up, Qt.Key.Key_Down,
                               Qt.Key.Key_Left, Qt.Key.Key_Right,
                               Qt.Key.Key_Escape}
        QApplication.instance().installEventFilter(self)

    # ------------------------------------------------------------- top bar
    def _build_top_bar(self) -> QWidget:
        barra = QWidget()
        barra.setObjectName("topBar")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(16, 10, 16, 10)
        fila.setSpacing(10)

        titulo = QLabel("🏠 " + self.cfg.get("app", {}).get("name", "Cliente Multimedia"))
        titulo.setObjectName("topTitle")
        fila.addWidget(titulo)

        btn_home = QPushButton("🏠 Inicio")
        btn_home.setObjectName("topButton")
        btn_home.clicked.connect(lambda: self.navigation.go("home"))
        fila.addWidget(btn_home)

        self.lbl_login = QLabel("")
        self.lbl_login.setObjectName("loginStatus")
        self.lbl_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_login.setToolTip("Estado de la sesion de YouTube. "
                                  "Click para ir a Ajustes.")
        self.lbl_login.mousePressEvent = (
            lambda _e: self.navigation.go("settings"))
        fila.addWidget(self.lbl_login)
        self._actualizar_indicador_login()

        fila.addStretch(1)

        for texto, slot in (
            ("🔍 Buscar", lambda: self.navigation.go("search")),
            ("⚙ Ajustes", lambda: self.navigation.go("settings")),
        ):
            btn = QPushButton(texto)
            btn.setObjectName("topButton")
            btn.clicked.connect(slot)
            fila.addWidget(btn)

        self.btn_pantalla = QPushButton("⛶")
        self.btn_pantalla.setObjectName("topButton")
        self.btn_pantalla.setFixedSize(52, 52)
        self.btn_pantalla.clicked.connect(self.alternar_pantalla_completa)
        fila.addWidget(self.btn_pantalla)

        btn_salir = QPushButton("✕")
        btn_salir.setObjectName("topButton")
        btn_salir.setFixedSize(52, 52)
        btn_salir.clicked.connect(self.close)
        fila.addWidget(btn_salir)

        return barra

    # ------------------------------------------------------------- navegacion
    PANTALLAS = {"home": 0, "search": 1, "player": 2, "settings": 3}

    def _show_screen(self, nombre: str) -> None:
        indice = self.PANTALLAS.get(nombre, 0)
        saliendo_de_player = self.stack.currentIndex() == self.PANTALLAS["player"]
        if saliendo_de_player and indice != self.PANTALLAS["player"]:
            self.playback.stop()
        self.stack.setCurrentIndex(indice)
        self._reiniciar_cursor_timer()

    def play_video(self, video, queue=None) -> None:
        self.playback.play_video(video, queue)

    def _on_stream_ready(self, video, url) -> None:
        self.navigation.go("player")

    def _on_stream_error(self, mensaje: str) -> None:
        self.playback.stop()
        self.navigation.go("home")
        QMessageBox.warning(self, "Reproduccion", mensaje)

    def _on_settings_saved(self, cfg: dict) -> None:
        self.cfg = cfg
        self.playback.cfg = cfg
        self._actualizar_indicador_login()

    def _actualizar_indicador_login(self) -> None:
        """Indicador visible de si YouTube tiene sesion activa."""
        auth = self.cfg.get("youtube", {}).get("auth", {})
        if auth.get("enabled"):
            navegador = auth.get("browser", "edge").capitalize()
            self.lbl_login.setText(f"🟢 YouTube · {navegador}")
            self.lbl_login.setStyleSheet(
                "color: #4caf50; font-size: 18px; padding: 0 14px;")
        else:
            self.lbl_login.setText("🔴 Sin sesión")
            self.lbl_login.setStyleSheet(
                "color: #ef5350; font-size: 18px; padding: 0 14px;")

    # ------------------------------------------------------------- pantalla completa
    def alternar_pantalla_completa(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            if self.cfg.get("app", {}).get("start_maximized", True):
                self.showMaximized()
        else:
            self.showFullScreen()

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)
        actual = self.stack.currentWidget()
        if actual is self.home and event.key() in self._teclas_nav:
            self.home.keyPressEvent(event)
            return event.isAccepted()
        if actual is self.player and event.key() in self._teclas_player:
            self.player.keyPressEvent(event)
            return event.isAccepted()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        tecla = event.key()
        if tecla == Qt.Key.Key_F11:
            self.alternar_pantalla_completa()
        elif tecla == Qt.Key.Key_Escape and self.isFullScreen():
            self.alternar_pantalla_completa()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------- cursor
    def _ocultar_cursor(self) -> None:
        self.setCursor(Qt.CursorShape.BlankCursor)

    def _reiniciar_cursor_timer(self) -> None:
        self.unsetCursor()
        self._cursor_timer.start()

    # ------------------------------------------------------------- eventos
    def mouseMoveEvent(self, event) -> None:
        self._reiniciar_cursor_timer()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._reiniciar_cursor_timer()
        super().mousePressEvent(event)

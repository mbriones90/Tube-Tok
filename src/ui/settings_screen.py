"""Pantalla de ajustes."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from infra import autostart


class SettingsScreen(QWidget):
    settings_saved = pyqtSignal(dict)  # cfg actualizado

    def __init__(self, cfg: dict, settings_path: Path, project_root: Path, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.settings_path = settings_path
        self.project_root = project_root

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        titulo = QLabel("⚙ Ajustes")
        titulo.setObjectName("pageTitle")
        layout.addWidget(titulo)

        # ---------- YouTube ----------
        self.chk_login = QCheckBox("Iniciar sesion en YouTube (cookies del navegador)")
        self.chk_login.setChecked(cfg.get("youtube", {}).get("auth", {}).get("enabled", False))
        layout.addWidget(self.chk_login)

        fila_nav = QHBoxLayout()
        fila_nav.addSpacing(30)
        lbl_nav = QLabel("Navegador:")
        fila_nav.addWidget(lbl_nav)
        self.combo_nav = QComboBox()
        self.combo_nav.addItems(["edge", "chrome", "firefox"])
        nav_actual = cfg.get("youtube", {}).get("auth", {}).get("browser", "edge")
        self.combo_nav.setCurrentText(nav_actual)
        fila_nav.addWidget(self.combo_nav)
        fila_nav.addStretch(1)
        layout.addLayout(fila_nav)

        nota = QLabel(
            "Debes tener la sesion iniciada en ese navegador del NUC.\n"
            "Esto habilita: suscripciones, videos restringidos y contenido de miembros."
        )
        nota.setObjectName("settingsNote")
        layout.addWidget(nota)

        self.lbl_test = QLabel("Estado: sin comprobar")
        self.lbl_test.setObjectName("settingsNote")
        layout.addWidget(self.lbl_test)

        self.btn_test = QPushButton("🔑 Probar sesión")
        self.btn_test.setMinimumHeight(56)
        self.btn_test.clicked.connect(self._probar_sesion)
        layout.addWidget(self.btn_test)

        # ---------- Reproduccion ----------
        self.chk_autoplay = QCheckBox("Reproducir siguiente video automaticamente")
        self.chk_autoplay.setChecked(cfg.get("youtube", {}).get("autoplay_next", True))
        layout.addWidget(self.chk_autoplay)

        self.chk_sponsor = QCheckBox("Omitir segmentos patrocinados (SponsorBlock)")
        self.chk_sponsor.setChecked(cfg.get("playback", {}).get("sponsorblock", True))
        layout.addWidget(self.chk_sponsor)

        self.chk_mono = QCheckBox("Unificar audio a mono (altavoz único / sonido irregular)")
        self.chk_mono.setChecked(cfg.get("playback", {}).get("mono_audio", False))
        layout.addWidget(self.chk_mono)

        self.chk_fullscreen = QCheckBox("Iniciar en pantalla completa (F11 para alternar)")
        self.chk_fullscreen.setChecked(cfg.get("app", {}).get("start_fullscreen", False))
        layout.addWidget(self.chk_fullscreen)

        # ---------- Entrada ----------
        self.chk_vk = QCheckBox("Mostrar teclado virtual en pantalla (respaldo tactil)")
        self.chk_vk.setChecked(cfg.get("input", {}).get("virtual_keyboard", False))
        layout.addWidget(self.chk_vk)

        # ---------- Sistema ----------
        self.chk_autostart = QCheckBox("Iniciar Cliente Multimedia al arrancar Windows")
        self.chk_autostart.setChecked(autostart.is_enabled())
        layout.addWidget(self.chk_autostart)

        layout.addStretch(1)

        # ---------- Botones ----------
        fila_btn = QHBoxLayout()
        fila_btn.addStretch(1)
        self.btn_guardar = QPushButton("💾 Guardar")
        self.btn_guardar.setMinimumHeight(64)
        self.btn_guardar.clicked.connect(self._guardar)
        fila_btn.addWidget(self.btn_guardar)
        layout.addLayout(fila_btn)

    def _probar_sesion(self) -> None:
        """Comprueba de verdad que las cookies del navegador funcionan."""
        auth = self.cfg.get("youtube", {}).get("auth", {})
        if not auth.get("enabled"):
            self.lbl_test.setText("Estado: el login esta desactivado. "
                                  "Activa el checkbox y guarda primero.")
            return
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Comprobando... cierra el navegador si esta abierto")
        self.lbl_test.setText("Estado: comprobando (leyendo cookies del navegador)...")
        from PyQt6.QtCore import QThreadPool

        from app.workers import Worker
        from infra import youtube_service

        w = Worker(youtube_service.fetch_subscriptions, self.cfg)
        w.signals.finished.connect(self._test_ok)
        w.signals.error.connect(self._test_error)
        QThreadPool.globalInstance().start(w)

    def _test_ok(self, videos: list) -> None:
        self.btn_test.setEnabled(True)
        self.btn_test.setText("🔑 Probar sesión")
        if videos:
            self.lbl_test.setText(
                f"Estado: ✅ SESION VALIDA - {len(videos)} videos de "
                f"tus suscripciones cargados")
        else:
            self.lbl_test.setText(
                "Estado: ⚠ Sesion leida pero 0 videos (cuenta sin suscripciones "
                "o sin actividad reciente)")

    def _test_error(self, mensaje: str) -> None:
        self.btn_test.setEnabled(True)
        self.btn_test.setText("🔑 Probar sesión")
        self.lbl_test.setText(f"Estado: ❌ FALLO - {mensaje[:160]}")

    def _guardar(self) -> None:
        cfg = self.cfg
        cfg["youtube"]["auth"]["enabled"] = self.chk_login.isChecked()
        cfg["youtube"]["auth"]["browser"] = self.combo_nav.currentText()
        cfg["youtube"]["autoplay_next"] = self.chk_autoplay.isChecked()
        cfg["playback"]["sponsorblock"] = self.chk_sponsor.isChecked()
        cfg["playback"]["mono_audio"] = self.chk_mono.isChecked()
        cfg["app"]["start_fullscreen"] = self.chk_fullscreen.isChecked()
        cfg["input"]["virtual_keyboard"] = self.chk_vk.isChecked()

        # Inicio automatico con Windows (aplica inmediatamente)
        try:
            if self.chk_autostart.isChecked():
                autostart.enable(self.project_root / "launch.bat")
            else:
                autostart.disable()
            cfg["autostart"]["enabled"] = self.chk_autostart.isChecked()
        except OSError as exc:
            QMessageBox.warning(self, "Inicio automatico", f"No se pudo configurar: {exc}")

        from infra.settings import save_settings
        save_settings(self.settings_path, cfg)
        self.settings_saved.emit(cfg)
        QMessageBox.information(self, "Ajustes", "Configuracion guardada.")

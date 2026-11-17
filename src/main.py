"""Entry point del Cliente Multimedia.

Flujo: preparar VLC -> QApplication -> MainWindow -> exec.
Se ejecuta con: uv run python src/main.py  (o via launch.bat)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

# El directorio del proyecto es el padre de src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from infra import vlc_setup  # noqa: E402  (antes de importar vlc)
from infra.settings import load_settings  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    settings_path = PROJECT_ROOT / "config" / "settings.toml"
    cfg = load_settings(settings_path)

    # VLC debe estar en el PATH de DLLs antes de que player_screen importe vlc
    vlc_dir = vlc_setup.ensure_vlc_on_path(cfg.get("vlc", {}).get("install_path", ""))

    app = QApplication(sys.argv)
    app.setApplicationName(cfg.get("app", {}).get("name", "Cliente Multimedia"))

    qss_path = Path(__file__).resolve().parent / "ui" / "styles.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    window = MainWindow(cfg, settings_path, PROJECT_ROOT, vlc_available=vlc_dir is not None)

    if cfg.get("app", {}).get("start_fullscreen", False):
        window.showFullScreen()
    elif cfg.get("app", {}).get("start_maximized", True):
        window.showMaximized()
    else:
        window.show()

    codigo = app.exec()

    # Apagado ordenado: el monitor de SponsorBlock y el timer de progreso
    # deben detenerse antes de tocar VLC, o el teardown de Qt crashea.
    window.playback.stop()
    window.pool.clear()
    window.pool.waitForDone(2000)
    window.player.shutdown()

    return codigo


if __name__ == "__main__":
    sys.exit(main())

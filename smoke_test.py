"""Prueba de humo: arranca la app offscreen, espera 6 segundos y sale.

Valida imports, creacion de MainWindow y pantallas sin necesitar monitor.
No reproduce video ni llama a YouTube (los shelves fallaran con red, es esperado).
"""
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(errors="replace")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# En offscreen los dialogs modales bloquean para siempre: se desactivan
QMessageBox.warning = lambda *a, **k: None
QMessageBox.information = lambda *a, **k: None

from infra import vlc_setup  # noqa: E402
from infra.settings import load_settings  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> int:
    cfg = load_settings(PROJECT_ROOT / "config" / "settings.toml")
    vlc_dir = vlc_setup.ensure_vlc_on_path(cfg.get("vlc", {}).get("install_path", ""))
    print(f"[smoke] VLC disponible: {vlc_dir is not None}", flush=True)

    app = QApplication(sys.argv)
    window = MainWindow(cfg, PROJECT_ROOT / "config" / "settings.toml",
                        PROJECT_ROOT, vlc_available=vlc_dir is not None)
    window.resize(1600, 900)
    window.show()
    print("[smoke] MainWindow creada y visible", flush=True)

    # Recorrer todas las pantallas del stack (sin showEvent de Home: no red)
    for nombre, indice in window.PANTALLAS.items():
        if nombre == "home":
            continue  # Home dispara workers de red en showEvent; se omite aqui
        window.stack.setCurrentIndex(indice)
        app.processEvents()
        print(f"[smoke] Pantalla '{nombre}' OK", flush=True)

    # Verificar componentes clave sin tocar la red
    assert window.playback is not None
    assert window.player is not None
    assert window.storage is not None
    print("[smoke] Controladores y storage presentes", flush=True)

    # Verificar shelves del home y navegacion por teclado
    assert len(window.home._shelves) == 4, f"shelves: {len(window.home._shelves)}"
    shelf = window.home._shelves[0]
    from domain.models import Video
    shelf.set_videos([
        Video(video_id=f"id{i}", title=f"Video {i}", duration=100 + i)
        for i in range(5)
    ])
    shelf.siguiente()
    assert shelf.current_video().video_id == "id1"
    shelf.anterior()
    assert shelf.current_video().video_id == "id0"
    window.home._cambiar_activo(1)
    assert window.home._activo == 1
    print("[smoke] Navegacion shelves OK", flush=True)

    # ---------------- Feed (pre-carga estilo TikTok) ----------------
    from app.feed_controller import FeedPreloader  # noqa: F401
    pre = window.playback.preloader
    pre._on_ready("vid_cache", {"url": "http://x", "title": "t", "duration": 10})
    assert pre.get("vid_cache") is not None
    print("[smoke] Preloader cache OK", flush=True)

    # feed_next/feed_prev con streams ya cacheados (sin red)
    queue = [Video(video_id=f"q{i}", title=f"Q{i}", duration=60) for i in range(5)]
    for v in queue:
        pre._on_ready(v.video_id, {"url": f"http://u/{v.video_id}",
                                   "title": v.title, "duration": 60})
    window.playback.play_video(queue[2], queue)
    app.processEvents()
    assert window.playback.queue_index == 2
    window.playback.feed_next()
    assert window.playback.queue_index == 3
    assert window.playback.current.video_id == "q3"
    window.playback.feed_prev()
    window.playback.feed_prev()
    assert window.playback.queue_index == 1
    window.playback._feed_goto(0)
    window.playback.feed_prev()
    assert window.playback.queue_index == 0
    window.playback._feed_goto(4)
    window.playback.feed_next()
    assert window.playback.queue_index == 4
    print("[smoke] Navegacion feed OK", flush=True)

    # Indicador de sesion: refleja la config de login
    window._actualizar_indicador_login()
    texto = window.lbl_login.text()
    assert "🟢" in texto or "🔴" in texto, f"indicador: {texto}"
    print(f"[smoke] Indicador sesion OK: {texto}", flush=True)

    QTimer.singleShot(3000, app.quit)
    codigo = app.exec()

    # Apagado ordenado (evita crash de Qt en teardown)
    window.playback.stop()
    window.pool.clear()
    window.pool.waitForDone(2000)
    window.player.shutdown()

    print("[smoke] App finalizada limpiamente", flush=True)
    return codigo


if __name__ == "__main__":
    sys.exit(main())

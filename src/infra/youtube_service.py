"""Acceso a YouTube via yt-dlp (sin API key).

Todas las funciones son bloqueantes: deben llamarse desde un hilo Worker,
nunca desde el hilo de la UI.

Politica de cookies:
- Busqueda/tendencias: SIN cookies (funcionan sin login; el navegador
  abierto bloquea la base de datos de cookies y romperia estas llamadas).
- Stream/suscripciones: CON cookies si el login esta activo. Si el navegador
  esta abierto (cookie DB bloqueada) se reintenta sin cookies y se informa
  al usuario con un mensaje claro.
"""
from __future__ import annotations

import yt_dlp

from domain.models import Video


class StreamAuthRequired(Exception):
    """YouTube exige verificacion (anti-bot): se necesita login con cookies."""


class BrowserLockedError(Exception):
    """El navegador esta abierto y bloquea la lectura de sus cookies."""


class _SilentLogger:
    """Silencia la salida de yt-dlp; los errores llegan como excepciones."""

    def debug(self, _msg):
        pass

    def warning(self, _msg):
        pass

    def error(self, _msg):
        pass


BASE_OPTS: dict = {
    "quiet": True,
    "no_warnings": True,
    "logger": _SilentLogger(),
    "socket_timeout": 20,
    "retries": 2,
    "nocheckcertificate": True,
}


# --------------------------------------------------------------------- utils
def _ydl_opts(flat: bool = True, browser: str | None = None) -> dict:
    opts = dict(BASE_OPTS)
    opts["extract_flat"] = flat
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def _pick_thumbnail(entry: dict) -> str:
    thumbs = entry.get("thumbnails")
    if thumbs:
        return thumbs[-1].get("url", "")
    return entry.get("thumbnail") or ""


def _flatten(entries) -> list[dict]:
    """Las feeds de YouTube mezclan videos, canales y tabs: se aplanan."""
    salida: list[dict] = []
    for e in entries or []:
        if not e:
            continue
        if e.get("entries"):
            salida.extend(_flatten(e["entries"]))
        elif e.get("id") and e.get("title"):
            salida.append(e)
    return salida


def _to_video(e: dict) -> Video:
    url = e.get("url") or e.get("webpage_url") or ""
    if url and url.startswith("/"):
        url = "https://www.youtube.com" + url
    return Video(
        video_id=str(e.get("id")),
        title=e.get("title", "Sin titulo"),
        thumbnail_url=_pick_thumbnail(e),
        duration=e.get("duration"),
        channel=e.get("channel") or e.get("uploader") or "",
        webpage_url=url,
    )


def _dedupe(videos: list[Video], limite: int) -> list[Video]:
    vistos: set[str] = set()
    unicos: list[Video] = []
    for v in videos:
        if v.video_id and v.video_id not in vistos:
            vistos.add(v.video_id)
            unicos.append(v)
    return unicos[:limite]


def _es_error_cookies(mensaje: str) -> bool:
    m = mensaje.lower()
    return "could not copy" in m or "failed to load cookies" in m


def _browser_nombre(browser: str) -> str:
    return {"edge": "Edge", "chrome": "Chrome", "firefox": "Firefox"}.get(browser, browser)


# ------------------------------------------------------- tendencias/busqueda
# Fallback cuando el feed oficial exige login: busqueda generica popular.
_QUERIES_POPULARES = {
    "es": "lo mas visto hoy",
    "en": "trending today",
}


def fetch_trending(cfg: dict) -> list[Video]:
    yt = cfg.get("youtube", {})
    max_resultados = yt.get("max_results", 20)
    region = yt.get("default_region", "ES")
    idioma = yt.get("default_language", "es")

    # 1) Feed oficial (solo funciona con login; sin el, YouTube redirige a home)
    url = f"https://www.youtube.com/feed/trending?gl={region}&hl={idioma}"
    try:
        with yt_dlp.YoutubeDL(_ydl_opts(flat=True)) as ydl:
            info = ydl.extract_info(url, download=False)
        videos = _dedupe([_to_video(e) for e in _flatten(info.get("entries"))],
                         max_resultados)
        if videos:
            return videos
    except yt_dlp.utils.DownloadError:
        pass  # Sin sesion YouTube redirige a home: se usa el fallback

    # 2) Fallback: busqueda generica (la fila nunca queda vacia)
    query = _QUERIES_POPULARES.get(idioma, _QUERIES_POPULARES["en"])
    return search_videos(cfg, query)


def search_videos(cfg: dict, query: str) -> list[Video]:
    max_resultados = cfg.get("youtube", {}).get("max_results", 20)
    with yt_dlp.YoutubeDL(_ydl_opts(flat=True)) as ydl:
        info = ydl.extract_info(f"ytsearch{max_resultados}:{query}", download=False)
    return _dedupe([_to_video(e) for e in _flatten(info.get("entries"))],
                   max_resultados)


# ------------------------------------------------------------ con auth (opc)
def _auth_browser(cfg: dict) -> str | None:
    auth = cfg.get("youtube", {}).get("auth", {})
    if auth.get("enabled"):
        return auth.get("browser", "edge")
    return None


def fetch_subscriptions(cfg: dict) -> list[Video]:
    """Feed de suscripciones. Requiere login activo (cookies del navegador)."""
    browser = _auth_browser(cfg)
    if not browser:
        raise StreamAuthRequired(
            "Las suscripciones requieren iniciar sesion.\n"
            "Activa 'Iniciar sesion en YouTube' en ⚙ Ajustes."
        )
    max_resultados = cfg.get("youtube", {}).get("max_results", 20)
    try:
        with yt_dlp.YoutubeDL(_ydl_opts(flat=True, browser=browser)) as ydl:
            info = ydl.extract_info(
                "https://www.youtube.com/feed/subscriptions", download=False
            )
    except yt_dlp.utils.DownloadError as exc:
        if _es_error_cookies(str(exc)):
            raise BrowserLockedError(
                f"{_browser_nombre(browser)} esta abierto y bloquea sus cookies.\n\n"
                f"Cierra completamente {_browser_nombre(browser)} (todas las ventanas) "
                "y vuelve a entrar a Inicio."
            ) from exc
        raise
    return _dedupe([_to_video(e) for e in _flatten(info.get("entries"))],
                   max_resultados)


# ------------------------------------------------------------------- streams
def _extract_stream(video_id: str, browser: str | None,
                    player_client: str | None = None) -> dict:
    opts = _ydl_opts(flat=False, browser=browser)
    opts["format"] = "best"
    opts["noplaylist"] = True
    if player_client:
        # Cliente alternativo: evita la verificacion anti-bot de YouTube
        opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=False
        )
    return info


def _es_error_bot(mensaje: str) -> bool:
    m = mensaje.lower()
    return "sign in to confirm" in m or "not a bot" in m


def _intentar_stream(video_id: str, browser: str | None) -> dict:
    """Estrategia en cascada para obtener el stream:
    1. Con cookies (si hay login y el navegador esta cerrado).
    2. Sin cookies, cliente normal.
    3. Cliente 'android': evita el chequeo anti-bot y siempre entrega un
       stream progresivo (audio+video en una sola URL, ideal para VLC),
       donde el cliente normal puede fallar por formato no disponible.
    """
    if browser:
        try:
            return _extract_stream(video_id, browser)
        except yt_dlp.utils.DownloadError as exc:
            if not _es_error_cookies(str(exc)):
                raise

    try:
        return _extract_stream(video_id, None)
    except yt_dlp.utils.DownloadError as exc_normal:
        try:
            return _extract_stream(video_id, None, player_client="android")
        except yt_dlp.utils.DownloadError:
            raise _clasificar_error(exc_normal, browser) from exc_normal


def _clasificar_error(exc: Exception, browser: str | None) -> Exception:
    mensaje = str(exc)
    if _es_error_cookies(mensaje):
        nombre = _browser_nombre(browser) if browser else "el navegador"
        return BrowserLockedError(
            f"{nombre} esta abierto y no se pudieron leer sus cookies.\n\n"
            f"Cierra completamente {nombre} (todas las ventanas) y vuelve a "
            "intentar reproducir."
        )
    if "sign in to confirm" in mensaje.lower() or "not a bot" in mensaje.lower():
        return StreamAuthRequired(
            "YouTube pide verificacion de que no eres un bot.\n\n"
            "Solucion:\n"
            "1. ⚙ Ajustes → activa 'Iniciar sesion en YouTube'.\n"
            "2. Inicia sesion en YouTube en ese navegador del NUC.\n"
            "3. Cierra completamente el navegador (si esta abierto no se\n"
            "   pueden leer sus cookies) y reproduce de nuevo."
        )
    return exc


def get_stream_url(cfg: dict, video_id: str) -> dict:
    """Obtiene la URL directa del stream para VLC (sin anuncios de plataforma).

    Raises:
        StreamAuthRequired: YouTube pide verificacion y no hay login util.
        BrowserLockedError: el navegador con la sesion esta abierto.
    """
    browser = _auth_browser(cfg)
    try:
        info = _intentar_stream(video_id, browser)
    except yt_dlp.utils.DownloadError as exc:
        raise _clasificar_error(exc, browser) from exc

    url = info.get("url") or ""
    if not url:
        raise StreamAuthRequired(
            "YouTube no entrego el stream del video.\n"
            "Prueba activando el login en ⚙ Ajustes."
        )
    return {
        "url": url,
        "title": info.get("title", ""),
        "duration": info.get("duration"),
    }

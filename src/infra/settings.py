"""Carga y guardado de la configuracion (config/settings.toml)."""
from __future__ import annotations

import copy
from pathlib import Path

import toml

# Valores por defecto: deben coincidir con config/settings.toml
DEFAULTS: dict = {
    "app": {
        "name": "Cliente Multimedia",
        "version": "0.1.0",
        "language": "es",
        "start_fullscreen": False,
        "start_maximized": True,
    },
    "home": {
        "show_app_launcher": True,
        "selected_app": "youtube",
        "sections": ["tendencias", "suscripciones", "historial", "favoritos"],
    },
    "ui": {
        "theme": "dark",
        "font_size": 24,
        "button_min_height": 80,
        "big_thumb_scale": 0.6,
        "show_titles": True,
        "hide_cursor_seconds": 5,
    },
    "input": {
        "primary": "mouse",
        "virtual_keyboard": False,
        "support_touch": True,
    },
    "youtube": {
        "mode": "stream",
        "autoplay_next": True,
        "max_results": 20,
        "default_region": "ES",
        "default_language": "es",
        "auth": {
            "enabled": False,
            "browser": "edge",
        },
    },
    "feed": {
        "autostart": True,
        "preload_radius": 3,
    },
    "playback": {
        "engine": "vlc",
        "volume": 80,
        "sponsorblock": True,
        "sponsorblock_categories": ["sponsor", "selfpromo", "interaction"],
        "skip_youtube_ads": True,
        "mono_audio": False,
    },
    "vlc": {
        "install_path": "",
    },
    "autostart": {
        "enabled": False,
        "mode": "startup_folder",
    },
    "storage": {
        "cache_dir": "./cache",
        "history_file": "./data/history.json",
        "favorites_file": "./data/favorites.json",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    for clave, valor in override.items():
        if isinstance(valor, dict) and isinstance(base.get(clave), dict):
            _deep_merge(base[clave], valor)
        else:
            base[clave] = valor
    return base


def load_settings(path: Path) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    try:
        user = toml.load(path)
    except (OSError, toml.TomlDecodeError):
        user = {}
    return _deep_merge(cfg, user)


def save_settings(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        toml.dump(cfg, f)

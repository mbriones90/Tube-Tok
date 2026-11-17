"""Inicio automatico con Windows via carpeta Startup (acceso directo .bat)."""
from __future__ import annotations

import os
from pathlib import Path

NOMBRE_ACCESO = "Cliente Multimedia.bat"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / NOMBRE_ACCESO


def is_enabled() -> bool:
    return shortcut_path().exists()


def enable(launch_bat: Path) -> None:
    startup_dir().mkdir(parents=True, exist_ok=True)
    contenido = (
        "@echo off\r\n"
        f'start "" "{launch_bat.resolve()}"\r\n'
    )
    shortcut_path().write_text(contenido, encoding="utf-8")


def disable() -> None:
    ruta = shortcut_path()
    if ruta.exists():
        ruta.unlink()

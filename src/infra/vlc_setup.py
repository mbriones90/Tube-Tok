"""Localizacion de la instalacion de VLC y preparacion del entorno.

python-vlc necesita encontrar libvlc.dll (Windows) antes de importar vlc.
Debe llamarse ANTES de 'import vlc'.
"""
from __future__ import annotations

import os


def find_vlc_dir(install_path: str = "") -> str | None:
    candidatos: list[str] = []
    if install_path:
        candidatos.append(install_path)
    env = os.environ.get("VLC_PATH")
    if env:
        candidatos.append(env)

    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidatos += [
        os.path.join(pf, "VideoLAN", "VLC"),
        os.path.join(pf86, "VideoLAN", "VLC"),
        os.path.join(local, "VideoLAN", "VLC") if local else "",
    ]

    for carpeta in candidatos:
        if carpeta and os.path.isfile(os.path.join(carpeta, "libvlc.dll")):
            return carpeta
    return None


def ensure_vlc_on_path(install_path: str = "") -> str | None:
    """Anade el directorio de VLC al buscador de DLLs. Devuelve la ruta o None."""
    carpeta = find_vlc_dir(install_path)
    if not carpeta:
        return None
    try:
        os.add_dll_directory(carpeta)  # Python 3.8+ en Windows
    except (OSError, AttributeError):
        pass
    os.environ["PATH"] = carpeta + os.pathsep + os.environ.get("PATH", "")
    return carpeta

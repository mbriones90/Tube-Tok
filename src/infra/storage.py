"""Almacenamiento local: historial y favoritos en JSON."""
from __future__ import annotations

import json
import os
from pathlib import Path

from domain.models import Video


class JsonStore:
    """Lista de videos persistida en un archivo JSON."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: list[dict] = self._load()

    def _load(self) -> list[dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._items[:200], f, ensure_ascii=False, indent=2)

    def videos(self, limite: int = 50) -> list[Video]:
        return [Video.from_dict(d) for d in self._items[:limite]]

    def add(self, video: Video) -> None:
        self._items = [v for v in self._items if v.get("video_id") != video.video_id]
        self._items.insert(0, video.to_dict())
        self.save()

    def remove(self, video_id: str) -> None:
        self._items = [v for v in self._items if v.get("video_id") != video_id]
        self.save()

    def contains(self, video_id: str) -> bool:
        return any(v.get("video_id") == video_id for v in self._items)


class Storage:
    """Historial y favoritos del usuario."""

    def __init__(self, storage_cfg: dict, base_dir: Path):
        def resolver(ruta: str) -> Path:
            p = Path(ruta)
            return p if p.is_absolute() else base_dir / p

        self.history = JsonStore(resolver(storage_cfg.get("history_file", "./data/history.json")))
        self.favorites = JsonStore(resolver(storage_cfg.get("favorites_file", "./data/favorites.json")))
        self.cache_dir = resolver(storage_cfg.get("cache_dir", "./cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def toggle_favorite(self, video: Video) -> bool:
        """Anade o quita de favoritos. Devuelve True si quedo como favorito."""
        if self.favorites.contains(video.video_id):
            self.favorites.remove(video.video_id)
            return False
        self.favorites.add(video)
        return True

    def is_favorite(self, video_id: str) -> bool:
        return self.favorites.contains(video_id)

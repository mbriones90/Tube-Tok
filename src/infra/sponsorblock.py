"""Cliente de SponsorBlock: salta segmentos patrocinados dentro de los videos.

API publica y gratuita (sin key): https://sponsor.ajay.app
"""
from __future__ import annotations

import json

import requests

API_URL = "https://sponsor.ajay.app/api/skipSegments"


def fetch_segments(video_id: str, categories: list[str]) -> list[tuple[float, float]]:
    """Devuelve lista de (inicio, fin) en segundos. Lista vacia si no hay datos."""
    try:
        resp = requests.get(
            API_URL,
            params={"videoID": video_id, "categories": json.dumps(categories)},
            timeout=10,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return [(float(s[0]), float(s[1])) for s in resp.json()]
    except (requests.RequestException, ValueError, IndexError, TypeError):
        return []

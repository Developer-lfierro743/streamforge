"""StreamForge — fetch VOD artwork (posters) from The Movie Database (TMDB)."""

from __future__ import annotations

import requests

from .playlist import MediaEntry

_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


class TMDBClient:
    """Minimal TMDB wrapper that resolves a movie title to a poster URL.

    Get a free API key at https://www.themoviedb.org/settings/api.
    """

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self._session = requests.Session()
        self._cache: dict[str, str] = {}

    def poster_for(self, title: str) -> str:
        if title in self._cache:
            return self._cache[title]
        url = ""
        try:
            resp = self._session.get(
                _SEARCH_URL,
                params={"api_key": self.api_key, "query": title, "include_adult": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if results and results[0].get("poster_path"):
                url = _IMAGE_BASE + results[0]["poster_path"]
        except requests.RequestException:
            url = ""
        self._cache[title] = url
        return url

    def enrich(self, entries: list[MediaEntry]) -> list[MediaEntry]:
        out: list[MediaEntry] = []
        for e in entries:
            if e.logo:
                out.append(e)
                continue
            logo = self.poster_for(e.name)
            out.append(MediaEntry(e.url, e.name, e.group, e.tvg_id, logo))
        return out


def _to_entries(dicts: list[dict]) -> list[MediaEntry]:
    return [MediaEntry(**d) for d in dicts]

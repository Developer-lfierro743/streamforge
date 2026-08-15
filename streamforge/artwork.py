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
        self._cache_details: dict[str, dict] = {}

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

    def details(self, title: str) -> dict:
        """Resolve a title to TMDB metadata: poster, year, overview, kind."""
        if title in self._cache_details:
            return self._cache_details[title]
        info: dict = {}
        try:
            for kind, endpoint, date_key in (
                ("movie", "search/movie", "release_date"),
                ("series", "search/tv", "first_air_date"),
            ):
                resp = self._session.get(
                    f"https://api.themoviedb.org/3/{endpoint}",
                    params={"api_key": self.api_key, "query": title, "include_adult": False},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                results = resp.json().get("results") or []
                if results:
                    top = results[0]
                    info = {
                        "logo": _IMAGE_BASE + top["poster_path"] if top.get("poster_path") else "",
                        "year": (top.get(date_key) or "")[:4],
                        "overview": top.get("overview", ""),
                        "kind": kind,
                    }
                    break
        except requests.RequestException:
            info = {}
        self._cache_details[title] = info
        return info

    def enrich(self, entries: list[MediaEntry]) -> list[MediaEntry]:
        out: list[MediaEntry] = []
        for e in entries:
            if e.logo and e.year and e.overview:
                out.append(e)
                continue
            d = self.details(e.name)
            out.append(
                MediaEntry(
                    e.url,
                    e.name,
                    e.group,
                    e.tvg_id,
                    d.get("logo") or e.logo,
                    d.get("year", ""),
                    d.get("overview", ""),
                    d.get("kind") or e.kind,
                )
            )
        return out


def _to_entries(dicts: list[dict]) -> list[MediaEntry]:
    return [MediaEntry(**d) for d in dicts]

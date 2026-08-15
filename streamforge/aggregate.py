"""StreamForge — multi-source link aggregator.

Pulls media links from several kinds of sources and merges them into a single
master playlist:

* ``playlist`` — a remote ``.m3u``/``.m3u8`` (e.g. Free-TV/IPTV, iptv-org).
* ``directory`` — an open web directory scraped for video files (VOD).
* ``epg``      — an XMLTV guide URL attached to the live channels.

TMDB (if configured) enriches the VOD half with posters/overviews so the
result isn't limited to live-only streams.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterable

import requests

from .playlist import MediaEntry, parse_m3u
from .scraper import DEFAULT_EXTENSIONS, OpenDirectoryScraper, ScraperConfig


@dataclass
class Source:
    type: str
    name: str = ""
    url: str = ""
    recursive: bool = False
    extensions: tuple = tuple(DEFAULT_EXTENSIONS)
    kind: str = ""        # "live" | "vod" | "" (auto-detect)
    epg_days: int = 1

    @property
    def is_epg(self) -> bool:
        return self.type == "epg"

    def to_dict(self) -> dict:
        return asdict(self)


def load_sources(toml_data: dict) -> list[Source]:
    """Build ``Source`` objects from a parsed ``config.toml`` ``[sources]``."""
    out: list[Source] = []
    raw = toml_data.get("sources") or []
    if isinstance(raw, dict):
        raw = [raw]
    for s in raw:
        if not isinstance(s, dict):
            continue
        stype = (s.get("type") or "").strip().lower()
        if stype == "epg":
            out.append(
                Source(
                    type="epg",
                    name=s.get("name", "EPG"),
                    url=s.get("url", ""),
                    epg_days=int(s.get("epg_days", 1)),
                )
            )
            continue
        if stype not in ("playlist", "directory"):
            continue
        exts = s.get("extensions") or list(DEFAULT_EXTENSIONS)
        if isinstance(exts, str):
            exts = [e.strip() for e in exts.split(",") if e.strip()]
        out.append(
            Source(
                type=stype,
                name=s.get("name", stype),
                url=s.get("url", ""),
                recursive=bool(s.get("recursive", False)),
                extensions=tuple(e.lower().lstrip(".") for e in exts),
                kind=(s.get("kind") or "").strip().lower(),
            )
        )
    return out


def gather(source: Source, timeout: float = 30.0) -> list[MediaEntry]:
    """Fetch one source and return its raw entries (kind-tagged)."""
    if source.type == "playlist":
        resp = requests.get(source.url, timeout=timeout)
        resp.raise_for_status()
        entries = parse_m3u(resp.text)
    elif source.type == "directory":
        cfg = ScraperConfig(
            extensions=source.extensions,
            recursive=source.recursive,
            max_depth=5,
            workers=6,
        )
        entries = OpenDirectoryScraper(cfg).scrape(source.url)
    else:
        return []

    for e in entries:
        if not e.group and source.name:
            e.group = source.name
        if source.kind:
            e.kind = source.kind
        elif not e.kind:
            e.kind = "live" if source.type == "playlist" else "vod"
    return entries


def aggregate(
    sources: Iterable[Source],
    *,
    tmdb_key: str = "",
    timeout: float = 30.0,
) -> tuple[list[MediaEntry], list[str]]:
    """Merge every source, dedup by URL and enrich VOD with TMDB.

    Returns ``(entries, epg_urls)``. A dead source is skipped rather than
    sinking the whole run.
    """
    seen: dict[str, MediaEntry] = {}
    epg_urls: list[str] = []
    live: list[MediaEntry] = []
    vod: list[MediaEntry] = []

    for src in sources:
        if src.is_epg:
            if src.url:
                epg_urls.append(src.url)
            continue
        if not src.url:
            continue
        try:
            entries = gather(src, timeout=timeout)
        except Exception:
            continue
        for e in entries:
            if not e.url or e.url in seen:
                continue
            seen[e.url] = e
            (live if e.kind == "live" else vod).append(e)

    if tmdb_key and vod:
        from .artwork import TMDBClient

        enriched = TMDBClient(tmdb_key).enrich(vod)
        by_url = {e.url: e for e in enriched}
        for i, e in enumerate(vod):
            if e.url in by_url:
                vod[i] = by_url[e.url]

    return live + vod, epg_urls


_TV_RE = re.compile(r"<tv[^>]*>(.*)</tv>", re.S | re.I)


def build_epg(
    epg_urls: list[str], entries: list[MediaEntry], timeout: float = 30.0
) -> str | None:
    """Fetch + filter each XMLTV source and merge them into one guide."""
    from . import epg as epg_mod

    blocks: list[str] = []
    for u in epg_urls:
        try:
            xml = epg_mod.fetch_and_filter_xmltv(u, entries, timeout=timeout)
        except Exception:
            continue
        m = _TV_RE.search(xml)
        if m:
            blocks.append(m.group(1))
    if not blocks:
        return None
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<tv>'
        + "\n".join(blocks)
        + "</tv>\n"
    )

"""StreamForge — persistent VOD catalog (SQLite) + metadata fetcher + playback.

This is the storage layer for Video-on-Demand: scraped/imported media is
persisted so it survives restarts and can be browsed, filtered, enriched with
TMDB metadata, and played back via a stable id.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .artwork import TMDBClient
from .config import tmdb_api_key
from .playlist import MediaEntry

DEFAULT_DB = "streamforge.db"


class VodCatalog:
    def __init__(self, db_path: str = DEFAULT_DB) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vod (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    url       TEXT UNIQUE,
                    name      TEXT,
                    group_title TEXT,
                    tvg_id    TEXT,
                    logo      TEXT,
                    year      TEXT,
                    overview  TEXT,
                    kind      TEXT,
                    source    TEXT,
                    added_at  REAL
                )
                """
            )
            self.conn.commit()

    def upsert(self, e: MediaEntry, source: str = "scrape") -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO vod
                    (url, name, group_title, tvg_id, logo, year, overview, kind, source, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    name=excluded.name, group_title=excluded.group_title,
                    tvg_id=excluded.tvg_id, logo=excluded.logo,
                    year=excluded.year, overview=excluded.overview,
                    kind=excluded.kind, source=excluded.source
                """,
                (e.url, e.name, e.group, e.tvg_id, e.logo, e.year,
                 e.overview, e.kind, source, time.time()),
            )
            self.conn.commit()

    def get(self, id: int) -> Optional[MediaEntry]:
        with self._lock:
            row = self.conn.execute("SELECT * FROM vod WHERE id=?", (id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def list(
        self,
        kind: str = "",
        group: str = "",
        q: str = "",
        art_only: bool = False,
        limit: int = 500,
    ) -> list[MediaEntry]:
        sql = "SELECT * FROM vod WHERE 1=1"
        args: list = []
        if kind == "movie":
            sql += " AND kind='movie'"
        elif kind == "series":
            sql += " AND kind='series'"
        elif kind == "live":
            sql += " AND (kind IS NULL OR kind='')"
        if group:
            sql += " AND group_title=?"
            args.append(group)
        if q:
            sql += " AND (name LIKE ? OR group_title LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        if art_only:
            sql += " AND logo IS NOT NULL AND logo<>''"
        sql += " ORDER BY added_at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def pending_metadata(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM vod WHERE (year IS NULL OR year='') "
                "AND (overview IS NULL OR overview='')"
            ).fetchall()

    def apply_metadata(
        self, url: str, logo: str = "", year: str = "", overview: str = "", kind: str = ""
    ) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE vod SET logo=?, year=?, overview=?, kind=? WHERE url=?",
                (logo, year, overview, kind, url),
            )
            self.conn.commit()

    def count(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM vod").fetchone()[0]

    def close(self) -> None:
        self.conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> MediaEntry:
        return MediaEntry(
            id=row["id"],
            url=row["url"],
            name=row["name"],
            group=row["group_title"] or "",
            tvg_id=row["tvg_id"] or "",
            logo=row["logo"] or "",
            year=row["year"] or "",
            overview=row["overview"] or "",
            kind=row["kind"] or "",
        )


def enrich_catalog(catalog: VodCatalog, api_key: str = "") -> int:
    """Fetch TMDB metadata for every catalog row missing it. Returns updated count."""
    key = tmdb_api_key(api_key)
    if not key:
        return 0
    client = TMDBClient(key)
    updated = 0
    for row in catalog.pending_metadata():
        d = client.details(row["name"])
        if not d:
            continue
        catalog.apply_metadata(
            row["url"],
            d.get("logo", "") or row["logo"] or "",
            d.get("year", ""),
            d.get("overview", ""),
            d.get("kind", ""),
        )
        updated += 1
    return updated

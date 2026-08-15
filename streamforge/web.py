"""StreamForge web UI — a small LAN/PWA server for scraping + browsing media."""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel

from .playlist import MediaEntry, build_m3u, parse_m3u
from .scraper import DEFAULT_EXTENSIONS, OpenDirectoryScraper, ScraperConfig
from . import epg as epg_mod
from .artwork import TMDBClient, _to_entries
from .vod import VodCatalog, enrich_catalog, DEFAULT_DB

STATIC_DIR = Path(__file__).parent / "webui"

app = FastAPI(title="StreamForge")

catalog = VodCatalog(os.environ.get("STREAMFORGE_DB", DEFAULT_DB))

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class ScrapeRequest(BaseModel):
    url: str
    recursive: bool = False
    extensions: str = ",".join(DEFAULT_EXTENSIONS)
    max_depth: int = 5
    workers: int = 6


class ImportRequest(BaseModel):
    url: str
    timeout: float = 30.0


def _run_scrape(job_id: str, req: ScrapeRequest) -> None:
    try:
        exts = tuple(e.lower().lstrip(".") for e in req.extensions.split(",") if e.strip())
        cfg = ScraperConfig(
            extensions=exts or DEFAULT_EXTENSIONS,
            recursive=req.recursive,
            max_depth=req.max_depth,
            workers=req.workers,
        )
        entries = OpenDirectoryScraper(cfg).scrape(req.url)
        for e in entries:
            catalog.upsert(e, source="scrape")
        with _jobs_lock:
            _jobs[job_id].update(status="done", entries=entries, count=len(entries))
    except Exception as exc:  # noqa: BLE001
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=str(exc))


@app.post("/api/scrape")
def start_scrape(req: ScrapeRequest) -> dict:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "entries": [], "count": 0, "error": ""}
    threading.Thread(target=_run_scrape, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    return job


@app.post("/api/import")
def import_playlist(req: ImportRequest) -> dict:
    import requests

    try:
        resp = requests.get(req.url, timeout=req.timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(502, f"fetch failed: {exc}") from exc
    entries = parse_m3u(resp.text)
    for e in entries:
        catalog.upsert(e, source="import")
    return {"count": len(entries), "entries": [e.__dict__ for e in entries]}


class EpgRequest(BaseModel):
    entries: list[dict]
    url: str = ""
    days: int = 1


@app.post("/api/epg")
def export_epg(req: EpgRequest) -> PlainTextResponse:
    entries = _to_entries(req.entries)
    if req.url:
        try:
            xml = epg_mod.fetch_and_filter_xmltv(req.url, entries)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"EPG fetch failed: {exc}") from exc
    else:
        xml = epg_mod.generate_xmltv(entries, days=req.days)
    return PlainTextResponse(
        xml,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=streamforge.xml"},
    )


class ArtworkRequest(BaseModel):
    entries: list[dict]
    api_key: str


@app.post("/api/artwork")
def fetch_artwork(req: ArtworkRequest) -> dict:
    from .config import tmdb_api_key

    key = tmdb_api_key(req.api_key)
    if not key:
        raise HTTPException(400, "TMDB API key required (paste it or set config.toml)")
    client = TMDBClient(key)
    enriched = client.enrich(_to_entries(req.entries))
    return {"count": len(enriched), "entries": [e.__dict__ for e in enriched]}


@app.get("/api/config")
def ui_config() -> dict:
    from .config import has_tmdb_key

    return {"has_tmdb_key": has_tmdb_key()}


# ---- VOD catalog (persistent storage) ----
@app.get("/api/vod")
def list_vod(kind: str = "", group: str = "", q: str = "", art: bool = False) -> dict:
    entries = catalog.list(kind=kind, group=group, q=q, art_only=art)
    return {"count": len(entries), "entries": [e.__dict__ for e in entries]}


class EnrichRequest(BaseModel):
    api_key: str = ""


@app.post("/api/vod/enrich")
def enrich_vod(req: EnrichRequest) -> dict:
    from .config import tmdb_api_key as resolve_key

    key = resolve_key(req.api_key)
    if not key:
        raise HTTPException(400, "TMDB API key required (paste it or set config.toml)")
    updated = enrich_catalog(catalog, key)
    return {"updated": updated, "total": catalog.count()}


@app.get("/api/vod/{vod_id}/play")
def play_vod(vod_id: int) -> RedirectResponse:
    entry = catalog.get(vod_id)
    if entry is None:
        raise HTTPException(404, "unknown id")
    return RedirectResponse(entry.url, status_code=307)


@app.get("/api/playlist")
def export_playlist(job_id: str = "", raw: str = "") -> PlainTextResponse:
    if job_id:
        with _jobs_lock:
            job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "unknown job")
        entries = [_to_entry(e) for e in job["entries"]]
    elif raw:
        entries = [MediaEntry(**d) for d in __import__("json").loads(raw)]
    else:
        raise HTTPException(400, "provide job_id or raw")
    return PlainTextResponse(build_m3u(entries), media_type="application/x-mpegurl")


def _to_entry(e: object) -> MediaEntry:
    return e if isinstance(e, MediaEntry) else MediaEntry(**e)


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/app.js")
def app_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")

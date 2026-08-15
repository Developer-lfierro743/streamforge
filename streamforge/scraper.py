"""StreamForge — scrape open directories for media files over HTTP."""

from __future__ import annotations

import queue
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock, Semaphore
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .playlist import MediaEntry, sanitize_name

DEFAULT_EXTENSIONS = ("mp4", "mkv", "avi", "mov", "webm", "ts", "flv", "wmv")


@dataclass
class ScraperConfig:
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS
    recursive: bool = False
    max_depth: int = 5
    workers: int = 6
    timeout: float = 20.0
    min_delay: float = 0.25
    user_agent: str = "StreamForge/0.1 (+https://github.com/streamforge)"


@dataclass
class _Job:
    url: str
    depth: int
    group: str


class OpenDirectoryScraper:
    """Crawl an open-directory listing and collect media file URLs.

    Uses a thread pool over a work queue so directory pages are fetched
    concurrently while per-host rate limiting is respected.
    """

    def __init__(self, config: ScraperConfig | None = None) -> None:
        self.cfg = config or ScraperConfig()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = self.cfg.user_agent
        self._seen: set[str] = set()
        self._seen_lock = Lock()
        self._last_hit: dict[str, float] = {}
        self._last_hit_lock = Lock()

    def scrape(self, start_url: str) -> list[MediaEntry]:
        start_url = start_url if start_url.endswith("/") else start_url + "/"
        self._work: queue.Queue[_Job] = queue.Queue()
        self._work.put(_Job(start_url, 0, urlparse(start_url).netloc))
        self._pending = 1
        self._pending_lock = Lock()
        self._stop = False
        results: list[MediaEntry] = []
        results_lock = Lock()

        with ThreadPoolExecutor(max_workers=self.cfg.workers) as pool:
            futures = [
                pool.submit(self._worker, results, results_lock)
                for _ in range(self.cfg.workers)
            ]
            for fut in futures:
                fut.result()
        return results

    def _worker(self, results: list[MediaEntry], lock: Lock) -> None:
        while True:
            try:
                job = self._work.get(timeout=1.0)
            except queue.Empty:
                with self._pending_lock:
                    if self._pending == 0:
                        return
                continue
            self._process(job, results, lock)
            with self._pending_lock:
                self._pending -= 1

    def _process(self, job: _Job, results: list[MediaEntry], lock: Lock) -> None:
        if job.depth > self.cfg.max_depth:
            return
        html = self._fetch(job.url)
        if html is None:
            return

        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            if not href or href.startswith(("?", "#", "javascript:")):
                continue
            full = urljoin(job.url, href)
            with self._seen_lock:
                if full in self._seen:
                    continue
                self._seen.add(full)

            if href.endswith("/"):
                if self.cfg.recursive and job.depth < self.cfg.max_depth:
                    sub_group = sanitize_name(href.rstrip("/")) or job.group
                    with self._pending_lock:
                        self._pending += 1
                    self._work.put(_Job(full, job.depth + 1, sub_group))
                continue

            if self._is_media(full):
                name = sanitize_name(full.rsplit("/", 1)[-1])
                with lock:
                    results.append(MediaEntry(url=full, name=name, group=job.group))

    def _is_media(self, url: str) -> bool:
        path = url.rsplit("?", 1)[0].rsplit("#", 1)[0].lower()
        return any(path.endswith("." + ext) for ext in self.cfg.extensions)

    def _fetch(self, url: str) -> str | None:
        host = urlparse(url).netloc
        now = time.monotonic()
        with self._last_hit_lock:
            wait = self.cfg.min_delay - (now - self._last_hit.get(host, 0.0))
            if wait > 0:
                time.sleep(wait)
            self._last_hit[host] = time.monotonic()

        try:
            resp = self._session.get(url, timeout=self.cfg.timeout)
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if not any(t in ctype for t in ("html", "text", "xml")):
                return None
            return resp.text
        except requests.RequestException:
            return None

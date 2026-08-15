"""StreamForge command-line interface."""

from __future__ import annotations

import argparse
import sys

from .playlist import build_m3u
from .scraper import DEFAULT_EXTENSIONS, OpenDirectoryScraper, ScraperConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="streamforge",
        description="Scrape public open directories into IPTV .m3u playlists.",
    )
    p.add_argument("--url", "-u", required=False, help="Root open-directory URL")
    p.add_argument("--output", "-o", default="streamforge.m3u", help="Output .m3u path")
    p.add_argument(
        "--extensions", "-e", nargs="+", default=list(DEFAULT_EXTENSIONS),
        help="File extensions to include (without dot)",
    )
    p.add_argument(
        "--recursive", "-r", action="store_true", help="Crawl subdirectories"
    )
    p.add_argument("--max-depth", type=int, default=5, help="Max crawl depth")
    p.add_argument("--workers", "-w", type=int, default=6, help="Concurrent workers")
    p.add_argument("--timeout", type=float, default=20.0, help="Request timeout (s)")
    p.add_argument("--min-delay", type=float, default=0.25, help="Per-host min delay (s)")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress progress")
    p.add_argument(
        "--serve", action="store_true", help="Launch the StreamForge web UI (PWA)"
    )
    p.add_argument("--host", default="0.0.0.0", help="Web UI bind host")
    p.add_argument("--port", type=int, default=8000, help="Web UI bind port")
    p.add_argument("--epg", default="", help="Write an XMLTV EPG to this path")
    p.add_argument(
        "--epg-url", default="", help="Fetch+filter a public XMLTV from this URL"
    )
    p.add_argument("--tmdb-key", default="", help="TMDB API key for VOD posters")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.serve:
        from .web import app
        import uvicorn

        # proot (and Android) cannot bind ports < 1024 without
        # CAP_NET_BIND_SERVICE. Transparently remap a privileged port so the
        # server "just works" — this is the proot hijack.
        if args.port < 1024:
            real_port = args.port + 10000
            print(
                f"[streamforge] proot can't bind port {args.port} (<1024); "
                f"remapping to {real_port}",
                file=sys.stderr,
            )
            args.port = real_port

        print(
            f"[streamforge] web UI on http://{args.host}:{args.port} "
            f"(open this on your Android browser)",
            file=sys.stderr,
        )
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    if not args.url:
        build_parser().error("--url is required unless using --serve")

    cfg = ScraperConfig(
        extensions=tuple(e.lower().lstrip(".") for e in args.extensions),
        recursive=args.recursive,
        max_depth=args.max_depth,
        workers=args.workers,
        timeout=args.timeout,
        min_delay=args.min_delay,
    )
    scraper = OpenDirectoryScraper(cfg)

    if not args.quiet:
        print(f"[streamforge] scraping {args.url} ...", file=sys.stderr)

    entries = scraper.scrape(args.url)

    if not entries:
        print("[streamforge] no media files found.", file=sys.stderr)
        return 1

    from .artwork import TMDBClient
    from .config import tmdb_api_key

    key = tmdb_api_key(args.tmdb_key)
    if key:
        entries = TMDBClient(key).enrich(entries)
        if not args.quiet:
            got = sum(1 for e in entries if e.logo)
            print(f"[streamforge] TMDB posters: {got}/{len(entries)}", file=sys.stderr)

    m3u = build_m3u(entries)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(m3u)

    if args.epg:
        from . import epg as epg_mod

        xml = (
            epg_mod.fetch_and_filter_xmltv(args.epg_url, entries)
            if args.epg_url
            else epg_mod.generate_xmltv(entries)
        )
        with open(args.epg, "w", encoding="utf-8") as fh:
            fh.write(xml)
        if not args.quiet:
            print(f"[streamforge] wrote EPG -> {args.epg}", file=sys.stderr)

    if not args.quiet:
        print(
            f"[streamforge] wrote {len(entries)} entries -> {args.output}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

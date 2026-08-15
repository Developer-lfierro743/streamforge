from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass
class MediaEntry:
    """A single media file discovered on a remote open directory."""

    url: str
    name: str
    group: str = ""
    tvg_id: str = ""
    logo: str = ""
    year: str = ""
    overview: str = ""
    kind: str = "vod"

    @property
    def channel_id(self) -> str:
        """Stable id used to link m3u entries to EPG channels."""
        return self.tvg_id or slugify(self.name)

    def extinf_line(self) -> str:
        """Return the ``#EXTINF`` metadata line for this entry."""
        safe_name = self.name.replace(",", " ")
        cid = self.channel_id
        parts = [f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{safe_name}"']
        if self.logo:
            parts.append(f'tvg-logo="{self.logo}"')
        parts.append(f'group-title="{self.group or "StreamForge"}"')
        return ", ".join(parts) + f",{safe_name}"


def slugify(text: str) -> str:
    """Build a URL/file-safe id from a title (lowercase, dashes)."""
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return out or "channel"


def sanitize_name(filename: str) -> str:
    """Turn a raw file name into a clean display title."""
    name = filename
    for ext in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".flv", ".wmv"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    name = name.replace("_", " ").replace(".", " ").strip()
    return " ".join(name.split())


def build_m3u(entries: Iterable[MediaEntry], header: str = "StreamForge") -> str:
    """Render a list of media entries into an IPTV-ready ``.m3u`` document."""
    lines = ["#EXTM3U", f"# Playlist: {header}"]
    for entry in entries:
        lines.append(entry.extinf_line())
        lines.append(entry.url)
    return "\n".join(lines) + "\n"


_ATTR_RE = re.compile(r'(\w[\w-]*)="([^"]*)"')


def parse_m3u(text: str) -> list[MediaEntry]:
    """Parse an existing ``.m3u``/``.m3u8`` playlist into media entries.

    Used to import public playlists (e.g. iptv-org) so they can be filtered
    and re-exported alongside scraped VOD.
    """
    entries: list[MediaEntry] = []
    pending: MediaEntry | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = {k.lower(): v for k, v in _ATTR_RE.findall(line)}
            name = line.rsplit(",", 1)[-1].strip() or attrs.get("tvg-name", "")
            pending = MediaEntry(
                url="",
                name=sanitize_name(name),
                group=attrs.get("group-title", ""),
                tvg_id=attrs.get("tvg-id", ""),
                logo=attrs.get("tvg-logo", ""),
            )
        elif line.startswith("#"):
            continue
        elif pending is not None:
            pending.url = line
            entries.append(pending)
            pending = None
    return entries

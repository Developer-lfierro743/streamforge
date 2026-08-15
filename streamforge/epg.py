"""StreamForge — XMLTV EPG generation and filtering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from xml.etree import ElementTree as ET

from .playlist import MediaEntry

_IMAGE_PROXY = None


def _xmltv_time(dt: datetime) -> str:
    """Format a datetime as XMLTV ``YYYYMMDDHHMMSS +0000``."""
    return dt.strftime("%Y%m%d%H%M%S") + " +0000"


def generate_xmltv(
    entries: Iterable[MediaEntry],
    generator: str = "StreamForge",
    days: int = 1,
    programmes_per_day: int = 4,
) -> str:
    """Build an XMLTV guide.

    Emits one ``<channel>`` per unique entry (keyed by ``channel_id``) and,
    optionally, a light placeholder programme schedule so players like
    TiviMate show a guide. For real schedules, use :func:`fetch_and_filter_xmltv`.
    """
    channels: dict[str, MediaEntry] = {}
    for e in entries:
        channels.setdefault(e.channel_id, e)

    tv = ET.Element("tv", attrib={"generator-info-name": generator})

    for cid, e in channels.items():
        ch = ET.SubElement(tv, "channel", attrib={"id": cid})
        ET.SubElement(ch, "display-name").text = e.name
        if e.logo:
            ET.SubElement(ch, "icon", attrib={"src": e.logo})

    if programmes_per_day > 0 and days > 0:
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        slot = timedelta(hours=24 // max(programmes_per_day, 1))
        for cid, e in channels.items():
            base = now
            for _ in range(days):
                for i in range(programmes_per_day):
                    start = base + slot * i
                    stop = start + slot
                    prog = ET.SubElement(
                        tv,
                        "programme",
                        attrib={
                            "start": _xmltv_time(start),
                            "stop": _xmltv_time(stop),
                            "channel": cid,
                        },
                    )
                    ET.SubElement(prog, "title").text = e.name
                    ET.SubElement(prog, "desc").text = (
                        f"Stream from {e.group or 'StreamForge'}"
                    )
                base += timedelta(days=1)

    ET.indent(tv, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tv, encoding="unicode")


def fetch_and_filter_xmltv(
    url: str, entries: Iterable[MediaEntry], timeout: float = 30.0
) -> str:
    """Download a public XMLTV and keep only channels present in ``entries``.

    This binds an imported playlist to a real guide (e.g. an iptv-org EPG) by
    matching each entry's ``channel_id`` against the guide's channel ids.
    """
    import requests

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    wanted = {e.channel_id for e in entries}
    new_root = ET.Element("tv", attrib=dict(root.attrib))
    for ch in root.findall("channel"):
        if ch.get("id") in wanted:
            new_root.append(ch)
    kept_channels = {ch.get("id") for ch in new_root.findall("channel")}
    for prog in root.findall("programme"):
        if prog.get("channel") in kept_channels:
            new_root.append(prog)

    ET.indent(new_root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(new_root, encoding="unicode")

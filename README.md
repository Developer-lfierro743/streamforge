StreamForge
==========

A small, dependency-light Python tool that scrapes **public open directories**
(Apache/nginx autoindex pages, etc.), extracts video files (``.mp4``, ``.mkv``,
and friends), and writes a clean ``.m3u`` playlist compatible with IPTV players
such as `TiviMate <https://tivimate.com/>`_.

Features
--------

* Recursively crawls open-directory listings (``<a href>`` based).
* Filters by file extension (configurable).
* Concurrent fetching for speed (thread pool).
* Emits IPTV-ready ``.m3u`` with ``#EXTINF`` metadata and group titles.
* Pure ``requests`` + ``beautifulsoup4`` (no browser needed).

Multi-source aggregator
-----------------------

StreamForge can merge **many** sources into one master playlist instead of
scraping a single directory. Add a ``[sources]`` table to ``config.toml``
(see ``config.example.toml``) and run:

.. code-block:: bash

   # CLI: merge every [sources] entry into one .m3u (+ optional EPG)
   python -m streamforge.cli --aggregate --output master.m3u --epg guide.xml

   # Or in the web UI: open the "Aggregate" tab and click "Aggregate sources".

Source types:

* ``playlist`` — a remote ``.m3u``/``.m3u8`` (e.g. Free-TV/IPTV, iptv-org live
  channels). Tagged as **live**.
* ``directory`` — an open web directory scraped for video files. Tagged as
  **VOD** and enriched with TMDB posters if a key is configured.
* ``epg`` — an XMLTV guide URL, filtered to the channels found and merged into
  a single guide.

Links are de-duplicated by URL, so the same file referenced by several sources
appears once. The result is **not limited to live-only** streams — mix live
channels and on-demand files freely.

Install
-------

.. code-block:: bash

   pip install -r requirements.txt

Usage
-----

.. code-block:: bash

   # Scrape a single open directory and write a playlist
   python -m streamforge.cli \
       --url "https://example.com/files/" \
       --output movies.m3u

   # Recursive crawl with custom extensions and more workers
   python -m streamforge.cli \
       --url "https://example.com/files/" \
       --output movies.m3u \
       --recursive \
       --extensions mp4 mkv avi \
       --workers 8

   # Quiet run, no progress output
   python -m streamforge.cli --url "https://example.com/files/" -o out.m3u -q

Web UI (PWA)
------------

StreamForge also ships a small web app you can open in a phone browser and
"Add to Home Screen" like a native app.

.. code-block:: bash

   pip install -r requirements.txt
   python -m streamforge.cli --serve --host 0.0.0.0 --port 8000

Then open the URL in your browser:

* On the **same Android device** (proot/Debian on the phone):
  ``http://127.0.0.1:8000``
* From **another device on the LAN**: use the phone's LAN IP, e.g.
  ``http://192.168.1.20:8000`` (bind with ``--host 0.0.0.0``).

The UI lets you:

* **Scrape** an open directory (recursive, with extension filter).
* **Import** an existing public playlist by URL (e.g. a legal, public IPTV
  source) and merge/filter it.
* Browse a responsive **channel grid with artwork** (auto-generated
  thumbnails), filter by name/group, and tap **▶ Play** to send the stream
  to an external player (VLC / TiviMate).
* **Download .m3u** for direct use in any IPTV player.

EPG (XMLTV) and artwork
-------------------------

* **EPG**: generate an XMLTV guide that links to your playlist via ``tvg-id``,
  or fetch a public XMLTV (e.g. an iptv-org guide) and filter it down to just
  the channels in your playlist::

     python -m streamforge.cli --url "https://example.com/files/" \
         --output movies.m3u --epg epg.xml --epg-url "https://.../guide.xml"

  In the web UI use the **Generate EPG** button (optionally paste an EPG URL
  to filter). Load the resulting ``streamforge.xml`` in your player's EPG setting.

* **TMDB artwork**: for VOD, fetch real posters from The Movie Database and
  attach them as ``tvg-logo`` (used as card art in the web UI)::

     python -m streamforge.cli --url "https://example.com/files/" \
         --output movies.m3u --tmdb-key "YOUR_TMDB_KEY"

  In the web UI paste your TMDB key and click **Fetch artwork**.   Get a free key
  at https://www.themoviedb.org/settings/api.

Keeping your API key private (personal use)
------------------------------------------------

The TMDB key is resolved in this order: ``--tmdb-key`` > env var
``STREAMFORGE_TMDB_KEY`` > a local ``config.toml``. The real ``config.toml``
is git-ignored, so it is **never committed**. Only ``config.example.toml``
(copy of the shape, no secret) is tracked.

.. code-block:: bash

   cp config.example.toml config.toml
   # edit config.toml and put your key in
   # or: export STREAMFORGE_TMDB_KEY=your_key

In the web UI the key field is auto-disabled when a key is already set via
config/env, so you don't paste it into the browser each time.

Attribution
-----------

* **The Movie Database (TMDB)** — VOD artwork is fetched from the TMDB API.
  Per TMDB's terms of use, the following notice must be displayed:

  *This product uses the TMDB API but is not endorsed or certified by TMDB.*

* Built with `requests <https://requests.readthedocs.io/>`_,
  `beautifulsoup4 <https://www.crummy.com/software/BeautifulSoup/>`_,
  `FastAPI <https://fastapi.tiangolo.com/>`_, and
  `uvicorn <https://www.uvicorn.org/>`_ (all MIT/ASL-2.0).

* Public playlists/EPGs (e.g. iptv-org) are aggregated by reference only;
  respect each source's license and only use legally-published streams.

The generated playlist looks like::

   #EXTM3U
   #EXTINF:-1 tvg-name="Movie (1080p)" group-title="files",Movie (1080p)
   https://example.com/files/Movie%20(1080p).mp4

Notes
-----

* Only point this at **public** directories you have the right to access.
* Honors a simple per-host rate limit so you don't hammer a server.
* Set ``--timeout`` and ``--max-depth`` to control crawling behaviour.

License
-------

MIT

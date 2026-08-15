const $ = (sel) => document.querySelector(sel);
const grid = $("#grid");
const status = $("#status");
const downloadBtn = $("#downloadBtn");
const filter = $("#filter");

let currentEntries = [];
let currentJobId = null;
const filters = { text: "", kind: "all", group: "", art: false };

// ---- tabs ----
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tabpane").forEach((x) => x.classList.add("hidden"));
    t.classList.add("active");
    $("#tab-" + t.dataset.tab).classList.remove("hidden");
  });
});

// ---- artwork (deterministic SVG placeholder) ----
function hash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}
function initials(name) {
  const words = name.replace(/[^\w\s]/g, "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}
function thumb(name) {
  const h = hash(name);
  const hue = h % 360;
  const hue2 = (hue + 40) % 360;
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='300' height='450'>
    <defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0' stop-color='hsl(${hue},65%,45%)'/>
      <stop offset='1' stop-color='hsl(${hue2},65%,30%)'/></linearGradient></defs>
    <rect width='300' height='450' fill='url(#g)'/>
    <text x='150' y='225' font-size='90' font-family='sans-serif' font-weight='800'
      fill='rgba(255,255,255,.92)' text-anchor='middle' dominant-baseline='central'>${initials(name)}</text>
  </svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

// ---- rendering ----
function render() {
  const q = filters.text.trim().toLowerCase();
  const list = currentEntries.filter((e) => {
    const name = (e.name || "").toLowerCase();
    const group = (e.group || "").toLowerCase();
    if (q && !(name.includes(q) || group.includes(q))) return false;
    if (filters.kind !== "all") {
      const k = e.kind || "live";
      if (filters.kind === "live" && e.kind) return false; // live = no kind set
      if (filters.kind !== "live" && k !== filters.kind) return false;
    }
    if (filters.group && (e.group || "") !== filters.group) return false;
    if (filters.art && !e.logo) return false;
    return true;
  });

  if (!list.length) {
    grid.innerHTML = `<div class="empty">No channels yet. Scrape or import a playlist.</div>`;
    return;
  }
  grid.innerHTML = list
    .map((e, i) => {
      const group = e.group || "Ungrouped";
      const art = e.logo ? escapeHtml(e.logo) : thumb(e.name);
      const year = e.year ? `<span class="year">${escapeHtml(e.year)}</span>` : "";
      const kind = e.kind
        ? `<span class="kind">${escapeHtml(e.kind)}</span>` : "";
      return `<div class="card" data-i="${i}">
        <img class="thumb" src="${art}" alt="" loading="lazy" />
        <div class="meta">
          <div class="title">${escapeHtml(e.name)}${year}${kind}</div>
          <div class="group">${escapeHtml(group)}</div>
        </div>
        <a class="play" href="${e.id ? "/api/vod/" + e.id + "/play" : encodeURI(e.url)}" target="_blank" rel="noopener">▶ Play</a>
      </div>`;
    })
    .join("");

  // open details modal when tapping a card (but not the Play link)
  grid.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", (ev) => {
      if (ev.target.closest(".play")) return;
      const e = list[Number(card.dataset.i)];
      openModal(e);
    });
  });
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ---- scrape ----
$("#scrapeBtn").addEventListener("click", async () => {
  const url = $("#url").value.trim();
  if (!url) return setStatus("Enter a URL first.");
  downloadBtn.disabled = true;
  currentEntries = [];
  currentJobId = null;
  render();
  setStatus("Starting scrape…");
  const res = await fetch("/api/scrape", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      recursive: $("#recursive").checked,
      extensions: $("#extensions").value,
    }),
  }).then((r) => r.json());
  currentJobId = res.job_id;
  poll(res.job_id);
});

function poll(jobId) {
  const timer = setInterval(async () => {
    const job = await fetch("/api/jobs/" + jobId).then((r) => r.json());
    if (job.status === "running") {
      setStatus(`Scraping… found ${job.count} so far`);
    } else if (job.status === "error") {
      clearInterval(timer);
      setStatus("Error: " + job.error);
    } else {
      clearInterval(timer);
      currentEntries = job.entries;
      filter.classList.remove("hidden");
      downloadBtn.disabled = false;
      setStatus(`Done — ${job.count} entries.`);
      showToolbar();
      render();
    }
  }, 1000);
}

// ---- import ----
$("#importBtn").addEventListener("click", async () => {
  const url = $("#importUrl").value.trim();
  if (!url) return setStatus("Enter a playlist URL.");
  downloadBtn.disabled = true;
  currentJobId = null;
  setStatus("Importing…");
  const res = await fetch("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  }).then((r) => (r.ok ? r.json() : Promise.reject(r)));
  currentEntries = res.entries;
  filter.classList.remove("hidden");
  downloadBtn.disabled = false;
  setStatus(`Imported ${res.count} entries.`);
  showToolbar();
  render();
});

// ---- download ----
downloadBtn.addEventListener("click", () => {
  if (!currentEntries.length) return;
  let url = "/api/playlist?";
  if (currentJobId) url += "job_id=" + currentJobId;
  else url += "raw=" + encodeURIComponent(JSON.stringify(currentEntries));
  const a = document.createElement("a");
  a.href = url;
  a.download = "streamforge.m3u";
  a.click();
});

filter.addEventListener("input", (e) => {
  filters.text = e.target.value;
  render();
});

// ---- VOD catalog (persistent storage) ----
$("#catalogBtn").addEventListener("click", async () => {
  setStatus("Loading catalog…");
  const p = new URLSearchParams({
    kind: filters.kind === "all" ? "" : filters.kind,
    group: filters.group,
    q: filters.text,
    art: filters.art ? "1" : "",
  });
  const res = await fetch("/api/vod?" + p.toString()).then((r) => r.json());
  currentEntries = res.entries;
  showToolbar();
  render();
  $("#catInfo").textContent = `${res.count} in catalog`;
  setStatus(`Loaded ${res.count} catalog entries.`);
});

$("#enrichCatBtn").addEventListener("click", async () => {
  setStatus("Enriching catalog from TMDB…");
  const res = await fetch("/api/vod/enrich", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: $("#tmdbKey").value.trim() }),
  }).then((r) => (r.ok ? r.json() : Promise.reject(r)));
  $("#catInfo").textContent = `catalog: ${res.total}`;
  setStatus(`Catalog enriched: ${res.updated} updated (${res.total} total).`);
  // refresh grid from catalog
  $("#catalogBtn").click();
});

// kind segmented control
$("#kindSeg").querySelectorAll("button").forEach((b) => {
  b.addEventListener("click", () => {
    $("#kindSeg").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    filters.kind = b.dataset.kind;
    render();
  });
});

$("#groupSel").addEventListener("change", (e) => {
  filters.group = e.target.value;
  render();
});

$("#artOnly").addEventListener("change", (e) => {
  filters.art = e.target.checked;
  render();
});

// ---- reveal toolbar + filters once we have entries ----
function showToolbar() {
  $("#toolbar").classList.remove("hidden");
  $("#filterbar").classList.remove("hidden");
  populateGroups();
}

function populateGroups() {
  const sel = $("#groupSel");
  const cur = sel.value;
  const groups = [...new Set(currentEntries.map((e) => e.group || "Ungrouped"))].sort();
  sel.innerHTML =
    '<option value="">All groups</option>' +
    groups.map((g) => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join("");
  sel.value = groups.includes(cur) ? cur : "";
}

// prefill TMDB key state from server config (so personal key isn't pasted each time)
fetch("/api/config")
  .then((r) => r.json())
  .then((c) => {
    if (c.has_tmdb_key) {
      $("#tmdbKey").placeholder = "TMDB key set via config/env ✓";
      $("#tmdbKey").disabled = true;
    }
  })
  .catch(() => {});

// ---- artwork (TMDB) ----
$("#artworkBtn").addEventListener("click", async () => {
  const apiKey = $("#tmdbKey").value.trim();
  if (!apiKey) return setStatus("Enter a TMDB API key first.");
  if (!currentEntries.length) return;
  setStatus("Fetching artwork from TMDB…");
  const res = await fetch("/api/artwork", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entries: currentEntries, api_key: apiKey }),
  }).then((r) => (r.ok ? r.json() : Promise.reject(r)));
  currentEntries = res.entries;
  render();
  const withArt = currentEntries.filter((e) => e.logo).length;
  setStatus(`Artwork: ${withArt}/${res.count} entries got posters.`);
});

// ---- EPG (XMLTV) ----
$("#epgBtn").addEventListener("click", async () => {
  if (!currentEntries.length) return;
  const epgUrl = $("#epgUrl").value.trim();
  setStatus("Building EPG…");
  const res = await fetch("/api/epg", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entries: currentEntries, url: epgUrl, days: 1 }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    return setStatus("EPG error: " + (err.detail || res.status));
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "streamforge.xml";
  a.click();
  setStatus("EPG downloaded (streamforge.xml). Load it in your player's EPG setting.");
});

function setStatus(msg) {
  status.textContent = msg;
}

// ---- details modal ----
const modal = $("#modal");
function openModal(e) {
  $("#modalArt").src = e.logo || thumb(e.name);
  $("#modalTitle").textContent = e.name;
  const meta = [e.kind || "Live", e.year, e.group]
    .filter(Boolean)
    .join(" · ");
  $("#modalMeta").textContent = meta;
  $("#modalOverview").textContent = e.overview || "No description available.";
  $("#modalPlay").href = e.url;
  modal.classList.remove("hidden");
}
$("#modalClose").addEventListener("click", () => modal.classList.add("hidden"));
modal.addEventListener("click", (ev) => {
  if (ev.target === modal) modal.classList.add("hidden");
});

// ---- PWA install ----
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

render();

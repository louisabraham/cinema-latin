"use strict";

const TZ = "Europe/Paris";
const PAGE = 60;
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmtDay = new Intl.DateTimeFormat("fr-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fmtHM = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fmtWd = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, weekday: "short" });
const fmtLong = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
const fmtShort = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const dayKey = (d) => fmtDay.format(d);
const hm = (d) => fmtHM.format(d).replace(":", "h");

let DATA = null;
let FILMS = {};
let CINES = {};
let SHOWS = [];
let pos = null;
let limit = PAGE;

const state = Object.assign(
  { view: "seances", day: "now", zone: "Quartier Latin", vo: false, old: false, near: false, q: "", cines: [], sort: "next" },
  load()
);

function load() {
  try { return JSON.parse(localStorage.getItem("cl-state") || "{}"); } catch { return {}; }
}
function save() {
  try {
    const { view, zone, vo, old, cines, sort } = state;
    localStorage.setItem("cl-state", JSON.stringify({ view, zone, vo, old, cines, sort }));
  } catch { /* storage unavailable */ }
}

/* ------------------------------------------------------------ helpers */

const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, " ").trim();

function score(f) {
  const r = f.ratings || {};
  const vals = [];
  if (r.imdb) vals.push(r.imdb);
  if (r.senscritique) vals.push(r.senscritique);
  if (r.letterboxd) vals.push(r.letterboxd * 2);
  if (r.allocine_spect) vals.push(r.allocine_spect * 2);
  if (r.allocine_press) vals.push(r.allocine_press * 2);
  if (!vals.length) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function dist(c) {
  if (!pos) return null;
  const R = 6371, rad = Math.PI / 180;
  const dLat = (c.lat - pos.lat) * rad, dLon = (c.lon - pos.lon) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(pos.lat * rad) * Math.cos(c.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
const fmtDist = (km) => (km == null ? "" : km < 1 ? `${Math.round(km * 1000 / 50) * 50} m` : `${km.toFixed(1).replace(".", ",")} km`);

const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
function directions(c) {
  const dest = `${c.name}, ${c.address}`;
  if (isIOS) return `https://maps.apple.com/?daddr=${encodeURIComponent(c.address)}&dirflg=r`;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(dest)}&travelmode=transit`;
}
const citymapper = (c) => `https://citymapper.com/directions?endcoord=${c.lat},${c.lon}&endname=${encodeURIComponent(c.name)}&endaddress=${encodeURIComponent(c.address)}`;

function facts(f) {
  const bits = [];
  if (f.directors?.length) bits.push(f.directors.slice(0, 2).join(", "));
  if (f.year) bits.push(f.year);
  if (f.duration) bits.push(`${Math.floor(f.duration / 60)}h${String(f.duration % 60).padStart(2, "0")}`);
  return bits.join(" · ");
}

function label(s) {
  // the cinema's own label, when it says more than the film title (event, cycle...)
  if (!s.title) return "";
  const f = FILMS[s.film];
  const a = norm(s.title), b = norm(f.title);
  if (a === b || a.includes(b) && a.length - b.length < 6) return "";
  if (f.original_title && a === norm(f.original_title)) return "";
  return s.title;
}

/* ------------------------------------------------------------ filtering */

function baseFilter(s) {
  const c = CINES[s.cinema], f = FILMS[s.film];
  if (!c || !f) return false;
  if (state.cines.length) {
    if (!state.cines.includes(s.cinema)) return false;
  } else if (state.zone !== "all" && c.group !== state.zone) return false;
  if (state.vo && s.version === "VF") return false;
  if (state.old && !(f.year && f.year <= new Date().getFullYear() - 20)) return false;
  if (state.q) {
    const q = norm(state.q);
    const hay = norm([f.title, f.original_title, (f.directors || []).join(" "), (f.cast || []).join(" "), s.title, c.name].join(" "));
    if (!q.split(" ").every((w) => hay.includes(w))) return false;
  }
  return true;
}

function visibleShows() {
  const now = Date.now() - 10 * 60e3;
  return SHOWS.filter((s) => {
    if (s.t < now) return false;
    if (state.day !== "now" && s.day !== state.day) return false;
    return baseFilter(s);
  });
}

/* ------------------------------------------------------------ controls */

function renderDays() {
  const el = $("#days");
  const today = new Date();
  const days = [];
  for (let i = 0; i < 14; i++) days.push(new Date(today.getTime() + i * 864e5));
  const counts = {};
  for (const s of SHOWS) counts[s.day] = (counts[s.day] || 0) + 1;
  el.innerHTML =
    `<button role="tab" class="now" data-day="now" aria-selected="${state.day === "now"}"><b>à partir</b><span>Maintenant</span></button>` +
    days.map((d, i) => {
      const k = dayKey(d);
      const wd = i === 0 ? "Auj." : i === 1 ? "Dem." : fmtWd.format(d);
      const n = Number(k.slice(8));
      return `<button role="tab" data-day="${k}" aria-selected="${state.day === k}" ${counts[k] ? "" : 'style="opacity:.35"'}><b>${wd}</b><span>${n}</span></button>`;
    }).join("");
}

function renderChips() {
  const list = DATA.cinemas.filter((c) => state.zone === "all" || c.group === state.zone || state.cines.includes(c.id));
  $("#chips").innerHTML =
    `<button class="all" data-cine="" aria-pressed="${!state.cines.length}">Toutes</button>` +
    list.map((c) => `<button data-cine="${c.id}" aria-pressed="${state.cines.includes(c.id)}">${esc(c.short || c.name)}</button>`).join("");
}

function syncControls() {
  document.querySelectorAll(".views button").forEach((b) => b.setAttribute("aria-selected", b.dataset.view === state.view));
  document.querySelectorAll("#zone button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.zone === state.zone));
  $("#f-vo").setAttribute("aria-pressed", state.vo);
  $("#f-old").setAttribute("aria-pressed", state.old);
  $("#f-near").setAttribute("aria-pressed", state.near);
  $("#days").style.display = state.view === "cinemas" ? "none" : "";
  renderDays();
  renderChips();
}

/* ------------------------------------------------------------ views */

function scoreHTML(f) {
  const sc = score(f);
  return sc ? `<span class="score ${sc >= 7.5 ? "hi" : ""}" title="Note moyenne /10">${sc.toFixed(1)}</span>` : "";
}

function rowHTML(s) {
  const f = FILMS[s.film], c = CINES[s.cinema];
  const soon = s.t - Date.now() < 45 * 60e3;
  const started = s.t < Date.now();
  const lbl = label(s);
  const tags = (s.tags || []).slice(0, 2).map((t) => `<span class="badge tag">${esc(t)}</span>`).join("");
  const d = dist(c);
  return `<button class="row" data-film="${esc(s.film)}">
    <div class="t ${soon ? "soon" : ""}">${hm(s.date)}${started ? "<small>en cours</small>" : ""}</div>
    <div>
      <h3>${esc(f.title)}</h3>
      ${lbl ? `<div class="sub">${esc(lbl)}</div>` : ""}
      <div class="sub">${esc(facts(f))}</div>
      <div class="where">${esc(c.name)}${d != null ? `<span class="dist">${fmtDist(d)}</span>` : ""}${tags}</div>
    </div>
    <div class="side">${s.version ? `<span class="badge ${s.version === "VO" ? "vo" : ""}">${s.version}</span>` : ""}${scoreHTML(f)}</div>
  </button>`;
}

function renderSeances() {
  const shows = visibleShows();
  if (!shows.length) return empty();
  let html = "", cur = "";
  const slice = shows.slice(0, limit);
  // within one hour, nearest cinema first when "Près de moi" is on
  const groups = [];
  for (const s of slice) {
    const hdr = (state.day === "now" && s.day !== dayKey(new Date()) ? fmtLong.format(s.date) + " · " : "") + fmtHM.format(s.date).slice(0, 2) + "h";
    if (hdr !== cur) { groups.push({ hdr, items: [] }); cur = hdr; }
    groups[groups.length - 1].items.push(s);
  }
  for (const g of groups) {
    if (state.near && pos) g.items.sort((a, b) => dist(CINES[a.cinema]) - dist(CINES[b.cinema]) || a.t - b.t);
    html += `<div class="hour">${esc(g.hdr)}</div>` + g.items.map(rowHTML).join("");
  }
  if (shows.length > limit) html += `<button class="more" data-more>Plus de séances (${shows.length - limit})</button>`;
  $("#main").innerHTML = html;
}

function renderFilms() {
  const shows = visibleShows();
  if (!shows.length) return empty();
  const by = new Map();
  for (const s of shows) {
    if (!by.has(s.film)) by.set(s.film, { f: FILMS[s.film], next: s, n: 0, cines: new Set() });
    const e = by.get(s.film);
    e.n++; e.cines.add(s.cinema);
  }
  let list = [...by.values()];
  if (state.sort === "score") list.sort((a, b) => (score(b.f) ?? 0) - (score(a.f) ?? 0));
  const seg = `<div class="filters"><div class="seg" id="sort">
      <button data-sort="next" aria-pressed="${state.sort === "next"}">Prochaine séance</button>
      <button data-sort="score" aria-pressed="${state.sort === "score"}">Mieux notés</button></div></div>`;
  $("#main").innerHTML = seg + `<div class="grid">` + list.map(({ f, next, n, cines }) => `
    <button class="film" data-film="${esc(f.id)}">
      ${f.poster ? `<img class="poster" loading="lazy" src="${esc(f.poster)}" alt="">` : `<div class="noposter">${esc(f.title)}</div>`}
      <div class="info">
        <h3>${esc(f.title)}</h3>
        <div class="sub">${esc(facts(f))}</div>
        ${scoreHTML(f)}
        <div class="next">${state.day === "now" ? fmtWd.format(next.date) + " " : ""}${hm(next.date)} · ${esc(CINES[next.cinema].short || CINES[next.cinema].name)}${n > 1 ? ` · ${n} séances` : ""}</div>
      </div>
    </button>`).join("") + `</div>`;
}

function renderCinemas() {
  const now = Date.now() - 10 * 60e3;
  const today = dayKey(new Date());
  const groups = { "Quartier Latin": [], Ailleurs: [] };
  for (const c of DATA.cinemas) (groups[c.group] ||= []).push(c);
  let html = "";
  for (const [g, list] of Object.entries(groups)) {
    if (state.near && pos) list.sort((a, b) => dist(a) - dist(b));
    html += `<h2 class="group-title">${esc(g)}</h2>` + list.map((c) => {
      const up = SHOWS.filter((s) => s.cinema === c.id && s.t >= now);
      const nToday = up.filter((s) => s.day === today).length;
      const next = up[0];
      const d = dist(c);
      return `<button class="cine" data-cinema="${c.id}">
        <div><h3>${esc(c.name)}</h3><div class="addr">${esc(c.address)}${d != null ? " · " + fmtDist(d) : ""}</div>
        <div class="addr">${next ? `Prochaine : ${hm(next.date)} ${esc(FILMS[next.film].title)}` : "Pas de séance connue"}</div></div>
        <div class="n">${nToday}<small>auj.</small></div></button>`;
    }).join("");
  }
  $("#main").innerHTML = html;
}

function empty() {
  $("#main").innerHTML = `<div class="empty"><div class="big">Rien</div><p>Aucune séance pour ces filtres.</p></div>`;
}

function render() {
  syncControls();
  if (state.view === "films") renderFilms();
  else if (state.view === "cinemas") renderCinemas();
  else renderSeances();
  save();
}

/* ------------------------------------------------------------ sheets */

const RATING_NAMES = [
  ["imdb", "IMDb", "/10", "imdb"],
  ["letterboxd", "Letterboxd", "/5", "letterboxd"],
  ["senscritique", "SensCritique", "/10", "senscritique"],
  ["allocine_press", "Presse", "/5", "allocine"],
  ["allocine_spect", "Spectateurs", "/5", "allocine"],
  ["rotten_tomatoes", "Rotten T.", "%", "rotten_tomatoes"],
  ["metacritic", "Metacritic", "", "metacritic"],
];

function slotHTML(s, showFilm) {
  const c = CINES[s.cinema], f = FILMS[s.film];
  const lbl = label(s);
  const tags = (s.tags || []).map((t) => `<span class="badge tag">${esc(t)}</span>`).join(" ");
  const d = dist(c);
  return `<div class="slot">
    <div>
      <div class="when"><b>${hm(s.date)}</b> ${esc(fmtShort.format(s.date))} ${s.version ? `<span class="badge ${s.version === "VO" ? "vo" : ""}">${s.version}</span>` : ""}</div>
      ${showFilm ? `<div class="cn"><a href="#film=${esc(s.film)}">${esc(f.title)}</a></div><div class="lbl">${esc(facts(f))}</div>`
                 : `<div class="cn"><a href="#cinema=${c.id}">${esc(c.name)}</a>${d != null ? ` <span class="lbl">${fmtDist(d)}</span>` : ""}</div>`}
      ${lbl ? `<div class="lbl">${esc(lbl)}</div>` : ""}
      ${s.room ? `<div class="lbl">${esc(s.room)}</div>` : ""}
      ${tags ? `<div>${tags}</div>` : ""}
    </div>
    <div class="acts">
      ${showFilm ? "" : `<a class="btn go" href="${directions(c)}" target="_blank" rel="noopener">Y aller</a>`}
      ${s.url ? `<a class="btn" href="${esc(s.url)}" target="_blank" rel="noopener">Réserver</a>` : ""}
    </div>
  </div>`;
}

function filmSheet(id) {
  const f = FILMS[id];
  if (!f) return "";
  const now = Date.now() - 10 * 60e3;
  const shows = SHOWS.filter((s) => s.film === id && s.t >= now);
  const r = f.ratings || {}, L = f.links || {};
  const ratings = RATING_NAMES.filter(([k]) => r[k]).map(([k, name, unit, link]) =>
    `<a href="${esc(L[link] || "#")}" target="_blank" rel="noopener"><b>${r[k]}<small>${unit}</small></b><span>${name}</span></a>`).join("");
  const genres = [...(f.countries || []).slice(0, 2), ...(f.genres || []).slice(0, 3)].map((g) => `<span class="badge">${esc(g)}</span>`).join("");
  return `
    <div class="hero ${f.poster ? "" : "noimg"}">
      ${f.poster ? `<img src="${esc(f.poster)}" alt="Affiche">` : ""}
      <div>
        <h2 id="sheet-title">${esc(f.title)}</h2>
        ${f.original_title && norm(f.original_title) !== norm(f.title) ? `<div class="orig">${esc(f.original_title)}</div>` : ""}
        <div class="facts">${esc(facts(f))}</div>
        ${f.cast?.length ? `<div class="facts" style="color:var(--mute)">avec ${esc(f.cast.slice(0, 3).join(", "))}</div>` : ""}
        <div class="genres">${genres}</div>
      </div>
    </div>
    ${ratings ? `<div class="ratings">${ratings}</div>` : ""}
    ${f.synopsis ? `<p class="synopsis">${esc(f.synopsis)}</p>` : ""}
    <div class="sec">Prochaines séances · ${shows.length}</div>
    ${shows.map((s) => slotHTML(s, false)).join("") || `<p class="synopsis">Plus de séance prévue.</p>`}`;
}

function cinemaSheet(id) {
  const c = CINES[id];
  if (!c) return "";
  const now = Date.now() - 10 * 60e3;
  const shows = SHOWS.filter((s) => s.cinema === id && s.t >= now).slice(0, 80);
  const d = dist(c);
  const src = { site: "site de la salle", allocine: "Allociné", previous: "données précédentes" }[c.source] || "—";
  return `
    <div class="hero noimg"><div>
      <h2 id="sheet-title">${esc(c.name)}</h2>
      <div class="facts">${esc(c.address)}${d != null ? " · " + fmtDist(d) : ""}</div>
      <div class="genres">${(c.tags || []).map((t) => `<span class="badge">${esc(t)}</span>`).join("")}</div>
    </div></div>
    <div class="addr-box">
      <div class="acts" style="justify-content:flex-start">
        <a class="btn go" href="${directions(c)}" target="_blank" rel="noopener">Y aller</a>
        <a class="btn" href="${citymapper(c)}" target="_blank" rel="noopener">Citymapper</a>
        <a class="btn" href="${esc(c.url)}" target="_blank" rel="noopener">Site</a>
      </div>
      <div class="lbl" style="font-size:12px;color:var(--mute)">Source : ${src}</div>
    </div>
    <div class="sec">Prochaines séances · ${shows.length}</div>
    ${shows.map((s) => slotHTML(s, true)).join("") || `<p class="synopsis">Pas de séance connue.</p>`}`;
}

function openFromHash() {
  const m = location.hash.match(/^#(film|cinema)=(.+)$/);
  const sheet = $("#sheet");
  if (!m || !DATA) { sheet.hidden = true; document.body.style.overflow = ""; return; }
  const id = decodeURIComponent(m[2]);
  const html = m[1] === "film" ? filmSheet(id) : cinemaSheet(id);
  if (!html) { sheet.hidden = true; return; }
  $("#sheet-body").innerHTML = html;
  sheet.hidden = false;
  document.body.style.overflow = "hidden";
  $(".sheet-card").scrollTop = 0;
}

function closeSheet() {
  if (history.state?.sheet) history.back();
  else { history.replaceState(null, "", location.pathname + location.search); openFromHash(); }
}

function go(hash) {
  history.pushState({ sheet: true }, "", hash);
  openFromHash();
}

/* ------------------------------------------------------------ events */

document.addEventListener("click", (e) => {
  const t = e.target.closest("button, a");
  if (!t) return;
  if (t.matches("[data-close]")) return closeSheet();
  if (t.matches("a[href^='#film='], a[href^='#cinema=']")) { e.preventDefault(); return go(t.getAttribute("href")); }
  if (t.dataset.film) return go(`#film=${encodeURIComponent(t.dataset.film)}`);
  if (t.dataset.cinema) return go(`#cinema=${encodeURIComponent(t.dataset.cinema)}`);
  if (t.dataset.view) { state.view = t.dataset.view; limit = PAGE; window.scrollTo(0, 0); return render(); }
  if (t.dataset.day) { state.day = t.dataset.day; limit = PAGE; return render(); }
  if (t.dataset.zone) { state.zone = t.dataset.zone; state.cines = []; limit = PAGE; return render(); }
  if (t.dataset.sort) { state.sort = t.dataset.sort; return render(); }
  if ("cine" in t.dataset) {
    const id = t.dataset.cine;
    if (!id) state.cines = [];
    else state.cines = state.cines.includes(id) ? state.cines.filter((x) => x !== id) : [...state.cines, id];
    limit = PAGE;
    return render();
  }
  if (t.matches("[data-more]")) { limit += PAGE * 2; return render(); }
  if (t.id === "f-vo") { state.vo = !state.vo; return render(); }
  if (t.id === "f-old") { state.old = !state.old; return render(); }
  if (t.id === "f-near") return toggleNear();
  if (t.classList.contains("logo")) { e.preventDefault(); state.view = "seances"; state.day = "now"; window.scrollTo(0, 0); return render(); }
});

document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#sheet").hidden) closeSheet(); });
window.addEventListener("popstate", openFromHash);
window.addEventListener("hashchange", openFromHash);

let qTimer;
$("#q").addEventListener("input", (e) => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { state.q = e.target.value; limit = PAGE; render(); }, 150);
});

function toggleNear() {
  if (state.near) { state.near = false; return render(); }
  if (!navigator.geolocation) return alert("Géolocalisation indisponible.");
  $("#f-near").textContent = "…";
  navigator.geolocation.getCurrentPosition(
    (p) => { pos = { lat: p.coords.latitude, lon: p.coords.longitude }; state.near = true; $("#f-near").textContent = "Près de moi"; render(); },
    () => { $("#f-near").textContent = "Près de moi"; alert("Position refusée ou indisponible."); },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
  );
}

/* ------------------------------------------------------------ boot */

const SHORT = {
  "La Filmothèque du Quartier Latin": "Filmothèque",
  "Christine Cinéma Club": "Christine",
  "Écoles Cinéma Club": "Écoles",
  "La Cinémathèque française": "Cinémathèque",
  "Fondation Jérôme Seydoux-Pathé": "Fondation Pathé",
  "Saint-André des Arts": "St-André",
  "Studio des Ursulines": "Ursulines",
  "Espace Saint-Michel": "St-Michel",
};

async function boot() {
  try {
    const r = await fetch("data/showtimes.json", { cache: "no-cache" });
    DATA = await r.json();
  } catch (e) {
    $("#main").innerHTML = `<div class="empty"><div class="big">Erreur</div><p>Impossible de charger les séances.</p></div>`;
    return;
  }
  FILMS = DATA.films;
  for (const c of DATA.cinemas) { c.short = SHORT[c.name] || c.name.replace(/^(Le |La |Les |L')/, ""); CINES[c.id] = c; }
  SHOWS = DATA.showtimes.map((s) => {
    const date = new Date(s.start);
    return Object.assign(s, { date, t: date.getTime(), day: dayKey(date) });
  }).sort((a, b) => a.t - b.t);
  const gen = new Date(DATA.generated_at);
  $("#meta").textContent = `${SHOWS.length} séances · ${Object.keys(FILMS).length} films · ${DATA.cinemas.length} salles · mis à jour le ${fmtLong.format(gen)} à ${hm(gen)}`;
  if (state.day !== "now" && state.day < dayKey(new Date())) state.day = "now";
  render();
  openFromHash();
  // keep "Maintenant" current
  setInterval(() => { if (state.day === "now" && state.view !== "cinemas" && $("#sheet").hidden) render(); }, 60e3);
}

boot();

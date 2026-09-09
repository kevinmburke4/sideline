/* Sideline: college football notebook. No build step, no accounts, no keys.
   Data: ESPN's public scoreboard feed. Notes: localStorage on this device. */
'use strict';

const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard';
const CONF = {
  '1': 'ACC', '4': 'Big 12', '5': 'Big Ten', '8': 'SEC', '9': 'Pac-12', '12': 'C-USA', '15': 'MAC',
  '17': 'MWC', '18': 'Indep.', '37': 'Sun Belt', '151': 'American',
};
const CHIP_CONFS = ['8', '5', '1', '4', '151', '17', '37', '15', '12', '9', '18'];
const DB_KEY = 'sideline.v1';

/* ---------- storage ---------- */
function getJSON(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
function setJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch (e) { toast('Storage full. Export your notes and clear cached data.'); return false; }
}
const db = Object.assign({
  priority: [],        // team ids, in order
  watched: {},         // gameId -> true | false
  notes: [],           // see addNote()
  teams: {},           // teamId -> {id, school, mascot, abbr, logo, conf, record, rank, seen}
  meta: null,          // {season, currentWeek, weeks: [{value, label, detail, start, end}]}
  ui: { conf: 'all', season: null, week: null, notesFilter: 'all' },
}, getJSON(DB_KEY, {}));
function persist() { setJSON(DB_KEY, db); }

/* ---------- helpers ---------- */
const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const fmtTime = (iso) => new Date(iso).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
const fmtDay = (iso) => new Date(iso).toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
const fmtStamp = (ms) => new Date(ms).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
const teamName = (t) => t ? t.school : 'Unknown';
const isP4 = (conf) => ['1', '4', '5', '8'].includes(String(conf));

let toastTimer;
function toast(msg, ms = 2200) {
  const el = $('#toast'); el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

/* ---------- ESPN ---------- */
function normTeam(x) {
  const t = x.team || {};
  const rank = x.curatedRank && x.curatedRank.current;
  const rec = (x.records || []).find((r) => r.type === 'total');
  return {
    id: String(t.id), school: t.location || t.shortDisplayName || t.displayName, mascot: t.name || '', abbr: t.abbreviation || '',
    logo: t.logo || '', color: t.color || '', conf: t.conferenceId ? String(t.conferenceId) : '',
    score: x.score != null && x.score !== '' ? Number(x.score) : null, winner: !!x.winner,
    rank: rank && rank <= 25 ? rank : null, record: rec ? rec.summary : '',
  };
}
function normGame(ev) {
  const c = ev.competitions[0];
  const home = c.competitors.find((x) => x.homeAway === 'home') || c.competitors[0];
  const away = c.competitors.find((x) => x.homeAway === 'away') || c.competitors[1];
  const st = c.status && c.status.type ? c.status.type : {};
  return {
    id: String(ev.id), date: ev.date, name: ev.name, shortName: ev.shortName,
    season: ev.season && ev.season.year, week: ev.week && ev.week.number,
    state: st.state || 'pre', completed: !!st.completed, statusShort: st.shortDetail || '', statusDetail: st.detail || '',
    venue: c.venue ? c.venue.fullName : '', city: c.venue && c.venue.address ? [c.venue.address.city, c.venue.address.state].filter(Boolean).join(', ') : '',
    neutral: !!c.neutralSite, confGame: !!c.conferenceCompetition, tv: c.broadcast || '',
    headline: c.headlines && c.headlines[0] ? (c.headlines[0].shortLinkText || '') : '',
    home: normTeam(home), away: normTeam(away),
  };
}
function weekKey(season, week) { return `sideline.wk.${season}.${week}`; }
function getWeek(season, week) { return getJSON(weekKey(season, week), null); }
function isStale(pack) {
  const age = Date.now() - pack.fetchedAt;
  if (pack.games.length && pack.games.every((g) => g.completed)) return age > 3 * 864e5;
  if (pack.games.some((g) => g.state === 'in')) return age > 2 * 60e3;
  const now = Date.now();
  const soon = pack.games.some((g) => { const d = new Date(g.date) - now; return !g.completed && d < 6 * 3600e3 && d > -5 * 3600e3; });
  return age > (soon ? 10 * 60e3 : 6 * 3600e3);
}
function indexTeams(games) {
  for (const g of games) for (const t of [g.home, g.away]) {
    const prev = db.teams[t.id];
    if (!prev || !prev.seen || new Date(g.date) >= new Date(prev.seen)) {
      db.teams[t.id] = { id: t.id, school: t.school, mascot: t.mascot, abbr: t.abbr, logo: t.logo, color: t.color,
        conf: t.conf || (prev && prev.conf) || '', record: t.record || (prev && prev.record) || '', rank: t.rank, seen: g.date };
    }
  }
}
async function fetchWeek(season, week, { force = false } = {}) {
  const cached = season && week ? getWeek(season, week) : null;
  if (cached && !force && !isStale(cached)) return cached;
  const qs = new URLSearchParams({ groups: '80', limit: '400', seasontype: '2' });
  if (season) qs.set('dates', season);
  if (week) qs.set('week', week);
  let data;
  try {
    const res = await fetch(`${ESPN}?${qs}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`ESPN ${res.status}`);
    data = await res.json();
  } catch (e) {
    if (cached) return cached;
    throw e;
  }
  const games = (data.events || []).map(normGame).sort((a, b) => new Date(a.date) - new Date(b.date));
  const pack = { season: data.season.year, week: data.week.number, fetchedAt: Date.now(), games };
  // calendar for week navigation
  try {
    const cal = (data.leagues[0].calendar || []).find((c) => c.value === '2' || /regular/i.test(c.label)) || data.leagues[0].calendar[0];
    const weeks = (cal.entries || []).map((e) => ({ value: Number(e.value), label: e.label, detail: e.detail, start: e.startDate, end: e.endDate }));
    const cur = (season && week) ? (db.meta && db.meta.currentWeek) : data.week.number;
    db.meta = { season: data.season.year, currentWeek: cur || data.week.number, weeks, updated: Date.now() };
  } catch { /* keep old meta */ }
  setJSON(weekKey(pack.season, pack.week), pack);
  indexTeams(games);
  persist();
  return pack;
}
function allCachedGames() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && k.startsWith('sideline.wk.')) { const p = getJSON(k, null); if (p) out.push(...p.games); }
  }
  return out.sort((a, b) => new Date(a.date) - new Date(b.date));
}
function findGame(id) {
  const season = db.ui.season, week = db.ui.week;
  const p = season && week ? getWeek(season, week) : null;
  const hit = p && p.games.find((g) => g.id === id);
  return hit || allCachedGames().find((g) => g.id === id) || null;
}

/* ---------- notes ---------- */
function addNote({ gameId = null, teamIds = [], kind, text, season, week }) {
  const g = gameId ? findGame(gameId) : null;
  const note = {
    id: uid(), createdAt: Date.now(), updatedAt: Date.now(), kind, text: text.trim(),
    gameId, gameLabel: g ? `${g.away.school} at ${g.home.school}` : '', teamIds: [...new Set(teamIds.map(String))],
    teamNames: teamIds.map((id) => teamName(db.teams[id])),
    season: season || (g && g.season) || (db.meta && db.meta.season) || null, week: week || (g && g.week) || null,
  };
  db.notes.unshift(note); persist(); return note;
}
function deleteNote(id) { db.notes = db.notes.filter((n) => n.id !== id); persist(); }
function notesForGame(id) { return db.notes.filter((n) => n.gameId === id); }
function notesForTeam(id, { excludeGame = null } = {}) {
  return db.notes.filter((n) => n.teamIds.includes(String(id)) && (!excludeGame || n.gameId !== excludeGame));
}

/* ---------- dictation ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let activeDictation = null;
function attachDictation(btn, ta, interimEl) {
  if (!SR) {
    btn.hidden = true;
    interimEl.textContent = 'Tip: tap the microphone key on the keyboard to dictate.';
    return null;
  }
  let rec = null, active = false, base = '', sessionFinal = '';
  const setBtn = () => { btn.classList.toggle('listening', active); btn.textContent = active ? '■ Stop' : '🎤 Dictate'; };
  function start() {
    if (activeDictation && activeDictation !== api) activeDictation.stop();
    rec = new SR(); rec.lang = 'en-US'; rec.continuous = true; rec.interimResults = true;
    active = true; activeDictation = api; setBtn();
    base = ta.value.trim() ? ta.value.replace(/\s+$/, '') + ' ' : '';
    sessionFinal = '';
    rec.onresult = (e) => {
      let fin = '', inter = '';
      for (const r of e.results) { if (r.isFinal) fin += r[0].transcript + ' '; else inter += r[0].transcript; }
      sessionFinal = fin;
      ta.value = (base + fin).replace(/\s+$/, '');
      interimEl.textContent = inter;
    };
    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { toast('Microphone access was blocked.'); stop(); }
      else if (e.error === 'network') { toast('Speech service unavailable. Try the keyboard mic.'); stop(); }
    };
    rec.onend = () => {
      if (!active) return;
      base = (base + sessionFinal).replace(/\s+$/, '') + (sessionFinal ? ' ' : '');
      sessionFinal = '';
      try { rec.start(); } catch { stop(); }
    };
    try { rec.start(); } catch (e) { toast('Could not start dictation.'); stop(); }
  }
  function stop() {
    active = false; setBtn(); interimEl.textContent = '';
    if (activeDictation === api) activeDictation = null;
    try { rec && rec.stop(); } catch { /* ignore */ }
  }
  const api = { start, stop, get active() { return active; } };
  btn.addEventListener('click', () => (active ? stop() : start()));
  return api;
}
function composerHTML({ id, placeholder, kind }) {
  return `
  <div class="stack" data-composer="${esc(id)}">
    <textarea id="ta-${esc(id)}" placeholder="${esc(placeholder)}" autocapitalize="sentences"></textarea>
    <div class="interim" id="interim-${esc(id)}"></div>
    <div class="row between wrap">
      <div class="row">
        <button class="btn" id="dict-${esc(id)}" type="button">🎤 Dictate</button>
        <span class="badge">${esc(kind)}</span>
      </div>
      <button class="btn primary" id="save-${esc(id)}" type="button">Save note</button>
    </div>
  </div>`;
}
function wireComposer(id, onSave) {
  const ta = $(`#ta-${id}`), btn = $(`#dict-${id}`), interim = $(`#interim-${id}`), save = $(`#save-${id}`);
  const dict = attachDictation(btn, ta, interim);
  save.addEventListener('click', () => {
    if (dict && dict.active) dict.stop();
    const text = ta.value.trim();
    if (!text) { toast('Nothing to save yet.'); ta.focus(); return; }
    onSave(text); ta.value = '';
  });
  return dict;
}

/* ---------- rendering ---------- */
const view = $('#view');
const titleEl = $('#title');
const actionsEl = $('#topbar-actions');
function setChrome(title, actionsHTML = '', tab = null) {
  titleEl.textContent = title; actionsEl.innerHTML = actionsHTML;
  document.querySelectorAll('.tabbar a').forEach((a) => a.classList.toggle('active', a.dataset.tab === tab));
}
function teamLine(t, g) {
  const loser = g.completed && !t.winner && g.home.score !== g.away.score;
  return `<div class="team-line ${loser ? 'loser' : ''}">
    <img src="${esc(t.logo)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
    <span class="rank">${t.rank ? '#' + t.rank : ''}</span>
    <span class="name">${esc(t.school)}${db.priority.includes(t.id) ? ' <span class="badge pri">★</span>' : ''}</span>
    <span class="rec">${esc(t.record)}</span>
    <span class="score">${g.state === 'pre' ? '' : (t.score ?? '')}</span>
  </div>`;
}
function gameCard(g) {
  const watched = db.watched[g.id];
  const nCount = notesForGame(g.id).length;
  const status = g.state === 'in' ? `<span class="status live">${esc(g.statusShort)}</span>`
    : g.completed ? `<span class="status final">${esc(g.statusShort)}</span>`
    : `<span class="status">${esc(fmtTime(g.date))}</span>`;
  const meta = [g.tv, g.neutral ? 'Neutral site' : '', g.confGame ? 'Conf.' : ''].filter(Boolean);
  return `<a class="card tap game" href="#game/${esc(g.id)}">
    <div class="teams">${teamLine(g.away, g)}${teamLine(g.home, g)}</div>
    <div class="side">${status}
      <div class="badges">${watched === true ? '<span class="badge watched">Watched</span>' : watched === false ? '<span class="badge">Skipped</span>' : ''}${nCount ? `<span class="badge notes">${nCount} note${nCount > 1 ? 's' : ''}</span>` : ''}</div>
    </div>
    ${meta.length ? `<div class="game-meta">${meta.map(esc).join(' • ')}</div>` : ''}
  </a>`;
}
function noteCard(n, { showGame = true } = {}) {
  const where = n.gameId && showGame ? `<a href="#game/${esc(n.gameId)}">${esc(n.gameLabel)}</a>` : (n.teamNames || []).map(esc).join(', ');
  return `<div class="note ${esc(n.kind)}" data-note="${esc(n.id)}">
    <div class="hdr"><span>${where}${n.week ? ` • Wk ${n.week}` : ''}</span><span>${esc(fmtStamp(n.createdAt))}</span></div>
    <div class="body">${esc(n.text)}</div>
    <div class="acts"><button class="btn sm ghost" data-copy="${esc(n.id)}" type="button">Copy</button><button class="btn sm ghost danger" data-del="${esc(n.id)}" type="button">Delete</button></div>
  </div>`;
}
function wireNoteActions(root, rerender) {
  root.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', () => {
    if (confirm('Delete this note?')) { deleteNote(b.dataset.del); toast('Deleted'); rerender(); }
  }));
  root.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    const n = db.notes.find((x) => x.id === b.dataset.copy);
    try { await navigator.clipboard.writeText(n.text); toast('Copied'); } catch { toast('Copy failed'); }
  }));
}

/* ---------- views ---------- */
async function renderGames() {
  setChrome('Sideline', '<button class="btn sm icon" id="refresh" title="Refresh" type="button">↻</button>', 'games');
  let season = db.ui.season, week = db.ui.week;
  let pack = null;
  if (!season || !week) {
    view.innerHTML = '<div class="empty"><span class="spinner"></span> Loading this week…</div>';
    try { pack = await fetchWeek(null, null); season = db.ui.season = pack.season; week = db.ui.week = pack.week; persist(); }
    catch (e) { view.innerHTML = `<div class="empty">Could not reach ESPN.<br><span class="small">${esc(e.message)}</span><br><br><button class="btn" onclick="location.reload()">Retry</button></div>`; return; }
    // warm the previous week in the background so team pages and last week's results are ready
    if (week > 1) fetchWeek(season, week - 1).catch(() => {});
  } else {
    pack = getWeek(season, week);
    if (!pack) {
      view.innerHTML = '<div class="empty"><span class="spinner"></span> Loading week…</div>';
      try { pack = await fetchWeek(season, week); }
      catch (e) { view.innerHTML = `<div class="empty">Could not load week ${week}.<br><span class="small">${esc(e.message)}</span></div>`; return; }
    } else if (isStale(pack)) {
      fetchWeek(season, week).then((p) => { if (p.fetchedAt !== pack.fetchedAt && location.hash.replace('#', '') === 'games') renderGames(); }).catch(() => {});
    }
  }
  $('#refresh').addEventListener('click', async () => {
    $('#refresh').innerHTML = '<span class="spinner"></span>';
    try { await fetchWeek(season, week, { force: true }); toast('Updated'); } catch { toast('Refresh failed'); }
    renderGames();
  });

  const weeks = (db.meta && db.meta.weeks) || [];
  const wk = weeks.find((w) => w.value === week);
  const minW = weeks.length ? weeks[0].value : 1, maxW = weeks.length ? weeks[weeks.length - 1].value : week;
  const conf = db.ui.conf || 'all';
  let games = pack.games;
  if (conf === 'mine') games = games.filter((g) => db.priority.includes(g.home.id) || db.priority.includes(g.away.id));
  else if (conf === 'ranked') games = games.filter((g) => g.home.rank || g.away.rank);
  else if (conf === 'p4') games = games.filter((g) => isP4(g.home.conf) || isP4(g.away.conf));
  else if (conf !== 'all') games = games.filter((g) => g.home.conf === conf || g.away.conf === conf);

  const chip = (val, label) => `<button class="chip ${conf === val ? 'on' : ''}" data-conf="${val}" type="button">${label}</button>`;
  const chips = [chip('all', 'All FBS'), chip('mine', '★ Mine'), chip('ranked', 'Ranked'), chip('p4', 'Power 4'), ...CHIP_CONFS.map((c) => chip(c, CONF[c]))].join('');

  // priority games first, then by day (ranked first within a day, then kickoff)
  const pri = (g) => Math.min(...[g.home.id, g.away.id].map((id) => { const i = db.priority.indexOf(id); return i < 0 ? 99 : i; }));
  const best = (g) => Math.min(g.home.rank || 99, g.away.rank || 99);
  const mine = games.filter((g) => pri(g) < 99).sort((a, b) => pri(a) - pri(b) || new Date(a.date) - new Date(b.date));
  const rest = games.filter((g) => pri(g) === 99);
  const byDay = new Map();
  for (const g of rest) { const k = fmtDay(g.date); if (!byDay.has(k)) byDay.set(k, []); byDay.get(k).push(g); }
  for (const list of byDay.values()) list.sort((a, b) => best(a) - best(b) || new Date(a.date) - new Date(b.date));

  const watchedCount = pack.games.filter((g) => db.watched[g.id] === true).length;
  view.innerHTML = `
    <div class="weeknav">
      <button class="btn icon" id="prevw" type="button" ${week <= minW ? 'disabled' : ''}>‹</button>
      <div class="label"><strong>Week ${week}</strong><span class="small muted">${esc(wk ? wk.detail : '')} • ${pack.games.length} games${watchedCount ? ` • ${watchedCount} watched` : ''}</span></div>
      <button class="btn icon" id="nextw" type="button" ${week >= maxW ? 'disabled' : ''}>›</button>
    </div>
    <div class="chips">${chips}</div>
    ${games.length === 0 ? '<div class="empty">No games match this filter.</div>' : ''}
    ${mine.length ? `<h3 class="mb">Your teams</h3>${mine.map(gameCard).join('')}` : ''}
    ${[...byDay.entries()].map(([day, list]) => `<h3 class="mb mt">${esc(day)}</h3>${list.map(gameCard).join('')}`).join('')}
    <p class="tiny muted center mt">Scores from ESPN • updated ${esc(fmtStamp(pack.fetchedAt))}</p>`;
  $('#prevw').addEventListener('click', () => { db.ui.week = week - 1; persist(); renderGames(); window.scrollTo(0, 0); });
  $('#nextw').addEventListener('click', () => { db.ui.week = week + 1; persist(); renderGames(); window.scrollTo(0, 0); });
  view.querySelectorAll('[data-conf]').forEach((b) => b.addEventListener('click', () => { db.ui.conf = b.dataset.conf; persist(); renderGames(); }));
}

function renderGame(id) {
  const g = findGame(id);
  setChrome(g ? `Week ${g.week}` : 'Game', '<a class="btn sm" href="#games">‹ Games</a>', 'games');
  if (!g) { view.innerHTML = '<div class="empty">Game not found in cached data.<br><a class="btn mt" href="#games">Back to games</a></div>'; return; }
  const watched = db.watched[g.id];
  const kind = g.completed ? 'recap' : 'preview';
  const hero = (t) => `<a class="t ${g.completed && !t.winner && g.home.score !== g.away.score ? 'loser' : ''}" href="#team/${esc(t.id)}">
      <img src="${esc(t.logo)}" alt="" onerror="this.style.visibility='hidden'">
      <span class="name">${t.rank ? '#' + t.rank + ' ' : ''}${esc(t.school)}</span>
      <span class="sub">${esc(t.record)}${t.conf && CONF[t.conf] ? ' • ' + CONF[t.conf] : ''}</span></a>`;
  const mid = g.state === 'pre'
    ? `<div class="score small muted">${esc(fmtTime(g.date))}</div><div class="tiny muted">${g.neutral ? 'vs' : 'at'}</div>`
    : `<div class="score">${g.away.score ?? ''}–${g.home.score ?? ''}</div><div class="tiny ${g.state === 'in' ? 'status live' : 'muted'}">${esc(g.statusShort)}</div>`;
  const teamSection = (t) => {
    const ns = notesForTeam(t.id, { excludeGame: g.id });
    if (!ns.length) return `<h3 class="mt mb">Your notes on ${esc(t.school)}</h3><p class="small muted">Nothing yet this season.</p>`;
    return `<h3 class="mt mb">Your notes on ${esc(t.school)} <span class="muted">(${ns.length})</span></h3>
      ${ns.slice(0, 4).map((n) => noteCard(n)).join('')}
      ${ns.length > 4 ? `<a class="btn sm ghost" href="#team/${esc(t.id)}">All ${ns.length} notes on ${esc(t.school)} ›</a>` : ''}`;
  };
  const own = notesForGame(g.id);
  view.innerHTML = `
    <div class="card">
      <div class="hero">${hero(g.away)}<div class="mid">${mid}</div>${hero(g.home)}</div>
      <dl class="kv">
        <dt>When</dt><dd>${esc(new Date(g.date).toLocaleString([], { weekday: 'long', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))}</dd>
        ${g.tv ? `<dt>TV</dt><dd>${esc(g.tv)}</dd>` : ''}
        ${g.venue ? `<dt>Where</dt><dd>${esc(g.venue)}${g.city ? ', ' + esc(g.city) : ''}</dd>` : ''}
        ${g.headline ? `<dt>Recap</dt><dd class="small">${esc(g.headline)}</dd>` : ''}
      </dl>
    </div>
    <div class="seg mb">
      <button type="button" class="${watched === true ? 'on' : ''}" data-w="1">👁 Watched</button>
      <button type="button" class="${watched === false ? 'on no' : ''}" data-w="0">Didn't watch</button>
    </div>
    <div class="card">
      <h3 class="mb">${kind === 'recap' ? 'What stood out?' : 'Pre-game thought'}</h3>
      ${composerHTML({ id: 'g', placeholder: kind === 'recap' ? 'Tap Dictate and talk, or type…' : 'Anything on this one?', kind })}
      <div class="row wrap mt small muted" id="tags"></div>
    </div>
    <div id="own">${own.length ? `<h3 class="mb">Notes on this game</h3>${own.map((n) => noteCard(n, { showGame: false })).join('')}` : ''}</div>
    ${teamSection(g.away)}${teamSection(g.home)}`;

  // team tags: both teams on by default, plus optional extra team via search
  const tags = new Set([g.away.id, g.home.id]);
  const tagsEl = $('#tags');
  function drawTags() {
    tagsEl.innerHTML = `<span>Tag:</span>${[...tags].map((id) => `<button class="chip ${tags.has(id) ? 'on' : ''}" data-tag="${esc(id)}" type="button">${esc(teamName(db.teams[id]))}</button>`).join('')}<button class="chip" id="addtag" type="button">+ team</button>`;
    tagsEl.querySelectorAll('[data-tag]').forEach((b) => b.addEventListener('click', () => {
      if (tags.size === 1 && tags.has(b.dataset.tag)) { toast('Keep at least one team'); return; }
      tags.delete(b.dataset.tag); drawTags();
    }));
    $('#addtag').addEventListener('click', () => pickTeam((id) => { tags.add(id); drawTags(); }));
  }
  drawTags();
  view.querySelectorAll('[data-w]').forEach((b) => b.addEventListener('click', () => {
    const val = b.dataset.w === '1';
    db.watched[g.id] = db.watched[g.id] === val ? undefined : val;
    if (db.watched[g.id] === undefined) delete db.watched[g.id];
    persist(); renderGame(id);
  }));
  wireComposer('g', (text) => {
    addNote({ gameId: g.id, teamIds: [...tags], kind, text });
    if (kind === 'recap' && db.watched[g.id] === undefined) { db.watched[g.id] = true; persist(); }
    toast('Saved'); renderGame(id);
  });
  wireNoteActions(view, () => renderGame(id));
}

function pickTeam(onPick) {
  const list = Object.values(db.teams).filter((t) => CONF[t.conf]).sort((a, b) => a.school.localeCompare(b.school));
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:30;display:flex;align-items:flex-end;';
  overlay.innerHTML = `<div class="card" style="width:100%;max-height:70vh;overflow:auto;border-radius:16px 16px 0 0;margin:0;padding-bottom:calc(16px + var(--safe-b))">
    <div class="row between mb"><h2>Tag a team</h2><button class="btn sm" id="closepick" type="button">Close</button></div>
    <input type="search" id="pickq" placeholder="Search teams" autocomplete="off">
    <div id="picklist" class="mt"></div></div>`;
  document.body.appendChild(overlay);
  const draw = (q) => {
    const ql = q.trim().toLowerCase();
    const hits = (ql ? list.filter((t) => (t.school + ' ' + t.mascot + ' ' + t.abbr).toLowerCase().includes(ql)) : list).slice(0, 40);
    $('#picklist', overlay).innerHTML = hits.map((t) => `<div class="list-row" data-pick="${esc(t.id)}"><img src="${esc(t.logo)}" alt=""><div class="grow"><div class="title">${esc(t.school)}</div><div class="sub">${esc(t.mascot)} • ${CONF[t.conf] || ''}</div></div></div>`).join('') || '<p class="muted small">No matches.</p>';
    overlay.querySelectorAll('[data-pick]').forEach((r) => r.addEventListener('click', () => { onPick(r.dataset.pick); overlay.remove(); }));
  };
  draw('');
  $('#pickq', overlay).addEventListener('input', (e) => draw(e.target.value));
  $('#closepick', overlay).addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  setTimeout(() => $('#pickq', overlay).focus(), 50);
}

function renderTeams() {
  setChrome('Teams', '', 'teams');
  const teams = Object.values(db.teams).filter((t) => CONF[t.conf]);
  if (!teams.length) { view.innerHTML = '<div class="empty">Teams appear here once a week of games has loaded.<br><a class="btn mt" href="#games">Go to games</a></div>'; return; }
  const q = db.ui.teamQuery || '';
  const row = (t) => `<div class="list-row">
      <button class="star ${db.priority.includes(t.id) ? 'on' : ''}" data-star="${esc(t.id)}" type="button" aria-label="Favorite">★</button>
      <a class="grow row" href="#team/${esc(t.id)}"><img src="${esc(t.logo)}" alt="" loading="lazy"><div class="grow"><div class="title">${t.rank ? '#' + t.rank + ' ' : ''}${esc(t.school)}</div><div class="sub">${esc(t.mascot)} • ${esc(t.record)} • ${notesForTeam(t.id).length} notes</div></div></a>
    </div>`;
  const ql = q.trim().toLowerCase();
  const filtered = ql ? teams.filter((t) => (t.school + ' ' + t.mascot + ' ' + t.abbr).toLowerCase().includes(ql)) : teams;
  const mine = db.priority.map((id) => db.teams[id]).filter(Boolean).filter((t) => filtered.includes(t));
  const byConf = new Map();
  for (const t of filtered.sort((a, b) => a.school.localeCompare(b.school))) { const k = CONF[t.conf]; if (!byConf.has(k)) byConf.set(k, []); byConf.get(k).push(t); }
  const order = [...byConf.keys()].sort((a, b) => CHIP_CONFS.indexOf(Object.keys(CONF).find((k) => CONF[k] === a)) - CHIP_CONFS.indexOf(Object.keys(CONF).find((k) => CONF[k] === b)));
  view.innerHTML = `
    <input type="search" id="teamq" placeholder="Search ${teams.length} teams" value="${esc(q)}" autocomplete="off">
    <p class="tiny muted">Star your teams to pin their games to the top of every week.</p>
    ${mine.length ? `<h3 class="mb">Your teams</h3>${mine.map(row).join('')}` : ''}
    ${order.map((c) => `<h3 class="mt mb">${esc(c)}</h3>${byConf.get(c).map(row).join('')}`).join('')}`;
  $('#teamq').addEventListener('input', (e) => { db.ui.teamQuery = e.target.value; persist(); renderTeams(); const i = $('#teamq'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); });
  view.querySelectorAll('[data-star]').forEach((b) => b.addEventListener('click', () => { toggleStar(b.dataset.star); renderTeams(); }));
}
function toggleStar(id) {
  const i = db.priority.indexOf(id);
  if (i >= 0) db.priority.splice(i, 1); else db.priority.push(id);
  persist();
}

function renderTeam(id) {
  const t = db.teams[id];
  setChrome(t ? t.school : 'Team', '<a class="btn sm" href="javascript:history.back()">‹ Back</a>', 'teams');
  if (!t) { view.innerHTML = '<div class="empty">Team not found.</div>'; return; }
  const games = allCachedGames().filter((g) => g.home.id === id || g.away.id === id);
  const notes = notesForTeam(id);
  const gameRow = (g) => {
    const me = g.home.id === id ? g.home : g.away, opp = g.home.id === id ? g.away : g.home;
    const res = g.completed ? `${me.winner ? 'W' : (me.score === opp.score ? 'T' : 'L')} ${me.score}–${opp.score}` : g.state === 'in' ? g.statusShort : fmtTime(g.date);
    return `<a class="list-row" href="#game/${esc(g.id)}"><img src="${esc(opp.logo)}" alt="" loading="lazy"><div class="grow"><div class="title">${g.home.id === id || g.neutral ? 'vs' : 'at'} ${opp.rank ? '#' + opp.rank + ' ' : ''}${esc(opp.school)}</div><div class="sub">Week ${g.week} • ${esc(res)}${db.watched[g.id] === true ? ' • Watched' : ''}</div></div></a>`;
  };
  view.innerHTML = `
    <div class="card">
      <div class="row between">
        <div class="row"><img src="${esc(t.logo)}" alt="" style="width:48px;height:48px;object-fit:contain">
          <div><h2>${t.rank ? '#' + t.rank + ' ' : ''}${esc(t.school)} ${esc(t.mascot)}</h2><div class="small muted">${CONF[t.conf] || ''} • ${esc(t.record || '')}</div></div></div>
        <button class="star ${db.priority.includes(id) ? 'on' : ''}" id="star" type="button" aria-label="Favorite">★</button>
      </div>
    </div>
    <div class="card"><h3 class="mb">General thought on ${esc(t.school)}</h3>${composerHTML({ id: 't', placeholder: 'Not tied to a game…', kind: 'general' })}</div>
    <h3 class="mb">Your notes <span class="muted">(${notes.length})</span></h3>
    <div id="tnotes">${notes.length ? notes.map((n) => noteCard(n)).join('') : '<p class="small muted">Nothing yet this season.</p>'}</div>
    <h3 class="mt mb">Season <span class="muted">(${games.length} loaded)</span></h3>
    ${games.length ? games.map(gameRow).join('') : '<p class="small muted">Load more weeks from the Games tab or “Load full season” in More.</p>'}`;
  $('#star').addEventListener('click', () => { toggleStar(id); renderTeam(id); });
  wireComposer('t', (text) => { addNote({ teamIds: [id], kind: 'general', text, week: db.meta && db.meta.currentWeek }); toast('Saved'); renderTeam(id); });
  wireNoteActions(view, () => renderTeam(id));
}

function renderNotes() {
  setChrome('Notes', `<button class="btn sm" id="export" type="button">Export</button>`, 'notes');
  const q = db.ui.noteQuery || '';
  const f = db.ui.notesFilter || 'all';
  const ql = q.trim().toLowerCase();
  let notes = db.notes;
  if (f !== 'all') notes = notes.filter((n) => n.kind === f);
  if (ql) notes = notes.filter((n) => (n.text + ' ' + n.gameLabel + ' ' + (n.teamNames || []).join(' ')).toLowerCase().includes(ql));
  const chip = (v, l) => `<button class="chip ${f === v ? 'on' : ''}" data-f="${v}" type="button">${l}</button>`;
  view.innerHTML = `
    <input type="search" id="noteq" placeholder="Search ${db.notes.length} notes" value="${esc(q)}" autocomplete="off">
    <div class="chips mt">${chip('all', 'All')}${chip('recap', 'Recaps')}${chip('preview', 'Previews')}${chip('general', 'General')}</div>
    ${notes.length ? notes.map((n) => noteCard(n)).join('') : '<div class="empty">No notes yet. Open a game and tap Dictate.</div>'}`;
  $('#noteq').addEventListener('input', (e) => { db.ui.noteQuery = e.target.value; persist(); renderNotes(); const i = $('#noteq'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); });
  view.querySelectorAll('[data-f]').forEach((b) => b.addEventListener('click', () => { db.ui.notesFilter = b.dataset.f; persist(); renderNotes(); }));
  $('#export').addEventListener('click', exportNotes);
  wireNoteActions(view, renderNotes);
}

async function exportNotes() {
  const payload = { app: 'sideline', version: 1, exportedAt: new Date().toISOString(), priority: db.priority, watched: db.watched, notes: db.notes };
  const json = JSON.stringify(payload, null, 2);
  const file = new File([json], `sideline-notes-${new Date().toISOString().slice(0, 10)}.json`, { type: 'application/json' });
  if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], title: 'Sideline notes' }); return; } catch { /* fall through */ }
  }
  const a = document.createElement('a'); a.href = URL.createObjectURL(file); a.download = file.name; document.body.appendChild(a); a.click(); a.remove();
}

function renderSettings() {
  setChrome('More', '', 'settings');
  const weeks = allCachedGames().reduce((s, g) => s.add(g.week), new Set());
  let bytes = 0; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); bytes += (localStorage.getItem(k) || '').length * 2; }
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  view.innerHTML = `
    <div class="card stack">
      <h3>Data</h3>
      <dl class="kv"><dt>Season</dt><dd>${db.meta ? db.meta.season : '—'}</dd><dt>Current week</dt><dd>${db.meta ? db.meta.currentWeek : '—'}</dd><dt>Weeks cached</dt><dd>${[...weeks].sort((a, b) => a - b).join(', ') || 'none'}</dd><dt>Notes</dt><dd>${db.notes.length}</dd><dt>Storage</dt><dd>${(bytes / 1024).toFixed(0)} KB</dd></dl>
      <button class="btn" id="loadall" type="button">Load full season so far</button>
      <button class="btn ghost" id="clearcache" type="button">Clear cached schedule (keeps notes)</button>
    </div>
    <div class="card stack">
      <h3>Notes backup</h3>
      <button class="btn" id="export2" type="button">Export notes (JSON)</button>
      <label class="btn ghost" for="importf">Import notes (JSON)</label><input id="importf" type="file" accept="application/json,.json" hidden>
      <button class="btn ghost danger" id="wipe" type="button">Delete all notes</button>
    </div>
    <div class="card stack">
      <h3>Install on iPhone</h3>
      ${standalone ? '<p class="small">Installed. You are running from the home screen.</p>' : '<p class="small">In Safari tap <b>Share</b>, then <b>Add to Home Screen</b>. It opens full screen and works offline for anything already loaded.</p>'}
      <p class="small muted">Dictation uses Safari’s built-in speech recognition. If the Dictate button is missing, use the microphone key on the keyboard instead.</p>
    </div>
    <p class="tiny muted center">Scores and schedules from ESPN’s public feed. Notes never leave this device unless you export them.</p>`;
  $('#loadall').addEventListener('click', async () => {
    if (!db.meta) { toast('Load a week first'); return; }
    const btn = $('#loadall'); btn.disabled = true;
    const cur = db.meta.currentWeek;
    for (let w = 1; w <= cur; w++) {
      btn.textContent = `Loading week ${w} of ${cur}…`;
      try { await fetchWeek(db.meta.season, w); } catch { /* keep going */ }
    }
    toast('Season loaded'); renderSettings();
  });
  $('#clearcache').addEventListener('click', () => {
    const keys = []; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith('sideline.wk.')) keys.push(k); }
    keys.forEach((k) => localStorage.removeItem(k)); db.ui.season = null; db.ui.week = null; persist(); toast('Cache cleared'); renderSettings();
  });
  $('#export2').addEventListener('click', exportNotes);
  $('#importf').addEventListener('change', async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      if (!Array.isArray(data.notes)) throw new Error('No notes array');
      const have = new Set(db.notes.map((n) => n.id));
      const added = data.notes.filter((n) => n && n.id && !have.has(n.id));
      db.notes = [...added, ...db.notes].sort((a, b) => b.createdAt - a.createdAt);
      if (Array.isArray(data.priority)) db.priority = [...new Set([...db.priority, ...data.priority.map(String)])];
      if (data.watched && typeof data.watched === 'object') db.watched = { ...data.watched, ...db.watched };
      persist(); toast(`Imported ${added.length} notes`); renderSettings();
    } catch (err) { toast('Import failed: ' + err.message); }
  });
  $('#wipe').addEventListener('click', () => {
    if (confirm(`Delete all ${db.notes.length} notes? Export first if you want a copy.`)) { db.notes = []; db.watched = {}; persist(); toast('Notes deleted'); renderSettings(); }
  });
}

/* ---------- router ---------- */
function route() {
  if (activeDictation) activeDictation.stop();
  const h = (location.hash || '#games').slice(1);
  const [name, id] = h.split('/');
  window.scrollTo(0, 0);
  switch (name) {
    case 'game': return renderGame(id);
    case 'teams': return renderTeams();
    case 'team': return renderTeam(id);
    case 'notes': return renderNotes();
    case 'settings': return renderSettings();
    default: return renderGames();
  }
}
window.addEventListener('hashchange', route);
route();

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}

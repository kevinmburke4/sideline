/* Sideline Feed. Reads drops from feed/ and renders them in the Feed tab.
   Loaded after app.js and shares its globals (db, esc, $, toast, setChrome, CONF, getJSON, setJSON).
   Feed state lives in its own key and holds only post IDs, never content. */
'use strict';
(() => {
  const FEED_KEY = 'sideline.feed.v1';
  const CONF_CHIPS = ['SEC', 'Big Ten', 'ACC', 'Big 12'];
  const LISTEN_TYPES = new Set(['audio', 'video']);

  const feedState = Object.assign({ seen: {}, played: {} }, getJSON(FEED_KEY, {}));
  let saveTimer = null;
  function saveFeed() { clearTimeout(saveTimer); saveTimer = setTimeout(() => setJSON(FEED_KEY, feedState), 300); }

  // in-memory caches for this page load
  let accounts = {};
  let index = null;
  const drops = new Map();           // dropId -> posts[]
  let filter = 'all';
  let observer = null;
  let scrollMemo = 0;

  /* ---------- loading ---------- */
  async function loadFeed() {
    const idxRes = await fetch('feed/index.json', { cache: 'no-store' });
    if (!idxRes.ok) throw new Error(`feed index ${idxRes.status}`);
    index = await idxRes.json();
    if (!Object.keys(accounts).length) {
      try { accounts = await (await fetch('accounts.json', { cache: 'no-store' })).json(); } catch { accounts = {}; }
    }
    const wanted = (index.drops || []).slice(0, 2);
    await Promise.all(wanted.map(async (d) => {
      if (drops.has(d.id)) return;
      const r = await fetch(`feed/${d.id}/posts.json`, { cache: 'no-store' });
      if (!r.ok) return;
      const j = await r.json();
      drops.set(d.id, Array.isArray(j) ? j : (j.posts || []));
    }));
    for (const k of Object.keys(feedState.seen)) if (!(index.drops || []).some((d) => d.id === k)) delete feedState.seen[k];
    for (const k of Object.keys(feedState.played)) if (!(index.drops || []).some((d) => d.id === k)) delete feedState.played[k];
    saveFeed();
    return wanted.filter((d) => drops.has(d.id));
  }

  /* ---------- ordering ---------- */
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function rng(seed) {
    return () => { seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function orderPosts(dropId, posts) {
    const out = [];
    for (const tier of [1, 2, 3]) {
      const arr = posts.filter((p) => Math.min(3, Math.max(1, Number(p.tier) || 3)) === tier);
      const r = rng(hash(`${dropId}:${tier}`));
      for (let i = arr.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [arr[i], arr[j]] = [arr[j], arr[i]]; }
      out.push(...arr);
    }
    return out;
  }
  function postSeconds(p) {
    if (p.type === 'carousel') return (p.slides || []).length * 10;
    if (LISTEN_TYPES.has(p.type)) return Number(p.duration) || 60;
    return 20;
  }
  function fmtMinutes(sec) { const m = Math.round(sec / 60); return m < 1 ? 'under a minute' : m === 1 ? 'about 1 min' : `about ${m} min`; }
  function dropLabel(d) {
    const kind = d.kind === 'mon' ? 'Monday drop' : d.kind === 'fri' ? 'Friday drop' : 'Sample drop';
    return `Week ${d.week} · ${kind}`;
  }

  /* ---------- filtering ---------- */
  let confByName = null;
  function teamConf(name) {
    if (!confByName) { confByName = {}; for (const t of Object.values(db.teams)) confByName[t.school] = CONF[t.conf] || null; }
    return confByName[name] || null;
  }
  function teamIdByName(name) {
    const t = Object.values(db.teams).find((x) => x.school === name);
    return t ? t.id : null;
  }
  function matches(p) {
    if (filter === 'all') return true;
    if (filter === 'listen') return LISTEN_TYPES.has(p.type);
    if (filter === 'read') return !LISTEN_TYPES.has(p.type);
    if (p.type === 'slate' && p.conference === filter) return true;
    return (p.teams || []).some((n) => teamConf(n) === filter);
  }

  /* ---------- read state ---------- */
  function seenSet(dropId) { return new Set(feedState.seen[dropId] || []); }
  function markSeen(dropId, postId) {
    const arr = feedState.seen[dropId] || (feedState.seen[dropId] = []);
    if (arr.includes(postId)) return false;
    arr.push(postId); saveFeed(); return true;
  }

  /* ---------- rendering pieces ---------- */
  function assetURL(dropId, path) {
    if (!path) return '';
    if (/^(https?:)?\/\//.test(path) || path.startsWith('/')) return path;
    return `feed/${dropId}/${path}`;
  }
  function initials(name) { return name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase(); }
  function acct(p) {
    return accounts[p.account] || { name: p.account || 'Sideline', beat: '', color: '#3a4553' };
  }
  function postHead(p) {
    const a = acct(p);
    return `<div class="post-head">
      <span class="avatar" style="background:${esc(a.color || '#3a4553')}">${esc(a.initials || initials(a.name))}</span>
      <div class="grow"><div class="post-acct">${esc(a.name)}</div><div class="tiny muted">${esc(a.beat || '')}</div></div>
      <span class="tiny muted post-tier">T${esc(p.tier || 3)}</span>
    </div>`;
  }
  function teamChips(p) {
    const names = p.teams || [];
    if (!names.length) return '';
    return `<div class="post-teams">${names.map((n) => {
      const id = teamIdByName(n);
      return id ? `<a class="chip" href="#team/${esc(id)}">${esc(n)}</a>` : `<span class="chip">${esc(n)}</span>`;
    }).join('')}${p.gameId ? `<a class="chip" href="#game/${esc(p.gameId)}">Game page ›</a>` : ''}</div>`;
  }
  function sources(p) {
    const s = p.sources || [];
    if (!s.length) return '';
    return `<div class="post-sources tiny muted">Source: ${s.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.label)}</a>`).join(' · ')}</div>`;
  }
  function renderText(p, dropId) {
    return `${postHead(p)}
      ${p.title ? `<div class="post-title">${esc(p.title)}</div>` : ''}
      ${p.body ? `<div class="post-body">${esc(p.body)}</div>` : ''}
      ${p.image ? `<img class="post-img" src="${esc(assetURL(dropId, p.image))}" alt="${esc(p.alt || '')}" loading="lazy">` : ''}
      ${teamChips(p)}${sources(p)}`;
  }
  function renderCarousel(p, dropId) {
    const slides = (p.slides || []).slice(0, 6);
    return `${postHead(p)}
      ${p.title ? `<div class="post-title">${esc(p.title)}</div>` : ''}
      ${p.body ? `<div class="post-body">${esc(p.body)}</div>` : ''}
      <div class="slides">
        <div class="track">${slides.map((s) => `<figure class="slide"><img src="${esc(assetURL(dropId, s.image))}" alt="${esc(s.alt || '')}" loading="lazy">${s.caption ? `<figcaption>${esc(s.caption)}</figcaption>` : ''}</figure>`).join('')}</div>
        <div class="dots">${slides.map((_, i) => `<span class="dot ${i === 0 ? 'on' : ''}"></span>`).join('')}</div>
      </div>
      ${teamChips(p)}${sources(p)}`;
  }
  function renderXPost(p) {
    const when = p.postedAt ? new Date(p.postedAt).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
    return `<a class="xpost-link" href="${esc(p.url || 'https://x.com')}" target="_blank" rel="noopener">
      <div class="post-head">
        <span class="avatar x">𝕏</span>
        <div class="grow"><div class="post-acct">${esc(p.name || p.handle || '')}</div><div class="tiny muted">@${esc((p.handle || '').replace(/^@/, ''))}${when ? ' · ' + esc(when) : ''}</div></div>
      </div>
      <div class="post-body">${esc(p.text || p.body || '')}</div>
      ${p.hasMedia ? '<div class="xmedia tiny muted">▣ Photo or video on X</div>' : ''}
      <div class="tiny muted">Open on X ›</div>
    </a>${teamChips(p)}`;
  }
  function renderSlate(p) {
    const rows = (p.games || []).map((g) => {
      const t = g.kickoff ? new Date(g.kickoff).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : '';
      const nums = [g.spread, g.total != null && g.total !== '' ? `O/U ${g.total}` : ''].filter(Boolean).join(' · ');
      const inner = `<div class="grow"><div class="slate-teams">${esc(g.away)} at ${esc(g.home)}</div><div class="tiny muted">${esc([t, g.tv].filter(Boolean).join(' · '))}</div></div>${nums ? `<div class="slate-nums tiny muted">${esc(nums)}</div>` : ''}`;
      return g.gameId ? `<a class="slate-row" href="#game/${esc(g.gameId)}">${inner}</a>` : `<div class="slate-row">${inner}</div>`;
    }).join('');
    return `${postHead(p)}
      <div class="post-title">${esc(p.title || `${p.conference || ''} slate`)}</div>
      ${p.body ? `<div class="post-body">${esc(p.body)}</div>` : ''}
      <div class="slate">${rows}</div>${sources(p)}`;
  }
  function renderStub(p) {
    return `${postHead(p)}<div class="post-title">${esc(p.title || '')}</div><div class="post-body muted">${esc(p.type)} posts arrive in a later phase.</div>${teamChips(p)}`;
  }
  function postCard(p, dropId, seen) {
    let inner;
    switch (p.type) {
      case 'text': inner = renderText(p, dropId); break;
      case 'carousel': inner = renderCarousel(p, dropId); break;
      case 'xpost': inner = renderXPost(p); break;
      case 'slate': inner = renderSlate(p); break;
      default: inner = renderStub(p);
    }
    return `<article class="post ${esc(p.type)} ${seen ? 'seen' : ''}" data-post="${esc(p.id)}" data-drop="${esc(dropId)}">${inner}</article>`;
  }

  /* ---------- the view ---------- */
  function dropStats(d) {
    const posts = drops.get(d.id) || [];
    const seen = seenSet(d.id);
    const left = posts.filter((p) => !seen.has(p.id));
    return { total: posts.length, left: left.length, seconds: left.reduce((s, p) => s + postSeconds(p), 0) };
  }
  function updateHeader(newest) {
    const el = $('#feed-stats'); if (!el || !newest) return;
    const s = dropStats(newest);
    el.textContent = s.left === 0 ? `All ${s.total} posts seen` : `${s.left} of ${s.total} posts left · ${fmtMinutes(s.seconds)}`;
    const card = $('#caught'); if (card) card.hidden = s.left !== 0;
  }

  async function renderFeed() {
    setChrome('Feed', '<button class="btn sm icon" id="feed-refresh" title="Refresh" type="button">↻</button>', 'feed');
    if (observer) { observer.disconnect(); observer = null; }
    confByName = null;
    const hadDrops = drops.size > 0;
    if (!hadDrops) view.innerHTML = '<div class="empty"><span class="spinner"></span> Loading the feed…</div>';
    let wanted;
    try { wanted = await loadFeed(); }
    catch (e) {
      if (!hadDrops) { view.innerHTML = `<div class="empty">Could not load the feed.<br><span class="small">${esc(e.message)}</span><br><br><button class="btn" onclick="location.reload()">Retry</button></div>`; return; }
      wanted = (index && index.drops || []).slice(0, 2).filter((d) => drops.has(d.id));
      toast('Showing the last loaded feed');
    }
    if (location.hash.replace('#', '').split('/')[0] !== 'feed') return; // user navigated away while loading
    if (!wanted.length) { view.innerHTML = '<div class="empty">No drops yet. The first one will appear here.</div>'; return; }

    const newest = wanted[0];
    const chip = (v, l) => `<button class="chip ${filter === v ? 'on' : ''}" data-filter="${esc(v)}" type="button">${esc(l)}</button>`;
    const chips = [chip('all', 'All'), chip('listen', 'Listen'), chip('read', 'Read'), ...CONF_CHIPS.map((c) => chip(c, c))].join('');
    const isSample = newest.kind === 'sample' || /^sample/.test(newest.id);

    const sections = wanted.map((d, i) => {
      const posts = orderPosts(d.id, drops.get(d.id)).filter(matches);
      const seen = seenSet(d.id);
      const cards = posts.map((p) => postCard(p, d.id, seen.has(p.id))).join('');
      const caught = i === 0 ? `<div class="post caught" id="caught" hidden><div class="caught-mark">✓</div><div><strong>You're caught up for Week ${esc(d.week)}</strong><div class="small muted">Everything in this drop has been seen.</div></div></div>` : '';
      const divider = i > 0 ? `<div class="feed-divider"><span>Earlier · ${esc(dropLabel(d))}</span></div>` : '';
      return `${divider}<section data-dropsec="${esc(d.id)}">${cards || '<p class="small muted center">Nothing in this drop matches the filter.</p>'}${caught}</section>`;
    }).join('');

    view.innerHTML = `
      <div class="feed-head">
        <div class="grow"><strong>${esc(dropLabel(newest))}</strong>${isSample ? ' <span class="badge sample">SAMPLE CONTENT</span>' : ''}<div class="small muted" id="feed-stats"></div></div>
      </div>
      <div class="chips">${chips}</div>
      ${sections}
      <p class="tiny muted center mt">Drops are made outside the app and published to the feed folder.</p>`;
    updateHeader(newest);

    $('#feed-refresh').addEventListener('click', async () => {
      $('#feed-refresh').innerHTML = '<span class="spinner"></span>';
      drops.clear(); await renderFeed(); toast('Feed refreshed');
    });
    view.querySelectorAll('[data-filter]').forEach((b) => b.addEventListener('click', () => { filter = b.dataset.filter; renderFeed(); }));
    wireCarousels();
    wireSeen(newest);
    if (scrollMemo) { const y = scrollMemo; scrollMemo = 0; requestAnimationFrame(() => window.scrollTo(0, y)); }
  }

  function wireCarousels() {
    view.querySelectorAll('.slides').forEach((c) => {
      const track = c.querySelector('.track'), dots = c.querySelectorAll('.dot');
      let raf = 0;
      track.addEventListener('scroll', () => {
        if (raf) return;
        raf = requestAnimationFrame(() => {
          raf = 0;
          const w = track.clientWidth || 1;
          const i = Math.round(track.scrollLeft / w);
          dots.forEach((d, k) => d.classList.toggle('on', k === i));
        });
      }, { passive: true });
    });
  }

  function wireSeen(newest) {
    if (!('IntersectionObserver' in window)) return;
    const timers = new Map();
    observer = new IntersectionObserver((entries) => {
      for (const en of entries) {
        const el = en.target, id = el.dataset.post, dropId = el.dataset.drop;
        if (en.isIntersecting && en.intersectionRatio >= 0.6) {
          if (timers.has(id)) continue;
          timers.set(id, setTimeout(() => {
            timers.delete(id);
            if (markSeen(dropId, id)) { el.classList.add('seen'); updateHeader(newest); }
            observer && observer.unobserve(el);
          }, 1000));
        } else if (timers.has(id)) { clearTimeout(timers.get(id)); timers.delete(id); }
      }
    }, { threshold: [0, 0.6, 1] });
    view.querySelectorAll('.post[data-post]:not(.seen)').forEach((el) => observer.observe(el));
  }

  // remember scroll position when leaving the feed so coming back from a team or game page lands in the same spot
  window.addEventListener('hashchange', (e) => {
    const from = (new URL(e.oldURL).hash || '#games').slice(1).split('/')[0];
    if (from === 'feed') scrollMemo = window.scrollY;
  });

  window.renderFeed = renderFeed;
  // app.js routed before this file loaded; if the page opened on the feed, render it now
  if ((location.hash || '#games').slice(1).split('/')[0] === 'feed') renderFeed();
})();

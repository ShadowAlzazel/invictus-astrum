<script>
  // The tactical layer: every entity as a fixed-size mark over the true-scale scene.
  // Positions are true; only the marks are sized for legibility. Each frame this also
  // rebuilds map.marks, the list the cursor locks onto and clicks pick from.
  //
  // Folding keeps zoom honest. A moon closer than declutter_px to its planet on screen folds
  // into it; formation members closer than aggregate_px fold into the formation's symbol.
  // Zooming in never adds clutter, only resolves what was folded.
  import { onMount, onDestroy } from 'svelte';
  import { rgba, text, display, unitSymbol, bodyDisplay, bodyMark, barycentreMark, zoneRing } from './symbols.js';
  import { km } from './format.js';

  export let map = null;
  export let style = null;
  export let scale = 1;              // display-size slider
  export let layers = {};
  export let contacts = [];          // scenario contacts (static definitions)

  let canvas, ctx, unhook, W = 0, H = 0, dpr = 1;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // the body a body folds into on screen: its parent, or for a binary's secondary, the primary
  function visualParent(def, b) {
    if (!b.parent) return null;
    const p = def[b.parent];
    if (p.components) return p.components[0] === b.id ? (p.parent ? visualParent(def, p) : null) : p.components[0];
    return b.parent;
  }

  function isHot(kind, id) {
    const s = map.selected, h = map.hover;
    return (s && s.kind === kind && s.id === id) || (h && h.kind === kind && h.id === id);
  }

  function drawBodies(marks) {
    const def = map.bodies, st = map.state, D = style.display;
    const scr = {};
    for (const b of map.def.bodies) {
      const p = st.bodies[b.id];
      const s = p && map.project(p);
      if (s) scr[b.id] = s;
    }
    // how big each body is drawn: its true disc when that is larger, else its role's display, else a mark
    const drawn = {};
    for (const b of map.def.bodies) {
      if (!scr[b.id] || b.kind === 'barycenter') continue;
      const trueR = map.pxRadius(st.bodies[b.id], b.radius_km);
      const role = style.roles[b.display.role] ?? { size_px: 20 };
      const dispR = layers.display ? (role.size_px * scale) / 2 : 0;
      drawn[b.id] = trueR >= dispR && trueR > 3 ? { r: trueR, how: 'true' } : dispR > 0 ? { r: dispR, how: 'display' } : { r: D.symbol_px / 2, how: 'mark' };
    }
    // fold: a body hides when it sits inside what it orbits, as drawn (unless selected or hovered)
    const folded = new Set();
    const order = [...map.def.bodies].sort((a, b) => (scr[b.id]?.depth ?? 0) - (scr[a.id]?.depth ?? 0));  // far first
    for (const b of map.def.bodies) {
      const vp = visualParent(def, b), s = scr[b.id], ps = vp && scr[vp];
      if (!s || !ps || isHot('body', b.id)) continue;
      const reach = Math.max(D.declutter_px, (drawn[vp]?.r ?? 0) * 0.9);
      if (Math.hypot(s.x - ps.x, s.y - ps.y) < reach) folded.add(b.id);
    }
    for (const b of map.def.bodies) {                     // a moon of a folded planet folds with it
      let vp = visualParent(def, b);
      while (vp && !folded.has(b.id)) { if (folded.has(vp)) folded.add(b.id); vp = visualParent(def, def[vp]); }
    }
    for (const b of order) {
      const s = scr[b.id];
      if (!s || folded.has(b.id)) continue;
      const hot = isHot('body', b.id);
      if (b.kind === 'barycenter') {
        const [a, c] = b.components;
        if (!folded.has(c) && scr[a] && scr[c] && Math.hypot(scr[a].x - scr[c].x, scr[a].y - scr[c].y) > 40) barycentreMark(ctx, style, s.x, s.y);
        continue;
      }
      const { r, how } = drawn[b.id];
      if (how === 'true') {                                // the true sphere is bigger: let it show
        if (hot) { ctx.strokeStyle = style.palette.fuchsia; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(s.x, s.y, r + 3, 0, Math.PI * 2); ctx.stroke(); }
      } else if (how === 'display') bodyDisplay(ctx, style, b, s.x, s.y, r, hot);
      else bodyMark(ctx, style, b, s.x, s.y, D.symbol_px, hot);
      if (layers.labels || hot) {
        const lx = s.x + Math.min(r, H) + 7;
        display(ctx, b.name, lx, s.y + 4, rgba(hot ? style.palette.fuchsia : style.palette.ink, hot ? 1 : 0.8), b.kind === 'moon' ? 11 : 12);
      }
      marks.push({ kind: 'body', id: b.id, x: s.x, y: s.y, r: Math.max(r, 6), depth: s.depth });
    }
  }

  // formations fold top-down: draw a formation when its members are too close to tell apart
  function drawContacts(marks) {
    const pos = map.state.contacts ?? {};
    const byId = Object.fromEntries(contacts.map((c) => [c.id, c]));
    const members = (id) => contacts.filter((c) => c.formation === id);
    const leaves = (id) => { const m = members(id); return m.length ? m.flatMap((c) => leaves(c.id)) : [id]; };
    const scrOf = (id) => pos[id] && map.project(pos[id]);

    const draw = (c) => {
      const s = scrOf(c.id);
      const kids = members(c.id);
      if (kids.length) {
        const pts = leaves(c.id).map(scrOf).filter(Boolean);
        const spread = pts.length ? Math.max(...pts.map((a) => Math.max(...pts.map((b) => Math.hypot(a.x - b.x, a.y - b.y))))) : 0;
        if (spread >= style.display.aggregate_px && !isHot('contact', c.id)) { kids.forEach(draw); return; }
      }
      if (!s) return;
      const hot = isHot('contact', c.id);
      unitSymbol(ctx, style, c, s.x, s.y, { h: c.echelon === 'ship' ? 15 : 18, hot, label: layers.labels || hot });
      marks.push({ kind: 'contact', id: c.id, x: s.x, y: s.y, r: 14, depth: s.depth });
    };
    contacts.filter((c) => !c.formation || !byId[c.formation]).forEach(draw);
  }

  // the selected body's wells, as rings around it
  function drawZones() {
    const sel = map.selected;
    if (!sel || sel.kind !== 'body' || !layers.zones) return;
    const b = map.bodies[sel.id], p = map.state.bodies[sel.id];
    const s = p && map.project(p);
    if (!b || !s) return;
    const z = b.zones, pal = style.palette;
    const ring = (rkm, col, label, dash) => rkm && zoneRing(ctx, s.x, s.y, map.pxRadius(p, rkm), col, `${label} ${km(rkm)}`, dash);
    ring(z.orbis_km, rgba(pal.fuchsia, 0.6), 'Orbis', [2, 3]);
    ring(map.state.magnetopause_km?.[b.id], rgba(pal.cyan, 0.55), 'Magnetopause', [6, 4]);
    if (z.well_of === b.id) {
      ring(z.soi_km, rgba(pal.violet, 0.75), 'Well', [4, 5]);
      ring(z.hill_km, rgba(pal.violet, 0.45), 'Hill', [1, 5]);
    }
    if (z.hz_km) { ring(z.hz_km[0], rgba('#5fd38d', 0.45), 'HZ', [3, 6]); ring(z.hz_km[1], rgba('#5fd38d', 0.45), 'HZ', [3, 6]); }
    ring(z.snow_line_km, rgba(pal.cyan, 0.35), 'Snow line', [1, 6]);
  }

  function drawBullseyeLabels() {
    const pal = style.palette;
    for (const { r, p } of map.ringLabels()) text(ctx, km(r), p.x + 4, p.y - 4, rgba(pal.violet, 0.65), 9);
    for (const { deg, p } of map.bearingLabels()) text(ctx, String(deg).padStart(3, '0'), p.x, p.y + 3, rgba(deg === 0 ? pal.cyan : pal.violet, deg === 0 ? 0.8 : 0.5), 9, undefined, 'center');
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!map || !style || !map.state || !map.def || map.state.system !== map.def.id) return;
    const marks = [];
    drawBullseyeLabels();
    drawZones();
    drawBodies(marks);
    if (layers.contacts) drawContacts(marks);
    map.marks = marks;
  }

  onMount(() => { ctx = canvas.getContext('2d'); resize(); window.addEventListener('resize', resize); });
  $: if (map && ctx && !unhook) unhook = map.onFrame(draw);
  onDestroy(() => { unhook?.(); window.removeEventListener('resize', resize); });
</script>

<canvas bind:this={canvas} aria-hidden="true"></canvas>

<style>
  canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 5; }
</style>

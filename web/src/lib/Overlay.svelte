<script>
  // The tactical layer: every entity as a fixed-size mark over the true-scale scene.
  // Positions are true; only the marks are sized for legibility. Each frame this also
  // rebuilds map.marks, the list the cursor locks onto and clicks pick from.
  //
  // Folding keeps zoom honest. A moon closer than declutter_px to its planet on screen folds
  // into it; formation members closer than aggregate_px fold into the formation's symbol; others'
  // ships (tracks), and our own formations that orders have brought together, closer than that
  // collapse into a flight, group or task force by their count of ships ([folding]).
  // Zooming in never adds clutter, only resolves what was folded.
  import { onMount, onDestroy } from 'svelte';
  import { rgba, text, display, unitSymbol, bodyDisplay, bodyMark, barycentreMark, zoneRing, HARM } from './symbols.js';
  import { km } from './format.js';
  import { reveal } from './hierarchy.js';
  import { ofGroup } from './orders.js';

  export let map = null;
  export let style = null;
  export let settings = null;        // display.toml values, with the player's settings applied
  export let drules = {};            // display.toml rules
  export let contacts = [];          // scenario contacts (static definitions, with their tree)
  export let ranges = false;         // G held: where every armed ship's weapons start to matter
  export let sensing = false;        // R held: how far every ship's sensors see
  export let watched = new Set();    // ships whose sensors are drawn always (her panel's Show sensors)


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
    const def = map.bodies, st = map.state, S = settings, layers = S.layers;
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
      const dispR = layers.display ? (role.size_px * S.icons.body_display) / 2 : 0;
      drawn[b.id] = trueR >= dispR && trueR > 3 ? { r: trueR, how: 'true' } : dispR > 0 ? { r: dispR, how: 'display' } : { r: S.icons.body_mark_px / 2, how: 'mark' };
    }
    // fold: a body hides when it sits inside what it orbits, as drawn (unless selected or hovered)
    const folded = new Set();
    const order = [...map.def.bodies].sort((a, b) => (scr[b.id]?.depth ?? 0) - (scr[a.id]?.depth ?? 0));  // far first
    for (const b of map.def.bodies) {
      const vp = visualParent(def, b), s = scr[b.id], ps = vp && scr[vp];
      if (!s || !ps || isHot('body', b.id)) continue;
      const reach = Math.max(S.folding.declutter_px, (drawn[vp]?.r ?? 0) * 0.9);
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
      else bodyMark(ctx, style, b, s.x, s.y, S.icons.body_mark_px, hot);
      if (layers.labels || hot) {
        const lx = s.x + Math.min(r, H) + 7;
        const px = S.text.body_label_px - (b.kind === 'moon' ? 1 : 0);
        display(ctx, b.name, lx, s.y + px / 3, rgba(hot ? style.palette.fuchsia : style.palette.ink, hot ? 1 : 0.8), px);
      }
      marks.push({ kind: 'body', id: b.id, x: s.x, y: s.y, r: Math.max(r, 6), depth: s.depth });
    }
  }

  // Formations fold where their units are too close to tell apart (see fold, below). A selection
  // overrides folding (display.toml [selection]): the selected formation
  // opens to show the units that answer to it, highlighted and joined to it by lines; the chain
  // above it stays open, and the formation it answers to is marked. Everything else dims.
  function drawContacts(marks) {
    const pos = map.state.contacts ?? {};
    const S = settings, pal = style.palette;
    const byId = Object.fromEntries(contacts.map((c) => [c.id, c]));
    const kids = (id) => (byId[id]?.children ?? []).filter((k) => byId[k]);
    const leaves = (id) => (kids(id).length ? kids(id).flatMap(leaves) : [id]);
    const scrOf = (id) => pos[id] && map.project(pos[id]);
    const selId = map.selected?.kind === 'contact' ? map.selected.id : null;
    const rv = reveal(byId, selId, S.selection);
    const related = new Set([selId, ...rv.open, ...rv.children, ...rv.parents]);
    const picks = map.picks;                       // a group picked (⇧-click): what is left out of it dims
    const childCol = pal[drules.selection?.rules.child_color] ?? pal.cyan;
    const parentCol = pal[drules.selection?.rules.parent_color] ?? pal.violet;
    const drawnAt = {};

    const symbol = (c, s, also = null) => {
      const hot = isHot('contact', c.id), formation = kids(c.id).length > 0;
      const h = S.icons.unit_px * (formation || c.echelon !== 'ship' ? S.icons.formation_scale : 1);
      const ring = rv.children.has(c.id) ? childCol : rv.parents.has(c.id) ? parentCol : null;
      // as the side sees her; a symbol of many (a formation, a group, tracks together) only once every
      // one is out: the least of their harms, from disabled on
      const ships = (also?.group ?? also?.members ?? [c.id]).flatMap(leaves).map((l) => map.state.ships?.[l]?.harm ?? 0);
      const least = ships.length ? Math.min(...ships) : 0;
      const harm = ships.length === 1 || least >= 2 ? HARM[least] : null;
      if (harm) c = { ...c, status: [...(c.status ?? []), harm] };
      unitSymbol(ctx, style, c, s.x, s.y, {
        h, hot, ring, label: S.layers.labels || hot || ring !== null,
        alpha: picks ? (ofGroup(byId, picks, c.id) ? 1 : S.selection.dim_unpicked ?? 0.3) : selId && !related.has(c.id) ? S.selection.dim_others : 1,
        hq: S.icons.hq_staff && formation && c.has_position,
        labelPx: S.text.unit_label_px, tagPx: S.text.unit_tag_px, faction: S.text.faction_tag ?? true,
      });
      drawnAt[c.id] = s;
      marks.push({ kind: 'contact', id: c.id, x: s.x, y: s.y, r: h, depth: s.depth, ...also });
    };

    // Folding by clusters, bottom-up. Each formation gathers what its units became ("blobs": a
    // unit, or a formation folded around its core), links blobs closer than aggregate_px on screen,
    // and folds its biggest linked cluster into its own symbol, if that cluster holds more than
    // core_share of the formation's ships (its main body). Blobs outside the core stay as
    // they are, at their own echelon: a far picket squadron reads as a squadron, while the tight
    // body around it folds. Its parent then does the same with what is passed up.
    const R = S.folding.aggregate_px;
    const nLeaves = (id) => leaves(id).length;

    function clusters(blobs, r = R, apart = null) { // single-linkage: a chain of near blobs is one cluster
      const near = (a, b) => Math.hypot(a.s.x - b.s.x, a.s.y - b.s.y) < r && (!apart || apart(a, b));
      const seen = new Set(), out = [];
      for (const b of blobs) {
        if (seen.has(b)) continue;
        const group = [b], queue = [b];
        seen.add(b);
        while (queue.length) {
          const x = queue.pop();
          for (const y of blobs) if (!seen.has(y) && near(x, y)) { seen.add(y); group.push(y); queue.push(y); }
        }
        out.push(group);
      }
      return out;
    }

    function fold(c) {
      const k = kids(c.id), s = scrOf(c.id);
      if (!k.length) return s ? [{ id: c.id, s, leaves: 1 }] : [];
      const whole = () => (s ? [{ id: c.id, s, leaves: nLeaves(c.id) }] : []);
      if (rv.children.has(c.id) && !rv.open.has(c.id)) return whole();       // a revealed unit stays whole
      if (!rv.open.has(c.id) && isHot('contact', c.id)) return whole();      // hovered: hold still
      const blobs = k.flatMap((id) => fold(byId[id]));
      // the formation still shows where it is a place (its HQ), or where it is the focus
      const hq = s && ((c.has_position && S.icons.hq_staff) || c.id === selId || rv.parents.has(c.id))
        ? [{ id: c.id, s, leaves: 0, hq: true }] : [];
      if (rv.open.has(c.id)) return [...hq, ...blobs];                       // opened by the selection
      const core = clusters(blobs).sort((a, b) => b.reduce((n, x) => n + x.leaves, 0) - a.reduce((n, x) => n + x.leaves, 0))[0];
      const coreLeaves = core ? core.reduce((n, x) => n + x.leaves, 0) : 0;
      // the symbol stands for the main body only: a cluster that holds most of the formation's ships
      const total = nLeaves(c.id);
      if (!core || (core.length < 2 && coreLeaves < total) || coreLeaves <= S.folding.core_share * total) return [...hq, ...blobs];
      // drawn on its HQ or flagship when that sits in the core, else at the core's centre
      const cx = core.reduce((n, x) => n + x.s.x, 0) / core.length, cy = core.reduce((n, x) => n + x.s.y, 0) / core.length;
      const at = s && Math.hypot(s.x - cx, s.y - cy) < R ? s : { x: cx, y: cy, depth: core[0].s.depth };
      return [{ id: c.id, s: at, leaves: coreLeaves }, ...blobs.filter((b) => !core.includes(b))];
    }
    // What the simulation does not form together, near each other on screen, is drawn as one symbol
    // of the echelon its count of ships reads as (display.toml [folding]). Others' ships come one by
    // one (tracks), standing on the track first by id (hovered, it holds still; selected, that track
    // stands out of it). Our own formations, side by side, stand on the one with the most ships;
    // what the selection opens or picks stands out of it, and a click on it picks them all
    const F = S.folding;
    const echelonOf = (n) => (n <= F.flight_max ? 'flight' : n <= F.group_max ? 'group' : 'task-force');
    const centre = (g) => ({ x: g.reduce((a, b) => a + b.s.x, 0) / g.length, y: g.reduce((a, b) => a + b.s.y, 0) / g.length, depth: g[0].s.depth });
    const tops = contacts.filter((c) => !c.parent).flatMap((c) => fold(c));
    // (old tracks fold among themselves: an empty circle for many, as for one)
    const loose = F.tracks ? tops.filter((b) => byId[b.id].track && b.id !== selId) : [];
    const mine = (id) => leaves(id).some((l) => map.state.ships?.[l]?.mass_t != null);     // (her own figures: the side's)
    const ours = F.groups ? tops.filter((b) => !byId[b.id].track && !b.hq && !related.has(b.id) && !(picks && ofGroup(byId, picks, b.id)) && mine(b.id)) : [];
    // (a unit left out of its formation's fold stays out of it: not one of a group with it)
    const apart = (a, b) => !(byId[a.id].ancestors ?? []).includes(b.id) && !(byId[b.id].ancestors ?? []).includes(a.id);
    for (const b of tops) if (!loose.includes(b) && !ours.includes(b)) symbol(byId[b.id], b.s);
    const sides = new Map();                       // ours: a side's (affiliation, faction) with its own
    for (const b of ours) { const c = byId[b.id], k = `${c.affiliation}|${c.faction?.id ?? ''}`; sides.set(k, [...(sides.get(k) ?? []), b]); }
    for (const g of [...sides.values()].flatMap((bs) => clusters(bs, R, apart))) {
      if (g.length < 2) { symbol(byId[g[0].id], g[0].s); continue; }
      const c = byId[g.reduce((a, b) => (b.leaves > a.leaves ? b : a)).id], ships = g.reduce((n, b) => n + b.leaves, 0);
      symbol({ id: c.id, affiliation: c.affiliation, faction: c.faction, children: g.map((b) => b.id), echelon: echelonOf(ships),
               callsign: `${g.length} units`, status: [] }, centre(g), { group: g.map((b) => b.id) });
    }
    const groups = [...clusters(loose.filter((b) => !byId[b.id].old)), ...clusters(loose.filter((b) => byId[b.id].old))];
    for (const g of groups) {
      if (g.length < 2) { symbol(byId[g[0].id], g[0].s); continue; }
      const cs = g.map((b) => byId[b.id]).sort((a, b) => (a.id < b.id ? -1 : 1)), n = cs.length;
      const same = (f) => (cs.every((c) => f(c) === f(cs[0])) ? cs[0] : null);
      const bogeys = cs.filter((c) => c.brevity === 'bogey').length;
      symbol({ id: cs[0].id, track: true, children: [], echelon: echelonOf(n),
               affiliation: same((c) => c.affiliation)?.affiliation ?? 'unknown', faction: same((c) => c.faction?.id)?.faction ?? null,
               callsign: cs[0].old ? `${n} old tracks` : `${n} ${bogeys === n ? 'bogeys' : 'tracks'}`, brevity: bogeys && !cs[0].old ? 'bogey' : '',
               old: !!cs[0].old, status: cs[0].old ? ['old-track'] : cs.every((c) => c.status?.includes('track-lost')) ? ['track-lost'] : [] },
             centre(g), { members: g.map((b) => b.id) });
    }

    // lines: from each open formation to the units it reveals, and from the selection up
    if (S.selection.hierarchy_lines && selId) {
      const line = (a, b, col, dash) => {
        ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.setLineDash(dash);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); ctx.setLineDash([]);
      };
      for (const id of rv.children) {
        const from = drawnAt[byId[id].parent] ?? scrOf(byId[id].parent), to = drawnAt[id];
        if (from && to) line(from, to, rgba(childCol, 0.6), [4, 4]);
      }
      for (const id of rv.parents) {
        const from = drawnAt[selId], to = drawnAt[id] ?? scrOf(id);
        if (from && to) line(from, to, rgba(parentCol, 0.55), [2, 5]);
      }
    }
  }

  // the selected body's wells, as rings around it
  function drawZones() {
    const sel = map.selected;
    if (!sel || sel.kind !== 'body' || !settings.layers.zones) return;
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

  // G held: a dotted ring for each kind of weapon a ship carries, where it starts to matter (her
  // class's ranges: de-mast, dazzle, guns), each where it is big enough on screen to read. A
  // selected ship's rings are fuchsia; a selected formation's units' rings (its own ships, or if it
  // has none, the ships of the units under it) take the selection's child colour. Those carry
  // their figures; of the rest, the first ring of each kind and range does. With [ranges]
  // selected_only, the rest are not drawn. Rings of one kind whose centres all but meet on screen
  // (a formation seen from far off) are drawn as one about them all, with how many it holds.
  const RANGE_DASH = { 'de-mast': [2, 4], dazzle: [1, 7], guns: [5, 4] };
  const RANGE_ALPHA = { 'de-mast': 0.5, dazzle: 0.3, guns: 0.45 };
  const MERGE = 0.25;                   // rings merge when their centres are this share of the ring apart, or less
  // R held: the same, for each of a ship's sensors (her class's suite), where it sees a ship giving
  // off display.toml [detection] vs_mw; dotted finer, and fainter. Sensors whose cones leave most of
  // the sphere unseen (the infrared telescopes, the strip optics) are drawn as their cones along her
  // hull, for a ship of the side's own drawn alone; the selected ship's are all drawn so, her
  // passive suite's cones too (each sweeps, and will be dazzled, on its own); otherwise, and for a
  // formation, a ring. A ship her panel set to show her sensors has them drawn so always, R held or not.
  const weapons = (c) => c.ship?.ranges ?? [];
  const sensors = (c) => {
    const vs = Number(settings.detection?.vs_mw ?? 30);
    return (c.ship?.sensors ?? []).map((s) => ({
      what: s.name, km: s.km * Math.sqrt(vs / s.ref_mw), dash: [1, 3], alpha: 0.3,
      cone: s.cone_deg < 90 ? s : null, narrow: s.cones * (1 - Math.cos((s.cone_deg * Math.PI) / 180)) < 1.9 }));
  };
  function rangeFocus(byId, sel) {
    const c = sel && byId[sel];
    if (!c) return new Set();
    if (c.ship) return new Set([sel]);
    const kids = (c.children ?? []).filter((k) => byId[k]?.ship);
    if (kids.length) return new Set(kids);
    const out = new Set(), walk = (id) => (byId[id]?.children ?? []).forEach((k) => (byId[k]?.ship ? out.add(k) : walk(k)));
    walk(sel);
    return out;
  }
  // her hull's frame, as the simulation lays her sensors on it: forward where her hull points (else
  // where she goes), up the system's, and across
  function hullFrame(dir, v) {
    let f = dir && dir[0] * dir[0] + dir[1] * dir[1] + dir[2] * dir[2] > 0.25 ? dir : v;
    const fn = f ? Math.hypot(...f) : 0;
    f = fn > 1e-9 ? f.map((x) => x / fn) : [1, 0, 0];
    let side = Math.abs(f[2]) > 0.99 ? [f[2], 0, -f[0]] : [-f[1], f[0], 0];
    const sn = Math.hypot(...side);
    side = side.map((x) => x / sn);
    return [f, side, [f[1] * side[2] - f[2] * side[1], f[2] * side[0] - f[0] * side[2], f[0] * side[1] - f[1] * side[0]]];
  }
  // one cone, apex at p (km), along axis a, half-angle th (rad), reaching L km: its rim and four edges
  function cone(p, a, th, L, color, dash) {
    const e1 = Math.abs(a[2]) < 0.9 ? [-a[1], a[0], 0] : [0, -a[2], a[1]], n1 = Math.hypot(...e1);
    const u = e1.map((x) => x / n1), w = [a[1] * u[2] - a[2] * u[1], a[2] * u[0] - a[0] * u[2], a[0] * u[1] - a[1] * u[0]];
    const c = Math.cos(th) * L, r = Math.sin(th) * L;
    const rim = [];
    for (let k = 0; k <= 32; k++) {
      const q = (k / 32) * 2 * Math.PI, cs = Math.cos(q) * r, sn = Math.sin(q) * r;
      rim.push(map.project([0, 1, 2].map((i) => p[i] + a[i] * c + u[i] * cs + w[i] * sn)));
    }
    const s = map.project(p);
    if (!s || rim.some((x) => !x)) return;
    ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash(dash);
    ctx.beginPath();
    rim.forEach((x, k) => (k ? ctx.lineTo(x.x, x.y) : ctx.moveTo(x.x, x.y)));
    for (const k of [0, 8, 16, 24]) { ctx.moveTo(s.x, s.y); ctx.lineTo(rim[k].x, rim[k].y); }
    ctx.stroke(); ctx.setLineDash([]);
  }
  function drawRanges(ringsOf = weapons, R = settings.ranges ?? {}, pick = null) {
    const pos = map.state.contacts ?? {}, sel = map.selected?.kind === 'contact' ? map.selected.id : null;
    const ships = map.state.ships ?? {};
    const byId = Object.fromEntries(contacts.map((c) => [c.id, c]));
    const focus = rangeFocus(byId, sel);
    const only = R.selected_only, minPx = R.min_px ?? 14;
    const childCol = style.palette[drules.selection?.rules.child_color] ?? style.palette.cyan;
    const kinds = new Map();              // one kind of ring, one colour -> every one of them on screen
    for (const c of contacts) {
      const p = pos[c.id], on = focus.has(c.id);
      const rings = ringsOf(c);
      if (!rings.length || !p || (pick ? !pick.has(c.id) : only && !on)) continue;
      const s = map.project(p);
      if (!s) continue;
      const col = on ? (c.id === sel ? style.palette.fuchsia : childCol) : (style.affiliation[c.affiliation] ?? style.affiliation.unknown).color;
      for (const r of rings) {
        const px = map.pxRadius(p, r.km);
        if (px < minPx || px > 4 * Math.max(W, H)) continue;
        const key = `${r.what} ${r.km} ${col} ${on}`;
        if (!kinds.has(key)) kinds.set(key, []);
        kinds.get(key).push({ c, p, s, px, r, col, on });
      }
    }
    const labelled = new Set();
    for (const items of kinds.values()) {
      const groups = [];                  // centres that all but meet: one ring about them all
      for (const it of items.sort((x, y) => y.px - x.px)) {
        const g = groups.find((g) => Math.hypot(g.x - it.s.x, g.y - it.s.y) <= MERGE * Math.max(g.px, it.px));
        if (g) { g.items.push(it); g.x += (it.s.x - g.x) / g.items.length; g.y += (it.s.y - g.y) / g.items.length; }
        else groups.push({ x: it.s.x, y: it.s.y, px: it.px, items: [it] });
      }
      for (const g of groups) {
        const it = g.items[0], r = it.r;
        const key = `${it.on ? 'on ' : ''}${r.what} ${r.km}`;
        const label = labelled.has(key) ? '' : `${r.what} ${km(r.km)}${g.items.length > 1 ? ` ×${g.items.length}` : ''}`;
        labelled.add(key);
        const color = rgba(it.col, it.on ? 0.85 : r.alpha ?? RANGE_ALPHA[r.what] ?? 0.45), dash = r.dash ?? RANGE_DASH[r.what] ?? [2, 4];
        const own = ships[it.c.id];
        if (g.items.length === 1 && r.cone && own?.dir && (r.narrow || it.c.id === sel)) {   // her cones, along her hull
          const [f, side, up] = hullFrame(own.dir, own.velocity_kms), th = (r.cone.cone_deg * Math.PI) / 180;
          for (const b of r.cone.axes ?? []) cone(it.p, [0, 1, 2].map((i) => b[0] * f[i] + b[1] * side[i] + b[2] * up[i]), th, r.km, color, dash);
          if (label) text(ctx, label, g.x + 6, g.y - 6, color, settings.text.readout_px);
          continue;
        }
        const rad = Math.max(...g.items.map((x) => Math.hypot(x.s.x - g.x, x.s.y - g.y) + x.px));
        zoneRing(ctx, g.x, g.y, rad, color, label, dash);
      }
    }
  }

  function drawBullseyeLabels() {
    const pal = style.palette;
    const px = settings.text.readout_px;
    for (const { r, p } of map.ringLabels()) text(ctx, km(r), p.x + 4, p.y - 4, rgba(pal.violet, 0.65), px);
    for (const { deg, p } of map.bearingLabels()) text(ctx, String(deg).padStart(3, '0'), p.x, p.y + 3, rgba(deg === 0 ? pal.cyan : pal.violet, deg === 0 ? 0.8 : 0.5), px, undefined, 'center');
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!map || !style || !settings || !map.state || !map.def || map.state.system !== map.def.id) return;
    const marks = [];
    drawBullseyeLabels();
    drawZones();
    drawBodies(marks);
    if (ranges && settings.layers.contacts) drawRanges();
    if (sensing && settings.layers.contacts) drawRanges(sensors, settings.detection ?? {});
    else if (watched.size && settings.layers.contacts) drawRanges(sensors, settings.detection ?? {}, watched);
    if (settings.layers.contacts) drawContacts(marks);
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

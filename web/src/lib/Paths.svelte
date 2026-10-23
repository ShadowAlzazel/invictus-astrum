<script>
  // Free paths: where the side's free ships go with no drive lit, as the map can tell from its own
  // picture. A ship on an orbit (orbit_of) or coasting with no order is drawn her conic about the
  // body whose well she is in (in a binary, the one that pulls harder; out of every well, the
  // star): two bodies only, her state read off the picture and the body's, an estimate like Eva's.
  // An ellipse whole; a hyperbola from where she is, outward. Nothing of it is asked of the server.
  // Folded as the units are, before anything is worked out: of the ships drawn inside one mark (a
  // formation's, at this zoom) only the first is, and her path is drawn for them all. Each path is
  // worked out again at most every REDO_MS (a conic moves little), and drawn about where its body
  // is drawn, every point through one projection.
  // In fuchsia, dotted (estimates): what going free would give. For the selection's ships on
  // station, the orbit they would go onto (circular at their height, prograde about the system's
  // up, as the simulation puts them on one; out of every well, their coast); aiming a move given
  // free, what she does once there: at a body, or a point in a well, the orbit she goes onto; a
  // point out of every well, her coast from it (at rest by its bullseye, as she stops there).
  import { onMount, onDestroy } from 'svelte';
  import { rgba, text } from './symbols.js';
  import { G, add, conic, dominant, len, onto, scale, sub, ballisticAim, ballisticAt } from './kepler.js';
  import { G0 } from './orders.js';

  export let map = null;
  export let style = null;
  export let on = true;                 // [layers] paths
  export let estimates = true;          // [layers] path_estimates
  export let contacts = [];
  export let sel = null;
  export let ordering = null;           // an order being aimed (Orders), and where it is aimed: aim()
  export let aim = () => null;
  export let motion = null;             // motion.js: how fast each bullseye's origin moves

  const N = 96, REDO_MS = 500;
  // the ballistic predictor's notches, as Eva's: where she is 1 min, 10 min, 1 h, 1 d and 1 wk on
  const NOTCH = [[60, '1m'], [600, '10m'], [3600, '1h'], [86400, '1d'], [604800, '1w']], WEEK = 604800, M = 80;
  let canvas, ctx, unhook, W = 0, H = 0;
  const kept = new Map();               // ship (k: as K would give) -> { at, body, pts: Float64Array, closed }
  let scr = new Float32Array(2 * (N + 1));
  const line = new Float64Array(3 * (M + 1)), dots = new Float64Array(3 * NOTCH.length);
  let dotScr = new Float32Array(2 * NOTCH.length);

  // the units by id, and the selection's (worked out as they change, not every frame)
  $: byId = Object.fromEntries(contacts.map((c) => [c.id, c]));
  $: under = subtree(sel?.kind === 'contact' ? sel.id : null, byId);
  function subtree(id, byId) {
    const out = new Set(), walk = (u) => { out.add(u); (byId[u]?.children ?? []).forEach(walk); };
    if (id) walk(id);
    return out;
  }

  // (the math: kepler.js)
  const dominantAt = (p) => dominant(map.def.bodies, map.bodies, map.state.bodies, p);
  // what going free at p moving at v gives: an orbit in a body's well, else her coast about the star
  function goingFree(p, v) {
    const st = map.state, b = dominantAt(p), bp = b && st.bodies[b.id], bv = b && st.bodies_kms?.[b.id];
    if (!bp || !bv || !(b.mass_kg > 0)) return null;
    const r = sub(p, bp), mu = G * b.mass_kg;
    return { body: b.id, ...(b.kind !== 'star' ? onto(r, mu, N) : conic(r, sub(v, bv), mu, Math.max(3 * len(r), 1), N)) };
  }

  // a ship's path now, as she is in the picture: her own conic (free), or what K would give (on station)
  function pathOf(id, s, k) {
    const st = map.state, p = st.contacts?.[id];
    if (!p) return null;
    if (k) return goingFree(p, s.velocity_kms);
    const b = s.orbit_of ? map.bodies[s.orbit_of] : dominantAt(p), bp = b && st.bodies[b.id], bv = b && st.bodies_kms?.[b.id];
    if (!bp || !bv || !(b.mass_kg > 0)) return null;
    const r = sub(p, bp), path = conic(r, sub(s.velocity_kms, bv), G * b.mass_kg, Math.max(3 * len(r), b.zones?.soi_km ?? 0), N);
    return path && { body: b.id, ...path };
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function stroke(path, origin, color, dash) {
    const n = path.pts.length / 3;
    if (scr.length < 2 * n) scr = new Float32Array(2 * n);
    map.projectMany(origin, path.pts, scr);
    ctx.strokeStyle = color; ctx.setLineDash(dash);
    ctx.beginPath();
    let pen = false;
    for (let k = 0; k < n; k++) {
      const x = scr[2 * k], y = scr[2 * k + 1];
      if (x !== x) { pen = false; continue; }          // (NaN: behind the camera)
      if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      pen = true;
    }
    ctx.stroke();
  }
  // BALLISTIC aimed: as the simulation aims it (kepler.js ballisticAim) from the ships' mean, the
  // burn's line, then her coast about the body whose well she is in when it ends (two bodies, it
  // moving on as it does now), out to a week, notched where she is 1 min, 10 min, 1 h, 1 d, 1 wk on
  function ballistic(a, color) {
    const st = map.state, ships = ordering.ships.filter((id) => st.contacts?.[id] && st.ships?.[id]?.velocity_kms);
    if (!ships.length || !(ordering.g > 0)) return;
    const mean = (f) => [0, 1, 2].map((k) => ships.reduce((x, id) => x + f(id)[k], 0) / ships.length);
    const r0 = mean((id) => st.contacts[id]), v0 = mean((id) => st.ships[id].velocity_kms), acc = ordering.g * G0;
    const bv = (id) => st.bodies_kms?.[id] ?? [0, 0, 0];
    let P;                                             // where the target is T on
    if (a.kind === 'body') {
      const b = map.bodies[a.id], B0 = st.bodies[a.id], stand = Math.max(3 * (b?.radius_km ?? 0), 1000);
      P = (T) => {                                     // past it, as the simulation aims: off it across her line
        const Bt = add(B0, scale(bv(a.id), T)), d = sub(Bt, r0), across = [-d[1], d[0], 0], n = len(across);
        return n < 1e-3 ? add(Bt, [stand, 0, 0]) : add(Bt, scale(across, stand / n));
      };
    } else if (a.kind === 'contact') {
      const p = st.contacts[a.id], v = st.ships?.[a.id]?.velocity_kms ?? [0, 0, 0];
      P = (T) => add(p, scale(v, T));
    } else {
      const vb = motion?.of(a.target?.bullseye) ?? [0, 0, 0];
      P = (T) => add(a.to, scale(vb, T));
    }
    const aim = ballisticAim(r0, v0, acc, P);
    const endAt = ballisticAt(r0, v0, acc, aim, aim.tb, null), b = dominantAt(endAt), B = b && st.bodies[b.id];
    const body = B && b.mass_kg > 0 ? { mu: G * b.mass_kg, v: bv(b.id), at: (t) => add(B, scale(bv(b.id), t)) } : null;
    const span = Math.max(WEEK, 1.2 * aim.T);
    for (let k = 0; k <= M; k++) {                     // denser early on, where the burn is and the near notches
      const t = span * (k / M) ** 3, p = ballisticAt(r0, v0, acc, aim, t, body);
      for (let i = 0; i < 3; i++) line[3 * k + i] = p[i] - r0[i];
    }
    NOTCH.forEach(([t], k) => { const p = ballisticAt(r0, v0, acc, aim, t, body); for (let i = 0; i < 3; i++) dots[3 * k + i] = p[i] - r0[i]; });
    stroke({ pts: line }, r0, color, [1, 4]);
    map.projectMany(r0, dots, dotScr);
    ctx.setLineDash([]); ctx.strokeStyle = color;
    NOTCH.forEach(([, label], k) => {
      const x = dotScr[2 * k], y = dotScr[2 * k + 1];
      if (x !== x) return;
      ctx.beginPath(); ctx.moveTo(x - 4, y - 4); ctx.lineTo(x + 4, y + 4); ctx.moveTo(x - 4, y + 4); ctx.lineTo(x + 4, y - 4); ctx.stroke();
      text(ctx, label, x + 6, y - 6, color, 10);
    });
  }
  function draw(now) {
    ctx.clearRect(0, 0, W, H);
    const st = map?.state;
    if (!st || !map.def || !style || (!on && !estimates)) return;
    const marked = new Set();
    for (const m of map.marks ?? []) marked.add(m.id);
    const friend = rgba((style.affiliation.friend ?? style.affiliation.unknown).color, 0.28);
    const friendOn = rgba((style.affiliation.friend ?? style.affiliation.unknown).color, 0.75), fuchsia = rgba(style.palette.fuchsia, 0.8);
    ctx.lineWidth = 1;
    const drawn = new Set();
    for (const c of contacts) {
      const s = st.ships?.[c.id];
      if (!s || s.propellant_share == null || !s.velocity_kms) continue;          // the side's own, with what she moves at
      const free = s.mode === 'orbit' || (s.mode === 'free' && !s.goal && !s.burning);
      const k = !free && s.mode === 'station' && under.has(c.id) && estimates && !ordering;   // what K would give
      if (free ? !on : !k) continue;
      let as = c.id;                                   // the mark she is drawn in: hers, or the formation's she is folded into
      while (as && !marked.has(as)) as = byId[as]?.parent;
      const key = `${k ? 'k' : ''}${as ?? c.id}`;
      if (drawn.has(key)) continue;                    // one path a mark: worked out for its first ship alone
      drawn.add(key);
      const tag = `${k ? 'k' : ''}${c.id}`;
      let path = kept.get(tag);
      if (!path || now - path.at > REDO_MS || path.mode !== s.mode) {
        path = pathOf(c.id, s, k);
        if (!path) { kept.delete(tag); continue; }
        path.at = now; path.mode = s.mode;
        kept.set(tag, path);
      }
      const o = map.position({ kind: 'body', id: path.body });
      if (o) stroke(path, o, k ? fuchsia : under.has(c.id) ? friendOn : friend, k ? [1, 4] : [3, 4]);
    }
    if (kept.size > 4 * contacts.length) kept.clear();
    // a move aimed: given free, what she does once there; ballistic, her whole way, notched in time
    const a = estimates && ordering?.mode === 'move' && ordering.then !== 'station' ? aim() : null;
    if (a && ordering.then === 'free') {
      let path = null;
      const b = a.kind === 'body' && map.bodies[a.id];
      if (b && b.mass_kg > 0 && a.standoff > 0) {
        const d = sub(a.from, a.to);
        path = { body: b.id, ...onto(scale(d, a.standoff / len(d)), G * b.mass_kg, N) };
      } else if (a.kind === 'point') {                 // she stops at rest by the bullseye: its origin's motion
        path = goingFree(a.to, motion?.of(a.target?.bullseye) ?? [0, 0, 0]);
      }
      const o = path?.pts && (a.kind === 'body' ? a.to : map.position({ kind: 'body', id: path.body }));
      if (o) stroke(path, o, fuchsia, [1, 4]);
    } else if (a && ordering.then === 'ballistic') {
      ballistic(a, fuchsia);
    }
    ctx.setLineDash([]);
  }
  onMount(() => { ctx = canvas.getContext('2d'); resize(); window.addEventListener('resize', resize); });
  $: if (map && ctx && !unhook) unhook = map.onFrame(draw);
  onDestroy(() => { unhook?.(); window.removeEventListener('resize', resize); });
</script>

<canvas bind:this={canvas} aria-hidden="true"></canvas>

<style>
  canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 17; }
</style>

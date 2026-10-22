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
  import { rgba } from './symbols.js';

  export let map = null;
  export let style = null;
  export let on = true;                 // [layers] paths
  export let estimates = true;          // [layers] path_estimates
  export let contacts = [];
  export let sel = null;
  export let ordering = null;           // an order being aimed (Orders), and where it is aimed: aim()
  export let aim = () => null;

  const G = 6.6743e-20;                 // km³/(kg·s²)
  const N = 96, REDO_MS = 500;
  let canvas, ctx, unhook, W = 0, H = 0;
  const kept = new Map();               // ship (k: as K would give) -> { at, body, pts: Float64Array, closed }
  let scr = new Float32Array(2 * (N + 1));
  let pics = [null, null];              // the last two pictures: how fast a bullseye's origin moves

  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const len = (a) => Math.hypot(a[0], a[1], a[2]);
  const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];

  // the body whose well a point is in: the smallest well about it; a binary's, the component that pulls harder
  function dominant(p) {
    const st = map.state.bodies, bodies = map.def.bodies;
    let best = null;
    for (const b of bodies) {
      const s = b.zones?.soi_km, q = st[b.id];
      if (s && q && len(sub(p, q)) < s && (!best || s < best.zones.soi_km)) best = b;
    }
    const well = best && map.bodies[best.zones.well_of ?? best.id];
    if (well?.components) {
      return well.components.map((id) => map.bodies[id]).filter((b) => st[b.id])
        .reduce((a, b) => (b.mass_kg / len(sub(p, st[b.id])) ** 2 > a.mass_kg / len(sub(p, st[a.id])) ** 2 ? b : a));
    }
    return best ?? bodies.find((b) => !b.parent);
  }

  // a conic about a body, as points off it (km, 3 a point): an ellipse whole, else the arc ahead to limit;
  // falling straight (no turn about it), the line in
  function conic(r, v, mu, limit) {
    const rn = len(r), h = cross(r, v), hn = len(h), pts = new Float64Array(3 * (N + 1));
    if (mu <= 0) return null;
    if (hn < 1e-9 * rn * Math.max(len(v), 1e-9)) {
      for (let k = 0; k <= N; k++) for (let i = 0; i < 3; i++) pts[3 * k + i] = r[i] * (1 - k / N);
      return { pts, closed: false };
    }
    const ev = sub(scale(cross(v, h), 1 / mu), scale(r, 1 / rn)), e = len(ev);
    const P = e > 1e-8 ? scale(ev, 1 / e) : scale(r, 1 / rn), Qr = cross(h, P), Q = scale(Qr, 1 / len(Qr)), p = (hn * hn) / mu;
    const put = (k, nu) => { const rr = p / (1 + e * Math.cos(nu)), c = Math.cos(nu) * rr, s = Math.sin(nu) * rr;
      for (let i = 0; i < 3; i++) pts[3 * k + i] = c * P[i] + s * Q[i]; };
    if (e < 1) { for (let k = 0; k <= N; k++) put(k, (2 * Math.PI * k) / N); return { pts, closed: true }; }
    const now = Math.atan2(dot(r, Q), dot(r, P)), far = Math.acos(-1 / e) - 1e-3;
    let end = far;                                     // outward only as far as the limit
    for (let k = 1; k <= N; k++) { const nu = now + ((far - now) * k) / N, rr = p / (1 + e * Math.cos(nu)); if (rr > limit) { end = nu; break; } }
    if (end <= now) return null;
    for (let k = 0; k <= N; k++) put(k, now + ((end - now) * k) / N);
    return { pts, closed: false };
  }
  // the orbit she goes onto, going free at rel off a body of mu: circular, prograde about the system's up
  function onto(rel, mu) {
    const R = len(rel), up = Math.abs(rel[2]) < 0.95 * R ? [0, 0, 1] : [1, 0, 0], along = cross(up, rel);
    return conic(rel, scale(along, Math.sqrt(mu / R) / len(along)), mu, 3 * R);
  }
  // what going free at p moving at v gives: an orbit in a body's well, else her coast about the star
  function goingFree(p, v) {
    const st = map.state, b = dominant(p), bp = b && st.bodies[b.id], bv = b && st.bodies_kms?.[b.id];
    if (!bp || !bv || !(b.mass_kg > 0)) return null;
    const r = sub(p, bp), mu = G * b.mass_kg;
    return { body: b.id, ...(b.kind !== 'star' ? onto(r, mu) : conic(r, sub(v, bv), mu, Math.max(3 * len(r), 1))) };
  }

  // a ship's path now, as she is in the picture: her own conic (free), or what K would give (on station)
  function pathOf(id, s, k) {
    const st = map.state, p = st.contacts?.[id];
    if (!p) return null;
    if (k) return goingFree(p, s.velocity_kms);
    const b = s.orbit_of ? map.bodies[s.orbit_of] : dominant(p), bp = b && st.bodies[b.id], bv = b && st.bodies_kms?.[b.id];
    if (!bp || !bv || !(b.mass_kg > 0)) return null;
    const r = sub(p, bp), path = conic(r, sub(s.velocity_kms, bv), G * b.mass_kg, Math.max(3 * len(r), b.zones?.soi_km ?? 0));
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
  function draw(now) {
    ctx.clearRect(0, 0, W, H);
    const st = map?.state;
    if (!st || !map.def || !style || (!on && !estimates)) return;
    if (pics[1] !== st) pics = [pics[1], st];
    const byId = {};
    for (const c of contacts) byId[c.id] = c;
    const under = new Set(), walk = (u) => { under.add(u); (byId[u]?.children ?? []).forEach(walk); };
    if (sel?.kind === 'contact') walk(sel.id);
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
    // a move given free, aimed: what she does once there
    const a = estimates && ordering?.mode === 'move' && ordering.free ? aim() : null;
    if (a) {
      let path = null;
      const b = a.kind === 'body' && map.bodies[a.id];
      if (b && b.mass_kg > 0 && a.standoff > 0) {
        const d = sub(a.from, a.to);
        path = { body: b.id, ...onto(scale(d, a.standoff / len(d)), G * b.mass_kg) };
      } else if (a.kind === 'point') {                 // she stops at rest by the bullseye: its origin's motion
        const bid = a.target?.bullseye, [p0, p1] = pics;
        const O0 = p0?.bullseyes?.[bid]?.origin, O1 = p1?.bullseyes?.[bid]?.origin, dt = p1 && p0 ? p1.t - p0.t : 0;
        const v = O0 && O1 && dt > 0 ? scale(sub(O1, O0), 1 / dt) : [0, 0, 0];
        path = goingFree(a.to, v);
      }
      const o = path?.pts && (path.body === (a.kind === 'body' ? a.id : null) ? a.to : map.position({ kind: 'body', id: path.body }));
      if (o) stroke(path, o, fuchsia, [1, 4]);
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

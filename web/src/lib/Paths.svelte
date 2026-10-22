<script>
  // Free paths: where the side's free ships go with no drive lit, as the map can tell from its own
  // picture. A ship on an orbit (orbit_of) or coasting with no order is drawn her conic about the
  // body whose well she is in (in a binary, the one that pulls harder; out of every well, the
  // star): two bodies only, her state read off the picture and the body's, an estimate like Eva's.
  // An ellipse whole; a hyperbola from where she is, outward. Worked out once a picture, drawn
  // every frame about where the body is drawn. Nothing of it is asked of the server.
  // Folded as the units are: a ship drawn inside her formation's mark has her formation's one path
  // drawn for all of them (its first ship's). And in fuchsia, dotted, what K would give: for the
  // selection's ships on station, the orbit they would go onto (circular at their height,
  // prograde about the system's up, as the simulation puts them on one; out of every well, their
  // coast); aiming a move given free at a body, the orbit she would be on there.
  import { onMount, onDestroy } from 'svelte';
  import { rgba } from './symbols.js';

  export let map = null;
  export let style = null;
  export let on = true;                 // [layers] paths
  export let contacts = [];
  export let sel = null;
  export let ordering = null;           // an order being aimed (Orders), and where it is aimed: aim()
  export let aim = () => null;

  const G = 6.6743e-20;                 // km³/(kg·s²)
  const N = 120;
  let canvas, ctx, unhook, W = 0, H = 0, kept = null, keptFor = null, keptSel = null;

  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const len = (a) => Math.hypot(...a);
  const scale = (a, k) => a.map((x) => x * k);

  // the body whose well she is in: the smallest well about her; a binary's, the component that pulls harder
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

  // her conic about the body, as points relative to it (km): an ellipse whole, else the arc ahead
  function conic(r, v, mu, limit) {
    const rn = len(r), h = cross(r, v), hn = len(h);
    if (hn <= 0 || mu <= 0) return null;
    const ev = sub(scale(cross(v, h), 1 / mu), scale(r, 1 / rn)), e = len(ev);
    const P = e > 1e-8 ? scale(ev, 1 / e) : scale(r, 1 / rn), Q = scale(cross(h, P), 1 / (hn * 1)), p = (hn * hn) / mu;
    const Qn = scale(Q, 1 / len(Q));
    const at = (nu) => { const rr = p / (1 + e * Math.cos(nu)); return [0, 1, 2].map((k) => rr * (Math.cos(nu) * P[k] + Math.sin(nu) * Qn[k])); };
    if (e < 1) return { pts: Array.from({ length: N + 1 }, (_, k) => at((2 * Math.PI * k) / N)), closed: true };
    const now = Math.atan2(dot(r, Qn), dot(r, P)), far = Math.acos(-1 / e) - 1e-3;
    let end = far;                                   // outward only as far as the limit
    for (let k = 1; k <= N; k++) { const nu = now + ((far - now) * k) / N; if (len(at(nu)) > limit) { end = nu; break; } }
    if (end <= now) return null;
    return { pts: Array.from({ length: N + 1 }, (_, k) => at(now + ((end - now) * k) / N)), closed: false };
  }

  // the orbit she goes onto, going free at rel off a body of mu: circular, prograde about the system's up
  function onto(rel, mu) {
    const R = len(rel), up = Math.abs(rel[2]) < 0.95 * R ? [0, 0, 1] : [1, 0, 0], along = cross(up, rel);
    return conic(rel, scale(along, Math.sqrt(mu / R) / len(along)), mu, 3 * R);
  }

  function work(under) {
    const st = map.state, out = [];
    for (const c of contacts) {
      const s = st.ships?.[c.id];
      if (!s || s.propellant_share == null || !s.velocity_kms) continue;          // the side's own, with what she moves at
      const free = s.mode === 'orbit' || (s.mode === 'free' && !s.goal && !s.burning);
      if (!free && (s.mode !== 'station' || !under.has(c.id))) continue;          // on station: the selection's alone
      const p = st.contacts?.[c.id];
      const b = p && (s.orbit_of ? map.bodies[s.orbit_of] : dominant(p));
      const bp = b && st.bodies[b.id], bv = b && st.bodies_kms?.[b.id];
      if (!bp || !bv || !(b.mass_kg > 0)) continue;
      const r = sub(p, bp), mu = G * b.mass_kg, path = free || b.parent == null   // on station: what K would give
        ? conic(r, sub(s.velocity_kms, bv), mu, Math.max(3 * len(r), b.zones?.soi_km ?? 0)) : onto(r, mu);
      if (path) out.push({ id: c.id, body: b.id, k: !free, ...path });
    }
    return out;
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  // the unit a ship's path is drawn for: herself if she has a mark of her own, else the nearest
  // formation over her that has one (folded into it)
  function drawnAs(id, marked, byId) {
    for (let u = id; u; u = byId[u]?.parent) if (marked.has(u)) return u;
    return id;
  }
  function stroke(pts, o, color, dash) {
    ctx.strokeStyle = color; ctx.setLineDash(dash);
    ctx.beginPath();
    let pen = false;
    for (const q of pts) {
      const s = map.project([o[0] + q[0], o[1] + q[1], o[2] + q[2]]);
      if (!s) { pen = false; continue; }
      if (pen) ctx.lineTo(s.x, s.y); else ctx.moveTo(s.x, s.y);
      pen = true;
    }
    ctx.stroke();
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!map?.state || !map.def || !style) return;
    const byId = Object.fromEntries(contacts.map((c) => [c.id, c]));
    const under = new Set(), walk = (u) => { under.add(u); (byId[u]?.children ?? []).forEach(walk); };
    if (sel?.kind === 'contact') walk(sel.id);
    if (keptFor !== map.state || keptSel !== sel) { kept = work(under); keptFor = map.state; keptSel = sel; }
    const marked = new Set((map.marks ?? []).map((m) => m.id)), seen = new Set();
    const friend = (style.affiliation.friend ?? style.affiliation.unknown).color, fuchsia = style.palette.fuchsia;
    ctx.lineWidth = 1;
    for (const k of kept) {
      if (k.k ? !under.has(k.id) || ordering : !on) continue;          // what K would give: only the selection's
      const as = `${k.k ? 'k' : ''}${drawnAs(k.id, marked, byId)}`;
      if (seen.has(as)) continue;                                      // one path for a folded formation
      seen.add(as);
      const o = map.position({ kind: 'body', id: k.body });
      if (o) stroke(k.pts, o, k.k ? rgba(fuchsia, 0.8) : rgba(friend, under.has(k.id) ? 0.75 : 0.28), k.k ? [1, 4] : [3, 4]);
    }
    const a = ordering?.mode === 'move' && ordering.free ? aim() : null;        // a free move at a body: there, her orbit
    const b = a?.kind === 'body' && map.bodies[a.id];
    if (b?.mass_kg > 0 && a.standoff > 0) {
      const d = sub(a.from, a.to), path = onto(scale(d, a.standoff / len(d)), G * b.mass_kg);
      if (path) stroke(path.pts, a.to, rgba(fuchsia, 0.8), [1, 4]);
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

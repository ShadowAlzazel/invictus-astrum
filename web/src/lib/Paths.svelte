<script>
  // Free paths: where the side's free ships go with no drive lit, as the map can tell from its own
  // picture. A ship on an orbit (orbit_of) or coasting with no order is drawn her conic about the
  // body whose well she is in (in a binary, the one that pulls harder; out of every well, the
  // star): two bodies only, her state read off the picture and the body's, an estimate like Eva's.
  // An ellipse whole; a hyperbola from where she is, outward. Worked out once a picture, drawn
  // every frame about where the body is drawn. Nothing of it is asked of the server.
  import { onMount, onDestroy } from 'svelte';
  import { rgba } from './symbols.js';

  export let map = null;
  export let style = null;
  export let on = true;                 // [layers] paths
  export let contacts = [];
  export let sel = null;

  const G = 6.6743e-20;                 // km³/(kg·s²)
  const N = 120;
  let canvas, ctx, unhook, W = 0, H = 0, kept = null, keptFor = null;

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

  function work() {
    const st = map.state, out = [];
    for (const c of contacts) {
      const s = st.ships?.[c.id];
      if (!s || s.propellant_share == null || !s.velocity_kms) continue;          // the side's own, with what she moves at
      const free = s.mode === 'orbit' || (s.mode === 'free' && !s.goal && !s.burning);
      if (!free) continue;
      const p = st.contacts?.[c.id];
      const b = p && (s.orbit_of ? map.bodies[s.orbit_of] : dominant(p));
      const bp = b && st.bodies[b.id], bv = b && st.bodies_kms?.[b.id];
      if (!bp || !bv || !(b.mass_kg > 0)) continue;
      const r = sub(p, bp), path = conic(r, sub(s.velocity_kms, bv), G * b.mass_kg, Math.max(3 * len(r), b.zones?.soi_km ?? 0));
      if (path) out.push({ id: c.id, body: b.id, ...path });
    }
    return out;
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!on || !map?.state || !map.def || !style) return;
    if (keptFor !== map.state) { kept = work(); keptFor = map.state; }
    const picked = new Set(sel?.kind === 'contact' ? [sel.id, ...(contacts.find((c) => c.id === sel.id)?.children ?? [])] : []);
    const color = (style.affiliation.friend ?? style.affiliation.unknown).color;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    for (const k of kept) {
      const o = map.position({ kind: 'body', id: k.body });
      if (!o) continue;
      ctx.strokeStyle = rgba(color, picked.has(k.id) ? 0.75 : 0.28);
      ctx.beginPath();
      let pen = false;
      for (const q of k.pts) {
        const s = map.project([o[0] + q[0], o[1] + q[1], o[2] + q[2]]);
        if (!s) { pen = false; continue; }
        if (pen) ctx.lineTo(s.x, s.y); else ctx.moveTo(s.x, s.y);
        pen = true;
      }
      ctx.stroke();
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

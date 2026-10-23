<script>
  // The galmap HUD cursor: same diamond, hairlines and colours. Here it locks onto any mark
  // (body or unit), reads bearing / range / Eve–Haid from the active bullseye, and brackets
  // the selection. When free, it reads the point under it on the bullseye's plane.
  import { onMount, onDestroy } from 'svelte';
  import { km, bearing, elev, lightTime } from './format.js';
  import { niceLength } from './SystemMap.js';

  export let map = null;
  export let style = null;
  export let overUI = false;    // pointer is over a panel: hide hairlines
  export let settings = null;   // display settings: hairlines, notches, readout, text sizes

  let canvas, ctx, unhook;
  let W = 0, H = 0, dpr = 1;
  let mx = -1, my = -1, hx = -1, hy = -1, dx = -1, dy = -1;

  const lerp = (a, b, t) => a + (b - a) * t;
  const col = (hex, a) => { const v = parseInt(hex.slice(1), 16); return `rgba(${(v >> 16) & 255},${(v >> 8) & 255},${v & 255},${a})`; };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (mx < 0) { mx = W / 2; my = H / 2; hx = mx; hy = my; dx = mx; dy = my; }
  }
  const onMove = (e) => { mx = e.clientX; my = e.clientY; };

  function text(s, x, y, c, size = 10, font = '"Share Tech Mono", monospace') {
    ctx.font = `${size}px ${font}`;
    ctx.fillStyle = c;
    ctx.fillText(s, x, y);
  }

  function brackets(x, y, r, c) {
    const k = 5;
    ctx.strokeStyle = c; ctx.lineWidth = 1.2;
    for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      ctx.beginPath();
      ctx.moveTo(x + sx * r, y + sy * (r - k));
      ctx.lineTo(x + sx * r, y + sy * r);
      ctx.lineTo(x + sx * (r - k), y + sy * r);
      ctx.stroke();
    }
  }

  function tick(p, c) {
    const f = p && map.footOf(p), s = f && map.project(f);
    if (!s) return;
    ctx.strokeStyle = c; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(s.x - 5, s.y); ctx.lineTo(s.x + 5, s.y); ctx.stroke();
  }

  // the scale on the hairlines: a notch every round distance (at the depth of what is under the
  // cursor), every fifth longer, the first one read
  const NOTCH_PX = 40;              // notches 40 to about 100 px apart
  function notches(x, y, p, c, size) {
    const k = map.pxPerKm(p ?? undefined);
    if (!(k > 0)) return;
    const step = niceLength(NOTCH_PX / k), s = step * k;
    ctx.strokeStyle = c; ctx.lineWidth = 0.8;
    ctx.beginPath();
    for (let i = 1; i * s < Math.max(W, H) && i < 80; i++) {
      const a = i % 5 ? 3 : 6, r = i * s;
      ctx.moveTo(x + r, y - a); ctx.lineTo(x + r, y + a);
      ctx.moveTo(x - r, y - a); ctx.lineTo(x - r, y + a);
      ctx.moveTo(x - a, y + r); ctx.lineTo(x + a, y + r);
      ctx.moveTo(x - a, y - r); ctx.lineTo(x + a, y - r);
    }
    ctx.stroke();
    text(km(step), x + 5, y + s + 3, c, size);
  }

  function readout(p) {
    const a = map.aer(p);
    return a ? `${bearing(a.bearing)}  ${km(a.range)}  ${elev(a.elevation)}  ·  ${lightTime(a.range)}` : '';
  }

  function nameOf(m) {
    if (m.kind === 'body') return map.bodies[m.id]?.name ?? m.id;
    if (m.kind === 'contact') return map.contactName?.(m.group ? m.group.join('+') : m.id) ?? m.id;
    return '';
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!style) return;
    const V = style.palette.violet, F = style.palette.fuchsia, INK = style.palette.ink;

    // selection
    const sel = map?.selected;
    const sp = sel && map.position(sel);
    const ss = sp && map.project(sp);
    if (ss) {
      const mk = map.marks.find((m) => m.kind === sel.kind && m.id === sel.id);
      brackets(ss.x, ss.y, (mk?.r ?? 8) + 6, col(F, 0.95));
      tick(sp, col(F, 0.8));
    }

    const hover = map && !overUI ? map.hover : null;
    const lock = hover && map.marks.find((m) => m.kind === hover.kind && m.id === hover.id);
    const tx = lock ? lock.x : mx, ty = lock ? lock.y : my;

    hx = lerp(hx, mx, 0.10); hy = lerp(hy, my, 0.10);
    dx = lerp(dx, tx, lock ? 0.35 : 0.20); dy = lerp(dy, ty, lock ? 0.35 : 0.20);

    const d = overUI ? 9 : 14;
    const gap = d + 6;

    const C = settings?.cursor ?? { hairlines: true, notches: true, readout: true };
    const px = settings?.text.readout_px ?? 9, namePx = settings?.text.unit_label_px ?? 12;
    if (!overUI && C.hairlines) {
      ctx.lineWidth = 0.8;
      ctx.strokeStyle = col(V, 0.35);
      ctx.beginPath(); ctx.moveTo(0, hy); ctx.lineTo(hx - gap, hy); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(hx + gap, hy); ctx.lineTo(W, hy); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(hx, 0); ctx.lineTo(hx, hy - gap); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(hx, hy + gap); ctx.lineTo(hx, H); ctx.stroke();
      if (C.notches && map?.state) notches(hx, hy, lock ? map.position(hover) : map.pointAt(mx, my), col(V, 0.5), px);
    }

    ctx.strokeStyle = col(lock ? F : V, 0.95);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(dx, dy - d); ctx.lineTo(dx + d, dy); ctx.lineTo(dx, dy + d); ctx.lineTo(dx - d, dy);
    ctx.closePath(); ctx.stroke();

    ctx.fillStyle = col(V, 0.9);
    ctx.fillRect(dx - 1.5, dy - 1.5, 3, 3);

    if (!overUI && map?.state) {
      if (lock) {
        const p = map.position(hover);
        text(nameOf(hover), dx + d + 8, dy - 3, col(INK, 0.95), namePx, '"Chakra Petch", sans-serif');
        if (p && C.readout) text(readout(p), dx + d + 8, dy + 1 + px, col(V, 0.85), px);
        tick(p, col(V, 0.8));
      } else {
        const p = map.pointAt(mx, my);
        const a = p && map.aer(p);
        if (a && C.readout) text(`${bearing(a.bearing)}  ${km(a.range)}`, dx + d + 8, dy + 4, col(V, 0.6), px);
      }
    }

    ctx.strokeStyle = col(F, 0.35);
    ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(dx - d - 4, dy); ctx.lineTo(dx - d - 10, dy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(dx + d + 4, dy); ctx.lineTo(dx + d + 10, dy); ctx.stroke();
  }

  onMount(() => {
    ctx = canvas.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', onMove);
  });
  $: if (map && ctx && !unhook) unhook = map.onFrame(draw);
  onDestroy(() => {
    unhook?.();
    window.removeEventListener('resize', resize);
    window.removeEventListener('mousemove', onMove);
  });
</script>

<canvas bind:this={canvas} aria-hidden="true"></canvas>

<style>
  canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 50; }
</style>

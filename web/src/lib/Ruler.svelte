<script>
  // The ruler (L): from where it was clicked to the cursor, or to the second click. Points are on
  // the active bullseye's plane, or a unit or a body under the cursor. It reads the length, the light
  // time, and the bearing and elevation from the first point in the bullseye's axes.
  import { onMount, onDestroy } from 'svelte';
  import { heading } from './orders.js';
  import { km, bearing, elev, lightTime } from './format.js';
  import { cap, keymap } from './keys.js';

  export let map = null;
  export let style = null;
  export let ruler = { a: null, b: null };
  export let markAt = () => null;

  let canvas, ctx, unhook, W = 0, H = 0;
  let cursor = { x: -1, y: -1 };
  const onMove = (e) => { cursor = { x: e.clientX, y: e.clientY }; };
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function here() {
    const m = markAt(cursor.x, cursor.y);
    return (m && map.position({ kind: m.kind, id: m.id })) || map.pointAt(cursor.x, cursor.y);
  }
  function tick(p, color) {
    ctx.strokeStyle = color; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(p.x - 6, p.y); ctx.lineTo(p.x + 6, p.y); ctx.moveTo(p.x, p.y - 6); ctx.lineTo(p.x, p.y + 6); ctx.stroke();
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!map?.state || !style || !ruler) return;
    const color = style.palette.cyan ?? '#9ff0ff';
    const a = ruler.a, b = ruler.b ?? (a ? here() : null);
    if (!a) {
      const p = here(), s = p && map.project(p);
      if (s) tick(s, color);
      return;
    }
    const sa = map.project(a), sb = b && map.project(b);
    if (!sa || !sb) return;
    ctx.strokeStyle = color; ctx.lineWidth = 1.4; ctx.setLineDash(ruler.b ? [] : [6, 4]);
    ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y); ctx.stroke(); ctx.setLineDash([]);
    tick(sa, color); tick(sb, color);
    const d = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]), hd = heading(map, { from: a, to: b });
    const lines = [km(d), `${lightTime(d)} light`, hd ? `${bearing(hd.bearing)} ${elev(hd.elevation)} from the first point` : ''];
    ctx.font = '11px "Share Tech Mono", monospace';
    const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 14, h = lines.length * 14 + 8;
    const x = Math.min((sa.x + sb.x) / 2 + 12, W - w - 8), y = Math.max(8, Math.min((sa.y + sb.y) / 2 - h - 8, H - h - 8));
    ctx.fillStyle = 'rgba(7,5,15,0.82)'; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = color; ctx.fillRect(x, y, 2, h);
    lines.forEach((l, i) => { ctx.fillStyle = i ? 'rgba(228,222,247,0.85)' : color; ctx.fillText(l, x + 8, y + 16 + i * 14); });
  }
  onMount(() => {
    ctx = canvas.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', onMove);
  });
  $: if (map && ctx && !unhook) unhook = map.onFrame(draw);
  onDestroy(() => {
    unhook?.();
    window.removeEventListener('resize', resize);
    window.removeEventListener('pointermove', onMove);
  });
</script>

<canvas bind:this={canvas} aria-hidden="true"></canvas>
<p class="hint" data-ui>Ruler: click {ruler?.a && !ruler.b ? 'where it ends' : 'where it starts'} · on a unit or a body, from it · right click or <kbd>{cap($keymap.ruler)}</kbd> put it away</p>

<style>
  canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 19; }
  .hint { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 40; margin: 0; padding: 6px 12px;
          background: var(--panel); border-left: 2px solid var(--cyan, #9ff0ff); font-size: 11px; color: var(--dim); }
  kbd { font-family: var(--mono); font-size: 10px; border: 1px solid var(--rule); padding: 0 4px; color: var(--ink); }
</style>

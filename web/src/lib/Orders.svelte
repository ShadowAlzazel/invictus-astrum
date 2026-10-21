<script>
  // Orders on the map. While an order is aimed (A on a selected ship): a vector from her to the
  // cursor, or to the unit or body under it, with what it will take; and the telegraph, which sets
  // the acceleration she will hold, from her most down to stop. Every ship flying an order shows
  // its vector and time to target; the selected one brightest.
  import { onMount, onDestroy } from 'svelte';
  import { aimAt, estimate, heading, hms, detents } from './orders.js';
  import { km, bearing, elev } from './format.js';

  export let map = null;
  export let style = null;
  export let state = null;
  export let contacts = [];
  export let sel = null;
  export let ordering = null;       // { unit, g, tilt } while an order is being aimed
  export let message = '';

  let canvas, ctx, unhook, W = 0, H = 0, dpr = 1;
  let cursor = { x: -1, y: -1 };

  $: ship = ordering ? state?.ships?.[ordering.unit] : null;
  $: spec = ordering ? contacts.find((c) => c.id === ordering.unit)?.ship : null;
  $: marks = ship ? detents(ship.max_accel_g, spec?.cruise_g) : [];
  $: shown = ordering ? Math.min(ordering.g, ship?.max_accel_g ?? ordering.g) : 0;
  $: name = ordering ? contacts.find((c) => c.id === ordering.unit)?.callsign ?? ordering.unit : '';

  // what the cursor points at now; App asks for it when the order is given
  export function aim() { return ordering && map ? aimAt(map, ordering.unit, cursor, ordering.tilt) : null; }

  // keys while aiming: W/S step the telegraph (Shift: by 0.01 g), E/Q tilt toward Eve or Haid
  export function key(e) {
    if (!ordering || !ship) return false;
    const k = e.key.toLowerCase();
    if (k === 'w' || k === 's') {
      const up = k === 'w';
      if (e.shiftKey) ordering.g = Math.max(0, Math.min(ship.max_accel_g, ordering.g + (up ? 0.01 : -0.01)));
      else {
        const list = marks.map((d) => d.g);
        const cur = Math.min(ordering.g, ship.max_accel_g);
        const next = up ? [...list].reverse().find((g) => g > cur + 1e-6) : list.find((g) => g < cur - 1e-6);
        if (next != null) ordering.g = next;
      }
      ordering = ordering;
      return true;
    }
    if (k === 'e' || k === 'q') {
      ordering.tilt = Math.max(-80, Math.min(80, ordering.tilt + (k === 'e' ? 5 : -5)));
      ordering = ordering;
      return true;
    }
    return false;
  }

  function setFrom(e) {                         // a click or drag on the scale
    const r = e.currentTarget.getBoundingClientRect();
    const f = 1 - Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
    ordering.g = Math.round(f * ship.max_accel_g * 100) / 100;
    ordering = ordering;
  }
  let dragging = false;

  const col = (hex, a) => { const v = parseInt(hex.slice(1), 16); return `rgba(${(v >> 16) & 255},${(v >> 8) & 255},${v & 255},${a})`; };
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  const onMove = (e) => { cursor = { x: e.clientX, y: e.clientY }; };

  function label(lines, x, y, color) {
    ctx.font = '11px "Share Tech Mono", monospace';
    const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 14, h = lines.length * 14 + 8;
    const bx = Math.min(x + 14, W - w - 8), by = Math.max(8, Math.min(y - h - 10, H - h - 8));
    ctx.fillStyle = 'rgba(7,5,15,0.82)'; ctx.fillRect(bx, by, w, h);
    ctx.fillStyle = color; ctx.fillRect(bx, by, 2, h);
    lines.forEach((l, i) => { ctx.fillStyle = i ? 'rgba(228,222,247,0.85)' : color; ctx.fillText(l, bx + 8, by + 16 + i * 14); });
  }

  function line(a, b, color, width, dash = []) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); ctx.setLineDash([]);
  }

  function diamond(p, r, color) {
    ctx.strokeStyle = color; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(p.x, p.y - r); ctx.lineTo(p.x + r, p.y); ctx.lineTo(p.x, p.y + r); ctx.lineTo(p.x - r, p.y); ctx.closePath(); ctx.stroke();
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!map?.state || !style) return;
    const F = style.palette.fuchsia, C = style.palette.cyan ?? '#9ff0ff';
    // orders being flown: every ship's vector, the selected one bright with its time to target
    for (const [id, s] of Object.entries(state?.ships ?? {})) {
      if (!s.goal?.aim_km) continue;
      const a = map.project(map.position({ kind: 'contact', id })), b = map.project(s.goal.aim_km);
      if (!a || !b) continue;
      const on = sel?.kind === 'contact' && sel.id === id;
      line(a, b, col(C, on ? 0.85 : 0.3), on ? 1.4 : 1, [6, 4]);
      diamond(b, on ? 5 : 3.5, col(C, on ? 0.9 : 0.35));
      if (on && !ordering) label([`${s.goal.label}`, `ETA ${hms(s.goal.eta_s)} · ${s.goal.g} g`, `${km(s.goal.range_km)} to go`], b.x, b.y, C);
    }
    // the order being aimed
    const aimed = aim();
    if (aimed) {
      const a = map.project(aimed.from), b = map.project(aimed.to);
      if (a && b) {
        const est = estimate(aimed, shown), hd = heading(map, aimed);
        line(a, b, col(F, 0.95), 1.6);
        if (aimed.kind === 'point') diamond(b, 6, col(F, 0.95));
        else { ctx.strokeStyle = col(F, 0.95); ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(b.x, b.y, 12, 0, Math.PI * 2); ctx.stroke(); }
        label([aimed.kind === 'point' ? `to ${bearing(hd.bearing)} ${elev(hd.elevation)}` : `to ${aimed.label}`,
               `${km(est.distance)}${aimed.standoff ? `, stopping ${km(aimed.standoff)} short` : ''}`,
               shown > 0 ? `ETA ≈ ${hms(est.eta)} at ${shown.toFixed(2)} g · Δv ≈ ${est.dv.toFixed(1)} km/s` : 'stop: cut her drive'],
              b.x, b.y, F);
      }
    }
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

{#if ordering && ship}
  <aside class="telegraph" data-ui>
    <header><b>Order</b><span>{name}</span></header>
    <div class="body">
      <div class="scale" role="slider" tabindex="-1" aria-label="acceleration" aria-valuenow={shown}
           on:pointerdown={(e) => { dragging = true; e.currentTarget.setPointerCapture(e.pointerId); setFrom(e); }}
           on:pointermove={(e) => dragging && setFrom(e)} on:pointerup={() => (dragging = false)}>
        <i class="fill" style="height:{(shown / ship.max_accel_g) * 100}%"></i>
        {#if spec?.cruise_g}
          <i class="band" style="bottom:{(Math.min(spec.cruise_g[0], ship.max_accel_g) / ship.max_accel_g) * 100}%;
             height:{((Math.min(spec.cruise_g[1], ship.max_accel_g) - Math.min(spec.cruise_g[0], ship.max_accel_g)) / ship.max_accel_g) * 100}%"></i>
        {/if}
        {#each marks as d}
          <button class="mark" class:on={Math.abs(d.g - shown) < 0.005} style="bottom:{(d.g / ship.max_accel_g) * 100}%"
                  on:pointerdown|stopPropagation={() => { ordering.g = d.g; ordering = ordering; }}>
            <span>{d.label}</span><em>{d.g.toFixed(2)} g</em>
          </button>
        {/each}
      </div>
      <div class="read">
        <b>{shown.toFixed(2)} <small>g</small></b>
        <span>{(shown * 9.80665).toFixed(2)} m/s²</span>
        <span class="dim">most {ship.max_accel_g.toFixed(3)} g now</span>
        <span class="dim">{ordering.tilt ? elev(ordering.tilt) : 'level'} of the bullseye</span>
      </div>
    </div>
    <p class="keys"><kbd>W</kbd><kbd>S</kbd> telegraph · <kbd>⇧</kbd> fine · <kbd>E</kbd><kbd>Q</kbd> Eve / Haid · click to order · <kbd>Esc</kbd> cancel</p>
    {#if message}<p class="msg">{message}</p>{/if}
  </aside>
{:else if message}
  <p class="toast" data-ui>{message}</p>
{/if}

<style>
  canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 30; }
  .telegraph { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 40; width: 330px;
               background: var(--panel); border-left: 2px solid var(--fuchsia); padding: 10px 14px; backdrop-filter: blur(6px); }
  header { display: flex; gap: 10px; align-items: baseline; font-family: var(--display); }
  header b { color: var(--fuchsia); letter-spacing: 0.1em; text-transform: uppercase; font-size: 12px; }
  header span { font-size: 15px; }
  .body { display: grid; grid-template-columns: 150px 1fr; gap: 14px; margin-top: 10px; }
  .scale { position: relative; height: 170px; margin-left: 4px; border-left: 2px solid var(--rule); cursor: ns-resize; touch-action: none; }
  .fill { position: absolute; left: -2px; bottom: 0; width: 6px; background: var(--fuchsia); }
  .band { position: absolute; left: -2px; width: 6px; background: rgba(159, 240, 255, 0.35); }
  .mark { position: absolute; left: 10px; transform: translateY(50%); display: flex; gap: 8px; align-items: baseline;
          background: none; border: 0; padding: 0; color: var(--dim); font: inherit; white-space: nowrap; }
  .mark::before { content: ''; position: absolute; left: -12px; top: 50%; width: 8px; height: 1px; background: var(--dim); }
  .mark span { font-family: var(--display); font-size: 12px; }
  .mark em { font-style: normal; font-size: 10px; }
  .mark:hover, .mark.on { color: var(--ink); }
  .mark.on span { color: var(--fuchsia); }
  .read { display: grid; align-content: start; gap: 3px; }
  .read b { font-family: var(--display); font-size: 30px; font-weight: 600; line-height: 1; }
  .read small { font-size: 14px; color: var(--dim); }
  .read .dim { color: var(--dim); font-size: 11px; }
  .keys { margin: 10px 0 0; font-size: 10px; color: var(--dim); }
  kbd { border: 1px solid var(--rule); padding: 0 3px; font-family: var(--mono); font-size: 9px; }
  .msg { margin: 6px 0 0; color: #ffd27a; font-size: 11px; }
  .toast { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 40; margin: 0; padding: 6px 12px;
           background: var(--panel); border-left: 2px solid var(--cyan, #9ff0ff); font-size: 12px; }
</style>

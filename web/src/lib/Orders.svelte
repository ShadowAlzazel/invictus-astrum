<script>
  // Orders on the map. While an order is aimed (A on a selected ship or formation): a vector from it
  // to the cursor, or to the unit or body under it, with what it will take, and for a formation
  // each ship's own line; and the telegraph, which sets the acceleration held, from the most the
  // slowest ship can give down to stop. Every ship flying an order shows its vector and time to
  // target; the selected ones brightest.
  import { onMount, onDestroy } from 'svelte';
  import { aimAt, estimate, heading, hms, group, stepG, shipsUnder } from './orders.js';
  import Telegraph from './Telegraph.svelte';
  import { km, bearing, elev } from './format.js';

  export let map = null;
  export let style = null;
  export let state = null;
  export let contacts = [];
  export let sel = null;
  export let ordering = null;       // { unit, ships, g, tilt } while an order is being aimed
  export let message = '';

  let canvas, ctx, unhook, W = 0, H = 0, dpr = 1;
  let cursor = { x: -1, y: -1 };

  $: grp = ordering ? group(state, contacts, ordering.ships) : null;
  $: shown = ordering ? Math.min(ordering.g, grp?.maxG ?? ordering.g) : 0;
  $: name = ordering ? map?.contactName?.(ordering.unit) ?? ordering.unit : '';
  $: selShips = sel?.kind === 'contact' ? new Set(shipsUnder(contacts, state, sel.id)) : new Set();

  // what the cursor points at now; App asks for it when the order is given
  export function aim() { return ordering && map ? aimAt(map, ordering.unit, ordering.ships, cursor, ordering.tilt) : null; }

  // keys while aiming: W/S step the telegraph (Shift: by 0.01 g), E/Q tilt toward Eve or Haid
  export function key(e) {
    if (!ordering || !grp) return false;
    const k = e.key.toLowerCase();
    if (k === 'w' || k === 's') {
      ordering.g = stepG(ordering.g, grp.maxG, grp.cruise, k === 'w', e.shiftKey);
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
      const on = selShips.has(id);
      line(a, b, col(C, on ? 0.85 : 0.3), on ? 1.4 : 1, [6, 4]);
      diamond(b, on ? 5 : 3.5, col(C, on ? 0.9 : 0.35));
      if (on && !ordering && sel?.id === id) label([`${s.goal.label}`, `ETA ${hms(s.goal.eta_s)} · ${s.goal.g} g`, `${km(s.goal.range_km)} to go`], b.x, b.y, C);
    }
    // the order being aimed
    const aimed = aim();
    if (aimed) {
      const a = map.project(aimed.from), b = map.project(aimed.to);
      if (a && b) {
        const est = estimate(aimed, shown), hd = heading(map, aimed);
        line(a, b, col(F, 0.95), 1.6);
        if (ordering.ships.length > 1 || ordering.ships[0] !== ordering.unit) {      // each ship's own line, offset kept
          for (const id of ordering.ships) {
            const p = map.position({ kind: 'contact', id });
            if (!p) continue;
            const to = [aimed.to[0] + p[0] - aimed.from[0], aimed.to[1] + p[1] - aimed.from[1], aimed.to[2] + p[2] - aimed.from[2]];
            const sa = map.project(p), sb = map.project(to);
            if (sa && sb) line(sa, sb, col(F, 0.3), 1, [3, 4]);
          }
        }
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

{#if ordering && grp}
  <aside class="telegraph" data-ui>
    <header><b>Order</b><span>{name}</span>{#if ordering.ships.length > 1}<i>{ordering.ships.length} ships</i>{/if}</header>
    <div class="body">
      <Telegraph maxG={grp.maxG} cruise={grp.cruise} value={shown}
                 note={`${ordering.tilt ? elev(ordering.tilt) : 'level'} of the bullseye`}
                 onset={(g) => { ordering.g = g; ordering = ordering; }}>
        {#if ordering.ships.length > 1}<span class="dim">held to the slowest ship's most</span>{/if}
      </Telegraph>
    </div>
    <p class="keys"><kbd>W</kbd><kbd>S</kbd> telegraph · <kbd>⇧</kbd> fine · <kbd>E</kbd><kbd>Q</kbd> Eve / Haid · click to order · <kbd>Esc</kbd> cancel</p>
    {#if message}<p class="msg">{message}</p>{/if}
  </aside>
{:else if message}
  <p class="toast" data-ui>{message}</p>
{/if}

<style>
  canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 18; }   /* under the panels */
  .telegraph { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 40; width: 330px;
               background: var(--panel); border-left: 2px solid var(--fuchsia); padding: 10px 14px; backdrop-filter: blur(6px); }
  header { display: flex; gap: 10px; align-items: baseline; font-family: var(--display); }
  header b { color: var(--fuchsia); letter-spacing: 0.1em; text-transform: uppercase; font-size: 12px; }
  header span { font-size: 15px; }
  .body { margin-top: 10px; }
  header i { margin-left: auto; font-style: normal; font-size: 11px; color: var(--dim); }
  .keys { margin: 10px 0 0; font-size: 10px; color: var(--dim); }
  kbd { border: 1px solid var(--rule); padding: 0 3px; font-family: var(--mono); font-size: 9px; }
  .msg { margin: 6px 0 0; color: #ffd27a; font-size: 11px; }
  .toast { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 40; margin: 0; padding: 6px 12px;
           background: var(--panel); border-left: 2px solid var(--cyan, #9ff0ff); font-size: 12px; }
</style>

<script>
  // Orders on the map. While an order is aimed (A on a selected ship or formation): a vector from it
  // to the cursor, or to the unit or body under it, with what it will take, and for a formation
  // each ship's own line; and the telegraph, which sets the acceleration held, from the most the
  // slowest ship can give down to stop. Every ship flying an order shows its vector and time to
  // target; the selected ones brightest.
  import { onMount, onDestroy } from 'svelte';
  import { nextThen, nextShape, shapes, toggleAttack, aimAt, estimate, heading, hms, group, stepG, shipsUnder } from './orders.js';
  import Telegraph from './Telegraph.svelte';
  import { cap, is, keymap } from './keys.js';
  import { km, bearing, elev } from './format.js';

  export let map = null;
  export let style = null;
  export let state = null;
  export let contacts = [];
  export let sel = null;
  export let chosen = null;             // the unit (or group, "a+b") the selection orders
  export let ordering = null;       // { unit, ships, g, tilt, plane } while an order is being aimed
  export let message = '';
  export let formations = null;         // the formation presets (data/formations.toml): the shape a formation takes

  let canvas, ctx, unhook, W = 0, H = 0, dpr = 1;
  let cursor = { x: -1, y: -1 };

  $: grp = ordering ? group(state, contacts, ordering.ships) : null;
  $: shown = ordering ? Math.min(ordering.g, grp?.maxG ?? ordering.g) : 0;
  $: name = ordering ? map?.contactName?.(ordering.unit) ?? ordering.unit : '';
  $: selShips = chosen ? new Set(shipsUnder(contacts, state, chosen)) : new Set();

  // what the cursor points at now; App asks for it when the order is given
  export function aim() { return ordering && map ? aimAt(map, ordering.unit, ordering.ships, cursor, ordering.tilt, ordering.plane) : null; }
  // Eve and Haid from her own height, or from the bullseye (level: on its plane)
  function togglePlane() { ordering.plane = ordering.plane === 'bullseye' ? 'her' : 'bullseye'; ordering.tilt = 0; ordering = ordering; }
  $: onBull = ordering?.plane === 'bullseye';
  $: note = onBull ? (ordering.tilt ? `${elev(ordering.tilt)} of the bullseye` : 'level with the bullseye')
                   : (ordering?.tilt ? `${elev(ordering.tilt)} from her` : 'level with her, along the bullseye');

  // keys while aiming (lib/keys.js): the telegraph up and down (Shift: by 0.01 g), tilt toward Eve
  // or Haid, and Eve and Haid from her own height or from the bullseye's plane
  export function key(e) {
    if (!ordering || !grp) return false;
    if (is(e, 'up') || is(e, 'down')) {
      ordering.g = stepG(ordering.g, grp.maxG, grp.cruise, is(e, 'up'), e.shiftKey);
      ordering = ordering;
      return true;
    }
    if (is(e, 'plane')) {
      togglePlane();
      return true;
    }
    if (is(e, 'eve') || is(e, 'haid')) {
      ordering.tilt = Math.max(-80, Math.min(80, ordering.tilt + (is(e, 'eve') ? 5 : -5)));
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
    const F = style.palette.fuchsia, C = style.palette.cyan ?? '#9ff0ff', E = style.palette.engage ?? '#ff3046';
    // orders being flown: every ship's vector, the selected one bright with its time to target
    for (const [id, s] of Object.entries(state?.ships ?? {})) {
      if (!s.goal?.aim_km) continue;
      const a = map.project(map.position({ kind: 'contact', id })), b = map.project(s.goal.aim_km);
      if (!a || !b) continue;
      const on = selShips.has(id), hue = s.goal.target?.engage ? E : C;      // an engage in red
      line(a, b, col(hue, on ? 0.85 : 0.3), on ? 1.4 : 1, [6, 4]);
      diamond(b, on ? 5 : 3.5, col(hue, on ? 0.9 : 0.35));
      if (on && !ordering && sel?.id === id) label([`${s.goal.label}`, `ETA ${hms(s.goal.eta_s)} · ${s.goal.g} g`, `${km(s.goal.range_km)} to go`], b.x, b.y, hue);
    }
    // the order being aimed
    const aimed = aim();
    if (aimed) {
      const a = map.project(aimed.from), b = map.project(aimed.to);
      if (a && b) {
        const pass = ordering.mode === 'attack' && ordering.then === 'pass';
        const ballistic = (ordering.mode === 'move' && ordering.then === 'ballistic') || pass, est = estimate(aimed, shown, ballistic), hd = heading(map, aimed);
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
        label(ordering.mode === 'turn'
          ? [`turn to ${aimed.kind === 'point' ? `${bearing(hd.bearing)} ${elev(hd.elevation)}` : aimed.label}`, 'her hull pointed there, nothing flown']
          : [aimed.kind === 'point' ? `to ${bearing(hd.bearing)} ${elev(hd.elevation)}` : `to ${aimed.label}`,
             `${km(est.distance)}${aimed.standoff && !ballistic ? `, stopping ${km(aimed.standoff)} short` : ''}`,
             shown > 0 ? `ETA ≈ ${hms(est.eta)} at ${shown.toFixed(2)} g · Δv ≈ ${est.dv.toFixed(1)} km/s` : 'stop: cut her drive',
             ...(ordering.mode === 'move' && shown > 0 ? [ballistic ? 'ballistic: no braking, on through it'
               : ordering.then === 'free' ? (aimed.kind === 'body' ? `then free: an orbit of ${aimed.label}` : 'then free: coasting, or an orbit in a well')
               : 'then holds station there'] : []),
             ...(ordering.mode === 'attack' && shown > 0 ? [pass ? 'pass on by: Ballistic orders, no braking' : 'then keeps station: Standing orders'] : [])],
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
    <header><b>{{ move: 'Move', attack: 'Attack-move', patrol: 'Patrol', turn: 'Turn' }[ordering.mode] ?? 'Order'}</b><span>{name}</span>{#if ordering.ships.length > 1}<i>{ordering.ships.length} ships</i>{/if}</header>
    <div class="body">
      <Telegraph maxG={grp.maxG} cruise={grp.cruise} value={shown}
                 {note}
                 onset={(g) => { ordering.g = g; ordering = ordering; }}>
        {#if ordering.ships.length > 1}<span class="dim">held to the slowest ship's most</span>{/if}
      </Telegraph>
    </div>
    <button class="plane" class:on={onBull} on:click={togglePlane} title="B: Eve and Haid from her own height, or from the bullseye's plane">
      <i></i>{onBull ? "Bullseye's plane" : 'Her own height'}<kbd>{cap($keymap.plane)}</kbd>
    </button>
    {#if ordering.mode === 'move'}
      <button class="plane" class:on={ordering.then !== 'station'} on:click={() => (ordering = { ...ordering, then: nextThen(ordering.then) })}
        title="How it ends (K cycles): hold station there (paying to hold her place); free there (an orbit in a body's well, paying only the burn onto it; else coasting); or ballistic (no braking: half the way burning, then on through it at that speed)">
        <i></i>{ordering.then === 'ballistic' ? 'Ballistic: burn, then on through' : ordering.then === 'free' ? 'Then free: orbit or coast' : 'Then hold station'}<kbd>{cap($keymap.free)}</kbd>
      </button>
    {:else if ordering.mode === 'attack'}
      <button class="plane" class:on={ordering.then !== 'station'} on:click={() => (ordering = { ...ordering, then: toggleAttack(ordering.then) })}
        title="K cycles: keep station (Standing orders, the usual); pass on by (Ballistic orders: one burn, no braking); or finish them (Destroy orders: the silenced and the wrecks too, till destroyed)">
        <i></i>{ordering.then === 'pass' ? 'Pass on by · Ballistic orders' : ordering.then === 'destroy' ? 'Finish them · Destroy orders' : 'Keep station · Standing orders'}<kbd>{cap($keymap.free)}</kbd>
      </button>
    {/if}
    {#if shapes(ordering) && formations}
      <button class="plane" class:on={ordering.shape !== formations.default} on:click={() => (ordering = { ...ordering, shape: nextShape(formations, ordering.shape) })}
        title="The shape its ships take on the way (O cycles; data/formations.toml)">
        <i></i>{formations.presets.find((p) => p.id === ordering.shape)?.name ?? 'As they stand'}<kbd>{cap($keymap.shape)}</kbd>
      </button>
    {/if}
    <p class="keys"><kbd>{cap($keymap.up)}</kbd><kbd>{cap($keymap.down)}</kbd> telegraph · <kbd>⇧</kbd> fine · <kbd>{cap($keymap.eve)}</kbd><kbd>{cap($keymap.haid)}</kbd> Eve / Haid · <kbd>{cap($keymap.plane)}</kbd> plane · click to order, <kbd>⇧</kbd>-click to queue · <kbd>{cap($keymap.order)}</kbd><kbd>{cap($keymap.attack)}</kbd><kbd>{cap($keymap.patrol)}</kbd><kbd>{cap($keymap.turn)}</kbd> move, attack, patrol, turn · <kbd>Esc</kbd> cancel</p>
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
  .plane { display: flex; align-items: center; gap: 8px; margin-top: 8px; background: none; border: 1px solid var(--rule);
           color: var(--dim); font: inherit; font-size: 11px; padding: 3px 8px; cursor: pointer; }
  .plane i { width: 7px; height: 7px; transform: rotate(45deg); border: 1px solid var(--violet); }
  .plane.on { color: var(--ink); border-color: var(--violet); }
  .plane.on i { background: var(--violet); }
  .plane kbd { margin-left: auto; }
  kbd { border: 1px solid var(--rule); padding: 0 3px; font-family: var(--mono); font-size: 9px; }
  .msg { margin: 6px 0 0; color: #ffd27a; font-size: 11px; }
  .toast { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 40; margin: 0; padding: 6px 12px;
           background: var(--panel); border-left: 2px solid var(--cyan, #9ff0ff); font-size: 12px; }
</style>

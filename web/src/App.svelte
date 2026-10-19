<script>
  import { onMount, onDestroy } from 'svelte';
  import { SystemMap } from './lib/SystemMap.js';
  import { api, StateStream } from './lib/api.js';
  import HudCursor from './lib/HudCursor.svelte';
  import Overlay from './lib/Overlay.svelte';
  import InfoPanel from './lib/InfoPanel.svelte';

  // sim seconds per real second; the clock runs in TDB seconds since J2000, like the server
  const WARPS = [[1, '1×'], [10, '10×'], [60, '1 min/s'], [600, '10 min/s'], [3600, '1 h/s'], [21600, '6 h/s'],
                 [86400, '1 d/s'], [604800, '1 wk/s'], [2629800, '1 mo/s'], [31557600, '1 yr/s']];

  let canvas, map = null, stream, meta = null, style = null, def = null, state = null;
  let systemId = null, playerId = 'arcvs', bullseyeId = 'system', scenarioOn = true;
  let t = 0, warp = 6, paused = false, last = 0, raf;
  let orbitsT = null, orbitsBusy = false;
  let layers = { orbits: true, bullseye: true, display: true, labels: true, contacts: true, zones: true };
  const LAYER_LABELS = { orbits: 'Orbits', bullseye: 'Bullseye', display: 'Body display', labels: 'Labels', contacts: 'Units', zones: 'Zones' };
  let scale = 1, sel = null, probe = null, overUI = false, error = null, errors = {}, version = 0;
  let showFindings = false, down = null, poll;

  $: player = meta?.players.find((p) => p.id === playerId);
  $: bullseyes = [{ id: 'system', name: `${def?.name ?? ''} centre` }, ...(player?.bullseyes.filter((b) => b.system === systemId) ?? [])];
  $: scenario = meta?.scenarios.find((s) => s.system === systemId);
  $: contacts = scenarioOn && scenario ? scenario.contacts : [];
  $: warnings = def?.findings.filter((f) => f.level === 'warning') ?? [];
  $: if (map) { map.bullseyeId = bullseyeId; map.contactName = (id) => contacts.find((c) => c.id === id)?.callsign ?? id; }

  function applyStyle(s) {
    style = s;
    const root = document.documentElement.style;
    for (const [k, v] of Object.entries(s.palette)) root.setProperty(`--${k}`, v);
    map?.setStyle(s);
  }

  async function loadMeta() {
    meta = await api.meta();
    applyStyle(meta.style);
    version = meta.version;
  }

  async function openSystem(id, keepTime = false) {
    systemId = id;
    def = await api.system(id);
    const sys = meta.systems.find((s) => s.id === id);
    if (!keepTime) t = sys.start;
    map.setSystem(def);
    sel = null; probe = null; orbitsT = null;
    if (!bullseyes.some((b) => b.id === bullseyeId)) bullseyeId = 'system';
    await refreshOrbits();
  }

  async function refreshOrbits() {
    if (orbitsBusy || !systemId) return;
    orbitsBusy = true;
    try { const at = t; map.setOrbits(await api.orbits(systemId, at)); orbitsT = at; } finally { orbitsBusy = false; }
  }

  function onstate(s) {
    if (s.error) { error = s.error; return; }
    if (s.system !== systemId) return;
    state = s;
    map.setState(s);
    if (orbitsT == null || Math.abs(s.t - orbitsT) > 2 * 86400) refreshOrbits();   // orbits precess: redraw now and then
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    const dt = last ? Math.min((now - last) / 1000, 0.25) : 0;
    last = now;
    if (!paused) t += dt * WARPS[warp][0];
    if (systemId) stream.request({ system: systemId, t, player: playerId, scenario: scenarioOn ? scenario?.id : null });
  }

  // ---- pointer ----------------------------------------------------------------------------------
  function markAt(x, y) {
    let best = null, bd = Infinity;
    for (const m of map.marks) {
      const d = Math.hypot(m.x - x, m.y - y);
      if (d < m.r + 8 && d < bd) { bd = d; best = m; }
    }
    return best;
  }
  function pointerMove(e) { const m = markAt(e.clientX, e.clientY); map.hover = m ? { kind: m.kind, id: m.id } : null; }
  function pointerDown(e) { down = { x: e.clientX, y: e.clientY, b: e.button }; }
  async function pointerUp(e) {
    if (!down || down.b !== 0 || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return;
    const m = markAt(e.clientX, e.clientY);
    if (m) { select({ kind: m.kind, id: m.id }); return; }
    const p = map.planeAt(e.clientX, e.clientY);
    if (!p) return select(null);
    select({ kind: 'point', p });
    probe = await api.probe(systemId, p, t, playerId, bullseyeId);
  }
  function dblclick(e) {
    const m = markAt(e.clientX, e.clientY);
    if (m) focusOn({ kind: m.kind, id: m.id });
  }
  function select(s) { sel = s; probe = null; map.selected = s; }

  // centre on something, and pull the camera in to a sensible distance for it
  function focusOn(s) {
    if (!s) return;
    let d = null;
    if (s.kind === 'body') {
      const b = map.bodies[s.id], kids = def.bodies.filter((c) => c.parent === s.id && c.orbit);
      const reach = Math.max(...kids.map((c) => c.orbit.apoapsis_km), 0);
      d = reach ? reach * 3 : Math.max(b.radius_km * 12, 2000);
    } else d = 2e5;
    map.focusOn(s, d);
  }

  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && e.target.type !== 'range') return;
    if (e.key === 'Escape') select(null);
    if (e.key === ' ') { e.preventDefault(); paused = !paused; }
    if (e.key === ']') warp = Math.min(warp + 1, WARPS.length - 1);
    if (e.key === '[') warp = Math.max(warp - 1, 0);
    if (e.key === 'f' || e.key === 'F') focusOn(sel);
    if (e.key === 'h' || e.key === 'H') focusOn({ kind: 'body', id: def.root });
    const i = Number(e.key) - 1;
    if (meta && i >= 0 && i < meta.systems.length) openSystem(meta.systems[i].id);
  }
  const trackUI = (e) => { overUI = !!e.target.closest?.('[data-ui]'); };
  function toggleLayer(k) { layers[k] = !layers[k]; map.setLayer(k, layers[k]); }
  function resetClock() { t = meta.systems.find((s) => s.id === systemId).start; }

  async function checkStatus() {
    try {
      const s = await api.status();
      errors = s.errors;
      if (s.version !== version) { await loadMeta(); await openSystem(systemId, true); }
    } catch { error = 'Cannot reach the server. Start it with: python serve.py'; return; }
    error = null;
  }

  onMount(async () => {
    map = new SystemMap(canvas);
    window.astrum = map;                 // for the console and for screenshot scripts
    canvas.addEventListener('pointermove', pointerMove);
    canvas.addEventListener('pointerdown', pointerDown, true);
    canvas.addEventListener('pointerup', pointerUp, true);
    canvas.addEventListener('dblclick', dblclick);
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('resize', () => map.resize());
    stream = new StateStream(onstate);
    try {
      await loadMeta();
      scale = style.display.scale_default;
      await openSystem(meta.systems.find((s) => s.id === 'sol')?.id ?? meta.systems[0].id);
    } catch (e) { error = 'Cannot reach the server. Start it with: python serve.py'; }
    raf = requestAnimationFrame(frame);
    poll = setInterval(checkStatus, 2000);
  });
  onDestroy(() => { cancelAnimationFrame(raf); clearInterval(poll); map?.dispose(); });
</script>

<svelte:window on:keydown={key} on:pointermove={trackUI} />

<canvas class="map" bind:this={canvas}></canvas>
<Overlay {map} {style} {scale} {layers} {contacts} />
<HudCursor {map} {style} {overUI} />

<div class="bar" data-ui>
  <span class="brand">INVICTUS <b>ASTRUM</b></span>
  {#each meta?.systems ?? [] as s, i}
    <button class:on={s.id === systemId} on:click={() => openSystem(s.id)} title="key {i + 1}">{s.name}</button>
  {/each}
</div>

<div class="clock" data-ui>
  <span class="utc">{state?.utc?.replace('T', ' ').replace('Z', ' UTC') ?? '—'}</span>
  <button on:click={() => (paused = !paused)} title="Space">{paused ? '▶' : '❚❚'}</button>
  <button on:click={() => (warp = Math.max(warp - 1, 0))} title="[">◀</button>
  <span class="warp">{WARPS[warp][1]}</span>
  <button on:click={() => (warp = Math.min(warp + 1, WARPS.length - 1))} title="]">▶</button>
  <button class="small" on:click={resetClock}>reset</button>
  <span class="src">{state?.source ?? ''}</span>
</div>

{#if error || Object.keys(errors).length}
  <div class="banner loud" data-ui>
    <strong>{error ? 'Offline' : 'Data errors'}</strong>
    {#if error}<p>{error}</p>{/if}
    {#each Object.entries(errors) as [file, msg]}<p><b>{file}</b>: {msg}</p>{/each}
  </div>
{:else if warnings.length}
  <div class="banner warn" data-ui>
    <button class="dismiss" on:click={() => (showFindings = !showFindings)}>{showFindings ? 'hide' : 'show'}</button>
    <strong>{warnings.length} finding{warnings.length > 1 ? 's' : ''}</strong> in {def.name}
    {#if showFindings}{#each warnings as f}<p><b>{f.where}</b>: {f.message}</p>{/each}{/if}
  </div>
{/if}

<div class="panel left" data-ui>
  <div class="row">
    <span class="lbl">Player</span>
    <select bind:value={playerId}>
      {#each meta?.players ?? [] as p}<option value={p.id}>{p.name}</option>{/each}
    </select>
  </div>
  <div class="list">
    <span class="lbl">Bullseye</span>
    {#each bullseyes as b}
      <button class:on={b.id === bullseyeId} on:click={() => (bullseyeId = b.id)}>{b.name}</button>
    {/each}
  </div>
  {#if scenario}
    <button class="toggle" class:on={scenarioOn} on:click={() => (scenarioOn = !scenarioOn)}><i></i>{scenario.name}</button>
  {/if}
  <p class="frame">{def?.frame.description ?? ''}{def && !def.frame.tied ? ' · untied' : ''}</p>
</div>

<div class="panel right" data-ui>
  {#each Object.keys(layers) as k}
    <button class="toggle" class:on={layers[k]} on:click={() => toggleLayer(k)}><i></i>{LAYER_LABELS[k]}</button>
  {/each}
  {#if style}
    <label class="count">
      <span class="lbl">Display size</span>
      <input type="range" min={style.display.scale_min} max={style.display.scale_max} step={style.display.scale_step} bind:value={scale} />
      <output>{Number(scale).toFixed(2)}</output>
    </label>
  {/if}
</div>

<InfoPanel {map} {sel} {state} {contacts} {probe} findings={def?.findings ?? []}
  bullseyeName={bullseyes.find((b) => b.id === bullseyeId)?.name ?? ''}
  onclose={() => select(null)} onfocus={focusOn} />

<style>
  .map { position: fixed; inset: 0; width: 100vw; height: 100vh; display: block; touch-action: none; }
  .bar { position: fixed; top: 20px; left: 20px; z-index: 30; display: flex; gap: 16px; align-items: baseline;
         background: var(--panel); border-left: 1px solid var(--violet); padding: 7px 14px; }
  .brand { font-family: var(--display); letter-spacing: 0.12em; color: var(--dim); font-size: 12px; margin-right: 6px; }
  .brand b { color: var(--ink); font-weight: 600; }
  .bar button { background: none; border: 0; padding: 2px 0; color: var(--dim); font-family: var(--display); font-size: 14px; }
  .bar button.on { color: var(--ink); box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .bar button:hover { color: var(--ink); }

  .clock { position: fixed; top: 20px; right: 20px; z-index: 30; display: flex; gap: 10px; align-items: center;
           background: var(--panel); border-left: 1px solid var(--violet); padding: 7px 14px; }
  .clock .utc { font-family: var(--display); font-size: 14px; font-variant-numeric: tabular-nums; }
  .clock button { background: none; border: 0; color: var(--dim); padding: 0 2px; }
  .clock button:hover { color: var(--fuchsia); }
  .clock .small { font-size: 11px; }
  .warp { min-width: 5.5em; text-align: center; color: var(--ink); }
  .src { color: var(--dim); font-size: 10px; }

  .panel { position: fixed; bottom: 20px; z-index: 20; background: var(--panel); border-left: 1px solid var(--violet); padding: 10px 14px; }
  .left { left: 20px; width: 300px; display: grid; gap: 6px; }
  .right { right: 20px; display: grid; gap: 2px; min-width: 200px; }
  .row { display: flex; gap: 10px; align-items: center; }
  .lbl { color: var(--dim); }
  select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 2px 4px; flex: 1; }
  .list { display: flex; flex-wrap: wrap; gap: 2px 12px; align-items: baseline; }
  .list button { background: none; border: 0; padding: 2px 0; color: var(--dim); font-family: var(--display); font-size: 13px; }
  .list button.on { color: var(--ink); box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .frame { margin: 2px 0 0; color: var(--dim); font-size: 10px; }

  .toggle { background: none; border: 0; padding: 3px 0; display: flex; align-items: center; gap: 8px; color: var(--dim); text-align: left; }
  .toggle i { width: 8px; height: 8px; border: 1px solid var(--violet); }
  .toggle.on { color: var(--ink); }
  .toggle.on i { background: var(--violet); }
  .toggle:hover { color: var(--ink); }
  .count { display: grid; grid-template-columns: auto 1fr 2.6em; align-items: center; gap: 8px; margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--rule); }
  output { text-align: right; font-variant-numeric: tabular-nums; }

  .banner { position: fixed; top: 64px; left: 20px; width: 520px; z-index: 40; background: var(--panel);
            border-left: 1px solid var(--fuchsia); padding: 9px 14px; color: var(--ink); max-height: 50vh; overflow: auto; }
  .banner strong { font-family: var(--display); font-weight: 600; color: var(--fuchsia); }
  .banner.loud { background: rgba(60, 6, 34, 0.92); border-left-width: 3px; }
  .banner.warn { border-left-color: #ffd27a; }
  .banner.warn strong { color: #ffd27a; }
  .banner.warn p { color: #ffe3a6; }
  .banner p { margin: 4px 0 0; color: #ff9fcf; font-size: 11px; overflow-wrap: anywhere; }
  .dismiss { float: right; background: none; border: 0; color: var(--dim); margin-left: 12px; }
  .dismiss:hover { color: var(--ink); }

  input[type='range'] { appearance: none; background: transparent; width: 100%; height: 18px; margin: 0; }
  input[type='range']::-webkit-slider-runnable-track { height: 1px; background: var(--rule); }
  input[type='range']::-moz-range-track { height: 1px; background: var(--rule); }
  input[type='range']::-webkit-slider-thumb {
    appearance: none; width: 10px; height: 10px; margin-top: -5px; background: var(--void);
    border: 1.5px solid var(--fuchsia); transform: rotate(45deg);
  }
  input[type='range']::-moz-range-thumb {
    width: 8px; height: 8px; background: var(--void); border: 1.5px solid var(--fuchsia); border-radius: 0; transform: rotate(45deg);
  }
</style>

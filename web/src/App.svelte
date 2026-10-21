<script>
  import { onMount, onDestroy } from 'svelte';
  import { SystemMap } from './lib/SystemMap.js';
  import { api, StateStream } from './lib/api.js';
  import HudCursor from './lib/HudCursor.svelte';
  import Orders from './lib/Orders.svelte';
  import { group, orderGroups, shipsUnder, stepG } from './lib/orders.js';
  import Overlay from './lib/Overlay.svelte';
  import InfoPanel from './lib/InfoPanel.svelte';
  import LevelSelect from './lib/LevelSelect.svelte';
  import MainMenu from './lib/MainMenu.svelte';
  import ShipRegistry from './lib/ShipRegistry.svelte';
  import Settings from './lib/Settings.svelte';
  import Workshop from './lib/Workshop.svelte';

  // sim seconds per real second; the clock runs in TDB seconds since J2000, like the server
  const WARPS = [[1, '1×'], [10, '10×'], [60, '1 min/s'], [600, '10 min/s'], [3600, '1 h/s'], [21600, '6 h/s'],
                 [86400, '1 d/s'], [604800, '1 wk/s'], [2629800, '1 mo/s'], [31557600, '1 yr/s']];

  let canvas, map = null, stream, meta = null, style = null, def = null, state = null;
  let systemId = null, playerId = 'arcvs', bullseyeId = 'system', scenarioOn = true;
  let t = 0, warp = 6, paused = false, last = 0, raf;
  let orbitsT = null, orbitsBusy = false;
  let drules = {}, settings = null, showSettings = false, settingsStatus = '', saveTimer, pendingSave = false;
  let sel = null, probe = null, overUI = false, error = null, errors = {}, version = 0;
  let showFindings = false, down = null, poll;
  let ordering = null, orderTool, orderMsg = '', msgTimer;   // an order being aimed: { unit, g, tilt }
  $: if (ordering && (mode !== 'map' || (state && !ordering.ships.some((id) => state.ships?.[id])))) ordering = null;
  let mode = 'menu';                    // 'menu' | 'levels' | 'map' | 'workshop' | 'ships'
  let purpose = 'play';                 // what the level list is for: 'play' or 'build'
  let registry, shipCount = 0;
  $: inMap = mode === 'map' || mode === 'workshop';   // the screens that use the map's controls
  let schema = null, wdoc = null, lastLevel = null;

  $: player = meta?.players.find((p) => p.id === playerId);
  $: bullseyes = [{ id: 'system', name: `${def?.name ?? ''} centre` }, ...(player?.bullseyes.filter((b) => b.system === systemId) ?? [])];
  $: scenario = meta?.scenarios.find((s) => s.system === systemId);
  $: contacts = scenarioOn && scenario ? scenario.contacts : [];
  $: warnings = def?.findings.filter((f) => f.level === 'warning') ?? [];
  $: if (map) { map.bullseyeId = bullseyeId; map.contactName = (id) => { const c = contacts.find((c) => c.id === id); return c?.name ?? c?.callsign ?? id; }; }

  // ---- settings: display.toml defaults, the player's settings.toml on top -----------------------
  function applySettings() {
    if (!settings) return;
    document.documentElement.style.setProperty('--ui-scale', settings.text.panel_scale);
    if (map) for (const [k, v] of Object.entries(settings.layers)) map.setLayer(k, v);
  }
  function setSetting(sec, k, v) {
    settings = { ...settings, [sec]: { ...settings[sec], [k]: v } };
    applySettings();
    settingsStatus = '';
    pendingSave = true;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveSettings, 500);
  }
  async function saveSettings() {
    try { settings = (await api.saveSettings(settings)).settings; settingsStatus = 'Saved'; applySettings(); }
    catch (e) { settingsStatus = e.message; }
    pendingSave = false;
  }
  function resetSettings(sec) {
    const d = (s) => Object.fromEntries(Object.entries(drules[s].settings).map(([k, v]) => [k, v.default]));
    settings = sec ? { ...settings, [sec]: d(sec) } : Object.fromEntries(Object.keys(drules).map((s) => [s, d(s)]));
    applySettings();
    clearTimeout(saveTimer);
    saveSettings();
  }

  function applyStyle(s) {
    style = s;
    const root = document.documentElement.style;
    for (const [k, v] of Object.entries(s.palette)) root.setProperty(`--${k}`, v);
    map?.setStyle(s);
  }

  async function loadMeta() {
    meta = await api.meta();
    applyStyle(meta.style);
    drules = meta.display.rules;
    if (!pendingSave) settings = meta.display.settings;   // unsaved changes here win over the file
    applySettings();
    version = meta.version;
  }

  // keepView: the same system rebuilt (a workshop edit, a live reload) keeps the camera, unless
  // bodies were added or removed, which reframes it
  async function openSystem(id, keepTime = false, keepView = false) {
    const before = def?.bodies.length;
    systemId = id;
    def = await api.system(id);
    const same = keepView && def.bodies.length === before;
    if (!keepTime) t = def.start;
    map.setSystem(def, same);
    if (!same) { sel = null; probe = null; map.selected = null; }
    orbitsT = null;
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
    if (ordering && down && Math.hypot(e.clientX - down.x, e.clientY - down.y) <= 4) {
      if (down.b === 2) { ordering = null; return; }             // right click: cancel
      if (down.b === 0) return giveOrder();
    }
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

  // ---- orders: A on a selected ship aims one; a click gives it -----------------------------------
  function say(m) { orderMsg = m; clearTimeout(msgTimer); msgTimer = setTimeout(() => (orderMsg = ''), 3500); }
  // the ships an order from the selection goes to: the ship, or every ship under the formation
  $: selShips = sel?.kind === 'contact' ? shipsUnder(contacts, state, sel.id) : [];
  function startOrder() {
    if (sel?.kind !== 'contact' || !selShips.length) return say('Select a ship or a formation to order: A');
    const able = selShips.filter((id) => contacts.find((c) => c.id === id)?.ship?.has_drive);
    if (!able.length) return say('No ship there has a drive stated; they cannot be ordered to move.');
    const grp = group(state, contacts, able);
    const g = grp.g ?? Math.min(grp.cruise?.[1] ?? grp.maxG, grp.maxG);
    ordering = { unit: sel.id, ships: able, g, tilt: 0 };
  }
  // a telegraph moved for orders already being flown: only their g changes. With an order
  // ({id, by}) only that order's ships, all of them; without, the selected ship
  let retuneTimer;
  async function retune(g, now = false, order = null) {
    if (!scenario || sel?.kind !== 'contact') return;
    const unit = order?.by ?? sel.id, orderId = order?.id ?? null;
    clearTimeout(retuneTimer);
    const send = async () => {
      try {
        await api.order({ scenario: scenario.id, unit, t, g, keep_target: true, order_id: orderId });
        say(`${map.contactName(unit)}${order ? `, to ${order.label}` : ''}: ${g > 0 ? `${g.toFixed(2)} g` : 'drive cut'}`);
      } catch (err) { say(String(err.message ?? err)); }
    };
    if (now) send(); else retuneTimer = setTimeout(send, 250);
  }
  async function giveOrder() {
    const aim = orderTool?.aim();
    if (!aim || !scenario) return say('Nothing to aim at there.');
    const o = ordering;
    try {
      const r = await api.order({ scenario: scenario.id, unit: o.unit, t, g: o.g, player: playerId,
                                  target: aim.target });
      const goal = Object.values(r.ships)[0]?.goal;
      const who = `${map.contactName(o.unit)}${o.ships.length > 1 ? ` (${o.ships.length} ships)` : ''}`;
      say(o.g > 0 ? `${who}: to ${goal?.label ?? aim.label} at ${o.g.toFixed(2)} g` : `${who}: drive cut`);
      ordering = null;
    } catch (err) {
      say(String(err.message ?? err));
    }
  }

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
    if (e.key === ' ') { e.preventDefault(); paused = !paused; }
    if (e.key === ']') warp = Math.min(warp + 1, WARPS.length - 1);
    if (e.key === '[') warp = Math.max(warp - 1, 0);
    if (e.key === ',') { showSettings = !showSettings; return; }
    if (e.key === 'Escape' && showSettings) { showSettings = false; return; }
    if (!inMap) return;                                  // menus have their own keys
    if (ordering) {                                      // aiming an order: its own keys first
      if (e.key === 'Escape' || e.key === 'a' || e.key === 'A') { ordering = null; return; }
      if (orderTool?.key(e)) { e.preventDefault(); return; }
    } else if ((e.key === 'a' || e.key === 'A') && mode === 'map') { startOrder(); return; }
    else if ((e.key === 'w' || e.key === 'W' || e.key === 's' || e.key === 'S') && mode === 'map') {
      const up = e.key.toLowerCase() === 'w', ship = state?.ships?.[sel?.id];
      if (ship?.goal) {                                     // a ship: her own telegraph
        const grp = group(state, contacts, [sel.id]);
        retune(stepG(ship.goal.g, grp.maxG, grp.cruise, up, e.shiftKey));
        return;
      }
      const orders = orderGroups(state, contacts, selShips);   // a formation: its order, if it flies one
      if (orders.length === 1) { const o = orders[0]; retune(stepG(o.g, o.maxG, o.cruise, up, e.shiftKey), false, o); return; }
      if (orders.length > 1) { say(`${orders.length} orders under ${map.contactName(sel.id)}: use each order's telegraph in the panel`); return; }
    }
    if (e.key === 'Escape') select(null);
    if (e.key === 'f' || e.key === 'F') focusOn(sel);
    if (e.key === 'h' || e.key === 'H') map.frameAll();
    if ((e.key === 'l' || e.key === 'L') && mode === 'map') toLevels();
    if ((e.key === 'u' || e.key === 'U') && sel?.kind === 'contact') {          // up the chain of command
      const parent = contacts.find((c) => c.id === sel.id)?.parent;
      if (parent) select({ kind: 'contact', id: parent });
    }
  }

  // ---- the menu, levels and the workshop --------------------------------------------------------
  function choose(what) {
    if (what === 'play' || what === 'build') { purpose = what; mode = 'levels'; }
    if (what === 'ships') mode = 'ships';
    if (what === 'settings') showSettings = true;
  }
  function toMenu() { mode = 'menu'; select(null); }
  async function previewLevel(id) { if (id !== systemId) await openSystem(id); lastLevel = id; }
  async function enter(id) { await previewLevel(id); mode = 'map'; }
  function toLevels() {
    mode = 'levels';
    const back = meta.systems.find((s) => s.id === (systemId === 'draft' ? lastLevel : systemId)) ?? meta.systems[0];
    if (back) previewLevel(back.id);
  }

  async function openWorkshop(id, copy) {
    schema ??= await api.workshop.schema();
    if (id) {
      const src = await api.workshop.source(id);
      wdoc = src.doc;
      if (copy) {
        let n = 1, nid = `${id}-copy`;
        while (meta.systems.some((s) => s.id === nid)) nid = `${id}-copy-${++n}`;
        wdoc.system.id = nid;
        wdoc.system.name = `${wdoc.system.name ?? id} (copy)`;
      }
    } else {
      const star = { ...(schema.presets['g-dwarf'] ?? { kind: 'star', mass_msun: 1, radius_rsun: 1, luminosity_lsun: 1, teff_k: 5772 }) };
      delete star.label;
      wdoc = { system: { id: 'new-system', name: 'New System', epoch: 'J2000' }, frame: { kind: 'untied' },
               body: [{ id: 'star', name: 'Star', ...star }], binary: [] };
    }
    mode = 'workshop';
  }
  async function draftBuilt(draftId) { await openSystem(draftId, systemId === draftId, systemId === draftId); }
  async function workshopSaved() { await loadMeta(); }
  const trackUI = (e) => { overUI = !!e.target.closest?.('[data-ui]'); };
  function resetClock() { t = def.start; }

  async function checkStatus() {
    try {
      const s = await api.status();
      errors = s.errors;
      if (s.version !== version) {
        await loadMeta();
        if (systemId) await openSystem(systemId, true, true);
        registry?.refresh();
      }
    } catch { error = 'Cannot reach the server. Start it with: python serve.py'; return; }
    error = null;
  }

  onMount(async () => {
    map = new SystemMap(canvas);
    window.astrum = map;                 // for the console and for screenshot scripts
    window.astrumClock = { get: () => t, set: (v) => (t = v), start: () => def?.start, pause: (v = true) => (paused = v) };
    canvas.addEventListener('pointermove', pointerMove);
    canvas.addEventListener('pointerdown', pointerDown, true);
    canvas.addEventListener('pointerup', pointerUp, true);
    canvas.addEventListener('dblclick', dblclick);
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('resize', () => map.resize());
    stream = new StateStream(onstate);
    try {
      await loadMeta();
      await previewLevel(meta.systems.find((s) => s.id === 'sol')?.id ?? meta.systems[0].id);
    } catch (e) { error = 'Cannot reach the server. Start it with: python serve.py'; }
    raf = requestAnimationFrame(frame);
    poll = setInterval(checkStatus, 2000);
  });
  onDestroy(() => { cancelAnimationFrame(raf); clearInterval(poll); map?.dispose(); });
</script>

<svelte:window on:keydown={key} on:pointermove={trackUI} />

<canvas class="map" bind:this={canvas}></canvas>
<Overlay {map} {style} {settings} {drules} {contacts} />
<HudCursor {map} {style} {settings} {overUI} />
{#if mode === 'map'}
  <Orders bind:this={orderTool} bind:ordering {map} {style} {state} {contacts} {sel} message={orderMsg} />
{/if}

{#if mode === 'menu'}
  <MainMenu onchoose={choose} counts={{ systems: meta?.systems.length ?? 0, ships: meta?.ship_classes ?? 0 }} />
{:else if mode === 'ships'}
  <ShipRegistry bind:this={registry} {style} onback={toMenu} />
{:else if mode === 'levels'}
  <LevelSelect {purpose} levels={meta?.systems ?? []} current={systemId} onpreview={previewLevel} onenter={enter} onworkshop={openWorkshop} onback={toMenu} />
{:else if mode === 'workshop' && schema && wdoc}
  <Workshop {schema} bind:doc={wdoc} onpreview={draftBuilt} onsaved={workshopSaved} onexit={toLevels} />
{:else}
  <div class="bar" data-ui>
    <button on:click={toMenu}>◂ Menu</button>
    <button on:click={toLevels} title="L">Levels</button>
    <button on:click={() => (showSettings = !showSettings)} title=",">Settings</button>
    <span class="brand">INVICTUS <b>ASTRUM</b></span>
    <span class="here">{def?.name ?? ''}</span>
  </div>
{/if}

{#if inMap || mode === 'levels'}
<div class="clock" data-ui>
  <span class="utc">{state?.utc?.replace('T', ' ').replace('Z', ' UTC') ?? '—'}</span>
  <button on:click={() => (paused = !paused)} title="Space">{paused ? '▶' : '❚❚'}</button>
  <button on:click={() => (warp = Math.max(warp - 1, 0))} title="[">◀</button>
  <span class="warp">{WARPS[warp][1]}</span>
  <button on:click={() => (warp = Math.min(warp + 1, WARPS.length - 1))} title="]">▶</button>
  <button class="small" on:click={resetClock}>reset</button>
  <span class="src">{state?.source ?? ''}</span>
</div>
{/if}

{#if mode !== 'map'}
  {#if error}<div class="banner loud low" data-ui><strong>Offline</strong><p>{error}</p></div>{/if}
{:else if error || Object.keys(errors).length}
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

{#if mode === 'map'}
<div class="leftcol">
<!-- the bullseyes, one to a row: bearings and ranges everywhere read from the one chosen -->
<div class="panel bulls" data-ui>
  <h3>Bullseye <span>{bullseyes.length}</span></h3>
  <ol>
    {#each bullseyes as b}
      <li><button class:on={b.id === bullseyeId} on:click={() => (bullseyeId = b.id)}><i></i><span>{b.name}</span></button></li>
    {/each}
  </ol>
</div>
<div class="panel left" data-ui>
  <div class="row">
    <span class="lbl">Player</span>
    <select bind:value={playerId}>
      {#each meta?.players ?? [] as p}<option value={p.id}>{p.name}</option>{/each}
    </select>
  </div>
  {#if scenario}
    <button class="toggle" class:on={scenarioOn} on:click={() => (scenarioOn = !scenarioOn)}><i></i>{scenario.name}</button>
  {/if}
  <p class="frame">{def?.frame.description ?? ''}{def && !def.frame.tied ? ' · untied' : ''}</p>
</div>
</div>
{/if}

{#if inMap && settings}
<div class="panel right" data-ui>
  {#each Object.entries(drules.layers.settings) as [k, spec]}
    <button class="toggle" class:on={settings.layers[k]} on:click={() => setSetting('layers', k, !settings.layers[k])}><i></i>{spec.label}</button>
  {/each}
  {#each [['icons', 'body_display'], ['icons', 'unit_px'], ['text', 'unit_label_px']] as [sec, k]}
    {@const spec = drules[sec].settings[k]}
    <label class="count">
      <span class="lbl">{spec.label}</span>
      <input type="range" min={spec.min} max={spec.max} step={spec.step} value={settings[sec][k]} on:input={(e) => setSetting(sec, k, Number(e.target.value))} />
      <output>{settings[sec][k]}</output>
    </label>
  {/each}
  <button class="more" on:click={() => (showSettings = true)}>All settings ,</button>
</div>

{#if !showSettings}
<InfoPanel {map} {style} {sel} {state} {contacts} {probe} findings={def?.findings ?? []}
  bullseyeName={bullseyes.find((b) => b.id === bullseyeId)?.name ?? ''}
  onclose={() => select(null)} onfocus={focusOn} onselect={select} onretune={retune} />
{/if}
{/if}

{#if showSettings && settings}
  <Settings rules={drules} values={settings} status={settingsStatus} onchange={setSetting} onreset={resetSettings} onclose={() => (showSettings = false)} />
{/if}

<style>
  .map { position: fixed; inset: 0; width: 100vw; height: 100vh; display: block; touch-action: none; }
  .bar { position: fixed; top: 20px; left: 20px; z-index: 30; display: flex; gap: 16px; align-items: baseline;
         background: var(--panel); border-left: 1px solid var(--violet); padding: 7px 14px; }
  .brand { font-family: var(--display); letter-spacing: 0.12em; color: var(--dim); font-size: 12px; margin-right: 6px; }
  .here { font-family: var(--display); font-size: 15px; color: var(--ink); }
  .banner.low { top: auto; bottom: 20px; left: 460px; }
  .brand b { color: var(--ink); font-weight: 600; }
  .bar button { background: none; border: 0; padding: 2px 0; color: var(--dim); font-family: var(--display); font-size: 14px; }
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
  .leftcol { position: fixed; left: 20px; bottom: 20px; z-index: 20; width: 300px; display: flex; flex-direction: column; gap: 8px; }
  .leftcol .panel { position: static; }
  .left { display: grid; gap: 6px; }
  .right { right: 20px; display: grid; gap: 2px; min-width: 200px; }
  .row { display: flex; gap: 10px; align-items: center; }
  .lbl { color: var(--dim); }
  select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 2px 4px; flex: 1; }
  .bulls { padding: 10px 14px 6px; max-height: 40vh; overflow: auto; }
  .bulls h3 { margin: 0 0 6px; font-family: var(--display); font-weight: 400; font-size: 11px; letter-spacing: 0.14em;
              text-transform: uppercase; color: var(--dim); display: flex; justify-content: space-between; }
  .bulls ol { list-style: none; margin: 0; padding: 0; }
  .bulls li + li { border-top: 1px solid var(--rule); }
  .bulls button { display: flex; align-items: center; gap: 10px; width: 100%; background: none; border: 0; padding: 6px 0;
                  color: var(--dim); font-family: var(--display); font-size: 14px; text-align: left; }
  .bulls button i { flex: none; width: 7px; height: 7px; transform: rotate(45deg); border: 1px solid var(--violet); }
  .bulls button:hover { color: var(--ink); }
  .bulls button.on { color: var(--ink); }
  .bulls button.on i { background: var(--fuchsia); border-color: var(--fuchsia); }
  .frame { margin: 2px 0 0; color: var(--dim); font-size: 10px; }

  .toggle { background: none; border: 0; padding: 3px 0; display: flex; align-items: center; gap: 8px; color: var(--dim); text-align: left; }
  .toggle i { width: 8px; height: 8px; border: 1px solid var(--violet); }
  .toggle.on { color: var(--ink); }
  .toggle.on i { background: var(--violet); }
  .toggle:hover { color: var(--ink); }
  .more { background: none; border: 0; color: var(--violet); filter: brightness(1.5); font: inherit; text-align: left; padding: 6px 0 0; }
  .more:hover { color: var(--fuchsia); filter: none; }
  .count { display: grid; grid-template-columns: 9em 1fr 2.6em; align-items: center; gap: 8px; margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--rule); }
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

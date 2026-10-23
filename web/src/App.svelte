<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { SystemMap } from './lib/SystemMap.js';
  import { api, StateStream } from './lib/api.js';
  import { cap, is, keymap } from './lib/keys.js';
  import HudCursor from './lib/HudCursor.svelte';
  import ScaleBar from './lib/ScaleBar.svelte';
  import Ruler from './lib/Ruler.svelte';
  import Adjutant from './lib/Adjutant.svelte';
  import Paths from './lib/Paths.svelte';
  import { config as adjutantConfig } from './lib/adjutant.js';
  import Orders from './lib/Orders.svelte';
  import Bullseyes from './lib/Bullseyes.svelte';
  import { group, hms, named, nextThen, orderGroups, shipsUnder, stepG } from './lib/orders.js';
  import { Motion } from './lib/motion.js';
  import Overlay from './lib/Overlay.svelte';
  import InfoPanel from './lib/InfoPanel.svelte';
  import LevelSelect from './lib/LevelSelect.svelte';
  import LevelList from './lib/LevelList.svelte';
  import Lobby from './lib/Lobby.svelte';
  import SignIn from './lib/SignIn.svelte';
  import { LobbySocket } from './lib/lobby.js';
  import { stepWarp, warpLabel } from './lib/clock.js';
  import MainMenu from './lib/MainMenu.svelte';
  import ShipRegistry from './lib/ShipRegistry.svelte';
  import FleetManager from './lib/FleetManager.svelte';
  import Settings from './lib/Settings.svelte';
  import Workshop from './lib/Workshop.svelte';

  let canvas, map = null, stream, meta = null, style = null, def = null, state = null;
  let systemId = null, pickedPlayer = 'arcvs', bullseyeId = 'system', scenarioOn = true;
  // whose side the map plays: one of the scenario's factions, or MASTER (null: the scenario's own),
  // kept in this browser by scenario. The server sends that side's table, and nothing more
  let sides = {};
  try { sides = JSON.parse(localStorage.getItem('astrum.sides') ?? '{}'); } catch { /* not kept */ }
  // the picture's switches (Settings, Game), kept in this browser and sent with every picture asked for
  let game = {};
  try { game = JSON.parse(localStorage.getItem('astrum.game') ?? '{}'); } catch { /* not kept */ }
  let settingsTab = 'display';
  const motion = new Motion();               // how fast the bullseyes' origins move, off the pictures
  $: frameVel = state ? motion.of(bullseyeId) : [0, 0, 0];
  // the adjutant's settings (Settings, Adjutant), kept in this browser; she reads the side's pictures
  let adjutant = adjutantConfig();
  try { adjutant = adjutantConfig(JSON.parse(localStorage.getItem('astrum.adjutant') ?? 'null')); } catch { /* not kept */ }
  function setAdjutant(cfg) {
    adjutant = adjutantConfig(cfg);
    try { localStorage.setItem('astrum.adjutant', JSON.stringify(adjutant)); } catch { /* for this visit only */ }
  }
  // ships whose sensors are drawn always (her panel's Show sensors), kept in this browser by scenario
  let watchedBy = {};
  try { watchedBy = JSON.parse(localStorage.getItem('astrum.watched') ?? '{}'); } catch { /* not kept */ }
  $: watched = new Set(scenario ? watchedBy[scenario.id] ?? [] : []);
  // a ship, or every ship under a formation that states sensors: all shown already, all hidden; else all shown
  function toggleWatch(unit = chosen) {
    if (!scenario || sel?.kind !== 'contact' || !unit) return say(`Select a ship or a formation: ${cap($keymap.watch)} shows its sensors`);
    const ids = shipsUnder(contacts, state, unit).filter((id) => contacts.find((c) => c.id === id)?.ship?.sensors?.length);
    if (!ids.length) return say('No sensors stated there to show.');
    const now = new Set(watched), all = ids.every((id) => now.has(id));
    for (const id of ids) all ? now.delete(id) : now.add(id);
    watchedBy = { ...watchedBy, [scenario.id]: [...now] };
    try { localStorage.setItem('astrum.watched', JSON.stringify(watchedBy)); } catch { /* for this visit only */ }
    say(`${map.contactName(unit)}: sensors ${all ? 'hidden' : 'shown'}${ids.length > 1 ? `, ${ids.length} ships` : ''}`);
  }
  // whom she serves: the side's own units (a formation's ships are under it), by scenario and side
  $: adjContext = mode === 'map' && scenarioOn && scenario ? {
    key: `${scenario.id}:${side}:${playerId}`,
    units: scenario.contacts.map((c) => ({ id: c.id, callsign: c.callsign ?? c.name ?? c.id, parent: c.parent ?? null, ship: c.echelon === 'ship' })),
  } : null;
  // The clock. In a level it is the level's, on the server (astrum/level.py): every picture says how
  // it stands (clockAt), and the map runs it on between pictures at its warp, eased onto what the
  // next one says; pausing, the warp and a restart are asked of the server, for everyone in it. Off a
  // level (a system's preview behind the menus, the workshop) the map keeps a clock of its own
  let t = 0, warpS = 3600, paused = true, last = 0, raf;
  let clockAt = null;                   // { t, warp, paused, wall }: the level's clock, as the last picture told it
  const BUFFER_S = 0.1;                 // drawn this far behind the newest picture: two pushes (and their jitter) to draw between
  let pictureMode = 'push';             // the server's [server] pictures: 'push' (sent unasked) or 'ask' (each asked for as the last lands)
  let levels = [], levelId = null, listed = null, levelNote = '';   // Play's list, the level on the map, the one chosen in the list
  $: level = levels.find((l) => l.id === levelId) ?? null;
  const scenarioIn = (lid, sid) => levels.find((l) => l.id === lid)?.systems.find((x) => x.id === sid)?.scenario ?? null;
  $: scenarioId = scenarioIn(levelId, systemId);
  $: running = clockAt ? !clockAt.paused : !paused;
  $: shownWarp = clockAt ? clockAt.warp : warpS;
  $: clockLocked = authOn && levelId && mode === 'map' && !amTimer;    // a member's map shows the host's clock (unless the host's rule lets anyone)
  let orbitsT = null, orbitsBusy = false;
  let drules = {}, settings = null, showSettings = false, settingsStatus = '';
  let sel = null, probe = null, overUI = false, error = null, errors = {}, version = 0;
  let showFindings = false, down = null, poll, kernels = '';   // kernels: why the flight is not compiled, if it is not
  let ordering = null, orderTool, orderMsg = '', msgTimer;   // an order being aimed: { unit, g, tilt, plane }
  // where orders measure Eve and Haid from: 'her' own height, or the active 'bullseye''s plane (level:
  // on it, so a formation above comes down to it). B while aiming, or the switch under the bullseyes
  let orderPlane = 'her';
  try { orderPlane = localStorage.getItem('astrum.orderPlane') === 'bullseye' ? 'bullseye' : 'her'; } catch {}
  $: if (ordering?.plane) orderPlane = ordering.plane;
  $: try { localStorage.setItem('astrum.orderPlane', orderPlane); } catch {}
  function setPlane(p) { orderPlane = p; if (ordering) ordering = { ...ordering, plane: p, tilt: 0 }; }
  $: if (ordering && (mode !== 'map' || (state && !ordering.ships.some((id) => state.ships?.[id])))) ordering = null;
  let mode = 'menu';                    // 'signin' | 'menu' | 'levels' | 'map' | 'workshop' | 'ships' | 'fleets'
  // Signed in (astrum/accounts.py, astrum/lobby.py): who this browser plays as, and the lobbies the
  // server pushes. Play is then a lobby: its host works the level's clock, and every picture and
  // order is made, on the server, as the lobby grants (its level, your side). With the server's
  // auth off, none of it: Play lists the levels and starts them, as one host alone
  let you = null, authOn = false, lobbySock = null, lobbies = [];
  let devEnter = false;                 // serve.py --dev: onto the lobby's level as soon as it shows started
  $: mine = lobbies.find((lb) => lb.members.some((m) => m.user === you)) ?? null;
  $: amHost = mine?.host === you;
  $: amTimer = amHost || !!mine?.rules?.anyone_speed;      // may pause the level and set its warp (the host's rule)
  $: sideFixed = !!mine && !amHost && !mine.rules?.switch_sides && !!levels.find((l) => l.id === mine.level)?.clock;
  $: mySide = mine?.members.find((m) => m.user === you)?.side ?? null;
  let metaSide;                         // the side the map's meta was asked as: again when the lobby changes it
  $: if (authOn && mySide !== metaSide) { metaSide = mySide; if (meta) loadMeta(); }
  function openLobby() {
    lobbySock?.close();
    lobbySock = new LobbySocket((m) => { lobbies = m.lobbies; levels = m.levels; }, (detail) => { levelNote = detail; say(detail); });
  }
  async function signedIn(user) { you = user; levelNote = ''; openLobby(); await loadMeta(); mode = 'menu'; }
  async function signOut() {
    await api.signOut().catch(() => {});
    lobbySock?.close(); lobbySock = null; you = null; lobbies = [];
    leaveFor('signin');
  }
  function lobbyAct(msg) { levelNote = ''; lobbySock?.send(msg); }
  let purpose = 'play';                 // what the level list is for: 'play' or 'build'
  let registry, shipCount = 0;
  $: inMap = mode === 'map' || mode === 'workshop';   // the screens that use the map's controls
  let schema = null, wdoc = null, lastLevel = null;

  // a scenario on the map: its side picks the player (bullseyes are a player's); else picked here
  $: side = scenario?.view ?? null;
  $: views = scenario ? [...(scenario.factions ?? []), { id: 'master', label: 'MASTER', player: scenario.player }] : [];
  $: playerId = scenarioOn && scenario ? views.find((v) => v.id === side)?.player ?? scenario.player : pickedPlayer;
  $: player = meta?.players.find((p) => p.id === playerId);
  $: bullseyes = [{ id: 'system', name: `${def?.name ?? ''} centre` }, ...(player?.bullseyes.filter((b) => b.system === systemId) ?? [])];   // the star centre always first
  $: scenario = scenarioId ? meta?.scenarios.find((s) => s.id === scenarioId) : null;    // the level's, in this system
  // the side's units (meta), and the others' ships it has seen, as tracks (each picture's)
  $: tracks = Object.values(state?.tracks ?? {}).map((c) => ({ ...c, ship: c.ship_class ? meta?.specs[c.ship_class] ?? null : null }));
  $: contacts = scenarioOn && scenario ? [...scenario.contacts, ...tracks] : [];
  $: warnings = def?.findings.filter((f) => f.level === 'warning') ?? [];
  $: if (map) { map.bullseyeId = bullseyeId; map.contactName = (id) => named((u) => { const c = contacts.find((c) => c.id === u); return c?.name ?? c?.callsign ?? u; }, id); }

  // ---- settings: display.toml defaults, settings.toml on top, this browser's on top of that -------
  function applySettings() {
    if (!settings) return;
    document.documentElement.style.setProperty('--ui-scale', settings.text.panel_scale);
    if (map) for (const [k, v] of Object.entries(settings.layers)) map.setLayer(k, v);
  }
  function keepSettings() {
    try { localStorage.setItem('astrum.display', JSON.stringify(settings)); settingsStatus = 'Kept in this browser'; }
    catch { settingsStatus = 'This browser keeps nothing: for this visit only'; }
  }
  function localSettings(server) {               // this browser's, over the server's, only for settings it has
    let mine = {};
    try { mine = JSON.parse(localStorage.getItem('astrum.display') ?? '{}'); } catch { /* none */ }
    return Object.fromEntries(Object.entries(server).map(([sec, v]) => [sec, { ...v,
      ...Object.fromEntries(Object.entries(mine[sec] ?? {}).filter(([k]) => k in v)) }]));
  }
  function setSetting(sec, k, v) {
    settings = { ...settings, [sec]: { ...settings[sec], [k]: v } };
    applySettings();
    keepSettings();
  }
  function resetSettings(sec) {
    const d = (s) => Object.fromEntries(Object.entries(drules[s].settings).map(([k, v]) => [k, v.default]));
    settings = sec ? { ...settings, [sec]: d(sec) } : Object.fromEntries(Object.keys(drules).map((s) => [s, d(s)]));
    applySettings();
    keepSettings();
  }
  // the switches: in a lobby, its own (the host sets them, every member is shown by them); else this browser's
  $: shownGame = authOn && mine ? mine.picture ?? {} : game;
  function setGame(k, v) {
    if (authOn && mine) {
      if (amHost) lobbyAct({ do: 'picture', picture: { [k]: v } });
      else say(`The picture's switches are the lobby's: its host, ${mine.host}, sets them`);
      return;
    }
    const g = { ...game };
    if (v == null) delete g[k]; else g[k] = v;
    game = g;
    try { localStorage.setItem('astrum.game', JSON.stringify(game)); } catch { /* for this visit only */ }
  }
  // the commander's combat profiles (Settings, Combat; the panel's Engagement), kept by the server
  let profiles = [], profileRules = {};
  $: if (showSettings || playerId) loadProfiles(playerId);       // (again whenever Settings opens: made elsewhere too)
  async function loadProfiles(pid) {
    if (!pid) return;
    try { ({ profiles, ...profileRules } = await api.profiles(pid)); } catch { /* none to show */ }
  }
  async function saveProfile(p) {
    const r = await api.saveProfile({ ...p, player: playerId });
    await loadProfiles(playerId);
    return r.profile;
  }
  async function dropProfile(id) { await api.dropProfile(playerId, id); await loadProfiles(playerId); }
  const engagement = (unit) => { loadProfiles(playerId); return api.engagement(scenario.id, unit, { t, view: side, player: playerId }); };
  async function setStance(unit, change) {
    try {
      await api.order({ scenario: scenario.id, unit, t, ...change, frame: change.stance ? bullseyeId : undefined, player: playerId, view: side });
      const what = change.stance ? profileRules.stances?.[change.stance]?.split(':')[0] : profiles.find((p) => p.id === change.profile)?.name;
      say(`${map.contactName(unit)}: ${change.stance ? 'stance' : 'profile'} ${what}`);
    } catch (err) { say(String(err.message ?? err)); }
  }
  async function setSide(id) {
    if (authOn) { select(null); ordering = null; lobbyAct({ do: 'side', side: id }); return; }   // the lobby's to grant
    sides = { ...sides, [scenario.id]: id };
    try { localStorage.setItem('astrum.sides', JSON.stringify(sides)); } catch { /* for this visit only */ }
    select(null);
    ordering = null;
    await loadMeta();
  }

  function applyStyle(s) {
    style = s;
    const root = document.documentElement.style;
    for (const [k, v] of Object.entries(s.palette)) root.setProperty(`--${k}`, v);
    map?.setStyle(s);
  }

  // the side kept for the scenario on the map (before any map: the one kept last)
  function wantedSide() {
    const sc = scenarioIn(levelId, systemId);
    return sc ? sides[sc] ?? null : Object.values(sides)[0] ?? null;
  }
  async function loadMeta() {
    meta = await api.meta(wantedSide());
    // what the simulation reads of a ship class comes once per class; every ship of it shares that one
    for (const sc of meta.scenarios) for (const c of sc.contacts) c.ship = c.ship_class ? meta.specs[c.ship_class] ?? null : null;
    applyStyle(meta.style);
    drules = meta.display.rules;
    settings = localSettings(meta.display.settings);
    applySettings();
    version = meta.version;
  }

  // keepView: the same system rebuilt (a workshop edit, a live reload) keeps the camera, unless
  // bodies were added or removed, which reframes it
  async function openSystem(id, keepTime = false, keepView = false) {
    const before = def?.bodies.length;
    systemId = id;
    const sc = meta?.scenarios.find((s) => s.id === scenarioIn(levelId, id));
    if (sc && (sides[sc.id] ?? sc.view) !== sc.view) await loadMeta();   // a scenario played as another side
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

  // ships come as changes since the last picture (full: everything); merged one level deep
  function mergeShips(prev, now, full) {
    if (full || !prev) return now;
    const out = { ...prev };
    for (const [id, d] of Object.entries(now)) {
      const p = out[id] ?? {}, m = { ...p };
      for (const [k, v] of Object.entries(d)) m[k] = v && typeof v === 'object' && !Array.isArray(v) && p[k] && typeof p[k] === 'object' ? { ...p[k], ...v } : v;
      out[id] = m;
    }
    return out;
  }

  function onstate(s) {
    if (s.stopped) { if (s.stopped === levelId) leaveLevel(`${level?.name ?? s.stopped} is not running on the server: it was stopped, or the server started again.`); return; }
    if (s.error) { error = s.error; return; }
    // a level's clock, from the pictures themselves: the map draws BUFFER_S of the clock's wall time
    // behind the newest it was sent, so there is always a picture after the moment it draws
    // (asked for: timed by the round trip, as it was sent half of one ago)
    if (s.clock?.level === levelId) clockAt = pictureMode === 'ask' ? { ...s.clock, wall: performance.now() - 500 * stream.rtt }
      : { ...s.clock, t: s.t - (s.clock.paused ? 0 : s.clock.warp * BUFFER_S), wall: performance.now() };
    if (s.system !== systemId) return;
    s.ships = mergeShips(state?.system === s.system ? state.ships : null, s.ships ?? {}, s.full);
    if (!s.tracks) s.tracks = s.full ? {} : state?.tracks ?? {};     // sent when they change
    motion.feed(s);
    state = s;
    map.setState(s);
    if (orbitsT == null || Math.abs(s.t - orbitsT) > 2 * 86400) refreshOrbits();   // orbits precess: redraw now and then
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    const dt = last ? Math.min((now - last) / 1000, 0.25) : 0;
    last = now;
    if (clockAt) {                                  // the level's: on from the last picture's word, eased onto it
      const w = clockAt.paused ? 0 : clockAt.warp, there = clockAt.t + (w * (now - clockAt.wall)) / 1000, run = t + dt * w;
      t = Math.abs(there - run) > Math.max(60, 2 * w) ? there : run + (there - run) * Math.min(1, 4 * dt);   // (run on, then eased: no lead of a frame)
    } else if (!paused) t += dt * warpS;
    map.setClock(t);
    // a picture a round trip or two ahead of the clock, so the one after it is there: a level's, at
    // the level's moment and that much of its wall time on (the server's clock); else at this one's
    const lead = Math.min(0.25, 1.5 * stream.rtt + 1 / 60);
    if (!systemId) return;
    const ask = { level: levelId, system: systemId, player: playerId, view: side, picture: game };
    if (levelId && mode === 'map' && pictureMode === 'ask') stream.ask({ ...ask, lead, step: 1 / 60 });     // its next as each lands, a 60th apart
    else if (levelId && mode === 'map') stream.watch(ask);                                                  // (sent unasked)
    else stream.request({ system: systemId, t: t + (paused ? 0 : warpS * lead), player: playerId, picture: game });
  }
  // the clock's controls: a level's asked of the server (it answers how the clock stands), else this map's
  async function clockDo(what, extra = {}) {
    if (authOn) {                                   // the lobby's host's: the clock comes back in the pictures
      if (['start', 'restart', 'stop'].includes(what) ? !amHost : !amTimer) { say(`Only the host, ${mine?.host ?? 'of the lobby'}, works the level's clock (the host's rule)`); return; }
      lobbyAct({ do: what, ...extra });
      return;
    }
    try {
      const r = await api.level(levelId, { do: what, ...extra });
      if (r.clock) { clockAt = { ...r.clock, wall: performance.now() }; if (what === 'restart') t = r.clock.t; }
    } catch (err) { say(String(err.message ?? err)); }
  }
  const inLevel = () => levelId && mode === 'map';
  function togglePause() { if (inLevel()) clockDo(running ? 'pause' : 'run'); else paused = !paused; }
  function warpStep(up) { const w = stepWarp(shownWarp, up); if (inLevel()) clockDo('warp', { warp: w }); else warpS = w; }
  let restartSure = false;
  function resetClock() {
    if (!inLevel()) { t = def.start; return; }
    if (!restartSure) { restartSure = true; setTimeout(() => (restartSure = false), 3000); return; }
    restartSure = false;
    select(null);
    clockDo('restart');
  }

  // ---- pointer ----------------------------------------------------------------------------------
  // the mark under the cursor; a body's disk only near its centre (zoomed in, the rest of its face is a point)
  const BODY_HIT_PX = 24;
  function markAt(x, y) {
    let best = null, bd = Infinity;
    for (const m of map.marks) {
      const d = Math.hypot(m.x - x, m.y - y);
      if (d < (m.kind === 'body' ? Math.min(m.r, BODY_HIT_PX) : m.r) + 8 && d < bd) { bd = d; best = m; }
    }
    return best;
  }
  function pointerMove(e) { const m = markAt(e.clientX, e.clientY); map.hover = m ? { kind: m.kind, id: m.id, group: m.group } : null; }
  function pointerDown(e) { down = { x: e.clientX, y: e.clientY, b: e.button, shift: e.shiftKey }; }
  // the ruler (L): a click sets where it starts, the next where it ends; a third starts again
  let ruler = null;                     // { a, b }: system-frame km, b null while it follows the cursor
  function rulerPoint(x, y) {
    const m = markAt(x, y);
    return (m && map.position({ kind: m.kind, id: m.id })) || map.pointAt(x, y);
  }
  async function pointerUp(e) {
    if (ruler && down && down.b === 0 && Math.hypot(e.clientX - down.x, e.clientY - down.y) <= 4) {
      const p = rulerPoint(e.clientX, e.clientY);
      if (p) ruler = !ruler.a || ruler.b ? { a: p, b: null } : { ...ruler, b: p };
      return;
    }
    if (ruler && down?.b === 2 && Math.hypot(e.clientX - down.x, e.clientY - down.y) <= 4) { ruler = null; return; }
    if (ordering && down && Math.hypot(e.clientX - down.x, e.clientY - down.y) <= 4) {
      if (down.b === 2) { ordering = null; return; }             // right click: cancel
      if (down.b === 0) return giveOrder(down.shift);
    }
    if (!down || down.b !== 0 || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return;
    const m = markAt(e.clientX, e.clientY);
    if (m) { if (m.group) pickGroup(m.group, down.shift); else if (down.shift && m.kind === 'contact') pick(m.id); else select({ kind: m.kind, id: m.id }); return; }
    const p = map.pointAt(e.clientX, e.clientY);
    if (!p) return select(null);
    select({ kind: 'point', p });
    probe = await api.probe(systemId, p, t, playerId, bullseyeId);
  }
  function dblclick(e) {
    const m = markAt(e.clientX, e.clientY);
    if (m) focusOn({ kind: m.kind, id: m.id });
  }
  function select(s) { sel = s; probe = null; map.selected = s; picks = null; }
  // ⇧-click: a group, ordered as one (orders.js groupOf). A unit under the selected formation: only
  // those picked of it take its orders, the rest dim; any other: added to the selection (again: taken
  // out). A plain click starts over
  let picks = null;
  $: if (map) map.picks = picks;
  $: chosen = sel?.kind === 'contact' ? (picks?.length ? picks.join('+') : sel.id) : null;
  function pick(id) {
    const c = contacts.find((x) => x.id === id), base = contacts.find((x) => x.id === sel?.id);
    if (!c || !base || base.track || c.track || (id === sel.id && !picks)) return select({ kind: 'contact', id });
    const now = picks ?? ((c.ancestors ?? []).includes(sel.id) ? [] : [sel.id]);
    const next = now.includes(id) ? now.filter((x) => x !== id) : [...now, id];
    picks = next.length ? next : null;
  }
  // a group the map drew (our own formations together, Overlay): all of it, as a group; ⇧: added to the one picked
  function pickGroup(ids, add) {
    const base = contacts.find((x) => x.id === sel?.id);
    if (!add || !base || base.track) { select({ kind: 'contact', id: ids[0] }); picks = [...ids]; return; }
    const now = picks ?? [sel.id];
    picks = [...now, ...ids.filter((id) => !now.includes(id))];
  }

  // ---- orders: A on a selected ship aims one; a click gives it -----------------------------------
  function say(m) { orderMsg = m; clearTimeout(msgTimer); msgTimer = setTimeout(() => (orderMsg = ''), 3500); }
  // the ships an order from the selection goes to: the ship, or every ship under the formation (a group's)
  $: selShips = chosen ? shipsUnder(contacts, state, chosen) : [];
  const MODES = { order: 'move', attack: 'attack', patrol: 'patrol', turn: 'turn' };   // the key's action -> the order's mode
  function startOrder(mode = 'move') {
    if (sel?.kind !== 'contact' || !selShips.length) return say(`Select a ship or a formation to order: ${cap($keymap.order)}`);
    if (contacts.find((c) => c.id === sel.id)?.track) return say('A track: not ours to order.');
    const able = mode === 'turn' ? selShips : selShips.filter((id) => contacts.find((c) => c.id === id)?.ship?.has_drive);
    if (!able.length) return say('No ship there has a drive stated; they cannot be ordered to move.');
    const grp = group(state, contacts, able);
    const g = grp.g ?? Math.min(grp.cruise?.[1] ?? grp.maxG, grp.maxG);
    ordering = { unit: chosen, ships: able, g, tilt: 0, plane: orderPlane, mode, then: lastThen };
  }
  // how a move ends (orders.js THEN): on station, free, or ballistic; K while aiming, kept for the next move
  let lastThen = 'station';
  $: if (ordering?.then) lastThen = ordering.then;
  // K: the selection goes free if any of its ships holds station, else takes station (decelerate: to
  // rest on the active bullseye, held there)
  async function toggleFree(unit = chosen) {
    if (!scenario || !unit || sel?.kind !== 'contact') return say(`Select a ship or a formation: ${cap($keymap.free)} takes station or goes free`);
    const ships = shipsUnder(contacts, state, unit), held = ships.filter((id) => state?.ships?.[id]?.mode === 'station');
    if (!held.length) return decelOrder(unit);
    try {
      const r = await api.order({ scenario: scenario.id, unit, t, free: true, player: playerId, view: side });
      const orbit = Object.values(r.ships).map((x) => x.station_at).find((a) => a?.startsWith('orbit of'));
      say(`${map.contactName(unit)}: free${orbit ? `, ${orbit}` : ', coasting'}`);
    } catch (err) { say(String(err.message ?? err)); }
  }
  // a telegraph moved for orders already being flown: only their g changes. With an order
  // ({id, by}) only that order's ships, all of them; without, the selected ship
  let retuneTimer;
  async function retune(g, now = false, order = null) {
    if (!scenario || sel?.kind !== 'contact') return;
    const unit = order?.by ?? chosen, orderId = order?.id ?? null;
    clearTimeout(retuneTimer);
    const send = async () => {
      try {
        await api.order({ scenario: scenario.id, unit, t, g, keep_target: true, order_id: orderId, player: playerId, view: side });
        say(`${map.contactName(unit)}${order ? `, to ${order.label}` : ''}: ${g > 0 ? `${g.toFixed(2)} g` : 'drive cut'}`);
      } catch (err) { say(String(err.message ?? err)); }
    };
    if (now) send(); else retuneTimer = setTimeout(send, 250);
  }
  async function setCold(cold) {
    if (!scenario || sel?.kind !== 'contact') return;
    try {
      await api.order({ scenario: scenario.id, unit: chosen, t, cold, player: playerId, view: side });
      say(`${map.contactName(chosen)}: ${cold ? 'wings folded, running cold' : 'wings spread'}`);
    } catch (err) { say(String(err.message ?? err)); }
  }
  // STOP: the order and the drive cut; she flies on as she goes, under gravity alone
  async function stopOrder(unit = chosen) {
    if (!scenario || !unit || sel?.kind !== 'contact') return say(`Select a ship or a formation to stop: ${cap($keymap.stop)}`);
    try {
      await api.order({ scenario: scenario.id, unit, t, g: 0, player: playerId, view: side });
      say(`${map.contactName(unit)}: STOP, drive cut, flying on as she goes`);
    } catch (err) { say(String(err.message ?? err)); }
  }
  // DECELERATE: a new order, to turn and burn to rest in the active bullseye's frame, and hold there
  async function decelOrder(unit = chosen) {
    if (!scenario || !unit || sel?.kind !== 'contact') return say(`Select a ship or a formation to decelerate: ${cap($keymap.decel)}`);
    const grp = group(state, contacts, shipsUnder(contacts, state, unit));
    const g = grp.g ?? Math.min(grp.cruise?.[1] ?? grp.maxG, grp.maxG);
    if (!(g > 0)) return say('No ship there has a drive to brake with.');
    try {
      const r = await api.order({ scenario: scenario.id, unit, t, g, halt: { bullseye: bullseyeId }, player: playerId, view: side });
      say(`${map.contactName(unit)}: decelerate, ${Object.values(r.ships)[0]?.goal?.label ?? 'to rest'} at ${g.toFixed(2)} g`);
    } catch (err) { say(String(err.message ?? err)); }
  }
  // active sensors: sweep (ping) or go quiet; a formation pings if none of its ships does, else goes quiet
  async function setPing(on = null, unit = chosen) {
    if (!scenario || !unit || sel?.kind !== 'contact') return say(`Select a ship or a formation: ${cap($keymap.ping)} pings`);
    const ships = shipsUnder(contacts, state, unit);
    on ??= !ships.some((id) => state?.ships?.[id]?.active);
    try {
      await api.order({ scenario: scenario.id, unit, t, active: on, player: playerId, view: side });
      say(`${map.contactName(unit)}: ${on ? 'active sensors sweeping: pinging (and seen pinging)' : 'active sensors quiet'}`);
    } catch (err) { say(String(err.message ?? err)); }
  }
  async function dismissTrack(id) {
    try { await api.dismissTrack(scenario.id, id, side, playerId); select(null); say('Old track removed'); }
    catch (err) { say(String(err.message ?? err)); }
  }
  async function withdrawOrder(id) {
    try { await api.withdrawOrder(scenario.id, id, side, playerId); say('Order withdrawn: as if it had never been given'); }
    catch (err) { say(String(err.message ?? err)); }
  }
  // a click gives the order aimed; Shift-click queues it after what they fly (and keeps aiming)
  async function giveOrder(queue = false) {
    const aim = orderTool?.aim();
    if (!aim || !scenario) return say('Nothing to aim at there.');
    const o = ordering;
    try {
      const r = await api.order({ scenario: scenario.id, unit: o.unit, t, g: o.g, player: playerId, view: side,
                                  target: aim.target, mode: o.mode, queue, free: o.mode === 'move' && o.then === 'free' ? true : undefined,
                                  ballistic: o.mode === 'move' && o.then === 'ballistic' && !queue ? true : undefined });
      const goal = Object.values(r.ships)[0]?.goal;
      const who = `${map.contactName(o.unit)}${o.ships.length > 1 ? ` (${o.ships.length} ships)` : ''}`;
      say(o.mode === 'turn' ? `${who}: turned to ${aim.kind === 'point' ? 'the point' : aim.label}` : o.g <= 0 ? `${who}: drive cut`
        : r.ballistic ? `${who}: ${r.ballistic.label}, burning ${hms(r.ballistic.burn_s)}, there in ${hms(r.ballistic.there_s)}`
        : queue ? `${who}: queued, then ${aim.label}` : `${who}: ${goal?.label ?? aim.label} at ${o.g.toFixed(2)} g`);
      if (!queue) ordering = null;
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

  // G held: weapon ranges on the map
  let ranges = false;
  // the display legend opens on hover; pinned, it stays open (remembered in this browser)
  let legendPinned = false;
  try { legendPinned = localStorage.getItem('astrum.legend.pinned') === '1'; } catch { /* not remembered */ }
  function pinLegend() {
    legendPinned = !legendPinned;
    try { localStorage.setItem('astrum.legend.pinned', legendPinned ? '1' : '0'); } catch { /* not remembered */ }
  }
  // R held: detection ranges
  let sensing = false;
  function keyUp(e) { if (is(e, 'ranges')) ranges = false; if (is(e, 'sensing')) sensing = false; }

  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && e.target.type !== 'range') return;
    if (is(e, 'ranges') && mode === 'map') { ranges = true; return; }
    if (is(e, 'sensing') && mode === 'map') { sensing = true; return; }
    if (is(e, 'pause') && (inMap || mode === 'menu')) { e.preventDefault(); togglePause(); }
    if (is(e, 'faster') && inMap) warpStep(true);
    if (is(e, 'slower') && inMap) warpStep(false);
    if (is(e, 'settings')) { showSettings = !showSettings; return; }
    if (e.key === 'Escape' && showSettings) { showSettings = false; return; }
    if (!inMap) return;                                  // menus have their own keys
    if (is(e, 'paths') && mode === 'map' && settings) {
      setSetting('layers', 'paths', !settings.layers.paths);
      say(`Trajectories ${settings.layers.paths ? 'shown' : 'hidden'}`);
      return;
    }
    if (is(e, 'ruler') && mode === 'map') { ruler = ruler ? null : { a: null, b: null }; return; }
    if (e.key === 'Escape' && ruler) { ruler = null; return; }
    if (ordering) {                                      // aiming an order: its own keys first
      const m = Object.keys(MODES).find((a) => is(e, a));
      if (e.key === 'Escape' || (m && MODES[m] === ordering.mode)) { ordering = null; return; }
      if (m) { ordering = { ...ordering, mode: MODES[m] }; return; }      // another kind of order, aimed the same
      if (is(e, 'free') && ordering.mode === 'move') { ordering = { ...ordering, then: nextThen(ordering.then) }; return; }
      if (orderTool?.key(e)) { e.preventDefault(); return; }
    } else if (Object.keys(MODES).some((a) => is(e, a)) && mode === 'map') { startOrder(MODES[Object.keys(MODES).find((a) => is(e, a))]); return; }
    else if (is(e, 'stop') && mode === 'map') { stopOrder(); return; }
    else if (is(e, 'decel') && mode === 'map') { decelOrder(); return; }
    else if (is(e, 'ping') && mode === 'map') { setPing(); return; }
    else if (is(e, 'watch') && mode === 'map') { toggleWatch(); return; }
    else if (is(e, 'free') && mode === 'map') { toggleFree(); return; }
    else if (/^[1-9]$/.test(e.key) && mode === 'map' && sel?.kind === 'contact') {    // a formation's n-th unit (a ship: her n-th sister)
      const c = contacts.find((x) => x.id === sel.id), under = c?.children?.length ? c.children : contacts.find((x) => x.id === c?.parent)?.children ?? [];
      const pick = under[Number(e.key) - 1];
      if (pick) select({ kind: 'contact', id: pick });
      return;
    }
    else if ((is(e, 'up') || is(e, 'down')) && mode === 'map') {
      const up = is(e, 'up'), ship = state?.ships?.[sel?.id];
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
    if (is(e, 'focus')) focusOn(sel);
    if (is(e, 'home')) map.frameAll();
    if (is(e, 'levels') && mode === 'map') toLevels();
    if (is(e, 'chain') && sel?.kind === 'contact') {          // up the chain of command
      const parent = contacts.find((c) => c.id === sel.id)?.parent;
      if (parent) select({ kind: 'contact', id: parent });
    }
  }

  // ---- the menu, levels and the workshop --------------------------------------------------------
  function choose(what) {
    if (what === 'play' || what === 'build') { purpose = what; toLevels(); }
    if (what === 'ships') mode = 'ships';
    if (what === 'fleets') mode = 'fleets';
    if (what === 'settings') showSettings = true;
  }
  // out of a level: it runs on on the server; behind the menus, its system stands still
  function leaveFor(next) { levelId = null; clockAt = null; paused = true; ordering = null; select(null); mode = next; }
  function toMenu() { leaveFor('menu'); }
  function leaveLevel(note) { levelNote = note; toLevels(); }
  async function loadLevels() { try { levels = await api.levels(); } catch { /* the banner says offline */ } }
  // Play lists levels: one chosen shows its first system behind the list, still, at its clock or its
  // start (no fleet: nothing is flown for a preview); Build lists systems
  async function previewLevel(id) {
    if (purpose === 'play') {
      const l = levels.find((x) => x.id === id);
      if (!l) return;
      listed = id;
      if (l.systems[0].id !== systemId) await openSystem(l.systems[0].id);
      t = l.clock?.t ?? l.start;
    } else if (id !== systemId) await openSystem(id);
    lastLevel = id;
  }
  // Play: the level started (nothing of it ran before), or gone back into, and the map. Signed in:
  // the lobby's level, once its host has started it
  async function enter(id) {
    if (purpose !== 'play') { await previewLevel(id); mode = 'map'; return; }
    if (authOn) {
      const l = levels.find((x) => x.id === mine?.level);
      if (!l?.clock) return;
      levelId = l.id; levelNote = '';
      clockAt = { ...l.clock, wall: performance.now() }; t = l.clock.t;
      await openSystem(l.systems[0].id, true);
      await loadMeta();
      mode = 'map';
      return;
    }
    try {
      const r = await api.level(id, { do: 'start' });
      await loadLevels();
      levelId = id; levelNote = '';
      clockAt = { ...r.clock, wall: performance.now() }; t = r.clock.t;
      const first = levels.find((l) => l.id === id).systems[0].id;
      await openSystem(first, true);
      await loadMeta();
      mode = 'map';
    } catch (err) { levelNote = String(err.message ?? err); }
  }
  async function restartLevel(id) { await api.level(id, { do: 'restart' }).catch(() => {}); await loadLevels(); previewLevel(id); }
  async function stopLevel(id) { await api.level(id, { do: 'stop' }).catch(() => {}); await loadLevels(); previewLevel(id); }
  async function toLevels() {
    const was = levelId;
    leaveFor('levels');
    if (purpose === 'play') {
      if (!authOn) await loadLevels();
      const back = levels.find((l) => l.id === (mine?.level ?? was ?? listed)) ?? levels[0];
      if (back) previewLevel(back.id);
      return;
    }
    const back = meta.systems.find((s) => s.id === (systemId === 'draft' ? lastLevel : systemId)) ?? meta.systems[0];
    if (back) previewLevel(back.id);
  }
  // the list's clocks, while it is up
  let listPoll;
  $: { clearInterval(listPoll); if (mode === 'levels' && purpose === 'play' && !authOn) listPoll = setInterval(loadLevels, 2000); }
  // in a lobby, its level behind the list
  $: if (mode === 'levels' && purpose === 'play' && mine && mine.level !== listed && levels.length) previewLevel(mine.level);
  $: if (devEnter && mine && levels.find((l) => l.id === mine.level)?.clock) { devEnter = false; purpose = 'play'; tick().then(() => enter(mine.level)); }   // (after this update: enter's own changes then update the map)

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

  async function checkStatus() {
    try {
      const s = await api.status();
      errors = s.errors;
      kernels = s.compiled === false ? s.kernels : '';
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
    window.astrumSelect = (s) => select(s);
    canvas.addEventListener('pointermove', pointerMove);
    canvas.addEventListener('pointerdown', pointerDown, true);
    canvas.addEventListener('pointerup', pointerUp, true);
    canvas.addEventListener('dblclick', dblclick);
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('resize', () => map.resize());
    stream = new StateStream(onstate);
    try {
      await loadMeta();
      await openSystem(meta.systems.find((s) => s.id === 'sol')?.id ?? meta.systems[0].id);   // behind the menu: still
      await loadLevels();
      ({ auth: authOn, user: you, pictures: pictureMode = 'push', dev: devEnter = false } = await api.me());
      if (authOn && !you) mode = 'signin';
      else if (authOn) openLobby();
    } catch (e) { error = 'Cannot reach the server. Start it with: python serve.py'; }
    raf = requestAnimationFrame(frame);
    poll = setInterval(checkStatus, 2000);
  });
  onDestroy(() => { cancelAnimationFrame(raf); clearInterval(poll); clearInterval(listPoll); lobbySock?.close(); map?.dispose(); });
</script>

<svelte:window on:keydown={key} on:keyup={keyUp} on:blur={() => (ranges = sensing = false)} on:pointermove={trackUI} />

<canvas class="map" bind:this={canvas}></canvas>
<Overlay {map} {style} {settings} {drules} {contacts} ranges={ranges && mode === 'map'} sensing={sensing && mode === 'map'}
  watched={mode === 'map' ? watched : new Set()} />
<HudCursor {map} {style} {settings} {overUI} />
{#if mode === 'map' && scenarioOn && scenario}<Paths {map} {style} on={settings?.layers.paths ?? true} estimates={settings?.layers.path_estimates ?? true}
  contacts={scenario.contacts} {chosen} {ordering} aim={() => orderTool?.aim()} {motion} />{/if}
{#if ruler && mode === 'map'}<Ruler {map} {style} {ruler} {markAt} />{/if}
{#if mode === 'map'}
  <Orders bind:this={orderTool} bind:ordering {map} {style} {state} {contacts} {sel} {chosen} message={orderMsg} />
{/if}

{#if mode === 'menu'}
  <MainMenu onchoose={choose} counts={{ levels: levels.filter((l) => !l.own).length, systems: meta?.systems.length ?? 0, ships: meta?.ship_classes ?? 0 }} />
  {#if you}<p class="whoami" data-ui>{you} · <button on:click={signOut}>sign out</button></p>{/if}
{:else if mode === 'ships'}
  <ShipRegistry bind:this={registry} {style} onback={toMenu} />
{:else if mode === 'fleets'}
  <FleetManager {style} onback={toMenu} />
{:else if mode === 'signin'}
  <SignIn onsigned={signedIn} />
{:else if mode === 'levels' && purpose === 'play' && authOn}
  <Lobby {you} {lobbies} {levels} current={listed} note={levelNote} switches={meta?.picture ?? {}} onpreview={previewLevel} onenter={enter} onact={lobbyAct} onsignout={signOut} onback={toMenu} />
{:else if mode === 'levels' && purpose === 'play'}
  <LevelList {levels} current={listed} note={levelNote} onpreview={previewLevel} onenter={enter} onrestart={restartLevel} onstop={stopLevel} onback={toMenu} />
{:else if mode === 'levels'}
  <LevelSelect {purpose} levels={meta?.systems ?? []} current={systemId} onpreview={previewLevel} onenter={enter} onworkshop={openWorkshop} onback={toMenu} />
{:else if mode === 'workshop' && schema && wdoc}
  <Workshop {schema} bind:doc={wdoc} onpreview={draftBuilt} onsaved={workshopSaved} onexit={toLevels} />
{:else}
  <div class="bar" data-ui>
    <button on:click={toMenu}>◂ Menu</button>
    <button on:click={toLevels} title={$keymap.levels ? cap($keymap.levels) : "Levels"}>Levels</button>
    <button on:click={() => (showSettings = !showSettings)} title={cap($keymap.settings)}>Settings</button>
    <span class="brand">INVICTUS <b>ASTRUM</b></span>
    <span class="here">{level ? `${level.name} · ` : ''}{def?.name ?? ''}</span>
    {#if level?.systems.length > 1}
      <select class="systems" value={systemId} on:change={(e) => openSystem(e.target.value, true)} title="The level's systems: each its own bullseyes, fleet and orders, on the level's one clock">
        {#each level.systems as x}<option value={x.id}>{x.name}</option>{/each}
      </select>
    {/if}
  </div>
{/if}

{#if inMap}
<div class="clock" class:locked={clockLocked} data-ui title={clockLocked ? `The level's clock is the host's, ${mine?.host}` : ''}>
  <span class="utc">{state?.utc?.replace('T', ' ').replace('Z', ' UTC') ?? '—'}</span>
  {#if kernels}<span class="lag" title={kernels}>flight not compiled</span>{/if}
  {#if state?.behind_s > 30}<span class="lag" title="The simulation is catching up with the clock: the map shows the moment it has reached">sim {hms(state.behind_s)} behind</span>{/if}
  <button on:click={togglePause} title="Space{levelId ? ': the level, for everyone in it' : ''}">{running ? '❚❚' : '▶'}</button>
  <button on:click={() => warpStep(false)} title="[">◀</button>
  <span class="warp">{warpLabel(shownWarp)}</span>
  <button on:click={() => warpStep(true)} title="]">▶</button>
  <button class="small restart" class:sure={restartSure} on:click={resetClock}
    title={levelId ? 'The level from its start again: its clock, and its fleets as their scenarios have them' : 'Back to the system\'s start'}>{levelId ? (restartSure ? 'restart?' : 'restart') : 'reset'}</button>
  {#if !levelId}<span class="src">{state?.source ?? ''}</span>{/if}
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
<Adjutant {map} {style} {stream} {state} cfg={adjutant} context={adjContext} onchange={setAdjutant}
  bullseye={{ id: bullseyeId, name: bullseyes.find((b) => b.id === bullseyeId)?.name ?? bullseyeId }} />
<Bullseyes {bullseyes} bind:bullseyeId {def} {sel} {map} {t} {playerId} onchange={loadMeta} {orderPlane} onplane={setPlane} />
<div class="panel left" data-ui>
  {#if scenarioOn && views.length}
    <div class="row" title="Whose side: its own units, and what its ships have seen and reported to its flagship. MASTER sees and orders everything.">
      <span class="lbl">Player</span>
      <select value={side} on:change={(e) => setSide(e.target.value)} disabled={sideFixed} title={sideFixed ? 'Sides are fixed while the level runs (the host\'s rule)' : ''}>
        {#each views as v}<option value={v.id} title={v.name}>{v.label}</option>{/each}
      </select>
    </div>
  {:else}
    <div class="row">
      <span class="lbl">Player</span>
      <select bind:value={pickedPlayer}>
        {#each meta?.players ?? [] as p}<option value={p.id}>{p.name}</option>{/each}
      </select>
    </div>
  {/if}
  {#if scenario}
    <button class="toggle" class:on={scenarioOn} on:click={() => (scenarioOn = !scenarioOn)}><i></i>{scenario.name}</button>
  {/if}
  <p class="frame">{def?.frame.description ?? ''}{def && !def.frame.tied ? ' · untied' : ''}</p>
</div>
</div>
{/if}

{#if inMap && settings}
<!-- the map's scale, and the display legend: a tab that opens while the pointer is over it, or stays open once pinned -->
<div class="corner">
<ScaleBar {map} />
<div class="panel right" class:pinned={legendPinned} data-ui>
  <button class="legend" on:click={pinLegend} title={legendPinned ? 'Unpin: open only on hover' : 'Pin open'}>
    <span>Display</span><i class:pin={legendPinned}></i>
  </button>
  <div class="legend-body">
    {#each Object.entries(drules.layers.settings) as [k, spec]}
      <button class="toggle" class:on={settings.layers[k]} on:click={() => setSetting('layers', k, !settings.layers[k])}><i></i>{spec.label}</button>
    {/each}
    {#if drules.ranges}
      <button class="toggle" class:on={settings.ranges?.selected_only} on:click={() => setSetting('ranges', 'selected_only', !settings.ranges?.selected_only)}><i></i>Ranges: selection only</button>
    {/if}
    {#each [['icons', 'body_display'], ['icons', 'unit_px'], ['text', 'unit_label_px']] as [sec, k]}
      {@const spec = drules[sec].settings[k]}
      <label class="count">
        <span class="lbl">{spec.label}</span>
        <input type="range" min={spec.min} max={spec.max} step={spec.step} value={settings[sec][k]} on:input={(e) => setSetting(sec, k, Number(e.target.value))} />
        <output>{settings[sec][k]}</output>
      </label>
    {/each}
    <button class="more" on:click={() => (showSettings = true)}>All settings {cap($keymap.settings)}</button>
  </div>
</div>
</div>

{#if !showSettings}
<InfoPanel {map} {style} {sel} {picks} onpick={pick} {state} {contacts} {probe} findings={def?.findings ?? []}
  bullseyeName={bullseyes.find((b) => b.id === bullseyeId)?.name ?? ''}
  onclose={() => select(null)} onfocus={focusOn} onselect={select} onretune={retune} onwithdraw={withdrawOrder} oncold={setCold}
  {watched} onwatch={toggleWatch} onfree={toggleFree} {frameVel}
  master={side === 'master'} onstop={stopOrder} ondecel={decelOrder} onping={setPing} ondismiss={dismissTrack}
  {profiles} stances={profileRules.stances ?? {}} {engagement} onstance={setStance} />
{/if}
{/if}

{#if showSettings && settings}
  <Settings rules={drules} values={settings} status={settingsStatus} onchange={setSetting} onreset={resetSettings}
    game={shownGame} gameRules={meta?.picture ?? {}} ongame={setGame} gameBy={authOn && mine ? (amHost ? 'host' : mine.host) : null} bind:tab={settingsTab} onclose={() => (showSettings = false)}
    {profiles} {profileRules} onprofile={saveProfile} ondropprofile={dropProfile} {adjutant} onadjutant={setAdjutant} />
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
  .clock .small.sure { color: #ffd27a; }
  .clock .restart { color: var(--ink); font-weight: 700; }
  .clock.locked button { opacity: 0.35; pointer-events: none; }
  .whoami { position: fixed; top: 20px; right: 24px; z-index: 30; margin: 0; color: var(--ink); font-size: 12px; }
  .whoami button { background: none; border: 0; padding: 0; color: var(--dim); font: inherit; }
  .whoami button:hover { color: var(--fuchsia); }
  .bar .systems { background: none; border: 1px solid var(--rule); color: var(--ink); font: inherit; font-size: 12px; }
  .warp { min-width: 5.5em; text-align: center; color: var(--ink); }
  .src { color: var(--dim); font-size: 10px; }
  .lag { color: #ffd27a; font-size: 11px; border-left: 2px solid #ffd27a; padding-left: 6px; }

  .panel { position: fixed; bottom: 20px; z-index: 20; background: var(--panel); border-left: 1px solid var(--violet); padding: 10px 14px; }
  .leftcol { position: fixed; left: 20px; bottom: 20px; z-index: 20; width: 300px; display: flex; flex-direction: column; gap: 8px; }
  .leftcol .panel { position: static; }
  .left { display: grid; gap: 6px; }
  .corner { position: fixed; right: 20px; bottom: 20px; z-index: 20; display: flex; align-items: flex-end; gap: 10px; }
  .corner .panel { position: static; }
  .right { display: grid; gap: 2px; min-width: 0; padding: 6px 12px; }
  .legend { display: flex; align-items: center; justify-content: space-between; gap: 12px; background: none; border: 0; padding: 0;
            color: var(--dim); font-family: var(--display); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; }
  .legend i { width: 6px; height: 6px; border: 1px solid var(--violet); transform: rotate(45deg); }
  .legend i.pin { background: var(--fuchsia); border-color: var(--fuchsia); }
  .legend:hover { color: var(--ink); }
  .legend-body { display: none; gap: 2px; min-width: 200px; margin-top: 6px; }
  .right:hover .legend-body, .right.pinned .legend-body { display: grid; }
  .right:hover, .right.pinned { padding: 10px 14px; }
  .row { display: flex; gap: 10px; align-items: center; }
  .lbl { color: var(--dim); }
  select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 2px 4px; flex: 1; }
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

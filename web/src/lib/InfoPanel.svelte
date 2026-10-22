<script>
  // What is selected: a body, a unit, or a point in space (probed on the server).
  import { km, kmFull, n, bearing, elev, lightTime, duration, watts, age } from './format.js';
  import { hms, group, shipsUnder, orderGroups, heading } from './orders.js';
  import { unitSymbol } from './symbols.js';
  import Telegraph from './Telegraph.svelte';
  import { cap, keymap } from './keys.js';

  export let map = null;
  export let style = null;
  export let sel = null;            // { kind: 'body'|'contact'|'point', id?, p? }
  export let state = null;          // latest state: re-renders the live readout
  export let contacts = [];
  export let findings = [];
  export let probe = null;          // /probe result for a point
  export let bullseyeName = '';
  export let onclose = () => {};
  export let onfocus = () => {};
  export let onselect = () => {};   // pick another unit: a member, or the formation above
  export let onretune = () => {};   // (g, now, order): a telegraph moved; order {id, by} for one order, else the selection
  export let onwithdraw = () => {}; // (order id): take an order from the map back, as if never given (MASTER's alone)
  export let master = false;        // MASTER: may take orders back
  export let onstop = () => {};     // (unit): STOP: the order and the drive cut
  export let ondecel = () => {};    // (unit): DECELERATE: turn and burn to rest on the bullseye
  export let oncold = () => {};     // (cold): fold her wings (run cold) or spread them
  export let onping = () => {};     // (on): sweep her active sensors (ping) or go quiet
  export let ondismiss = () => {};  // (track id): remove an old track
  export let profiles = [];         // the commander's combat profiles (the shared ones first)
  export let stances = {};          // stance -> what it does ("Guard: ...")
  export let engagement = async () => null;   // (unit): how it stands, and its last orders (/api/engagement)
  export let onstance = () => {};   // (unit, {stance} | {profile}): a stance or profile ordered
  // how far a track has been made out (astrum/picture.py STAGES)
  const STAGES = ['detected', 'tracked', 'classified', 'identified'];
  const STAGE_NOTE = { detected: 'seen once', tracked: 'seen again: a track', classified: 'her class made out: her plume, or an active return',
                       identified: 'who she is: her hull seen bright enough' };
  let withdrawing = null;           // the order asked about once: a second click takes it back
  const withdraw = (id) => { if (withdrawing !== id) { withdrawing = id; return; } withdrawing = null; onwithdraw(id); };

  const G = 6.6743e-20;             // km³/(kg·s²)
  $: body = sel?.kind === 'body' ? map?.bodies[sel.id] : null;
  $: contact = sel?.kind === 'contact' ? contacts.find((c) => c.id === sel.id) : null;
  $: p = state && map ? map.position(sel) : null;
  $: a = p ? map.aer(p) : null;
  $: mine = body ? findings.filter((f) => f.where === body.id || f.where.startsWith(body.id + ' ')) : [];
  $: parentName = body?.parent ? map.bodies[body.parent]?.name : null;
  $: byId = Object.fromEntries(contacts.map((c) => [c.id, c]));
  $: members = contact ? (contact.children ?? []).map((id) => byId[id]).filter(Boolean) : [];
  $: chain = contact ? (contact.ancestors ?? []).map((id) => byId[id]).filter(Boolean) : [];
  // a ship in the simulation: what she is now (the server flies her), and what her class gives her
  $: ship = contact ? state?.ships?.[contact.id] ?? null : null;
  $: spec = contact?.ship ?? null;
  // another's ship is shown as seen: where she was when her light reached one of ours, none of what only she knows
  $: seenOnly = ship ? ship.mass_t == null : false;
  $: arrives = ship?.goal?.eta_s != null && state?.utc && isFinite(ship.goal.eta_s)
    ? new Date(Date.parse(state.utc) + ship.goal.eta_s * 1000).toISOString().slice(11, 16) + ' UTC' : null;
  // the ships under this formation, and the orders they fly: each order its own telegraph
  $: under = contact ? shipsUnder(contacts, state, contact.id) : [];
  $: grp = under.length ? group(state, contacts, under) : null;
  $: flying = grp?.flying ?? [];
  $: orders = !ship && flying.length ? orderGroups(state, contacts, under) : [];
  // a telegraph shows where it was set until the server's g moves (the order took it, or another did)
  let tg = null, tgFor = null, tgServer = null, tgs = {}, seen = {};
  $: if (contact?.id !== tgFor) { tgFor = contact?.id; tgs = {}; seen = {}; tgServer = undefined; }
  $: if (ship?.goal?.g !== tgServer) { tgServer = ship?.goal?.g; tg = tgServer ?? null; }
  $: for (const o of orders) if (seen[o.id] !== o.g) { seen[o.id] = o.g; delete tgs[o.id]; tgs = tgs; }
  const nameOf = (id) => byId[id]?.name ?? byId[id]?.callsign ?? id;
  // the unit's own symbol, drawn by the map's code
  function symbol(canvas, c) {
    const draw = (c) => {
      if (!style || !c) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2), w = 58, h = 46;
      canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      unitSymbol(ctx, style, c, w / 2, h / 2 + 5, { h: 26, label: false });
    };
    draw(c);
    return { update: draw };
  }
  $: role = contact?.role ? style?.formation_role?.[contact.role]?.label ?? '' : '';
  // every section folds; which ones are folded is remembered in this browser
  const FOLD_KEY = 'astrum.panel.folded';
  let shut = {};
  try { shut = JSON.parse(localStorage.getItem(FOLD_KEY) ?? '{}') ?? {}; } catch { shut = {}; }
  function flip(k) {
    shut = { ...shut, [k]: !shut[k] };
    try { localStorage.setItem(FOLD_KEY, JSON.stringify(shut)); } catch { /* not remembered */ }
  }
  // Engagement (folded until opened): stance, profile and the last orders, asked of the server for
  // each unit selected, and again once a new order is flown
  let eng = null, engAsked = '';
  $: ownUnit = contact && (ship ? !seenOnly : under.some((id) => state?.ships?.[id]?.mass_t != null));
  $: engKey = ownUnit ? `${contact.id}|${ship?.goal?.order_id ?? orders.map((o) => o.id).join()}|${ship?.active}|${ship?.cold}` : '';
  $: if (engKey !== engAsked) { engAsked = engKey; askEngagement(); }
  async function askEngagement() {
    const key = engAsked;
    if (!key) { eng = null; return; }
    try { const e = await engagement(contact.id); if (key === engAsked) eng = e; } catch { eng = null; }
  }
  async function stance(change) { await onstance(contact.id, change); engAsked = ''; }
  const short = (label) => label?.split(':')[0] ?? '';
  const whence = (f) => !f ? '' : f.from === 'ordered' ? `ordered to ${nameOf(f.by)}` : f.from === 'written' ? `written for ${nameOf(f.by)}`
    : f.from === 'profile' ? "the profile's" : f.gone ? `the root (${f.gone} deleted)` : 'the root';
  const SAID = { coast: 'Stop: drive cut', cold: 'Run cold', warm: 'Spread wings', active: 'Ping', passive: 'Go quiet' };
  const upper = (s) => s[0].toUpperCase() + s.slice(1);
  const goes = (label) => /^(engage|patrol|attack|hold|back)/.test(label ?? '') ? upper(label) : `To ${label}`;
  const said = (o) => o.kind === 'setg' ? `Telegraph ${o.g ? `${o.g.toFixed(2)} g` : 'cut'}` : o.kind === 'goto' ? goes(o.label)
    : o.kind === 'queue' ? `Then ${o.label}` : o.kind === 'coast' && o.label ? upper(o.label)
    : o.kind === 'stance' ? o.label.replace(/(stance|profile) ([\w-]+)/g, (_, k, v) => k === 'stance' ? short(stances[v]) || v
      : `profile ${profiles.find((p) => p.id === v)?.name ?? v}`) : SAID[o.kind] ?? o.label ?? o.kind;
  // where her hull points (her drive's axis), in the active bullseye's axes (bullseyeName: when it changes)
  $: pointing = bullseyeName !== undefined && ship?.dir && Math.hypot(...ship.dir) > 0.5 && map ? heading(map, { from: [0, 0, 0], to: ship.dir }) : null;
  $: affColor = contact && style ? (style.affiliation[contact.affiliation] ?? style.affiliation.unknown).color : null;
  $: doing = !ship ? '' : seenOnly ? (ship.burning ? 'seen burning' : 'as seen') : ship.goal ? (ship.burning ? `on her order, ${ship.accel_g.toFixed(2)} g` : 'on her order, coasting') : ship.burning ? `burning ${ship.burn?.g != null ? `${ship.burn.g} g` : `${Math.round((ship.burn?.throttle ?? 1) * 100)}%`}`
    : ship.mode === 'station' ? 'holding station' : 'coasting';
  // every ship under a formation, counted by class: what the formation is made of
  $: makeup = contact && members.length ? tally(contact.id) : [];
  function tally(id) {
    const counts = {}, walk = (x) => { const c = byId[x]; if (!c) return; if (c.children?.length) c.children.forEach(walk); else { const k = c.class_name || c.unit_type || (c.echelon === 'ship' ? 'ship' : `${c.echelon}, no ships listed`); counts[k] = (counts[k] ?? 0) + 1; } };
    walk(id);
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }
  $: surfaceG = body && body.radius_km ? (body.gm_km3s2 / body.radius_km ** 2) * 1000 : null;
  const KIND = { star: 'Star', planet: 'Planet', dwarf: 'Dwarf planet', moon: 'Moon', barycenter: 'Barycentre', station: 'Station' };
  const REGION = { interior: 'Interior', orbis: 'Orbis', well: 'Well', astrum: 'Astrum' };
  const mass = (kg) => (kg > 1e29 ? `${n(kg / 1.98892e30, 4)} M☉` : kg > 1e24 ? `${n(kg / 5.9722e24, 3)} M⊕` : `${(kg).toExponential(3)} kg`);
</script>

{#if sel}
<aside data-ui>
  <header>
    <div>
      {#if body}
        <h1>{body.name}</h1>
        <p class="kind">{KIND[body.kind] ?? body.kind}{#if parentName} · of {parentName}{/if}{#if body.inhabited} · inhabited{/if}</p>
      {:else if contact}
        <h1>{contact.name ?? contact.callsign}{#if contact.hull_number}<span class="hull">{contact.hull_number}</span>{/if}</h1>
        <p class="kind">{contact.class_name || contact.unit_type || contact.echelon}{#if role}{` · ${role}`}{/if}{#if contact.brevity}{` · ${contact.brevity}`}{/if}{#if contact.pry}{` · Pry-${contact.pry}`}{/if}</p>
        {#if contact.track}
          <ol class="stages" title={STAGE_NOTE[contact.stage]}>
            {#each STAGES as st, i}<li class:on={STAGES.indexOf(contact.stage) >= i} class:at={contact.stage === st}>{st}</li>{/each}
          </ol>
          {#if !contact.class_known}<p class="dim note">Her class is not in our journal</p>{/if}
        {/if}
        <p class="aff" style="--aff:{affColor ?? 'var(--dim)'}">{contact.faction?.name ?? contact.affiliation}{#if contact.faction}<span>{contact.faction.branch_of ? `${contact.faction.branch_of} · ` : contact.faction.member_of ? `${contact.faction.member_of} member world · ` : ''}{contact.affiliation}</span>{/if}</p>
      {:else}
        <h1>Point</h1>
        <p class="kind">{probe ? `${REGION[probe.zone.region]} of ${map.bodies[probe.zone.dominant]?.name}` : 'probing…'}</p>
      {/if}
    </div>
    {#if contact && style}<canvas class="sym" use:symbol={{ ...contact, status: [] }} aria-hidden="true"></canvas>{/if}
    <button class="close" on:click={onclose} title="Esc">✕</button>
  </header>

  {#if a}
    <section>
      <h2><button class="fold" class:shut={shut.aer} on:click={() => flip('aer')}><i></i>From {bullseyeName}</button>{#if shut.aer} <span class="dim">{bearing(a.bearing)} for {km(a.range)}</span>{/if}</h2>
      {#if !shut.aer}
        <p class="big">{bearing(a.bearing)} for {km(a.range)}</p>
        <p class="dim">{elev(a.elevation)} · light {lightTime(a.range)}</p>
      {/if}
    </section>
  {/if}

  {#if body}
    {#if body.kind !== 'barycenter'}
      <dl>
        <dt>Mass</dt><dd>{mass(body.mass_kg)}{body.mass_is_minimum ? ' (min)' : ''}</dd>
        <dt>Radius</dt><dd>{km(body.radius_km)}</dd>
        <dt>Surface gravity</dt><dd>{n(surfaceG, 2)} m/s²</dd>
        <dt>Escape velocity</dt><dd>{n(body.zones.escape_surface_kms, 2)} km/s</dd>
        {#if body.rotation_period_h}<dt>Day</dt><dd>{duration(Math.abs(body.rotation_period_h) / 24)}{body.rotation_period_h < 0 ? ' retro' : ''}</dd>{/if}
        {#if body.luminosity_lsun}<dt>Luminosity</dt><dd>{n(body.luminosity_lsun, 4)} L☉ · {n(body.teff_k)} K</dd>{/if}
      </dl>
    {/if}
    {#if body.orbit}
      <dl>
        <dt>Semi-major axis</dt><dd>{kmFull(body.orbit.a_km)}</dd>
        <dt>Peri / apo</dt><dd>{km(body.orbit.periapsis_km)} / {km(body.orbit.apoapsis_km)}</dd>
        <dt>Eccentricity</dt><dd>{n(body.orbit.e, 4)}</dd>
        <dt>Inclination</dt><dd>{n(body.orbit.i_deg, 2)}°</dd>
        <dt>Period</dt><dd>{duration(body.orbit.period_d)}</dd>
      </dl>
    {/if}
    <dl>
      {#if body.zones.orbis_km}<dt>Orbis edge</dt><dd>{km(body.zones.orbis_km)}</dd>{/if}
      {#if body.zones.soi_km}<dt>Well{body.zones.well_of !== body.id ? ` (${map.bodies[body.zones.well_of].name})` : ''}</dt><dd>{km(body.zones.soi_km)}</dd>{/if}
      {#if body.zones.hill_km}<dt>Hill sphere</dt><dd>{km(body.zones.hill_km)}</dd>{/if}
      {#if body.zones.roche_km && body.kind !== 'barycenter'}<dt>Roche (ice)</dt><dd>{km(body.zones.roche_km)}</dd>{/if}
      {#if state?.magnetopause_km?.[body.id]}<dt>Magnetopause</dt><dd>{km(state.magnetopause_km[body.id])}</dd>{/if}
      {#if body.magnetic}<dt>Dipole</dt><dd>{n(body.magnetic.b_eq_nt)} nT · tilt {n(body.magnetic.tilt_deg, 1)}°</dd>{/if}
      {#if body.zones.hz_km}<dt>Habitable zone</dt><dd>{km(body.zones.hz_km[0])} – {km(body.zones.hz_km[1])}</dd>{/if}
      {#if body.zones.snow_line_km}<dt>Snow line</dt><dd>{km(body.zones.snow_line_km)}</dd>{/if}
    </dl>
    {#each mine as f}<p class="finding">{f.message}</p>{/each}
    {#if body.notes}<p class="note">{body.notes}</p>{/if}
    <button class="act" on:click={() => onfocus(sel)}>Centre and follow (F)</button>
  {:else if contact}
    {#if members.length}
      <section>
        <h2><button class="fold" class:shut={shut.units} on:click={() => flip('units')}><i></i>Under its command</button> <span class="dim">{members.length} unit{members.length > 1 ? 's' : ''}{under.length && !ship ? ` · ${under.length} ship${under.length > 1 ? 's' : ''}` : ''}</span></h2>
        {#if !shut.units}
          {#each members as m}
            <button class="unit" on:click={() => onselect({ kind: 'contact', id: m.id })}>
              <span>{m.name ?? m.callsign}</span><span class="dim">{m.children?.length ? m.echelon : m.class_name || m.unit_type || m.echelon}</span>
            </button>
          {/each}
          {#if makeup.length}<p class="dim makeup">{makeup.map(([k, n]) => `${n} × ${k}`).join(' · ')}</p>{/if}
        {/if}
      </section>
    {/if}
    {#if orders.length}
      <section class="orders">
        <h2><button class="fold" class:shut={shut.orders} on:click={() => flip('orders')}><i></i>Orders</button> <span class="dim">{orders.length} order{orders.length > 1 ? 's' : ''} · {flying.length} of {under.length} ships flying</span></h2>
        {#if !shut.orders}
        {#each orders as o (o.id)}
          <div class="order">
            <p><b>{o.halt ? `Decelerate, ${o.label}` : goes(o.label)}</b> <span>at {o.g.toFixed(2)} g</span></p>
            <p class="by dim">given to {nameOf(o.by)} · {o.ships.length} ship{o.ships.length > 1 ? 's' : ''}{o.here < o.ships.length ? `, ${o.here} of them here` : ''}
              {#if master && o.source === 'map'}<button class="withdraw" class:sure={withdrawing === o.id} on:click={() => withdraw(o.id)} on:blur={() => (withdrawing = null)}
                title="MASTER: take the order back, as if it had never been given">{withdrawing === o.id ? 'Withdraw?' : 'Withdraw'}</button>{/if}</p>
            <p class="acts"><button class="withdraw" on:click={() => onstop(o.by)} title="Drop the order and cut the drive: they fly on as they go">Stop <kbd>{cap($keymap.stop)}</kbd></button><button
              class="withdraw" on:click={() => ondecel(o.by)} title="Drop the order: turn and burn to rest on the active bullseye, and hold there">Decelerate <kbd>{cap($keymap.decel)}</kbd></button></p>
            <p class="eta">{hms(o.soonest)}{#if o.latest - o.soonest > 60} <span>to {hms(o.latest)}, the last ship</span>{/if}</p>
            <Telegraph maxG={o.maxG} cruise={o.cruise} value={tgs[o.id] ?? o.g ?? 0} height={130} color="var(--cyan, #9ff0ff)"
                       note={o.ships.length > 1 ? "held to the slowest ship's most" : ''}
                       onset={(g) => { tgs[o.id] = g; onretune(g, false, o); }} oncommit={() => onretune(tgs[o.id] ?? o.g, true, o)} />
          </div>
        {/each}
        {/if}
        <p class="dim hint">{#if orders.length === 1}<kbd>{cap($keymap.up)}</kbd><kbd>{cap($keymap.down)}</kbd> telegraph · {/if}<kbd>{cap($keymap.order)}</kbd> a new order for all of them</p>
      </section>
    {/if}
    {#if ship && seenOnly}
      <section class="ship">
        <h2>Ship <span class="dim">{doing}</span></h2>
        <dl class="tight">
          {#if contact.old}<dt title="Not seen for longer than a track is held: where she was last seen, and nothing of her since">Track</dt><dd class="hot">old</dd>{/if}
          {#if contact.brevity === 'bogey'}<dt title="Not yet seen bright enough to be known for who she is">Called</dt><dd>BOGEY</dd>{/if}
          {#if ship.lost}<dt title="Not seen again within her sensors' sweeps: where she was last seen">Track</dt><dd class="hot">lost</dd>{/if}
          <dt title="How old the light is that showed her: its flight to the ship of ours that saw her, and the report's up to our flagship">Seen</dt><dd>{age(ship.seen_s)} ago</dd>
          {#if ship.relay_s > 0.5}<dt class="sub" title="How long the report took to come up the chain to our fleet flagship">relayed</dt><dd class="sub">{age(ship.relay_s)}</dd>{/if}
          <dt>Drive</dt><dd class:hot={ship.burning}>{ship.burning ? 'burning' : 'not burning'}</dd>
          <dt>Signature</dt><dd>{watts(ship.sig_w)}</dd>
          {#if !contact.old}<dt class="sub">her rads</dt><dd class="sub">{watts(ship.glow_mw * 1e6)}</dd>{/if}
          {#if ship.velocity_kms && !contact.old}<dt>Speed</dt><dd>{n(Math.hypot(...ship.velocity_kms), 2)} km/s</dd>{/if}
          {#if ship.active}<dt title="Her active sensors sweep: each ping shows her">Active</dt><dd class="hot">pinging</dd>{/if}
        </dl>
        {#if contact.old}<button class="act" on:click={() => ondismiss(contact.id)} title="Take this old track off the map (if she is seen again, a new track)">Remove old track</button>{/if}
      </section>
    {:else if ship}
      <section class="ship">
        <h2>Ship <span class="dim">{doing}</span></h2>
        <div class="tank" title="propellant"><i style="width:{Math.max(0, Math.min(1, ship.propellant_share)) * 100}%"></i></div>
        {#if ship.goal}
          <div class="order">
            <p><b>{ship.goal.target?.halt ? `Decelerate, ${ship.goal.label}` : goes(ship.goal.label)}</b> <span>at {ship.goal.g.toFixed(2)} g</span></p>
            <p class="eta">{hms(ship.goal.eta_s)}{#if arrives} <span>· arrives {arrives}</span>{/if}</p>
            <p class="dim">{km(ship.goal.range_km)} to go · closing {n(ship.goal.closing_kms, 2)} km/s</p>
            {#if ship.goal.in_formation}<p class="dim form">In formation: she keeps her place on {nameOf(ship.goal.by)}. Her own telegraph takes her out of it.</p>{/if}
            {#if master && ship.goal.source === 'map'}<button class="withdraw" class:sure={withdrawing === ship.goal.order_id} on:click={() => withdraw(ship.goal.order_id)}
              on:blur={() => (withdrawing = null)} title="MASTER: take the order back (all the ships it went to), as if it had never been given">{withdrawing === ship.goal.order_id ? 'Withdraw?' : 'Withdraw'}</button>{/if}
            <p class="acts"><button class="withdraw" on:click={() => onstop(sel.id)} title="Drop the order and cut the drive: she flies on as she goes">Stop <kbd>{cap($keymap.stop)}</kbd></button><button
              class="withdraw" on:click={() => ondecel(sel.id)} title="Drop the order: turn and burn to rest on the active bullseye, and hold there">Decelerate <kbd>{cap($keymap.decel)}</kbd></button></p>
          </div>
          <div class="tgwrap">
            <Telegraph maxG={ship.max_accel_g} cruise={spec?.cruise_g} value={tg ?? ship.goal.g} height={130}
                       onset={(g) => { tg = g; onretune(g); }} oncommit={() => onretune(tg, true)} />
          </div>
        {:else if ship.station_at}
          <p class="dim held">Holding at {ship.station_at}</p>
        {/if}
        {#if pointing}<p class="dim held" title="Where her hull points (her drive's axis), in the active bullseye's axes: {cap($keymap.turn)} turns her">
          Pointing <b class="point">{bearing(pointing.bearing)} {elev(pointing.elevation)}</b> from {bullseyeName}{ship.burning ? ', burning along it' : ''}</p>{/if}
        <h3><button class="fold" class:shut={shut.drive} on:click={() => flip('drive')}><i></i>Propulsion</button>{#if shut.drive} <span class="dim">{n(ship.dv_left_kms, 0)} km/s left · most {ship.max_accel_g.toFixed(2)} g</span>{/if}</h3>
        {#if !shut.drive}
        <dl class="tight">
          <dt>Mass</dt><dd>{n(ship.mass_t)} t</dd>
          <dt class="sub">dry{ship.load !== 'hull' ? `, ${ship.load} load` : ''}</dt><dd class="sub">{n(ship.dry_t)} t</dd>
          <dt>Propellant</dt><dd>{n(ship.propellant_t)} t · {n(ship.propellant_share * 100, 1)}%</dd>
          <dt>Δv left</dt><dd>{n(ship.dv_left_kms, 1)} km/s</dd>
          <dt>Most acceleration</dt><dd>{ship.max_accel_g.toFixed(3)} g</dd>
          {#if ship.burning}
            <dt>Burning</dt><dd class="hot">{ship.accel_g.toFixed(3)} g · {n(ship.thrust_mn, 1)} MN</dd>
            <dt class="sub">plume</dt><dd class="sub">{n(ship.jet_pw, 2)} PW</dd>
          {/if}
          <dt>Δv spent</dt><dd>{ship.dv_spent_kms < 1 ? `${n(ship.dv_spent_kms * 1000, 1)} m/s` : `${n(ship.dv_spent_kms, 2)} km/s`}</dd>
          {#if spec?.length_m}<dt>Length</dt><dd>{n(spec.length_m)} m</dd>{/if}
          {#if spec?.cruise_g}<dt>Cruise band</dt><dd>{spec.cruise_g[0]}–{spec.cruise_g[1]} g</dd>{/if}
        </dl>
        {/if}
        <h3><button class="fold" class:shut={shut.heat} on:click={() => flip('heat')}><i></i>Heat</button>{#if shut.heat} <span class="dim">{ship.cold ? `cold · ${n(ship.cold_left_h, 1)} h left` : `radiating ${watts(ship.glow_mw * 1e6)}`}</span>{/if}</h3>
        {#if !shut.heat}
          {#if ship.cold != null}<div class="tank heat" title="her thermal store"><i style="width:{Math.max(0, Math.min(1, ship.heat_share ?? 0)) * 100}%"></i></div>{/if}
          <dl class="tight">
            <!-- Rads, as standard; Wings, where they fold -->
            {#if ship.cold != null}<dt>Wings</dt><dd class:cool={ship.cold}>{ship.cold ? 'folded: running cold' : 'spread'}</dd>
            {:else}<dt>Rads</dt><dd>always radiating</dd>{/if}
            {#if ship.cold != null}<dt>Cold time left</dt><dd>{n(ship.cold_left_h, 1)} h <span class="dim">of {n(spec?.cold_h, 0)}</span></dd>{/if}
            {#if ship.heat_share != null}<dt>Store</dt><dd>{n(ship.heat_share * 100, 1)}% <span class="dim">of {n(spec?.store_tj, 1)} TJ</span></dd>{/if}
            <dt>Radiating</dt><dd>{watts(ship.glow_mw * 1e6)}</dd>
          </dl>
          {#if ship.cold != null}<button class="act" on:click={() => oncold(!ship.cold)}
            title={ship.cold ? 'Spread her wings: her rads shed her heat and empty her store, glowing the brighter for it' : 'Fold her wings: her rads shed little while her store fills'}>{ship.cold ? 'Spread wings' : 'Run cold'}</button>{/if}
        {/if}
        <h3>Sensors <span class="dim">{ship.active ? 'pinging: seen pinging' : 'passive'}</span></h3>
        <button class="act" on:click={() => onping(!ship.active)}
          title={ship.active ? 'Stop the active sweep: passive only' : 'Sweep her active sensors: any hull in reach is seen and made out, and every ping shows her far beyond'}>{ship.active ? 'Go quiet' : 'Ping'} <kbd>{cap($keymap.ping)}</kbd></button>
        {#if spec?.ranges?.length}
          <h3><button class="fold" class:shut={shut.weapons} on:click={() => flip('weapons')}><i></i>Weapons</button>{#if shut.weapons} <span class="dim">{spec.ranges.map((r) => `${r.what} ${km(r.km)}`).join(' · ')}</span>{/if}</h3>
          {#if !shut.weapons}
          <dl class="tight">
            {#each spec.ranges as r}<dt title={r.note}>{r.what[0].toUpperCase() + r.what.slice(1)}</dt><dd title={r.note}>{km(r.km)}</dd><dt class="sub">{r.battery.toLowerCase()}</dt><dd class="sub">{r.note}</dd>{/each}
          </dl>
          {/if}
        {/if}
        {#if spec?.has_drive}<p class="dim hint"><kbd>{cap($keymap.order)}</kbd> move <kbd>{cap($keymap.attack)}</kbd> attack <kbd>{cap($keymap.patrol)}</kbd> patrol <kbd>{cap($keymap.turn)}</kbd> turn{#if ship.goal} · <kbd>{cap($keymap.up)}</kbd><kbd>{cap($keymap.down)}</kbd> telegraph{/if}{#if spec.ranges?.length} · hold <kbd>{cap($keymap.ranges)}</kbd> weapon ranges{/if}{#if spec.sensors?.length} · <kbd>{cap($keymap.sensing)}</kbd> detection{/if}</p>{/if}
      </section>
    {:else if spec && !spec.has_drive}
      <section><h2>Ship</h2><p class="dim">No drive stated for her class; she holds station.</p></section>
    {/if}
    {#if ownUnit}
      <section class="engage">
        <h2><button class="fold" class:shut={!shut.engage_open} on:click={() => flip('engage_open')}><i></i>Engagement</button>{#if eng}
          <span class="dim">{eng.stance ? short(stances[eng.stance]) : 'mixed stances'} · {eng.profile_name ?? 'mixed profiles'}</span>{/if}</h2>
        {#if shut.engage_open && eng}
        <dl class="tight">
          <dt title={stances[eng.stance] ?? 'Its ships stand in more than one'}>Stance</dt>
          <dd><select value={eng.stance ?? ''} on:change={(e) => stance({ stance: e.target.value })}>
            {#if !eng.stance}<option value="" disabled>mixed: {Object.entries(eng.stances).map(([s, k]) => `${k} ${short(stances[s])}`).join(', ')}</option>{/if}
            {#each Object.entries(stances) as [k, label]}<option value={k} title={label}>{short(label)}</option>{/each}</select></dd>
          {#if eng.stance_from}<dt class="sub">from</dt><dd class="sub">{whence(eng.stance_from)}</dd>{/if}
          <dt title="The rules its stance reads: ranges and targets (Settings, Combat)">Profile</dt>
          <dd><select value={eng.profile ?? ''} on:change={(e) => stance({ profile: e.target.value })}>
            {#if !eng.profile}<option value="" disabled>mixed</option>{/if}
            {#each profiles as p}<option value={p.id}>{p.name}</option>{/each}</select></dd>
          {#if eng.profile_from}<dt class="sub">from</dt><dd class="sub">{whence(eng.profile_from)}</dd>{/if}
          <dt title="Her crew's tier">Crew</dt><dd>{eng.veterancy ?? 'rated'}</dd>
        </dl>
        {#if eng.ledger.length}
          <h3>Last orders</h3>
          <ol class="ledger">
            {#each eng.ledger as o (o.id)}
              <li class:now={o.id === ship?.goal?.order_id || orders.some((x) => x.id === o.id)} class:gone={o.withdrawn}>
                <span>{said(o)}{#if o.by !== contact.id} <i class="dim">· {nameOf(o.by)}</i>{/if}</span><span class="dim">{state ? `${age(state.t - o.at)} ago` : ''}</span></li>
            {/each}
          </ol>
        {/if}
        {/if}
      </section>
    {/if}
    {#if chain.length}
      <section>
        <h2><button class="fold" class:shut={shut.chain} on:click={() => flip('chain')}><i></i>Chain of command</button>{#if shut.chain} <span class="dim">{chain.map((a) => a.name ?? a.callsign).join(' · ')}</span>{/if}</h2>
        {#if !shut.chain}
        <ol class="ladder">
          <li class="self"><span class="nm">{contact.name ?? contact.callsign}</span><span class="ech">{contact.echelon}</span></li>
          {#each chain as a}
            <li><button on:click={() => onselect({ kind: 'contact', id: a.id })}><span class="nm">{a.name ?? a.callsign}</span><span class="ech">{a.echelon}</span></button></li>
          {/each}
        </ol>
        {/if}
      </section>
    {/if}
    {#if contact.status?.length}<p class="dim">Status: {contact.status.map((s) => style?.status?.[s]?.label ?? s).join(', ')}</p>{/if}
    {#if contact.notes}<p class="note">{contact.notes}</p>{/if}
  {:else if probe}
    <dl>
      <dt>Region</dt><dd>{REGION[probe.zone.region]}</dd>
      <dt>Dominant body</dt><dd>{map.bodies[probe.zone.dominant]?.name}</dd>
      <dt>Distance</dt><dd>{km(probe.zone.distance_km)}</dd>
      {#if probe.zone.altitude_km != null}<dt>Altitude</dt><dd>{km(probe.zone.altitude_km)}</dd>{/if}
      <dt>Gravity</dt><dd>{probe.gravity_ms2 < 1e-3 ? probe.gravity_ms2.toExponential(2) : n(probe.gravity_ms2, 4)} m/s²</dd>
      <dt>Escape here</dt><dd>{n(probe.zone.escape_kms, 2)} km/s</dd>
      <dt>Circular orbit</dt><dd>{n(probe.zone.orbital_kms, 2)} km/s</dd>
      <dt>Magnetic field</dt><dd>{probe.magnetic_nt < 0.01 ? '< 0.01' : n(probe.magnetic_nt, 2)} nT</dd>
      {#if probe.zone.inside_hill.length}<dt>Inside Hill of</dt><dd>{probe.zone.inside_hill.map((i) => map.bodies[i]?.name).join(', ')}</dd>{/if}
    </dl>
  {/if}
</aside>
{/if}

<style>
  aside {
    position: fixed; top: 64px; right: 20px; width: 340px; max-height: calc(100vh - 100px); overflow: auto;
    background: var(--panel); border-left: 1px solid var(--violet); padding: 16px 18px 14px;
    backdrop-filter: blur(6px); z-index: 20;
  }
  header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  header > div { flex: 1; min-width: 0; }
  h1 { font-family: var(--display); font-weight: 600; font-size: 22px; line-height: 1.1; margin: 0; letter-spacing: 0.01em; }
  .kind { margin: 8px 0 0; color: var(--dim); font-family: var(--display); font-size: 13px; }
  .hull { margin-left: 10px; font-family: var(--mono); font-size: 12px; font-weight: 400; color: var(--cyan, #9ff0ff);
          border: 1px solid rgba(159, 240, 255, 0.4); padding: 1px 5px; vertical-align: 3px; letter-spacing: 0.06em; }
  /* the faction it serves, in its affiliation's colour */
  .aff { display: inline-flex; gap: 8px; align-items: baseline; margin: 7px 0 0; padding: 2px 8px 2px 7px;
         border-left: 2px solid var(--aff); background: color-mix(in srgb, var(--aff) 12%, transparent);
         font-family: var(--display); font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink); }
  .aff span { color: var(--dim); font-size: 10px; }
  .sym { flex: none; margin-top: -4px; }
  button { background: none; border: 0; padding: 2px 0; color: var(--dim); }
  button:hover { color: var(--ink); }
  .close:hover { color: var(--fuchsia); }
  .act { margin-top: 10px; font-size: 11px; color: var(--violet); filter: brightness(1.5); }
  .act:hover { color: var(--fuchsia); filter: none; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 5px 14px; margin: 12px 0 0; padding-top: 10px; border-top: 1px solid var(--rule); }
  dt { color: var(--dim); }
  dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
  section { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--rule); }
  h2 { font-family: var(--display); font-weight: 400; font-size: 13px; color: var(--dim); margin: 0 0 6px; }
  section p { margin: 3px 0; }
  .big { font-family: var(--display); font-size: 16px; color: var(--ink); }
  .dim { color: var(--dim); }
  .unit { display: flex; justify-content: space-between; gap: 10px; width: 100%; padding: 2px 0; color: var(--ink); text-align: left; }
  .unit:hover span:first-child { color: var(--fuchsia); }
  .makeup { margin-top: 6px; font-size: 11px; }
  .tank { height: 3px; background: var(--rule); margin: 2px 0 8px; }
  .tank i { display: block; height: 100%; background: var(--cyan, #9ff0ff); }
  .tank.heat i { background: #ff8a5c; }            /* her store filling: the heat she holds */
  .cool { color: var(--cyan, #9ff0ff); }
  dl.tight { margin: 0; padding-top: 0; border-top: 0; }
  dt.sub, dd.sub { font-size: 10px; margin-top: -3px; }
  dd.hot { color: var(--fuchsia); }
  .order { margin: 2px 0 10px; padding: 6px 8px; border-left: 2px solid var(--cyan, #9ff0ff); background: rgba(159, 240, 255, 0.05); }
  .order p { margin: 0 0 2px; }
  .order b { font-family: var(--display); font-weight: 600; }
  .order .eta { font-family: var(--display); font-size: 18px; color: var(--cyan, #9ff0ff); }
  .order .eta span { font-size: 11px; color: var(--dim); margin-left: 6px; }
  .held { margin: 0 0 8px; }
  .tgwrap { margin: 8px 0 12px; }
  .orders .order { margin-bottom: 12px; padding-bottom: 0; }
  .order .by { font-size: 11px; }
  .withdraw { background: none; border: 1px solid var(--rule); color: var(--dim); font: inherit; font-size: 10px; padding: 0 5px; margin-left: 6px; cursor: pointer; }
  .withdraw:hover, .withdraw.sure { color: var(--fuchsia); border-color: var(--fuchsia); }
  .acts { margin: 4px 0 0; display: flex; gap: 6px; }
  .stages { display: flex; gap: 2px; list-style: none; padding: 0; margin: 6px 0 2px; font-family: var(--mono); font-size: 9px; text-transform: uppercase; letter-spacing: 0.08em; }
  .stages li { flex: 1; text-align: center; padding: 2px 0; border-top: 2px solid var(--rule); color: var(--dim); }
  .stages li.on { border-top-color: var(--violet); color: var(--ink); }
  .stages li.at { border-top-color: var(--fuchsia); color: var(--fuchsia); }
  .note { margin: 0 0 4px; font-size: 10px; }
  .acts .withdraw { margin-left: 0; }
  .order .form { font-size: 10px; margin-top: 3px; }
  /* the chain of command, read upward: a ladder of rungs joined by a rail */
  .engage select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; max-width: 100%; }
  .point { color: var(--ink); font-weight: 400; }
  .ledger { list-style: none; margin: 0; padding: 0; display: grid; gap: 3px; }
  .ledger li { display: flex; justify-content: space-between; gap: 10px; padding-left: 10px; border-left: 1px solid var(--rule); }
  .ledger li.now { border-left-color: var(--cyan, #9ff0ff); }
  .ledger li.gone span:first-child { text-decoration: line-through; color: var(--dim); }
  .ledger i { font-style: normal; }
  .ladder { list-style: none; margin: 4px 0 0; padding: 0; }
  .ladder li { position: relative; padding: 0 0 14px 18px; }
  .ladder li:last-child { padding-bottom: 0; }
  .ladder li::before { content: ''; position: absolute; left: 3px; top: 5px; width: 7px; height: 7px; transform: rotate(45deg);
                       border: 1px solid var(--violet); background: var(--void); }
  .ladder li:not(:last-child)::after { content: ''; position: absolute; left: 6.5px; top: 14px; bottom: 2px; width: 1px; background: var(--violet); opacity: 0.6; }
  .ladder li.self::before { background: var(--fuchsia); border-color: var(--fuchsia); }
  .ladder li.self .nm { color: var(--dim); }
  .ladder button { display: flex; justify-content: space-between; gap: 10px; width: 100%; padding: 0; text-align: left; color: var(--ink); }
  .ladder li.self { display: flex; justify-content: space-between; gap: 10px; }
  .ladder .nm { font-family: var(--display); font-size: 13px; }
  .ladder .ech { color: var(--dim); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
  .ladder button:hover .nm { color: var(--fuchsia); }
  .hint { margin-top: 8px; font-size: 10px; }
  /* a section's heading folds it: a small diamond, open below, shut to the side */
  .fold { display: inline-flex; align-items: center; gap: 7px; padding: 0; font: inherit; color: inherit; cursor: pointer; }
  .fold i { width: 5px; height: 5px; border-right: 1px solid var(--violet); border-bottom: 1px solid var(--violet);
            transform: rotate(45deg) translate(-1px, -1px); transition: transform 0.12s; filter: brightness(1.6); }
  .fold.shut i { transform: rotate(-45deg); }
  .fold:hover { color: var(--ink); }
  .fold:hover i { border-color: var(--fuchsia); }
  h2 .dim, h3 .dim { font-size: 11px; margin-left: 6px; }
  h3 { font-family: var(--display); font-weight: 400; font-size: 12px; color: var(--dim); margin: 10px 0 5px; }
  kbd { border: 1px solid var(--rule); padding: 0 3px; font-family: var(--mono); font-size: 9px; }
  .finding { margin: 8px 0 0; color: #ffd27a; font-size: 11px; }
  .note { margin: 8px 0 0; color: var(--dim); font-size: 11px; }
</style>

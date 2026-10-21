<script>
  // What is selected: a body, a unit, or a point in space (probed on the server).
  import { km, kmFull, n, bearing, elev, lightTime, duration } from './format.js';
  import { hms, group, shipsUnder } from './orders.js';
  import Telegraph from './Telegraph.svelte';

  export let map = null;
  export let sel = null;            // { kind: 'body'|'contact'|'point', id?, p? }
  export let state = null;          // latest state: re-renders the live readout
  export let contacts = [];
  export let findings = [];
  export let probe = null;          // /probe result for a point
  export let bullseyeName = '';
  export let onclose = () => {};
  export let onfocus = () => {};
  export let onselect = () => {};   // pick another unit: a member, or the formation above
  export let onretune = () => {};   // (g, now): the telegraph moved for orders being flown

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
  $: arrives = ship?.goal?.eta_s != null && state?.utc && isFinite(ship.goal.eta_s)
    ? new Date(Date.parse(state.utc) + ship.goal.eta_s * 1000).toISOString().slice(11, 16) + ' UTC' : null;
  // the orders being flown by this ship, or by the ships under this formation: one telegraph for them
  $: under = contact ? shipsUnder(contacts, state, contact.id) : [];
  $: grp = under.length ? group(state, contacts, under) : null;
  $: flying = grp?.flying ?? [];
  let tg = null, tgFor = null, tgServer = null;
  $: if (contact?.id !== tgFor || grp?.g !== tgServer) { tgFor = contact?.id; tgServer = grp?.g ?? null; tg = tgServer; }
  $: soonest = flying.length ? Math.min(...flying.map((s) => s.goal.eta_s ?? Infinity)) : null;
  $: latest = flying.length ? Math.max(...flying.map((s) => s.goal.eta_s ?? 0)) : null;
  $: doing = !ship ? '' : ship.goal ? (ship.burning ? `on her order, ${ship.accel_g.toFixed(2)} g` : 'on her order, coasting') : ship.burning ? `burning ${ship.burn?.g != null ? `${ship.burn.g} g` : `${Math.round((ship.burn?.throttle ?? 1) * 100)}%`}`
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
        <h1>{contact.callsign}</h1>
        <p class="kind">{contact.class_name || contact.unit_type || contact.echelon} · {contact.affiliation}{#if contact.brevity} · {contact.brevity}{/if}{#if contact.pry} · Pry-{contact.pry}{/if}</p>
      {:else}
        <h1>Point</h1>
        <p class="kind">{probe ? `${REGION[probe.zone.region]} of ${map.bodies[probe.zone.dominant]?.name}` : 'probing…'}</p>
      {/if}
    </div>
    <button class="close" on:click={onclose} title="Esc">✕</button>
  </header>

  {#if a}
    <section>
      <h2>From {bullseyeName}</h2>
      <p class="big">{bearing(a.bearing)} for {km(a.range)}</p>
      <p class="dim">{elev(a.elevation)} · light {lightTime(a.range)}</p>
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
        <h2>Under its command <span class="dim">{members.length} unit{members.length > 1 ? 's' : ''}{under.length && !ship ? ` · ${under.length} ship${under.length > 1 ? 's' : ''}` : ''}</span></h2>
        {#each members as m}
          <button class="unit" on:click={() => onselect({ kind: 'contact', id: m.id })}>
            <span>{m.callsign}</span><span class="dim">{m.children?.length ? m.echelon : m.class_name || m.unit_type || m.echelon}</span>
          </button>
        {/each}
        {#if makeup.length}<p class="dim makeup">{makeup.map(([k, n]) => `${n} × ${k}`).join(' · ')}</p>{/if}
      </section>
    {/if}
    {#if !ship && flying.length}
      <section class="orders">
        <h2>Orders <span class="dim">{flying.length} of {under.length} ships flying</span></h2>
        <div class="order">
          <p><b>To {flying[0].goal.label}</b>{#if new Set(flying.map((s) => s.goal.label)).size > 1} <span class="dim">and others</span>{/if}</p>
          <p class="eta">{hms(soonest)}{#if latest - soonest > 60} <span>to {hms(latest)}, the last ship</span>{/if}</p>
        </div>
        <Telegraph maxG={grp.maxG} cruise={grp.cruise} value={tg ?? 0} height={130} note="held to the slowest ship's most"
                   onset={(g) => { tg = g; onretune(g); }} oncommit={() => onretune(tg, true)} />
        <p class="dim hint"><kbd>W</kbd><kbd>S</kbd> telegraph · <kbd>A</kbd> a new order for all of them</p>
      </section>
    {/if}
    {#if ship}
      <section class="ship">
        <h2>Ship <span class="dim">{doing}</span></h2>
        <div class="tank" title="propellant"><i style="width:{Math.max(0, Math.min(1, ship.propellant_share)) * 100}%"></i></div>
        {#if ship.goal}
          <div class="order">
            <p><b>To {ship.goal.label}</b> <span>at {ship.goal.g} g</span></p>
            <p class="eta">{hms(ship.goal.eta_s)}{#if arrives} <span>· arrives {arrives}</span>{/if}</p>
            <p class="dim">{km(ship.goal.range_km)} to go · closing {n(ship.goal.closing_kms, 2)} km/s</p>
          </div>
          <div class="tgwrap">
            <Telegraph maxG={ship.max_accel_g} cruise={spec?.cruise_g} value={tg ?? ship.goal.g} height={130}
                       onset={(g) => { tg = g; onretune(g); }} oncommit={() => onretune(tg, true)} />
          </div>
        {:else if ship.station_at}
          <p class="dim held">Holding at {ship.station_at}</p>
        {/if}
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
        {#if spec?.has_drive}<p class="dim hint"><kbd>A</kbd> order her{#if ship.goal} · <kbd>W</kbd><kbd>S</kbd> telegraph{/if}</p>{/if}
      </section>
    {:else if spec && !spec.has_drive}
      <section><h2>Ship</h2><p class="dim">No drive stated for her class; she holds station.</p></section>
    {/if}
    {#if chain.length}
      <section>
        <h2>Chain of command</h2>
        <ol class="ladder">
          <li class="self"><span class="nm">{contact.callsign}</span><span class="ech">{contact.echelon}</span></li>
          {#each chain as a}
            <li><button on:click={() => onselect({ kind: 'contact', id: a.id })}><span class="nm">{a.callsign}</span><span class="ech">{a.echelon}</span></button></li>
          {/each}
        </ol>
      </section>
    {/if}
    {#if contact.status?.length}<p class="dim">Status: {contact.status.join(', ')}</p>{/if}
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
  dl.tight { margin: 0; padding-top: 0; border-top: 0; }
  dt.sub, dd.sub { font-size: 10px; margin-top: -3px; }
  dd.hot { color: var(--fuchsia); }
  .order { margin: 2px 0 10px; padding: 6px 8px; border-left: 2px solid var(--cyan, #9ff0ff); background: rgba(159, 240, 255, 0.05); }
  .order p { margin: 0 0 2px; }
  .order b { font-family: var(--display); font-weight: 600; }
  .order .eta { font-family: var(--display); font-size: 18px; color: var(--cyan, #9ff0ff); }
  .order .eta span { font-size: 11px; color: var(--dim); }
  .held { margin: 0 0 8px; }
  .tgwrap { margin: 8px 0 12px; }
  .orders .order { margin-bottom: 12px; }
  /* the chain of command, read upward: a ladder of rungs joined by a rail */
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
  kbd { border: 1px solid var(--rule); padding: 0 3px; font-family: var(--mono); font-size: 9px; }
  .finding { margin: 8px 0 0; color: #ffd27a; font-size: 11px; }
  .note { margin: 8px 0 0; color: var(--dim); font-size: 11px; }
</style>

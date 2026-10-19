<script>
  // What is selected: a body, a unit, or a point in space (probed on the server).
  import { km, kmFull, n, bearing, elev, lightTime, duration } from './format.js';

  export let map = null;
  export let sel = null;            // { kind: 'body'|'contact'|'point', id?, p? }
  export let state = null;          // latest state: re-renders the live readout
  export let contacts = [];
  export let findings = [];
  export let probe = null;          // /probe result for a point
  export let bullseyeName = '';
  export let onclose = () => {};
  export let onfocus = () => {};

  const G = 6.6743e-20;             // km³/(kg·s²)
  $: body = sel?.kind === 'body' ? map?.bodies[sel.id] : null;
  $: contact = sel?.kind === 'contact' ? contacts.find((c) => c.id === sel.id) : null;
  $: p = state && map ? map.position(sel) : null;
  $: a = p ? map.aer(p) : null;
  $: mine = body ? findings.filter((f) => f.where === body.id || f.where.startsWith(body.id + ' ')) : [];
  $: parentName = body?.parent ? map.bodies[body.parent]?.name : null;
  $: members = contact ? contacts.filter((c) => c.formation === contact.id) : [];
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
        <p class="kind">{contact.unit_type || contact.echelon} · {contact.affiliation}{#if contact.brevity} · {contact.brevity}{/if}{#if contact.pry} · Pry-{contact.pry}{/if}</p>
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
      <section><h2>Members</h2>{#each members as m}<p>{m.callsign} <span class="dim">{m.unit_type || m.echelon}</span></p>{/each}</section>
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
  .finding { margin: 8px 0 0; color: #ffd27a; font-size: 11px; }
  .note { margin: 8px 0 0; color: var(--dim); font-size: 11px; }
</style>

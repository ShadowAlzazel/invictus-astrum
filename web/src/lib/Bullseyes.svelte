<script>
  // The bullseyes, one to a row: bearings and ranges everywhere read from the one chosen. The star
  // centre (the stellar plane) is always first and always there; players.toml's come next; a
  // commander's own, made here, can be deleted here (orders already given off one keep flying).
  // A new one stands at what is selected: a body, a unit's place now, or a point picked on the map
  // (carried with the body whose space it is in, unless told otherwise). Under the list: whether
  // orders aim level with the chosen bullseye's plane (a formation above it comes down to it) or
  // keep the ship's own height; B while aiming switches it too.
  import { api } from './api.js';
  import { cap, keymap } from './keys.js';

  export let bullseyes = [];        // [{ id, name, made }]
  export let bullseyeId = 'system';
  export let def = null;            // the system: bodies, frame
  export let sel = null;
  export let map = null;
  export let t = 0;
  export let playerId = '';
  export let onchange = async () => {};
  export let orderPlane = 'her';    // orders' Eve and Haid: from 'her' own height, or this 'bullseye''s plane
  export let onplane = () => {};

  let making = null, error = '', dropping = null;
  $: bodies = (def?.bodies ?? []).filter((b) => b.kind !== 'barycenter' || b.id === def?.root);
  $: tied = !!def?.frame?.tied;
  $: where = sel?.kind === 'body' ? { label: map?.bodies?.[sel.id]?.name ?? sel.id, body: sel.id }
           : sel?.kind === 'contact' ? { label: `${map?.contactName?.(sel.id) ?? sel.id}'s place now`, point: true }
           : sel?.kind === 'point' ? { label: 'the point picked', point: true }
           : { label: `${def?.name ?? ''} centre`, body: def?.root };
  const bodyName = (id) => bodies.find((b) => b.id === id)?.name ?? id;

  function start() {
    error = '';
    making = { name: `Bullseye ${bullseyes.filter((b) => b.made).length + 1}`, carry: 'auto', up: 'system', ref: 'system', toward: '', roll: 0 };
  }
  async function make() {
    const p = where.point ? map?.position(sel) : null;
    const origin = where.body ? { body: where.body } : p ? { point_km: p, t, carry: making.carry } : null;
    if (!origin) { error = 'Nothing selected to stand it at.'; return; }
    const ref = making.ref === 'toward' ? (making.toward ? `toward:${making.toward}` : null) : making.ref;
    if (!ref) { error = 'Toward which body is 000?'; return; }
    try {
      const r = await api.makeBullseye({ player: playerId, system: def.id, name: making.name, origin,
                                         up: making.up, ref, roll_deg: Number(making.roll) || 0 });
      making = null;
      await onchange();
      bullseyeId = r.bullseye.id;
    } catch (e) { error = String(e.message ?? e); }
  }
  async function drop(b) {
    if (dropping !== b.id) { dropping = b.id; return; }        // a second click deletes
    dropping = null;
    try {
      await api.dropBullseye(playerId, b.id);
      if (bullseyeId === b.id) bullseyeId = 'system';
      await onchange();
    } catch (e) { error = String(e.message ?? e); }
  }
</script>

<div class="panel bulls" data-ui>
  <h3>Bullseye <span>{bullseyes.length}</span><button class="add" title="A new bullseye at what is selected" on:click={start}>+ New</button></h3>
  <ol>
    {#each bullseyes as b}
      <li>
        <button class="pick" class:on={b.id === bullseyeId} on:click={() => (bullseyeId = b.id)}><i></i><span>{b.name}</span></button>
        {#if b.made}
          <button class="drop" class:sure={dropping === b.id} on:click={() => drop(b)} on:blur={() => (dropping = null)}
                  title="Delete it (orders already given off it keep flying)">{dropping === b.id ? 'Delete?' : '✕'}</button>
        {/if}
      </li>
    {/each}
  </ol>
  <button class="plane" class:on={orderPlane === 'bullseye'} title="Orders aimed level with this bullseye's plane, or at the ship's own height (B while aiming)"
          on:click={() => onplane(orderPlane === 'bullseye' ? 'her' : 'bullseye')}>
    <i></i><span>{orderPlane === 'bullseye' ? `Orders level with ${bullseyes.find((b) => b.id === bullseyeId)?.name ?? 'the bullseye'}` : 'Orders keep their own height'}</span><kbd>{cap($keymap.plane)}</kbd>
  </button>
  {#if making}
    <form class="maker" on:submit|preventDefault={make}>
      <label>Name<input bind:value={making.name} maxlength="40" /></label>
      <p class="at">At {where.label}</p>
      {#if where.point}
        <label>Carried with
          <select bind:value={making.carry}>
            <option value="auto">the body whose space it is in</option>
            {#each bodies as b}<option value={b.id}>{b.name}</option>{/each}
            <option value="fixed">nothing: fixed in space</option>
          </select>
        </label>
      {/if}
      <label>Eve
        <select bind:value={making.up}>
          <option value="system">the stellar plane's north</option>
          {#if tied}<option value="ecliptic">ecliptic north</option><option value="galactic">galactic north</option>{/if}
          {#each bodies as b}<option value={`pole:${b.id}`}>{b.name}'s pole</option>{/each}
        </select>
      </label>
      <label>000
        <select bind:value={making.ref}>
          <option value="system">the stellar plane's 000</option>
          {#if tied}<option value="vernal-equinox">the vernal equinox</option><option value="galactic-centre">the galactic centre</option>{/if}
          <option value="toward">toward a body…</option>
        </select>
      </label>
      {#if making.ref === 'toward'}
        <label>Toward
          <select bind:value={making.toward}>
            <option value="" disabled>a body</option>
            {#each bodies as b}<option value={b.id}>{bodyName(b.id)}</option>{/each}
          </select>
        </label>
      {/if}
      <label>Roll<input type="number" bind:value={making.roll} step="5" min="-180" max="180" /><span class="u">°</span></label>
      <div class="go"><button type="submit">Make</button><button type="button" on:click={() => (making = null)}>Cancel</button></div>
    </form>
  {/if}
  {#if error}<p class="err">{error}</p>{/if}
</div>

<style>
  .bulls { padding: 10px 14px 6px; max-height: 50vh; overflow: auto; }
  h3 { margin: 0 0 6px; font-family: var(--display); font-weight: 400; font-size: 11px; letter-spacing: 0.14em;
       text-transform: uppercase; color: var(--dim); display: flex; gap: 8px; align-items: baseline; }
  .add { margin-left: auto; background: none; border: 1px solid var(--rule); color: var(--dim); font: inherit; font-size: 10px;
         letter-spacing: 0.08em; padding: 1px 6px; cursor: pointer; }
  .add:hover { color: var(--ink); border-color: var(--violet); }
  ol { list-style: none; margin: 0; padding: 0; }
  li { display: flex; align-items: center; }
  li + li { border-top: 1px solid var(--rule); }
  .pick { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; background: none; border: 0; padding: 6px 0;
          color: var(--dim); font-family: var(--display); font-size: 14px; text-align: left; }
  .pick i { flex: none; width: 7px; height: 7px; transform: rotate(45deg); border: 1px solid var(--violet); }
  .pick:hover, .pick.on { color: var(--ink); }
  .pick.on i { background: var(--fuchsia); border-color: var(--fuchsia); }
  .drop { background: none; border: 0; color: var(--dim); font: inherit; font-size: 11px; padding: 2px 4px; cursor: pointer; opacity: 0; }
  li:hover .drop, .drop:focus-visible, .drop.sure { opacity: 1; }
  .drop:hover, .drop.sure { color: var(--fuchsia); }
  .plane { display: flex; align-items: center; gap: 8px; width: 100%; margin: 6px 0 2px; background: none; border: 1px solid var(--rule);
           color: var(--dim); font: inherit; font-size: 11px; padding: 4px 8px; cursor: pointer; text-align: left; }
  .plane i { flex: none; width: 7px; height: 7px; transform: rotate(45deg); border: 1px solid var(--violet); }
  .plane span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .plane.on { color: var(--ink); border-color: var(--violet); }
  .plane.on i { background: var(--violet); }
  .plane kbd { border: 1px solid var(--rule); padding: 0 3px; font-size: 9px; }
  .maker { display: grid; gap: 5px; margin: 8px 0 4px; padding-top: 8px; border-top: 1px solid var(--violet); }
  label { display: flex; gap: 8px; align-items: center; color: var(--dim); font-size: 11px; }
  input, select { flex: 1; min-width: 0; background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 2px 4px; }
  input[type='number'] { flex: 0 0 70px; }
  .u { color: var(--dim); }
  .at { margin: 0; font-size: 11px; color: var(--ink); }
  .go { display: flex; gap: 6px; margin-top: 4px; }
  .go button { background: none; border: 1px solid var(--rule); color: var(--ink); font: inherit; padding: 2px 10px; cursor: pointer; }
  .go button[type='submit'] { border-color: var(--fuchsia); }
  .err { margin: 6px 0 0; color: #ffd27a; font-size: 11px; }
</style>

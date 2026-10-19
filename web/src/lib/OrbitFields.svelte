<script>
  // An orbit, as the TOML writes it. The common elements get their own fields; anything else the
  // document carries (drift rates, epochs, ϖ or L instead of ω or M) stays and is editable as raw keys.
  import UnitField from './UnitField.svelte';

  export let orbit;
  export let schema;
  export let onchange = () => {};

  const SHOWN = ['a_au', 'a_km', 'period_d', 'period_yr', 'e', 'i_deg', 'node_deg', 'peri_deg', 'm0_deg', 'plane'];
  const ANGLES = [['e', 'Eccentricity'], ['i_deg', 'Inclination °'], ['node_deg', 'Node Ω °'], ['peri_deg', 'Periapsis ω °'], ['m0_deg', 'Mean anomaly °']];
  $: sizeKeys = Object.keys(schema.units.size).filter((k) => k in orbit);
  $: extra = Object.keys(orbit).filter((k) => !SHOWN.includes(k) || (sizeKeys.length > 1 && k === sizeKeys[1]));
  let newKey = '';

  function num(k, e) {
    const v = e.target.value === '' ? null : Number(e.target.value);
    if (v === null) delete orbit[k]; else orbit[k] = v;
    onchange();
  }
  function raw(k, e) {
    const s = e.target.value.trim();
    if (s === '') delete orbit[k];
    else orbit[k] = isNaN(Number(s)) ? s : Number(s);
    onchange();
  }
  function add() { if (newKey && !(newKey in orbit)) { orbit[newKey] = 0; newKey = ''; onchange(); } }
</script>

<div class="orbit">
  <UnitField obj={orbit} units={schema.units.size} label="Size" {onchange} />
  {#each ANGLES as [k, lab]}
    <label class="f"><span>{lab}</span>
      <input type="number" step="any" value={orbit[k] ?? ''} placeholder={k === 'm0_deg' ? 'blank = placeholder' : '0'} on:change={(e) => num(k, e)} />
    </label>
  {/each}
  <label class="f"><span>Plane</span>
    <select value={orbit.plane ?? 'system'} on:change={(e) => { orbit.plane = e.target.value; onchange(); }}>
      {#each schema.planes as p}<option value={p}>{p}</option>{/each}
    </select>
  </label>
  {#each extra as k}
    <label class="f raw"><span title={k}>{k}</span>
      <input value={orbit[k]} on:change={(e) => raw(k, e)} />
      <button title="remove" on:click={() => { delete orbit[k]; onchange(); }}>×</button>
    </label>
  {/each}
  <div class="addkey">
    <input placeholder="another key (e.g. dnode_deg, t_peri)" bind:value={newKey} />
    <button on:click={add}>add</button>
  </div>
</div>

<style>
  .orbit { display: grid; gap: 4px; padding: 6px 0 2px 10px; border-left: 1px solid var(--rule); }
  .f { display: grid; grid-template-columns: 7.5em 1fr; gap: 6px; align-items: center; }
  .raw { grid-template-columns: 7.5em 1fr 1.2em; }
  span { color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  input, select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 2px 4px; min-width: 0; }
  button { background: none; border: 0; color: var(--dim); padding: 0; }
  button:hover { color: var(--fuchsia); }
  .addkey { display: grid; grid-template-columns: 1fr auto; gap: 6px; margin-top: 2px; }
  .addkey input { font-size: 11px; }
</style>

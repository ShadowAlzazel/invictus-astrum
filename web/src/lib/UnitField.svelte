<script>
  // One quantity with a choice of units. The document keeps whichever unit key is chosen
  // (mass_msun, radius_km, a_au...); switching unit converts the number, so nothing is lost.
  export let obj;                 // the object holding the key, edited in place
  export let units;               // { key: { label, si } } from the server's schema
  export let label = '';
  export let onchange = () => {};

  $: keys = Object.keys(units);
  $: key = keys.find((k) => k in obj && obj[k] !== null) ?? keys[0];
  $: value = obj[key] ?? null;

  const sig = (v) => Number(v.toPrecision(7));
  function setValue(e) {
    const v = e.target.value === '' ? null : Number(e.target.value);
    if (v === null) delete obj[key]; else obj[key] = v;
    onchange();
  }
  function setUnit(e) {
    const to = e.target.value;
    if (value !== null) obj[to] = sig((value * units[key].si) / units[to].si);
    delete obj[key];
    onchange();
  }
</script>

<label class="f">
  <span>{label}</span>
  <input type="number" step="any" value={value ?? ''} on:change={setValue} />
  <select value={key} on:change={setUnit}>
    {#each keys as k}<option value={k}>{units[k].label}</option>{/each}
  </select>
</label>

<style>
  .f { display: grid; grid-template-columns: 7.5em 1fr 7.5em; gap: 6px; align-items: center; }
  span { color: var(--dim); }
  input, select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 2px 4px; min-width: 0; }
</style>

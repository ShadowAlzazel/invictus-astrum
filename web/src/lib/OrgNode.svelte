<script>
  // One unit of a fleet's organisation chart and the units under it: its symbol (drawn by the same
  // code as the map's), its name, and for a ship her class. An admin edits them in place, through
  // the Fleets screen's own value and change. Ships hidden, a formation tallies them by class.
  import { unitSymbol } from './symbols.js';

  export let unit;                      // { ...the unit, kids: [units under it] }
  export let style = null;
  export let admin = false;
  export let ships = true;              // show ships, or tally them
  export let value = (u, k) => u[k];
  export let change = () => {};
  export let changed = {};
  export let classes = [];
  export let onfocus = () => {};        // (id): a formation as the chart's top
  export let role = () => '';           // a ship's: Flagship, or the formation she leads
  export let handed = (u) => u.handed;   // the veterancy handed down to her

  $: kids = ships ? unit.kids : unit.kids.filter((k) => !k.class);
  $: tally = ships ? [] : Object.entries(unit.kids.filter((k) => k.class).reduce((t, k) => ({ ...t, [k.class_name || k.class]: (t[k.class_name || k.class] ?? 0) + 1 }), {}));

  // as the map draws her: her crew's stars, and a pennant if she leads (filled: the fleet flagship)
  $: mark = { u: unit, vet: value(unit, 'veterancy') || handed(unit), lead: unit.class ? (role(unit) === 'Flagship' ? 'flagship' : role(unit) ? 'leader' : null) : null };
  function symbol(canvas, m) {
    const draw = ({ u, vet, lead }) => {
      if (!style) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2), w = 52, h = 40;
      canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      unitSymbol(ctx, style, { ...u, callsign: '', veterancy: vet }, w / 2 - 3, h / 2 + 5, { h: 13, label: false, lead });
    };
    draw(m);
    return { update: draw };
  }
</script>

<div class="node" class:ship={unit.class} class:changed={changed[unit.id]}>
  <button class="sym" on:click={() => !unit.class && onfocus(unit.id)} title={unit.class ? '' : 'Make it the top of the chart'}>
    <canvas use:symbol={mark}></canvas>
  </button>
  <div class="txt">
    {#if admin}<input value={value(unit, 'callsign')} on:input={(e) => change(unit, 'callsign', e.target.value)} />
    {:else}<span class="nm">{unit.callsign}</span>{/if}
    {#if unit.class}
      {#if admin}
        <select value={value(unit, 'class')} on:change={(e) => change(unit, 'class', e.target.value)}>
          {#each classes as c}<option value={c.id}>{c.name}</option>{/each}
        </select>
      {:else}<span class="sub">{unit.class_name || unit.class}{unit.hull_number ? ` · ${unit.hull_number}` : ''}</span>{/if}
    {:else if tally.length}
      <span class="sub">{tally.map(([c, n]) => `${n} ${c}`).join(' · ')}</span>
    {/if}
  </div>
</div>
{#if kids.length}
  <ul>
    {#each kids as k (k.id)}
      <li><svelte:self unit={k} {style} {admin} {ships} {value} {change} {changed} {classes} {onfocus} {role} {handed} /></li>
    {/each}
  </ul>
{/if}

<style>
  .node { display: flex; align-items: center; gap: 4px; padding: 2px 0; }
  .sym { background: none; border: 0; padding: 0; cursor: pointer; }
  .ship .sym { cursor: default; }
  .txt { display: grid; gap: 1px; }
  .nm { font-weight: 600; letter-spacing: 0.03em; }
  .ship .nm { font-weight: 500; }
  .sub { color: var(--t2); font-size: 11px; }
  .changed .txt { box-shadow: inset 2px 0 0 var(--c); padding-left: 4px; }
  input, select { background: transparent; border: 1px solid transparent; color: var(--t); font: inherit; padding: 1px 4px; width: 190px; }
  .ship input { font-weight: 500; }
  input { font-weight: 600; }
  input:hover, select:hover { border-color: var(--line); }
  input:focus, select:focus { outline: none; border-color: var(--y); background: rgba(0, 0, 0, 0.3); }
  select { color: var(--t2); font-size: 11px; width: 190px; }
  /* the lines: each unit hangs from the one above it, the last line stopping at the last unit */
  ul { list-style: none; margin: 0 0 0 25px; padding: 0; }
  li { position: relative; padding-left: 14px; }
  li::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; border-left: 1px solid var(--t3); }
  li:last-child::before { bottom: auto; height: 23px; }
  li::after { content: ''; position: absolute; left: 0; top: 23px; width: 12px; border-top: 1px solid var(--t3); }
</style>

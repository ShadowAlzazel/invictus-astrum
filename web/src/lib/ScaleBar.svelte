<script>
  // The map's scale: a round distance and its length on screen, at the centre of the view. The map
  // is in perspective, so what is nearer than the centre reads larger, what is farther smaller.
  import { onDestroy } from 'svelte';
  import { niceLength } from './SystemMap.js';
  import { km } from './format.js';

  export let map = null;
  const MIN_PX = 50;                  // the bar is 50 to about 125 px long

  let len = 0, px = 0, unhook;
  function update() {
    const k = map.pxPerKm();
    if (!(k > 0)) { px = 0; return; }
    len = niceLength(MIN_PX / k);
    px = Math.round(len * k);
  }
  $: if (map && !unhook) unhook = map.onFrame(update);
  onDestroy(() => unhook?.());
</script>

{#if px}
<div class="scale" data-ui title="The map's scale at the centre of the view">
  <span class="bar" style="width: {px}px"><i></i></span>
  <span class="lbl">{km(len)}</span>
</div>
{/if}

<style>
  .scale { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; padding: 6px 4px; pointer-events: none; }
  .bar { position: relative; height: 6px; border: 1px solid var(--violet); border-top: 0; }
  .bar i { position: absolute; left: 50%; bottom: 0; height: 3px; border-left: 1px solid var(--violet); }
  .lbl { color: var(--dim); font-family: var(--mono, monospace); font-size: 10px; font-variant-numeric: tabular-nums; }
</style>

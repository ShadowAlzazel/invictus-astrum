<script>
  // The telegraph: the acceleration an order holds, from the most a ship (or the slowest ship of a
  // formation) can give down to stop, the doctrine's cruise band marked. Drag the scale or click a
  // detent; onset fires as it moves, oncommit when it is let go.
  import { detents } from './orders.js';

  export let maxG = 0.5;
  export let cruise = null;          // [floor, top] in g, or null
  export let value = 0;
  export let note = '';              // a line under the readout
  export let onset = () => {};
  export let oncommit = () => {};
  export let height = 170;
  export let color = 'var(--fuchsia)';   // a ship's own scale and a new order: fuchsia; an order being flown: light blue

  $: marks = spread(detents(maxG, cruise), height);
  // detents close together keep their ticks where they are, their labels pushed apart to be read
  function spread(list, h, gap = 17) {
    const y = list.map((d) => (maxG > 0 ? (1 - Math.min(d.g, maxG) / maxG) * h : h));
    const at = [...y];
    for (let i = 1; i < at.length; i++) at[i] = Math.max(at[i], at[i - 1] + gap);
    for (let i = at.length - 1; i >= 0; i--) at[i] = Math.min(at[i], (i === at.length - 1 ? h : at[i + 1] - gap));
    return list.map((d, i) => ({ ...d, dy: at[i] - y[i] }));
  }
  $: shown = Math.min(value, maxG);
  let dragging = false;

  function setFrom(e, el) {
    const r = el.getBoundingClientRect();
    const f = 1 - Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
    onset(Math.round(f * maxG * 100) / 100);
  }
  const pct = (g) => (maxG > 0 ? (Math.min(g, maxG) / maxG) * 100 : 0);
</script>

<div class="tg" style="--tg:{color}">
  <div class="scale" style="height:{height}px" role="slider" tabindex="-1" aria-label="acceleration" aria-valuenow={shown}
       on:pointerdown={(e) => { dragging = true; e.currentTarget.setPointerCapture(e.pointerId); setFrom(e, e.currentTarget); }}
       on:pointermove={(e) => dragging && setFrom(e, e.currentTarget)}
       on:pointerup={() => { if (dragging) { dragging = false; oncommit(); } }}>
    <i class="fill" style="height:{pct(shown)}%"></i>
    {#if cruise}
      <i class="band" style="bottom:{pct(cruise[0])}%; height:{pct(cruise[1]) - pct(cruise[0])}%"></i>
    {/if}
    {#each marks as d}
      <button class="mark" class:on={Math.abs(d.g - shown) < 0.005} style="bottom:{pct(d.g)}%; --dy:{d.dy}px"
              on:pointerdown|stopPropagation={() => { onset(d.g); oncommit(); }}>
        <span>{d.label}</span><em>{d.g.toFixed(2)} g</em>
      </button>
    {/each}
  </div>
  <div class="read">
    <b>{shown.toFixed(2)} <small>g</small></b>
    <span>{(shown * 9.80665).toFixed(2)} m/s²</span>
    <span class="dim">most {maxG.toFixed(3)} g now</span>
    {#if note}<span class="dim">{note}</span>{/if}
    <slot />
  </div>
</div>

<style>
  .tg { display: grid; grid-template-columns: 150px 1fr; gap: 14px; padding: 9px 0 12px; }
  .scale { position: relative; margin-left: 4px; border-left: 2px solid var(--rule); cursor: ns-resize; touch-action: none; }
  .fill { position: absolute; left: -2px; bottom: 0; width: 6px; background: var(--tg); }
  .band { position: absolute; left: -2px; width: 6px; background: rgba(159, 240, 255, 0.35); }
  .mark { position: absolute; left: 10px; transform: translateY(50%); display: flex; gap: 8px; align-items: baseline;
          background: none; border: 0; padding: 0; color: var(--dim); font: inherit; white-space: nowrap; }
  .mark::before { content: ''; position: absolute; left: -12px; top: 50%; width: 8px; height: 1px; background: var(--dim); }
  .mark span { font-family: var(--display); font-size: 12px; }
  .mark em { font-style: normal; font-size: 10px; }
  .mark span, .mark em { display: inline-block; transform: translateY(var(--dy, 0)); }
  .mark:hover, .mark.on { color: var(--ink); }
  .mark:focus { outline: none; }
  .mark.on span { color: var(--tg); }
  .read { display: grid; align-content: start; gap: 3px; }
  .read b { font-family: var(--display); font-size: 30px; font-weight: 600; line-height: 1; }
  .read small { font-size: 14px; color: var(--dim); }
  .read .dim { color: var(--dim); font-size: 11px; }
</style>

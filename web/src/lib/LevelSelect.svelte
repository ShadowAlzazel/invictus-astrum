<script>
  // The start screen: every system on disk is a level. Choosing one previews it behind the list;
  // Enter takes the map. Hand-written systems are copied into the workshop; workshop systems edited.
  import { n } from './format.js';

  export let levels = [];
  export let current = null;
  export let onpreview = () => {};
  export let onenter = () => {};
  export let onworkshop = () => {};    // (id | null, copy)
  export let onback = () => {};
  export let purpose = 'play';         // 'play': Enter takes the map. 'build': it opens the workshop

  const LY_PER_PC = 3.261564;
  function line(l) {
    const c = l.counts, parts = [];
    const stars = c.star ?? 0, planets = (c.planet ?? 0) + (c.dwarf ?? 0), moons = c.moon ?? 0;
    parts.push(`${stars} star${stars === 1 ? '' : 's'}`);
    if (planets) parts.push(`${planets} planet${planets === 1 ? '' : 's'}`);
    if (moons) parts.push(`${moons} moon${moons === 1 ? '' : 's'}`);
    if (l.distance_pc) parts.push(`${n(l.distance_pc * LY_PER_PC, 2)} ly`);
    return parts.join(' · ');
  }
  function primary(l) { if (purpose === 'build') onworkshop(l.id, !l.workshop_made); else onenter(l.id); }
  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    const i = levels.findIndex((l) => l.id === current);
    if (e.key === 'ArrowDown' && levels.length) { e.preventDefault(); onpreview(levels[(i + 1) % levels.length].id); }
    if (e.key === 'ArrowUp' && levels.length) { e.preventDefault(); onpreview(levels[(i - 1 + levels.length) % levels.length].id); }
    if (e.key === 'Enter' && current) primary(levels.find((l) => l.id === current));
    if (e.key === 'Escape') onback();
  }
</script>

<svelte:window on:keydown={key} />

<aside data-ui>
  <button class="back" on:click={onback}>◂ Menu</button>
  <h1>{purpose === 'build' ? 'Build from a system' : 'Select a system'}</h1>
  {#if purpose === 'build'}
    <button class="new top" on:click={() => onworkshop(null, false)}>+ New system</button>
  {/if}
  <ul>
    {#each levels as l (l.id)}
      <li class:on={l.id === current}>
        <button class="lvl" on:click={() => onpreview(l.id)} on:dblclick={() => primary(l)}>
          <span class="name">{l.name}</span>
          <span class="sub">{line(l)}</span>
          <span class="tags">
            {#each l.stars.slice(0, 3) as s}<i>{s}</i>{/each}
            {#if l.numerical}<i class="jpl">JPL ephemeris</i>{/if}
            {#if l.workshop_made}<i class="ws">workshop</i>{/if}
            {#if !l.tied}<i>untied</i>{/if}
            {#if l.warnings}<i class="warn">{l.warnings} finding{l.warnings > 1 ? 's' : ''}</i>{/if}
          </span>
        </button>
        {#if l.id === current}
          <div class="acts">
            {#if purpose === 'build'}
              <button class="enter" on:click={() => onworkshop(l.id, !l.workshop_made)}>{l.workshop_made ? 'Edit ▸' : 'Copy and build ▸'}</button>
            {:else}
              <button class="enter" on:click={() => onenter(l.id)}>Enter ▸</button>
            {/if}
            <span class="file">{l.file}</span>
          </div>
        {/if}
      </li>
    {/each}
  </ul>
  <p class="keys">↑ ↓ choose · Enter {purpose === 'build' ? 'to build' : 'to take the map'} · Esc back · the list is data/systems/</p>
</aside>

<style>
  aside {
    position: fixed; top: 20px; left: 20px; bottom: 20px; width: 400px; overflow: auto; z-index: 25;
    background: var(--panel); border-left: 1px solid var(--violet); padding: 18px 20px; backdrop-filter: blur(6px);
  }
  .back { font-family: var(--display); }
  h1 { font-family: var(--display); font-weight: 600; font-size: 26px; margin: 10px 0 16px; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  li { border-left: 1px solid transparent; padding: 6px 0 6px 10px; }
  li.on { border-left-color: var(--fuchsia); background: rgba(116, 51, 250, 0.07); }
  button { background: none; border: 0; color: var(--dim); font: inherit; padding: 0; text-align: left; }
  button:hover { color: var(--ink); }
  .lvl { display: grid; gap: 3px; width: 100%; }
  .name { font-family: var(--display); font-size: 18px; color: var(--ink); }
  .sub { color: var(--dim); }
  .tags { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 10px; }
  .tags i { font-style: normal; color: var(--dim); }
  .tags .jpl { color: var(--cyan, #9ff0ff); }
  .tags .ws { color: var(--fuchsia); }
  .tags .warn { color: #ffd27a; }
  .acts { display: flex; gap: 16px; align-items: baseline; margin-top: 8px; }
  .enter { color: var(--ink); font-family: var(--display); font-size: 14px; box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .file { margin-left: auto; color: var(--dim); font-size: 10px; }
  .new { margin: 0 0 14px; color: var(--violet); filter: brightness(1.5); font-family: var(--display); font-size: 14px; }
  .new:hover { color: var(--fuchsia); filter: none; }
  .keys { color: var(--dim); font-size: 10px; margin: 14px 0 0; }
</style>

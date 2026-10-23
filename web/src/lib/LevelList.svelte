<script>
  // Play: the levels, each a game with a clock of its own on the server (astrum/level.py). Nothing
  // ticks until one is started; a started one runs on, watched or not, until it is stopped. Choosing
  // one previews its first system behind the list (still: no fleet, no clock); Enter starts it, or
  // goes back into it. The authored levels first (data/levels/), then every system alone.
  import { utcOf, warpLabel } from './clock.js';

  export let levels = [];
  export let current = null;
  export let note = '';                // why the map came back here (its level stopped), if it did
  export let onpreview = () => {};
  export let onenter = () => {};       // (id): start it, or go back into it
  export let onrestart = () => {};     // (id): from its start again
  export let onstop = () => {};        // (id): no clock, no fleets
  export let onback = () => {};

  let sure = null;                     // restart or stop asked once: a second click does it
  const ask = (what, id, fn) => { if (sure !== `${what}:${id}`) { sure = `${what}:${id}`; return; } sure = null; fn(id); };
  $: games = levels.filter((l) => !l.own);
  $: alone = levels.filter((l) => l.own);
  $: order = [...games, ...alone];
  const held = (l) => (l.own ? 'the system alone: no scenario'
    : l.systems.map((s) => (s.scenario_name ? `${s.name} · ${s.scenario_name}` : s.name)).join('  /  '));
  const stands = (l) => !l.clock ? `starts ${l.start_utc.slice(0, 16).replace('T', ' ')} UTC · ${warpLabel(l.warp)}`
    : `${l.clock.paused ? 'paused' : `running · ${warpLabel(l.clock.warp)}`} · ${utcOf(l.clock.t)}`;
  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    const i = order.findIndex((l) => l.id === current);
    if (e.key === 'ArrowDown' && order.length) { e.preventDefault(); onpreview(order[(i + 1) % order.length].id); }
    if (e.key === 'ArrowUp' && order.length) { e.preventDefault(); onpreview(order[(i - 1 + order.length) % order.length].id); }
    if (e.key === 'Enter' && current) onenter(current);
    if (e.key === 'Escape') onback();
  }
</script>

<svelte:window on:keydown={key} />

<aside data-ui>
  <button class="back" on:click={onback}>◂ Menu</button>
  <h1>Select a level</h1>
  {#if note}<p class="note">{note}</p>{/if}
  {#each [[games, ''], [alone, 'Systems alone']] as [list, head]}
    {#if list.length}
      {#if head}<h2>{head}</h2>{/if}
      <ul>
        {#each list as l (l.id)}
          <li class:on={l.id === current}>
            <button class="lvl" on:click={() => onpreview(l.id)} on:dblclick={() => onenter(l.id)}>
              <span class="name">{l.name}</span>
              <span class="sub">{held(l)}</span>
              <span class="tags"><i class:live={l.clock && !l.clock.paused} class:paused={l.clock?.paused}>{stands(l)}</i></span>
            </button>
            {#if l.id === current}
              {#if l.notes && !l.own}<p class="notes">{l.notes}</p>{/if}
              <div class="acts">
                <button class="enter" on:click={() => onenter(l.id)}>{l.clock ? 'Resume ▸' : 'Start ▸'}</button>
                {#if l.clock}
                  <button class="small" class:sure={sure === `restart:${l.id}`} on:click={() => ask('restart', l.id, onrestart)}
                    on:blur={() => (sure = null)} title="Its clock back to its start, its fleets as their scenarios have them">{sure === `restart:${l.id}` ? 'Restart?' : 'Restart'}</button>
                  <button class="small" class:sure={sure === `stop:${l.id}`} on:click={() => ask('stop', l.id, onstop)}
                    on:blur={() => (sure = null)} title="Stop its clock and drop its fleets: nothing of it runs">{sure === `stop:${l.id}` ? 'Stop?' : 'Stop'}</button>
                {/if}
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  {/each}
  <p class="keys">↑ ↓ choose · Enter to start or resume · Esc back · the levels are data/levels/; a level runs on the server until it is stopped</p>
</aside>

<style>
  aside {
    position: fixed; top: 20px; left: 20px; bottom: 20px; width: 400px; overflow: auto; z-index: 25;
    background: var(--panel); border-left: 1px solid var(--violet); padding: 18px 20px; backdrop-filter: blur(6px);
  }
  .back { font-family: var(--display); }
  h1 { font-family: var(--display); font-weight: 600; font-size: 26px; margin: 10px 0 16px; }
  h2 { font-family: var(--display); font-weight: 500; font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--dim); margin: 18px 0 6px; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  li { border-left: 1px solid transparent; padding: 6px 0 6px 10px; }
  li.on { border-left-color: var(--fuchsia); background: rgba(116, 51, 250, 0.07); }
  button { background: none; border: 0; color: var(--dim); font: inherit; padding: 0; text-align: left; }
  button:hover { color: var(--ink); }
  .lvl { display: grid; gap: 3px; width: 100%; }
  .name { font-family: var(--display); font-size: 18px; color: var(--ink); }
  .sub { color: var(--dim); }
  .tags { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 10px; }
  .tags i { font-style: normal; color: var(--dim); font-variant-numeric: tabular-nums; }
  .tags i.live { color: var(--cyan, #9ff0ff); }
  .tags i.paused { color: #ffd27a; }
  .notes { margin: 6px 0 0; color: var(--dim); font-size: 11px; line-height: 1.4; }
  .note { margin: 0 0 12px; color: #ffd27a; font-size: 12px; line-height: 1.4; }
  .acts { display: flex; gap: 16px; align-items: baseline; margin-top: 8px; }
  .enter { color: var(--ink); font-family: var(--display); font-size: 14px; box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .small { font-size: 11px; }
  .small.sure { color: #ffd27a; }
  .keys { color: var(--dim); font-size: 10px; margin: 14px 0 0; }
</style>

<script>
  // The landing page: one place to choose what to do, so no screen carries another's controls.
  export let onchoose = () => {};
  export let counts = { levels: 0, systems: 0, ships: 0 };

  const ITEMS = [
    { id: 'play', title: 'Simulation', text: 'Choose a level and start it: its clock runs on the server, true scale, tactical picture.' },
    { id: 'build', title: 'System workshop', text: 'Build a stellar system, or copy one and change it. Every saved system is also a level of its own.' },
    { id: 'ships', title: 'Ship registry', text: 'The classes of the fleet: particulars, batteries, reaches by crew, and what is still blank.' },
    { id: 'fleets', title: 'Fleets', text: 'Every fleet, its ships by class and its order of battle. An admin renames and refits them.' },
    { id: 'shipyard', title: 'Ship workshop', text: 'Design ship classes.', soon: true },
    { id: 'settings', title: 'Settings', text: 'Text and icon sizes, folding, what a selection shows. Saved on this machine.' },
  ];
  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    const i = Number(e.key) - 1;
    if (ITEMS[i] && !ITEMS[i].soon) onchoose(ITEMS[i].id);
  }
</script>

<svelte:window on:keydown={key} />

<main data-ui>
  <p class="eyebrow">ARCVS VOID COMMAND</p>
  <h1>INVICTUS <b>ASTRUM</b></h1>
  <nav>
    {#each ITEMS as it, i}
      <button class:soon={it.soon} disabled={it.soon} on:click={() => onchoose(it.id)}>
        <span class="k">{i + 1}</span>
        <span class="t">{it.title}{#if it.soon}<i>next</i>{/if}</span>
        <span class="d">{it.text}</span>
      </button>
    {/each}
  </nav>
  <p class="foot">{counts.levels} levels · {counts.systems} systems · {counts.ships} ship classes · all data on this machine, in data/</p>
</main>

<style>
  main {
    position: fixed; top: 50%; left: 6vw; transform: translateY(-50%); width: min(520px, 88vw); z-index: 25;
    background: var(--panel); border-left: 1px solid var(--violet); padding: 28px 30px 22px; backdrop-filter: blur(6px);
  }
  .eyebrow { margin: 0; font-family: var(--display); letter-spacing: 0.22em; color: var(--dim); font-size: 11px; }
  h1 { font-family: var(--display); font-weight: 400; letter-spacing: 0.14em; font-size: 34px; margin: 8px 0 26px; color: var(--dim); }
  h1 b { color: var(--ink); font-weight: 600; }
  nav { display: grid; gap: 4px; }
  button { display: grid; grid-template-columns: 1.6em 1fr; gap: 2px 10px; background: none; border: 0; text-align: left;
           padding: 10px 10px 10px 8px; border-left: 1px solid transparent; color: var(--ink); font: inherit; }
  button:hover:not(:disabled) { border-left-color: var(--fuchsia); background: rgba(116, 51, 250, 0.08); }
  .k { grid-row: span 2; color: var(--violet); filter: brightness(1.5); font-family: var(--display); font-size: 15px; }
  .t { font-family: var(--display); font-size: 20px; }
  .t i { font-style: normal; font-size: 10px; color: var(--fuchsia); margin-left: 10px; letter-spacing: 0.1em; vertical-align: middle; }
  .d { color: var(--dim); font-size: 12px; }
  .soon { opacity: 0.5; }
  .foot { margin: 22px 0 0; color: var(--dim); font-size: 10px; }
</style>

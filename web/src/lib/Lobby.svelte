<script>
  // Play, signed in: the lobbies (astrum/lobby.py), as the server pushes them. Out of one: the open
  // lobbies to join, and every level to make a new one for (it previews its first system behind,
  // still). In one: its level, its members and the side each plays (yours to choose: any of the
  // level's, or MASTER), the host's rules, and the level's clock: the host starts, restarts and
  // stops it and chooses another while it does not run; pausing it and its warp are the host's, or
  // anyone's by the rule. Once it runs, everyone in it may take the map.
  import { utcOf, warpLabel, stepWarp } from './clock.js';

  export let you = null;
  export let lobbies = [];
  export let levels = [];
  export let current = null;           // the level chosen in the list (out of a lobby)
  export let note = '';                // why the map came back here, or what the server said no to
  export let onpreview = () => {};     // (level)
  export let onenter = () => {};       // take the map: your lobby's level, running
  export let onact = () => {};         // (msg): a lobby action
  export let onsignout = () => {};
  export let onback = () => {};

  let sure = null;                     // restart or stop asked once: a second click does it
  const ask = (what) => { if (sure !== what) { sure = what; return; } sure = null; onact({ do: what }); };
  $: mine = lobbies.find((lb) => lb.members.some((m) => m.user === you)) ?? null;
  $: level = mine ? levels.find((l) => l.id === mine.level) : null;
  $: host = mine?.host === you;
  $: side = mine?.members.find((m) => m.user === you)?.side ?? null;
  $: running = !!level?.clock;
  $: rules = mine?.rules ?? {};
  $: timer = host || rules.anyone_speed;
  $: fixed = running && !host && !rules.switch_sides && !!side;
  $: takenBy = (s) => (!rules.shared_sides && mine?.members.find((m) => m.side === s && m.user !== you)?.user) || null;
  const RULES = [['anyone_speed', 'Anyone may pause and set the warp'], ['switch_sides', 'Anyone may switch sides while it runs'],
                 ['shared_sides', 'A side may be played by several']];
  $: lobbyOf = (lid) => lobbies.find((lb) => lb.level === lid);
  $: games = levels.filter((l) => !l.own);
  $: alone = levels.filter((l) => l.own);
  $: order = [...games, ...alone];
  const nameOf = (lid) => levels.find((l) => l.id === lid)?.name ?? lid;
  const sideName = (l, s) => l?.sides.find((x) => x.id === s)?.label ?? 'no side chosen';
  const held = (l) => (l.own ? 'the system alone: no scenario'
    : l.systems.map((s) => (s.scenario_name ? `${s.name} · ${s.scenario_name}` : s.name)).join('  /  '));
  const stands = (l) => !l?.clock ? `not running · starts ${l.start_utc.slice(0, 16).replace('T', ' ')} UTC · ${warpLabel(l.warp)}`
    : `${l.clock.paused ? 'paused' : `running · ${warpLabel(l.clock.warp)}`} · ${utcOf(l.clock.t)}`;
  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    if (e.key === 'Escape') { onback(); return; }
    if (mine) { if (e.key === 'Enter' && running) onenter(); return; }
    const i = order.findIndex((l) => l.id === current);
    if (e.key === 'ArrowDown' && order.length) { e.preventDefault(); onpreview(order[(i + 1) % order.length].id); }
    if (e.key === 'ArrowUp' && order.length) { e.preventDefault(); onpreview(order[(i - 1 + order.length) % order.length].id); }
    if (e.key === 'Enter' && current) choose(current);
  }
  // a level: into its lobby, or a new one for it
  function choose(lid) { const lb = lobbyOf(lid); onact(lb ? { do: 'join', lobby: lb.id } : { do: 'make', level: lid }); }
</script>

<svelte:window on:keydown={key} />

<aside data-ui>
  <div class="top">
    <button class="back" on:click={onback}>◂ Menu</button>
    <span class="who">{you} · <button class="small" on:click={onsignout}>sign out</button></span>
  </div>
  {#if note}<p class="note">{note}</p>{/if}

  {#if mine && level}
    <h1>{level.name}</h1>
    <p class="sub">{held(level)}</p>
    <p class="tags"><i class:live={running && !level.clock.paused} class:paused={level.clock?.paused}>{stands(level)}</i></p>
    {#if host && !running}
      <label class="pick">Level
        <select value={level.id} on:change={(e) => onact({ do: 'level', level: e.target.value })}>
          {#each levels.filter((l) => l.id === level.id || !lobbyOf(l.id)) as l (l.id)}<option value={l.id}>{l.name}</option>{/each}
        </select>
      </label>
    {/if}

    <h2>In this lobby</h2>
    <ul class="members">
      {#each mine.members as m (m.user)}
        <li><i class="dot" class:online={m.online} title={m.online ? 'connected' : 'not connected'}></i>
          <span class="name">{m.user}</span>{#if m.user === mine.host}<span class="hosttag">host</span>{/if}
          {#if m.user === you}
            <select value={side ?? ''} on:change={(e) => onact({ do: 'side', side: e.target.value })} disabled={fixed}
              title={fixed ? "Sides are fixed while the level runs (the host's rule)" : 'The side you play: its units, and what its ships have seen'}>
              {#if !side}<option value="">choose a side</option>{/if}
              {#each level.sides as s (s.id)}<option value={s.id} disabled={!!takenBy(s.id)}>{s.label}{takenBy(s.id) ? ` · ${takenBy(s.id)}` : ''}</option>{/each}
            </select>
          {:else}<span class="side">{sideName(level, m.side)}</span>{/if}
        </li>
      {/each}
    </ul>

    <h2>Rules <span class="by">the host's</span></h2>
    <ul class="rules">
      {#each RULES as [k, label] (k)}
        <li><label><input id={`rule-${k}`} type="checkbox" checked={rules[k]} disabled={!host}
          on:change={(e) => onact({ do: 'rules', rules: { [k]: e.target.checked } })} />{label}</label></li>
      {/each}
    </ul>

    <div class="acts">
      {#if running}<button class="enter" on:click={onenter} disabled={!side} title={side ? '' : 'Choose a side first'}>Take the map ▸</button>{/if}
      {#if host && !running}<button class="enter" on:click={() => onact({ do: 'start' })}>Start ▸</button>
      {:else if !running}<span class="dim">waiting for {mine.host} to start it</span>{/if}
      {#if running && timer}
        <button class="small" on:click={() => onact({ do: level.clock.paused ? 'run' : 'pause' })}>{level.clock.paused ? 'run' : 'pause'}</button>
        <span class="warp"><button class="small" on:click={() => onact({ do: 'warp', warp: stepWarp(level.clock.warp, false) })}>◀</button>
          {warpLabel(level.clock.warp)}<button class="small" on:click={() => onact({ do: 'warp', warp: stepWarp(level.clock.warp, true) })}>▶</button></span>
      {/if}
      {#if running && host}
        <button class="small" class:sure={sure === 'restart'} on:click={() => ask('restart')} on:blur={() => (sure = null)}
          title="Its clock back to its start, its fleets as their scenarios have them">{sure === 'restart' ? 'restart?' : 'restart'}</button>
        <button class="small" class:sure={sure === 'stop'} on:click={() => ask('stop')} on:blur={() => (sure = null)}
          title="Stop its clock and drop its fleets">{sure === 'stop' ? 'stop?' : 'stop'}</button>
      {/if}
    </div>
    <p class="leave"><button class="small" on:click={() => onact({ do: 'leave' })}>Leave the lobby</button>
      {#if mine.members.length === 1}<span class="dim"> · the last one out stops its level</span>{/if}</p>
  {:else}
    {#if lobbies.length}
      <h1>Lobbies</h1>
      <ul>
        {#each lobbies as lb (lb.id)}
          {@const l = levels.find((x) => x.id === lb.level)}
          <li class:on={lb.level === current}>
            <button class="lvl" on:click={() => onpreview(lb.level)} on:dblclick={() => onact({ do: 'join', lobby: lb.id })}>
              <span class="name">{nameOf(lb.level)}</span>
              <span class="sub">host {lb.host} · {lb.members.map((m) => m.user).join(', ')}</span>
              {#if l}<span class="tags"><i class:live={l.clock && !l.clock.paused} class:paused={l.clock?.paused}>{stands(l)}</i></span>{/if}
            </button>
            {#if lb.level === current}<div class="acts"><button class="enter" on:click={() => onact({ do: 'join', lobby: lb.id })}>Join ▸</button></div>{/if}
          </li>
        {/each}
      </ul>
    {/if}
    <h1 class:second={lobbies.length}>New lobby</h1>
    {#each [[games.filter((l) => !lobbyOf(l.id)), ''], [alone.filter((l) => !lobbyOf(l.id)), 'Systems alone']] as [list, head]}
      {#if list.length}
        {#if head}<h2>{head}</h2>{/if}
        <ul>
          {#each list as l (l.id)}
            <li class:on={l.id === current}>
              <button class="lvl" on:click={() => onpreview(l.id)} on:dblclick={() => choose(l.id)}>
                <span class="name">{l.name}</span>
                <span class="sub">{held(l)}</span>
              </button>
              {#if l.id === current}
                {#if l.notes && !l.own}<p class="notes">{l.notes}</p>{/if}
                <div class="acts"><button class="enter" on:click={() => choose(l.id)}>Make a lobby ▸</button></div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    {/each}
  {/if}
  <p class="keys">{mine ? 'Enter takes the map once it runs · Esc back · the level runs on the server, whoever watches' : '↑ ↓ choose · Enter to make its lobby, or join it · Esc back'}</p>
</aside>

<style>
  aside {
    position: fixed; top: 20px; left: 20px; bottom: 20px; width: 400px; overflow: auto; z-index: 25;
    background: var(--panel); border-left: 1px solid var(--violet); padding: 18px 20px; backdrop-filter: blur(6px);
  }
  .top { display: flex; justify-content: space-between; align-items: baseline; }
  .back { font-family: var(--display); }
  .who { color: var(--ink); font-size: 12px; }
  h1 { font-family: var(--display); font-weight: 600; font-size: 26px; margin: 10px 0 12px; }
  h1.second { margin-top: 24px; }
  h2 { font-family: var(--display); font-weight: 500; font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--dim); margin: 18px 0 6px; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  li { border-left: 1px solid transparent; padding: 6px 0 6px 10px; }
  li.on { border-left-color: var(--fuchsia); background: rgba(116, 51, 250, 0.07); }
  button { background: none; border: 0; color: var(--dim); font: inherit; padding: 0; text-align: left; }
  button:hover { color: var(--ink); }
  button:disabled { color: var(--dim); box-shadow: none; cursor: default; }
  select { background: rgba(0, 0, 0, 0.3); border: 1px solid var(--rule); color: var(--ink); font: inherit; font-size: 12px; }
  .lvl { display: grid; gap: 3px; width: 100%; }
  .name { font-family: var(--display); font-size: 18px; color: var(--ink); }
  .sub { color: var(--dim); }
  .tags { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 10px; margin: 4px 0 0; }
  .tags i { font-style: normal; color: var(--dim); font-variant-numeric: tabular-nums; }
  .tags i.live { color: var(--cyan, #9ff0ff); }
  .tags i.paused { color: #ffd27a; }
  .pick { display: flex; gap: 10px; align-items: baseline; color: var(--dim); font-size: 11px; margin-top: 10px; }
  .members li { display: flex; gap: 8px; align-items: baseline; padding: 4px 0; }
  .members .name { font-size: 16px; }
  .members .side { margin-left: auto; color: var(--dim); }
  .members select { margin-left: auto; }
  .hosttag { font-size: 10px; color: var(--fuchsia); letter-spacing: 0.1em; text-transform: uppercase; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--rule); align-self: center; }
  .dot.online { background: var(--cyan, #9ff0ff); }
  .notes { margin: 6px 0 0; color: var(--dim); font-size: 11px; line-height: 1.4; }
  .note { margin: 10px 0 0; color: #ffd27a; font-size: 12px; line-height: 1.4; }
  .acts { display: flex; gap: 16px; align-items: baseline; margin-top: 12px; flex-wrap: wrap; }
  .enter { color: var(--ink); font-family: var(--display); font-size: 14px; box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .small { font-size: 11px; }
  .small.sure { color: #ffd27a; }
  .warp { color: var(--ink); font-size: 11px; display: inline-flex; gap: 6px; }
  .leave { margin: 18px 0 0; font-size: 11px; }
  .rules li { padding: 2px 0; }
  .rules label { display: flex; gap: 8px; align-items: center; color: var(--ink); font-size: 12px; }
  .rules input { accent-color: var(--fuchsia); }
  h2 .by { text-transform: none; letter-spacing: 0; font-size: 10px; color: var(--dim); margin-left: 6px; }
  .dim { color: var(--dim); font-size: 11px; }
  .keys { color: var(--dim); font-size: 10px; margin: 18px 0 0; }
</style>

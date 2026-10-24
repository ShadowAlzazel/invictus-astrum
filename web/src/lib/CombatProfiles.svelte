<script>
  // Combat profiles, each drawn as its automaton (astrum/shipai, data/automata.toml): the states a
  // ship goes through, the events that move her between them, and, in the state that engages, her
  // stance with the profile's range, targets and ending. Read-only; profiles are made in Settings.
  import { onMount } from 'svelte';
  import { api } from './api.js';

  export let player = null;
  export let onback = () => {};

  let data = null, error = '', pick = null;
  onMount(async () => {
    try { data = await api.profiles(player); pick = data.profiles[0]?.id; } catch (e) { error = String(e.message ?? e); }
  });
  $: profile = data?.profiles.find((p) => p.id === pick);
  $: root = data?.profiles.find((p) => p.root);
  $: auto = profile && (data.automata[profile.automaton] ?? data.automata.default);

  const ROMAN = { 1: 'I', 2: 'II', 3: 'III' };
  const short = (label) => label?.split(':')[0] ?? '';
  const after = (label) => label?.split(':').slice(1).join(':').trim() ?? '';
  const reach = (p, s) => p.range?.[s] ?? root?.range?.[s];
  const sayReach = (v) => typeof v === 'number' ? `${v.toLocaleString()} km` : v ?? '—';

  // the state map: states on a half-ellipse, readiness rising left to right (III ... I), the events
  // as arrows between them (a pair either way bowed apart)
  const W = 760, H = 420, NW = 170, NH = 72;
  $: layout = auto ? place(auto) : null;
  function place(a) {
    const ids = Object.keys(a.states).sort((x, y) => a.states[y].quarters - a.states[x].quarters);
    const n = ids.length, at = {};
    ids.forEach((id, k) => {
      const th = n === 1 ? Math.PI / 2 : Math.PI - (k * Math.PI) / (n - 1);
      at[id] = { x: W / 2 + (W / 2 - NW / 2 - 24) * Math.cos(th), y: 160 + 190 * Math.sin(th) * (n > 2 ? 1 : 0) };
    });
    const edges = [];
    for (const [from, s] of Object.entries(a.states))
      for (const [ev, to] of Object.entries(s.on ?? {}))
        if (to !== from && at[to]) edges.push({ from, to, ev, both: Object.values(a.states[to].on ?? {}).includes(from) });
    return { at, edges: edges.map((e) => curve(e, at[e.from], at[e.to])) };
  }
  function edgeOf(c, d) {            // where a line from a box's centre along d leaves it
    const t = Math.min((NW / 2 + 4) / Math.max(Math.abs(d.x), 1e-9), (NH / 2 + 4) / Math.max(Math.abs(d.y), 1e-9));
    return { x: c.x + d.x * t, y: c.y + d.y * t };
  }
  function curve(e, p, q) {
    const dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy) || 1;
    const off = e.both ? 38 : 0;
    const c = { x: (p.x + q.x) / 2 - (dy / len) * off, y: (p.y + q.y) / 2 + (dx / len) * off };
    const a = edgeOf(p, { x: c.x - p.x, y: c.y - p.y }), b = edgeOf(q, { x: c.x - q.x, y: c.y - q.y });
    return { ...e, d: `M${a.x},${a.y} Q${c.x},${c.y} ${b.x},${b.y}`, lx: 0.25 * a.x + 0.5 * c.x + 0.25 * b.x, ly: 0.25 * a.y + 0.5 * c.y + 0.25 * b.y };
  }
  const tone = (q) => (q === 1 ? 'var(--engage, #ff3046)' : q === 2 ? 'var(--fuchsia, #fa1f99)' : 'var(--violet, #7433fa)');
  const sensed = (s) => (s.sensors === 'active' ? 'pinging' : s.sensors === 'passive' ? 'passive' : 'sensors as they were');
  const evLabel = (ev, a) => (ev === 'quiet' ? `quiet ${Math.round(a.quiet_h)} h` : ev);
  const BOX = 330;
  $: ending = profile ? wrap(`ends ${profile.end ? `${short(data.ends[profile.end])}: ${after(data.ends[profile.end])}` : 'by her stance'}`, 52) : [];
  $: boxH = 76 + 14 * ending.length;
  function wrap(text, n) {               // words into lines of at most n characters
    const out = [];
    for (const w of text.split(' ')) {
      if (out.length && (out[out.length - 1] + ' ' + w).length <= n) out[out.length - 1] += ' ' + w;
      else out.push(w);
    }
    return out;
  }
  const boxX = (x) => Math.min(Math.max(x, BOX / 2 + 6), W - BOX / 2 - 6);

  function key(e) {
    if (e.key === 'Escape' && !['INPUT', 'SELECT'].includes(e.target.tagName)) onback();
  }
</script>

<svelte:window on:keydown={key} />

<div class="cp" data-ui>
  <header class="top">
    <p><span class="sl">//</span> Combat profiles <span class="sl">/</span> <b>{profile?.name ?? '…'}</b></p>
    <span class="who">read here · made in Settings, Combat</span>
    <button class="close" on:click={onback} title="Back to the menu (Esc)"><svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17" /></svg></button>
  </header>

  <aside class="roster">
    <h3>Profiles</h3>
    {#each data?.profiles ?? [] as p (p.id)}
      <button class="item" class:on={p.id === pick} on:click={() => (pick = p.id)}>
        <span class="nm">{p.name}</span>
        <span class="sub">{short(data.stances[p.stance])} · {p.end ? `ends ${short(data.ends[p.end])}` : 'ends by stance'} · {data.automata[p.automaton]?.name ?? p.automaton}{p.root ? ' · the root' : p.player ? ' · yours' : ''}</span>
      </button>
    {/each}
    <p class="note"><b>Stance</b> is what she does with a target. It is ordered to a ship or a formation and passed down its chain; a ship none is ordered to stands in her profile's.</p>
    <p class="note"><b>Profile</b> is the rules her stance reads: how far for each stance, at whom, her automaton (when she is ready to engage at all) and how an engagement ends.</p>
  </aside>

  <main>
    {#if error}<p class="err">{error}</p>{/if}
    {#if profile && auto && layout}
      <section class="head">
        <h2>{profile.name}</h2>
        <p class="dim">automaton <b>{auto.name}</b> · starts {auto.states[auto.start]?.label} · stands down after {Math.round(auto.quiet_h)} h quiet</p>
      </section>

      <svg class="map" viewBox="0 0 {W} {H}" role="img" aria-label="{auto.name}: its states and the events between them">
        <defs>
          <marker id="cp-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" /></marker>
        </defs>
        {#each layout.edges as e}
          <g class="edge"><path d={e.d} marker-end="url(#cp-arr)" /><title>{e.ev}: {data.events[e.ev]}</title>
            <text x={e.lx} y={e.ly - 5} text-anchor="middle">{evLabel(e.ev, auto)}</text></g>
        {/each}
        {#each Object.entries(auto.states) as [id, s]}
          {@const p = layout.at[id]}
          {#if id === auto.start}
            <circle class="start" cx={p.x - NW / 2 - 30} cy={p.y} r="5" />
            <path class="startline" d="M{p.x - NW / 2 - 25},{p.y} L{p.x - NW / 2 - 4},{p.y}" marker-end="url(#cp-arr)" />
          {/if}
          {#if s.engage}
            {@const bx = boxX(p.x)}
            {@const by = p.y > 200 ? p.y + NH / 2 + 22 : Math.max(4, p.y - NH / 2 - 26 - boxH)}
            <path class="tie" d="M{p.x},{p.y > 200 ? p.y + NH / 2 : p.y - NH / 2} L{p.x},{p.y > 200 ? by : by + boxH}" />
            <g class="engage">
              <rect x={bx - BOX / 2} y={by} width={BOX} height={boxH} />
              <text x={bx - BOX / 2 + 10} y={by + 17} class="cap">engages by her stance</text>
              <text x={bx - BOX / 2 + 10} y={by + 35} class="big">{short(data.stances[profile.stance])}<title>{data.stances[profile.stance]}</title></text>
              <text x={bx - BOX / 2 + 10} y={by + 51}>{after(data.stances[profile.stance])}</text>
              <text x={bx - BOX / 2 + 10} y={by + 67} class="dimt">in {sayReach(reach(profile, profile.stance))} · at {profile.targets.join(', ')}<title>{data.ranges[reach(profile, profile.stance)] ?? ''}</title></text>
              {#each ending as line, k}<text x={bx - BOX / 2 + 10} y={by + 83 + 14 * k} class="dimt">{line}</text>{/each}
            </g>
          {/if}
          <g class="node" style="--tone: {tone(s.quarters)}">
            <rect x={p.x - NW / 2} y={p.y - NH / 2} width={NW} height={NH} />
            <text x={p.x - NW / 2 + 12} y={p.y - 10} class="q">{ROMAN[s.quarters]}</text>
            <text x={p.x - NW / 2 + 46} y={p.y - 10} class="lbl">{s.label}</text>
            <text x={p.x - NW / 2 + 46} y={p.y + 8} class="dimt">{sensed(s)}</text>
            <text x={p.x - NW / 2 + 46} y={p.y + 24} class={s.engage ? 'hot' : 'dimt'}>{s.engage ? 'engages' : 'engages nothing'}</text>
          </g>
        {/each}
      </svg>

      <section class="legend">
        <h3>Events</h3>
        <dl>
          {#each Object.entries(data.events) as [ev, what]}<dt>{evLabel(ev, auto)}</dt><dd>{what}</dd>{/each}
        </dl>
        <h3>Ranges, by stance</h3>
        <dl>
          {#each Object.keys(data.stances).filter((s) => s !== 'hold-fire') as s}
            <dt class:here={s === profile.stance}>{short(data.stances[s])}</dt>
            <dd title={data.ranges[reach(profile, s)] ?? ''}>{sayReach(reach(profile, s))}{#if profile.range?.[s] == null} <span class="dim">· the root's</span>{/if}</dd>
          {/each}
        </dl>
      </section>
    {/if}
  </main>
</div>

<style>
  .cp {
    --t: #ececf0; --t2: #9a9aa6; --t3: #5d5d68; --line: rgba(255, 255, 255, 0.1); --band: rgba(255, 255, 255, 0.035);
    position: fixed; inset: 0; z-index: 25; color: var(--t); font-family: 'Barlow', 'Chakra Petch', sans-serif; font-size: 13px;
    display: grid; grid-template-columns: 300px 1fr; grid-template-rows: 56px 1fr;
    background: linear-gradient(115deg, rgba(14, 13, 20, 0.97) 0%, rgba(10, 9, 16, 0.92) 60%, rgba(26, 8, 22, 0.92) 100%);
    backdrop-filter: blur(4px);
  }
  button { background: none; border: 0; color: inherit; font: inherit; padding: 0; text-align: left; }
  .dim { color: var(--t2); }
  .top { grid-column: 1 / -1; display: flex; align-items: center; gap: 14px; padding: 10px 22px; border-bottom: 1px solid var(--line); }
  .top p { margin: 0; font-size: 18px; flex: 1; }
  .sl { color: var(--t2); margin: 0 2px; }
  .who { color: var(--t2); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; }
  .close { width: 36px; height: 36px; display: grid; place-items: center; background: rgba(255, 255, 255, 0.08); }
  .close svg { width: 18px; height: 18px; stroke: currentColor; stroke-width: 2; fill: none; }
  .close:hover { background: var(--fuchsia, #fa1f99); }

  .roster { overflow: auto; padding: 6px 12px 16px 22px; border-right: 1px solid var(--line); }
  h3 { margin: 14px 0 6px; font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t2); }
  .item { display: grid; width: 100%; padding: 8px 10px; border-left: 2px solid transparent; }
  .item:hover { background: var(--band); }
  .item.on { background: rgba(250, 31, 153, 0.1); border-left-color: var(--fuchsia, #fa1f99); }
  .nm { font-weight: 600; letter-spacing: 0.04em; }
  .sub { color: var(--t2); font-size: 11px; }
  .note { color: var(--t2); font-size: 11px; margin-top: 14px; line-height: 1.45; }
  .note b { color: var(--t); }

  main { overflow: auto; padding: 14px 26px 30px; }
  .err { color: #ffd27a; }
  .head h2 { margin: 0 0 4px; font-size: 26px; font-weight: 600; }
  .head p { margin: 0 0 10px; }
  .map { width: 100%; max-width: 980px; display: block; color: var(--t2); }
  .edge path { fill: none; stroke: currentColor; stroke-width: 1.2; }
  .edge text { fill: var(--t); font-size: 12px; letter-spacing: 0.06em; paint-order: stroke; stroke: #0d0c13; stroke-width: 4px; }
  .start { fill: var(--t); }
  .startline { stroke: var(--t); stroke-width: 1.2; color: var(--t); }
  .node rect { fill: rgba(10, 9, 16, 0.9); stroke: var(--tone); stroke-width: 1.4; }
  .node .q { fill: var(--tone); font-size: 22px; font-family: var(--display, inherit); dominant-baseline: hanging; transform: translateY(-12px); }
  .node .lbl { fill: var(--t); font-size: 14px; font-weight: 600; }
  text { fill: var(--t); font-size: 12px; }
  .dimt { fill: var(--t2); font-size: 11px; }
  .hot { fill: var(--engage, #ff3046); font-size: 11px; }
  .tie { stroke: var(--engage, #ff3046); stroke-dasharray: 3 3; }
  .engage rect { fill: rgba(255, 48, 70, 0.07); stroke: var(--engage, #ff3046); stroke-dasharray: 4 3; }
  .engage .cap { fill: var(--engage, #ff3046); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; }
  .engage .big { font-size: 14px; font-weight: 600; }
  .legend { max-width: 980px; display: grid; grid-template-columns: 1fr 1fr; gap: 0 30px; }
  .legend h3 { grid-row: 1; }
  .legend dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; align-content: start; }
  .legend dt { color: var(--t); }
  .legend dt.here { color: var(--engage, #ff3046); }
  .legend dd { margin: 0; color: var(--t2); }
</style>

<script>
  // Combat profiles, each drawn as the MINERVA it makes (astrum/shipai: one automaton for a ship):
  // her ReadyStance (picked above the map: her readiness, what takes her into combat), the profile's
  // engagement (its nodes, what each does, the conditions between them), and out of combat what her
  // stance or her profile says she does after, back to her ReadyStance. Read-only; a commander's own
  // profiles are made in Settings, Combat.
  import { onMount } from 'svelte';
  import { api } from './api.js';

  export let player = null;
  export let onback = () => {};

  let data = null, error = '', pick = null, stance = null;
  onMount(async () => {
    try {
      data = await api.profiles(player);
      pick = data.profiles[0]?.id;
      stance = data.minerva.stance;
    } catch (e) { error = String(e.message ?? e); }
  });
  $: profile = data?.profiles.find((p) => p.id === pick);
  $: eng = profile && (profile.engagement ?? data.profiles.find((p) => p.id === profile.map)?.engagement ?? data.profiles[0].engagement);
  $: rs = data && stance ? data.minerva.stances[stance] : null;

  const ROMAN = { 1: 'I', 2: 'II', 3: 'III' };
  const QUARTERS = { 1: 'general quarters, pinging', 2: 'attack', 3: 'watching' };
  const ENTER = { seen: 'a target seen in range', 'fired-on': 'a ship engaging her, in range', never: 'never' };
  const sayReach = (v) => typeof v === 'number' ? `${v.toLocaleString()} km` : v ?? '—';
  const reach = (p, s) => p?.range?.[s] ?? data?.minerva.stances[s]?.range;

  // the map: the ReadyStance on the left, the engagement's nodes in layers from its start (each
  // layer one step further on), Exit and what comes after on the right, the way back beneath
  const NW = 196, NH = 70, GX = 250, GY = 112, TOP = 74, X0 = 380;
  $: layout = eng && rs ? place(eng) : null;
  function place(e) {
    const depth = { [e.start]: 0 }, order = [e.start];
    for (let q = 0; q < order.length; q++)
      for (const w of e.nodes[order[q]].on) if (w.go !== 'exit' && !(w.go in depth)) { depth[w.go] = depth[order[q]] + 1; order.push(w.go); }
    for (const id of Object.keys(e.nodes)) if (!(id in depth)) { depth[id] = 0; order.push(id); }
    const layers = [];
    for (const id of order) (layers[depth[id]] ??= []).push(id);
    const rows = Math.max(...layers.map((l) => l.length));
    const backs = layers.length;                      // room above for the ways back
    const top = TOP + 40 + 14 * Math.min(backs, 4);
    const at = {};
    layers.forEach((l, k) => l.forEach((id, m) => (at[id] = { x: X0 + k * GX, y: top + NH / 2 + (m + (rows - l.length) / 2) * GY })));
    const midY = top + NH / 2 + ((rows - 1) * GY) / 2;
    const busY = top + (rows - 1) * GY + NH + 34;     // the ways out run along here to Exit
    const exitX = X0 + (layers.length - 0.5) * GX;
    const W = exitX + 250, H = busY + 80;
    const edges = [];
    let nb = 0;
    for (const [id, n] of Object.entries(e.nodes))
      n.on.forEach((w) => {
        const p = at[id];
        if (w.go === 'exit') { edges.push(out(p, exitX, busY, w.if)); return; }
        if (id === w.go) { edges.push(loop(p, w.if)); return; }
        const back = depth[w.go] <= depth[id];
        edges.push(bend(p, at[w.go], w.if, back, back ? nb++ : 0, top));
      });
    return { at, edges, exitX, busY, midY, top, W, H, ready: { x: 110, y: midY }, after: { x: exitX + 138, y: busY } };
  }
  function rim(c, d) {               // where a line from a box's centre along d leaves it
    const t = Math.min((NW / 2 + 3) / Math.max(Math.abs(d.x), 1e-9), (NH / 2 + 3) / Math.max(Math.abs(d.y), 1e-9));
    return { x: c.x + d.x * t, y: c.y + d.y * t };
  }
  function out(p, exitX, busY, cond) {  // down from the node to the bus, along it to Exit
    const x = p.x + NW / 2 - 28, y = p.y + NH / 2 + 2;
    return { cond, kind: 'exit', d: `M${x},${y} L${x},${busY} L${exitX - 16},${busY}`, lx: x + 5, ly: y + 15, anchor: 'start' };
  }
  function bend(p, q, cond, back, k, top) {  // on: straight, bowed below if it skips a layer; back: an arc above
    if (back) {
      const a = { x: p.x - 20 + 8 * k, y: p.y - NH / 2 - 2 }, b = { x: q.x + 20 - 8 * k, y: q.y - NH / 2 - 2 };
      const apex = top - 18 - 14 * (k % 4);
      return { cond, kind: 'back', d: `M${a.x},${a.y} C${a.x},${apex} ${b.x},${apex} ${b.x},${b.y}`,
               lx: (a.x + b.x) / 2, ly: apex + 6 * 0.75 - 2, anchor: 'middle' };
    }
    const dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy) || 1;
    const off = Math.abs(dx) > GX * 1.2 ? 44 : 0;
    const c = { x: (p.x + q.x) / 2 - (dy / len) * off, y: (p.y + q.y) / 2 + (dx / len) * off };
    const a = rim(p, { x: c.x - p.x, y: c.y - p.y }), b = rim(q, { x: c.x - q.x, y: c.y - q.y });
    return { cond, kind: 'on', d: `M${a.x},${a.y} Q${c.x},${c.y} ${b.x},${b.y}`,
             lx: 0.25 * a.x + 0.5 * c.x + 0.25 * b.x, ly: 0.25 * a.y + 0.5 * c.y + 0.25 * b.y - 5, anchor: 'middle' };
  }
  function loop(p, cond) {
    const x = p.x + NW / 2, y = p.y - NH / 2;
    return { cond, kind: 'back', d: `M${x - 34},${y} C${x - 24},${y - 44} ${x + 40},${y - 30} ${x},${y + 14}`, lx: x + 10, ly: y - 32, anchor: 'start' };
  }
  function wrap(text, n) {               // words into lines of at most n characters
    const out = [];
    for (const w of (text ?? '').split(' ')) {
      if (out.length && (out[out.length - 1] + ' ' + w).length <= n) out[out.length - 1] += ' ' + w;
      else out.push(w);
    }
    return out;
  }
  const does = (n) => {
    const line = n.do.length ? n.do.map((a) => (a === 'fire' || a === 'station') && n.weapon !== 'focus' ? `${a} (${n.weapon})` : a).join(' · ') : 'nothing: await next tick';
    return n.spine && n.spine !== 'cut' ? `${line} · spine ${n.spine}` : line;
  };
  $: used = eng ? [...new Set(Object.values(eng.nodes).flatMap((n) => n.on.map((w) => w.if)))] : [];
  $: acts = eng ? [...new Set(Object.values(eng.nodes).flatMap((n) => n.do))] : [];
  $: after = profile?.after || rs?.after;

  function key(e) {
    if (e.key === 'Escape' && !['INPUT', 'SELECT'].includes(e.target.tagName)) onback();
  }
</script>

<svelte:window on:keydown={key} />

<div class="cp" data-ui>
  <header class="top">
    <p><span class="sl">//</span> Combat profiles <span class="sl">/</span> <b>{profile?.name ?? '…'}</b></p>
    <span class="who">MINERVA · read here · made in Settings, Combat</span>
    <button class="close" on:click={onback} title="Back to the menu (Esc)"><svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17" /></svg></button>
  </header>

  <aside class="roster">
    <h3>Profiles</h3>
    {#each data?.profiles ?? [] as p (p.id)}
      <button class="item" class:on={p.id === pick} on:click={() => (pick = p.id)}>
        <span class="nm">{p.name}</span>
        <span class="sub">{p.targets.join(', ')}{p.engagement ? '' : ` · flies ${data.profiles.find((x) => x.id === p.map)?.name ?? p.map}`}{p.after ? ` · after: ${p.after}` : ''}{p.root ? ' · the root' : p.player ? ' · yours' : ''}</span>
      </button>
    {/each}
    <p class="note"><b>MINERVA</b> is her ship AI: one automaton. Her <b>ReadyStance</b> is where she stands out of combat: her readiness, what takes her into combat, and what she does once out of it. It is ordered to a ship or a formation and passed down its chain; none ordered, she holds ground.</p>
    <p class="note">Her <b>profile</b> is what she does in combat: the engagement in the middle, its nodes and the conditions between them, whom she engages and how far out. The CAPTAIN moves her through it and gives each node's orders.</p>
  </aside>

  <main>
    {#if error}<p class="err">{error}</p>{/if}
    {#if profile && eng && layout && rs}
      <section class="head">
        <h2>{profile.name}</h2>
        <div class="stances">
          <span class="dim">ReadyStance</span>
          {#each Object.values(data.minerva.stances) as s (s.id)}
            <button class:on={s.id === stance} on:click={() => (stance = s.id)} title={s.text}>{s.label}{s.id === data.minerva.stance ? ' ·' : ''}</button>
          {/each}
        </div>
      </section>

      <svg class="map" viewBox="0 0 {layout.W} {layout.H}" role="img" aria-label="{profile.name}: her MINERVA at {rs.label}">
        <defs>
          <marker id="cp-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" /></marker>
        </defs>
        <rect class="region" x={X0 - NW / 2 - 22} y={TOP - 34} width={layout.exitX - (X0 - NW / 2 - 22) + 22} height={layout.busY - TOP + 50} />
        <text class="cap" x={X0 - NW / 2 - 10} y={TOP - 16}>engagement · {profile.name}</text>

        <g class="ready" style="--tone: {rs.readiness === 1 ? 'var(--engage, #ff3046)' : rs.readiness === 2 ? 'var(--fuchsia, #fa1f99)' : 'var(--violet, #7433fa)'}">
          <rect x={layout.ready.x - 98} y={layout.ready.y - 70} width="196" height="140" />
          <text class="cap2" x={layout.ready.x - 86} y={layout.ready.y - 50}>readystance</text>
          <text class="lbl" x={layout.ready.x - 86} y={layout.ready.y - 29}>{rs.label}</text>
          <text class="q" x={layout.ready.x - 86} y={layout.ready.y - 9}>readiness {ROMAN[rs.readiness]}</text>
          <text class="dimt" x={layout.ready.x - 86} y={layout.ready.y + 8}>{QUARTERS[rs.readiness]}</text>
          <text class="dimt" x={layout.ready.x - 86} y={layout.ready.y + 26}>enters on {ENTER[rs.enter]}</text>
          {#if rs.enter !== 'never'}<text class="dimt" x={layout.ready.x - 86} y={layout.ready.y + 42}>within {sayReach(reach(profile, stance))}{profile.range?.[stance] != null ? ' (profile)' : ''}</text>{/if}
          {#if !rs.moves}<text class="dimt" x={layout.ready.x - 86} y={layout.ready.y + 58}>never moves: hull turned</text>{/if}
        </g>
        {#if rs.enter !== 'never'}
          {@const s = layout.at[eng.start]}
          <path class="enter" d="M{layout.ready.x + 100},{layout.ready.y} C{layout.ready.x + 130},{layout.ready.y} {s.x - NW / 2 - 40},{s.y} {s.x - NW / 2 - 4},{s.y}" marker-end="url(#cp-arr)" />
          <text class="elbl" x={layout.ready.x + 104} y={Math.min(layout.ready.y, s.y) - 10}>enter</text>
        {/if}

        {#each layout.edges as e}
          <g class="edge {e.kind}"><path d={e.d} marker-end="url(#cp-arr)" /><title>{e.cond}: {data.conditions[e.cond]}</title>
            <text x={e.lx} y={e.ly} text-anchor={e.anchor}>{e.cond}</text></g>
        {/each}
        {#each Object.entries(eng.nodes) as [id, n] (id)}
          {@const p = layout.at[id]}
          <g class="node" class:start={id === eng.start}>
            <rect x={p.x - NW / 2} y={p.y - NH / 2} width={NW} height={NH} />
            <text class="lbl" x={p.x - NW / 2 + 10} y={p.y - 13}>{n.label}</text>
            <text class="dimt" x={p.x - NW / 2 + 10} y={p.y + 7}>{does(n)}{!rs.moves && n.do.some((a) => ['station', 'pass', 'hold'].includes(a)) ? ' ↺' : ''}</text>
            {#if n.wait_s}<text class="dimt" x={p.x - NW / 2 + 10} y={p.y + 24}>waits {Math.round(n.wait_s / 60)} min</text>{/if}
          </g>
        {/each}
        <g class="exit">
          <circle cx={layout.exitX} cy={layout.busY} r="15" /><text x={layout.exitX} y={layout.busY + 4} text-anchor="middle">exit</text>
          <path d="M{layout.exitX + 16},{layout.busY} L{layout.after.x - 102},{layout.busY}" marker-end="url(#cp-arr)" />
          <rect x={layout.after.x - 100} y={layout.after.y - 36} width="200" height={50 + 13 * wrap(data.afters[after], 30).length} />
          <text class="cap2" x={layout.after.x - 90} y={layout.after.y - 17}>after{profile.after ? ' (profile)' : ''}</text>
          <text class="lbl" x={layout.after.x - 90} y={layout.after.y + 3}>{after}</text>
          {#each wrap(data.afters[after], 30) as l, k}<text class="dimt" x={layout.after.x - 90} y={layout.after.y + 20 + 13 * k}>{l}</text>{/each}
          <path class="home" d="M{layout.after.x},{layout.after.y + 16 + 13 * wrap(data.afters[after], 30).length} L{layout.after.x},{layout.H - 14} L{layout.ready.x},{layout.H - 14} L{layout.ready.x},{layout.ready.y + 72}" marker-end="url(#cp-arr)" />
          <text class="dimt" x={(layout.after.x + layout.ready.x) / 2} y={layout.H - 20} text-anchor="middle">back to her ReadyStance</text>
        </g>
      </svg>

      <section class="legend">
        <div><h3>Conditions</h3>
          <dl>{#each used as c}<dt>{c}</dt><dd>{data.conditions[c]}</dd>{/each}</dl></div>
        <div><h3>Actions</h3>
          <dl>{#each acts as a}<dt>{a}</dt><dd>{data.actions[a]}</dd>{/each}
            <dt>tick</dt><dd>engaged, every {data.minerva.engaged_s} s near her envelope, else by how fast she closes (at most {data.minerva.block_s / 60} min); a battery fires again after {data.minerva.cycle_s} s</dd>
            {#each Object.entries(data.spines ?? {}) as [k, text]}<dt>spine {k}</dt><dd>{text}</dd>{/each}</dl></div>
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
  .head h2 { margin: 0 0 8px; font-size: 26px; font-weight: 600; }
  .stances { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
  .stances .dim { font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; margin-right: 6px; }
  .stances button { padding: 3px 10px; border: 1px solid var(--line); font-size: 12px; }
  .stances button.on { border-color: var(--fuchsia, #fa1f99); background: rgba(250, 31, 153, 0.12); }
  .map { width: 100%; max-width: 1200px; display: block; color: var(--t2); }
  text { fill: var(--t); font-size: 14px; }
  .dimt { fill: var(--t2); font-size: 13px; }
  .lbl { font-size: 16px; font-weight: 600; }
  .cap, .cap2 { fill: var(--t2); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; }
  .region { fill: rgba(255, 48, 70, 0.035); stroke: var(--engage, #ff3046); stroke-dasharray: 4 4; stroke-opacity: 0.6; }
  .ready rect { fill: rgba(10, 9, 16, 0.9); stroke: var(--tone); stroke-width: 1.4; }
  .ready .q { fill: var(--tone); font-size: 15px; }
  .ready .q tspan { font-size: 12px; }
  .enter { fill: none; stroke: var(--engage, #ff3046); stroke-width: 1.3; color: var(--engage, #ff3046); }
  .elbl { fill: var(--engage, #ff3046); font-size: 13px; }
  .node rect { fill: rgba(10, 9, 16, 0.92); stroke: var(--t3); stroke-width: 1.2; }
  .node.start rect { stroke: var(--engage, #ff3046); }
  .edge path { fill: none; stroke: currentColor; stroke-width: 1.1; }
  .edge.back { color: var(--violet, #7433fa); filter: brightness(1.6); }
  .edge.exit { color: var(--t3); }
  .edge text { fill: var(--t); font-size: 13px; paint-order: stroke; stroke: #0d0c13; stroke-width: 4px; }
  .exit circle { fill: rgba(10, 9, 16, 0.9); stroke: var(--t2); }
  .exit rect { fill: rgba(10, 9, 16, 0.9); stroke: var(--t2); }
  .exit path { fill: none; stroke: var(--t2); stroke-width: 1.1; }
  .exit .home { stroke-dasharray: 3 4; }
  .legend { max-width: 1200px; display: grid; grid-template-columns: 1fr 1fr; gap: 0 30px; }
  .legend dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; align-content: start; }
  .legend dt { color: var(--t); }
  .legend dd { margin: 0; color: var(--t2); }
</style>

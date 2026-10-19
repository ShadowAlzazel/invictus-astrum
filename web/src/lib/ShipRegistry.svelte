<script>
  // The ship registry: every class in data/ships/classes, as the server reads and derives it.
  // Read-only; the server is the authority on every figure, and the map only lays them out.
  import { onMount } from 'svelte';
  import { api } from './api.js';
  import { unitSymbol } from './symbols.js';
  import { q, row } from './quantity.js';

  export let style;
  export let onback = () => {};

  let reg = null, cls = null, current = null, tier = 'rated', error = null;

  // Garden first, then the Old Forest; within each, by rate in the order the rules list them
  $: groups = reg ? group(reg) : [];
  function group(r) {
    const rates = [...Object.keys(r.rules.rates), null];
    const out = [];
    for (const [lid, lin] of Object.entries(r.rules.lineages)) {
      for (const rate of rates) {
        const list = r.classes.filter((c) => c.lineage === lid && (c.rate ?? null) === rate);
        if (list.length) out.push({ title: `${lin.label} · ${rate ? r.rules.rates[rate].label : 'Not yet rated'}`, list });
      }
    }
    return out;
  }

  async function open(id) {
    current = id;
    cls = await api.ship(id);
    const tiers = Object.keys(cls.aim.tiers);
    if (tiers.length && !tiers.includes(tier)) tier = tiers.includes('rated') ? 'rated' : tiers[0];
  }

  async function load() {
    try {
      reg = await api.ships();
      if (!current || !reg.classes.some((c) => c.id === current)) await open(reg.classes.find((c) => c.id === 'papilion')?.id ?? reg.classes[0]?.id);
      else await open(current);
      error = null;
    } catch (e) { error = 'The ship registry did not load. Is the server running?'; }
  }
  onMount(load);
  export function refresh() { load(); }

  // the class's own tactical symbol, drawn by the same code as the map's units
  function symbol(canvas, { sym, size }) {
    const draw = (p) => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2), w = size * 2.2, h = size * 1.7;
      canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      unitSymbol(ctx, style, { affiliation: 'friend', echelon: 'ship', unit_type: p.sym, callsign: '' }, w / 2, h / 2 + 3, { h: p.size, label: false });
    };
    draw({ sym, size });
    return { update: draw };
  }

  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    if (e.key === 'Escape') onback();
    const flat = groups.flatMap((g) => g.list), i = flat.findIndex((c) => c.id === current);
    if (e.key === 'ArrowDown' && flat.length) { e.preventDefault(); open(flat[(i + 1) % flat.length].id); }
    if (e.key === 'ArrowUp' && flat.length) { e.preventDefault(); open(flat[(i - 1 + flat.length) % flat.length].id); }
  }
  const tierLabel = (t) => reg?.rules.crew[t]?.label ?? t;
  const effectRows = (c) => c.reach;
</script>

<svelte:window on:keydown={key} />

<div class="screen" data-ui>
  <nav>
    <button class="back" on:click={onback}>◂ Menu</button>
    <h1>Ship registry</h1>
    {#if error}<p class="err">{error}</p>{/if}
    {#each groups as g}
      <h2>{g.title}</h2>
      {#each g.list as c (c.id)}
        <button class="item" class:on={c.id === current} on:click={() => open(c.id)}>
          {#if style}<canvas use:symbol={{ sym: c.symbol, size: 13 }}></canvas>{/if}
          <span class="nm">{c.name}</span>
          <span class="tm">{[c.terms.sail, c.terms.modern].filter(Boolean).join(' · ') || '—'}</span>
          {#if c.blanks}<span class="bl" title="figures not yet stated">{c.blanks}</span>{/if}
          {#if c.errors}<span class="ex">{c.errors} error{c.errors > 1 ? 's' : ''}</span>{/if}
        </button>
      {/each}
    {/each}
    <p class="foot">data/ships/ · ↑ ↓ choose · Esc back</p>
  </nav>

  {#if cls}
    <article>
      <header>
        {#if style}<canvas use:symbol={{ sym: cls.symbol, size: 26 }}></canvas>{/if}
        <div>
          <h1>{cls.name}</h1>
          {#if cls.genus || cls.epithet}
            <p class="bin">{cls.genus?.word ?? ''} <i>{cls.genus?.meaning ?? ''}</i> · {cls.epithet?.word ?? ''} <i>{cls.epithet?.meaning ?? ''}</i></p>
          {/if}
          <p class="sum">{cls.summary}</p>
        </div>
      </header>

      <section class="readers">
        {#each [['Sail reader', cls.terms.sail], ['Modern reader', cls.terms.modern], ['ARCVS reader', cls.terms.arcvs]] as [who, word]}
          <div><span>{who}</span><b class:blank={!word}>{word ?? '—'}</b></div>
        {/each}
      </section>

      <div class="cols">
        <section>
          <h2>Identity</h2>
          <dl>
            <dt>Lineage</dt><dd>{cls.lineage_rules.label ?? cls.lineage}</dd>
            <dt>Rate</dt><dd class:blank={!cls.rate}>{cls.rate_rules.label ?? '—'}</dd>
            {#if cls.derived.commanded_by}<dt>Commanded by</dt><dd>{cls.derived.commanded_by}</dd>{/if}
            {#if cls.rate_rules.hands}<dt>Hands</dt><dd>{cls.rate_rules.hands}</dd>{/if}
            {#if cls.old_rating}<dt>Old Forest rating</dt><dd class:blank={cls.old_rating === '—'}>{cls.old_rating}</dd>{/if}
            {#if cls.designation}<dt>Designation</dt><dd>{cls.designation}</dd>{/if}
            {#if cls.body}<dt>Body</dt><dd>{cls.body}</dd>{/if}
            {#if cls.places.length}<dt>Places</dt><dd>{cls.places.join(', ')}</dd>{/if}
            {#if cls.in_classis}<dt>In a Classis</dt><dd>{q(cls.in_classis)}{cls.in_classis.note ? ` (${cls.in_classis.note})` : ''}</dd>{/if}
            {#if cls.successor}<dt>Succeeded by</dt><dd><button class="link" on:click={() => open(cls.successor)}>{cls.successor}</button></dd>{/if}
            {#if cls.derived.successor_of}<dt>Successor of</dt><dd><button class="link" on:click={() => open(cls.derived.successor_of)}>{cls.derived.successor_of}</button></dd>{/if}
          </dl>
        </section>

        <section>
          <h2>Particulars</h2>
          {#if cls.hull.length}
            <dl>
              {#each cls.hull as r}<dt>{r.label}</dt><dd class:blank={r.blank}>{row(r)}</dd>{/each}
              {#if cls.derived.thrust_mn}<dt>Thrust</dt><dd class="der" title="mass × acceleration">~{Math.round(cls.derived.thrust_mn)} MN</dd>{/if}
            </dl>
          {:else}<p class="blank">No particulars stated yet.</p>{/if}
        </section>
      </div>

      {#if Object.keys(cls.aim.tiers).length}
        <section>
          <h2>Aim and reach <span class="sub">the beam is fixed by the ship; the aim is made by the crew</span></h2>
          <div class="tiers">
            {#each Object.entries(cls.aim.tiers) as [t, a]}
              <button class:on={t === tier} on:click={() => (tier = t)}>{tierLabel(t)} <i>{q(a, 'µrad')}</i></button>
            {/each}
            {#if cls.aim.demasted}<span class="dim">de-masted {q(cls.aim.demasted, 'µrad')}</span>{/if}
          </div>
          <table>
            <thead><tr><th>Effect</th><th>Beam carries</th><th>{tierLabel(tier)} crew reaches</th><th>Set by</th></tr></thead>
            <tbody>
              {#each effectRows(cls) as r}
                <tr>
                  <td>{r.label}</td>
                  <td>{r.beam === 'aim' ? 'past every wall' : q(r.beam, 'km')}</td>
                  <td class="num">{q(r.by_tier[tier]?.q, 'km')}</td>
                  <td class:aim={r.by_tier[tier]?.set_by === 'aim'}>{r.by_tier[tier]?.set_by ?? ''}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if cls.walls[tier]}
            <p class="dim">Walls at {tierLabel(tier).toLowerCase()} aim: citadel {q(cls.walls[tier].citadel, 'km')}, silhouette {q(cls.walls[tier].silhouette, 'km')}. Past a wall, salvos land less often, not never.</p>
          {/if}
        </section>
      {:else if cls.reach.length}
        <section>
          <h2>Reach</h2>
          <dl>{#each cls.reach as r}<dt>{r.label}</dt><dd>{q(r.beam, 'km')}</dd>{/each}</dl>
        </section>
      {/if}

      {#if cls.batteries.length}
        <section>
          <h2>Batteries</h2>
          {#each cls.batteries as b}
            <div class="bat">
              <h3>{b.label} <span class="dim">{b.component?.name ?? b.component_id}</span></h3>
              <dl>
                {#each b.figures as r}<dt>{r.label}</dt><dd class:blank={r.blank}>{row(r)}</dd>{/each}
                {#if b.component?.round}<dt>Round</dt><dd>{b.component.round}, {b.component.round_kg} kg at {b.component.velocity_kms} km/s</dd>{/if}
                {#if b.component?.energy_gev}<dt>Channel</dt><dd>{b.component.energy_gev} GeV</dd>{/if}
                {#if b.derived.round_mj}<dt>A round</dt><dd class="der" title="½mv²">{Math.round(b.derived.round_mj * 10) / 10} MJ</dd>{/if}
                {#if b.derived.broadside_gj}<dt>Full broadside</dt><dd class="der">{Math.round(b.derived.broadside_gj * 100) / 100} GJ</dd>{/if}
                {#if b.derived.channels_per_stack}<dt>Channels per stack</dt><dd class="der">{b.derived.channels_per_stack}</dd>{/if}
                {#if b.derived.rounds_per_s}<dt>Rate of fire</dt><dd class="der">{b.derived.rounds_per_s} rounds/s</dd>{/if}
                {#if b.magazine}<dt>Magazine</dt><dd>{Object.entries(b.magazine).map(([k, v]) => `${v.toLocaleString('en-US')} ${k}`).join(' · ')}</dd>{/if}
                {#each Object.entries(b.reach_km ?? {}) as [what, km]}<dt>{what}</dt><dd>{km.toLocaleString('en-US')} km</dd>{/each}
              </dl>
              {#if b.fire}<p class="dim">{b.fire}</p>{/if}
              {#if b.arrangement}<p class="dim">{b.arrangement}</p>{/if}
              {#if b.notes}<p class="dim">{b.notes}</p>{/if}
            </div>
          {/each}
        </section>
      {/if}

      {#if cls.point_defence.length}
        <section>
          <h2>Point defence</h2>
          <table>
            <thead><tr><th>Bearing</th><th>At</th><th>Kills</th></tr></thead>
            <tbody>
              {#each cls.point_defence as p}<tr><td>{p.bearing}</td><td>{p.at_km?.toLocaleString('en-US')} km</td><td class="num">{q(p.kills_per_s, '/s')}</td></tr>{/each}
            </tbody>
          </table>
        </section>
      {/if}

      {#each [['Endurance', cls.endurance], ['Tending', cls.tending], ['Combat', cls.combat]] as [title, rows]}
        {#if rows.length}
          <section><h2>{title}</h2><dl>{#each rows as r}<dt>{r.label}</dt><dd class:blank={r.blank}>{row(r)}</dd>{/each}</dl></section>
        {/if}
      {/each}

      {#if cls.sensors.length}
        <section><h2>Sensors</h2><dl>{#each cls.sensors as s}<dt>{s.what}</dt><dd>{s.reach}</dd>{/each}</dl></section>
      {/if}

      {#if Object.keys(cls.history).length}
        <section>
          <h2>History</h2>
          <dl>
            {#if cls.history.built_as}<dt>Built as</dt><dd>{cls.history.built_as}</dd>{/if}
            {#if cls.history.serves_as}<dt>Serves as</dt><dd>{cls.history.serves_as}</dd>{/if}
            {#if cls.history.refit}<dt>Refit</dt><dd>{cls.history.refit}</dd>{/if}
          </dl>
          {#each cls.history.notable ?? [] as n}<p class="dim">· {n}</p>{/each}
        </section>
      {/if}

      {#if cls.blanks.length}
        <section class="open">
          <h2>Left for the author</h2>
          <p>{cls.blanks.join(' · ')}</p>
        </section>
      {/if}
      {#each cls.findings as f}<p class="find {f.level}">{f.where}: {f.message}</p>{/each}
      <p class="foot">data/ships/classes/{cls.file} · figures marked est. are estimates in the class documents; ~ is about; derived values are dotted</p>
    </article>
  {/if}
</div>

<style>
  .screen { position: fixed; inset: 0; z-index: 25; display: grid; grid-template-columns: 340px 1fr; gap: 20px; padding: 20px;
            background: rgba(7, 5, 15, 0.72); backdrop-filter: blur(3px); }
  nav, article { background: var(--panel); border-left: 1px solid var(--violet); overflow: auto; padding: 16px 18px; }
  article { max-width: 980px; }
  h1 { font-family: var(--display); font-weight: 600; font-size: 22px; margin: 6px 0 10px; letter-spacing: 0.02em; }
  h2 { font-family: var(--display); font-weight: 400; font-size: 14px; color: var(--dim); margin: 0 0 8px; }
  h3 { font-family: var(--display); font-weight: 600; font-size: 14px; margin: 0 0 4px; }
  nav h2 { margin: 16px 0 4px; font-size: 12px; }
  button { background: none; border: 0; color: var(--dim); font: inherit; text-align: left; padding: 0; }
  button:hover { color: var(--ink); }
  .back { font-family: var(--display); }
  .item { display: grid; grid-template-columns: 30px 1fr auto; grid-template-rows: auto auto; column-gap: 8px; width: 100%;
          padding: 5px 6px; border-left: 1px solid transparent; align-items: center; }
  .item canvas { grid-row: span 2; }
  .item.on { border-left-color: var(--fuchsia); background: rgba(116, 51, 250, 0.08); }
  .nm { font-family: var(--display); font-size: 13px; color: var(--ink); }
  .tm { grid-column: 2; font-size: 10px; color: var(--dim); }
  .bl { grid-row: 1; grid-column: 3; font-size: 10px; color: #ffd27a; }
  .ex { grid-column: 3; font-size: 10px; color: #ff9fcf; }
  header { display: flex; gap: 16px; align-items: flex-start; }
  .bin { margin: 0; font-family: var(--display); font-size: 13px; color: var(--ink); }
  .bin i { color: var(--dim); font-style: normal; margin-right: 6px; }
  .sum { margin: 8px 0 0; color: var(--dim); max-width: 70ch; line-height: 1.45; }
  section { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--rule); }
  .readers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .readers span { display: block; color: var(--dim); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
  .readers b { font-family: var(--display); font-weight: 400; font-size: 15px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 0 28px; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin: 0; }
  dt { color: var(--dim); }
  dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
  .blank { color: #ffd27a; opacity: 0.85; }
  .der { border-bottom: 1px dotted var(--violet); }
  .sub { font-size: 11px; margin-left: 8px; }
  .tiers { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: baseline; margin-bottom: 8px; }
  .tiers button { font-family: var(--display); font-size: 13px; padding: 2px 0; }
  .tiers button.on { color: var(--ink); box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .tiers i { font-style: normal; font-family: var(--mono); font-size: 10px; color: var(--dim); }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; color: var(--dim); font-weight: 400; font-size: 11px; padding: 3px 8px 3px 0; border-bottom: 1px solid var(--rule); }
  td { padding: 3px 8px 3px 0; font-variant-numeric: tabular-nums; }
  td.num { text-align: right; }
  td.aim { color: var(--cyan, #9ff0ff); }
  .bat { margin: 10px 0 0; padding-left: 10px; border-left: 1px solid var(--rule); }
  .dim { color: var(--dim); font-size: 11px; margin: 4px 0 0; }
  .link { color: var(--violet); filter: brightness(1.5); }
  .open p { color: #ffe3a6; margin: 0; }
  .find { margin: 6px 0 0; font-size: 11px; }
  .find.error { color: #ff9fcf; }
  .find.warning { color: #ffe3a6; }
  .foot { color: var(--dim); font-size: 10px; margin: 16px 0 0; }
  .err { color: #ff9fcf; }
</style>

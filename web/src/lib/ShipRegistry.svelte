<script>
  // The ship registry: every class in data/ships/classes, as the server reads and derives it.
  // Read-only; the server is the authority on every figure, and this screen only lays them out.
  // Laid out in tabs down a right-hand rail: Overview, Drive, Armament, Systems, Lore, Open.
  import { onMount } from 'svelte';
  import { api } from './api.js';
  import { unitSymbol } from './symbols.js';
  import { q, row } from './quantity.js';

  export let style;
  export let onback = () => {};

  const TABS = [
    { id: 'overview', label: 'Overview', icon: 'overview' },
    { id: 'drive', label: 'Drive', icon: 'drive' },
    { id: 'armament', label: 'Armament', icon: 'armament' },
    { id: 'systems', label: 'Systems', icon: 'systems' },
    { id: 'lore', label: 'Lore', icon: 'lore' },
    { id: 'open', label: 'Open', icon: 'open' },
  ];
  let reg = null, cls = null, current = null, tier = 'rated', error = null, tab = 'overview', why = {}, mainEl;
  $: if (mainEl && (tab || current)) mainEl.scrollTo(0, 0);           // each tab and class opens at its top

  // Garden first, then the Old Forest; within each, by rate in the order the rules list them
  $: groups = reg ? group(reg) : [];
  $: flat = groups.flatMap((g) => g.list);
  function group(r) {
    const rates = [...Object.keys(r.rules.rates), null];
    const out = [];
    for (const [lid, lin] of Object.entries(r.rules.lineages)) {
      for (const rate of rates) {
        const list = r.classes.filter((c) => c.lineage === lid && (c.rate ?? null) === rate);
        if (list.length) out.push({ title: lin.label, first: !out.some((g) => g.lineage === lid), lineage: lid,
                                    sub: rate ? r.rules.rates[rate].label : 'Not yet rated', list });
      }
    }
    return out;
  }

  async function open(id) {
    if (!id) return;
    current = id;
    cls = await api.ship(id);
    why = {};
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
  function symbol(canvas, { sym, size, color }) {
    const draw = (p) => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2), w = p.size * 2.2, h = p.size * 1.7;
      canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const st = p.color ? { ...style, affiliation: { ...style.affiliation, friend: { ...style.affiliation.friend, color: p.color } } } : style;
      unitSymbol(ctx, st, { affiliation: 'friend', echelon: 'ship', unit_type: p.sym, callsign: '' }, w / 2, h / 2 + 3, { h: p.size, label: false });
    };
    draw({ sym, size, color });
    return { update: draw };
  }

  const step = (k) => { const i = flat.findIndex((c) => c.id === current); if (flat.length) open(flat[(i + k + flat.length) % flat.length].id); };
  const stepTab = (k) => { const i = TABS.findIndex((t) => t.id === tab); tab = TABS[(i + k + TABS.length) % TABS.length].id; };
  function key(e) {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    if (e.key === 'Escape') onback();
    if (e.key === 'ArrowDown' || e.key === 'e' || e.key === 'E') { e.preventDefault(); step(1); }
    if (e.key === 'ArrowUp' || e.key === 'q' || e.key === 'Q') { e.preventDefault(); step(-1); }
    if (e.key === 'ArrowRight') { e.preventDefault(); stepTab(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); stepTab(-1); }
    const n = Number(e.key);
    if (n >= 1 && n <= TABS.length) tab = TABS[n - 1].id;
  }

  // ---- reading figures ------------------------------------------------------------------------
  const tierLabel = (t) => reg?.rules.crew[t]?.label ?? t;
  const v = (x) => (x && x.lo != null ? (x.lo + x.hi) / 2 : null);
  const num = (x, d = 0) => (x == null || Number.isNaN(x) ? '—' : Number(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const g3 = (x) => (x && x.lo != null ? (x.lo === x.hi ? x.lo.toFixed(3) : `${x.lo.toFixed(3)}–${x.hi.toFixed(3)}`) : '—');
  const scale = (x, k) => (x && x.lo != null ? { ...x, lo: x.lo * k, hi: x.hi * k } : x);
  const loadName = (r) => `${r.load || 'hull'}, tanks ${r.tanks}`;
  const hullRow = (k) => cls?.hull.find((r) => r.key === k);
  const pickNamed = (r, prefer = ['full', 'spread', 'loaded']) => {
    if (!r) return null;
    if (r.q) return r.q;
    if (r.named) { const k = prefer.find((p) => r.named[p]) ?? Object.keys(r.named)[0]; return r.named[k]; }
    return null;
  };
  const sci = (x) => (x == null ? '—' : x < 1e-3 ? x.toExponential(2).replace('e-', ' × 10⁻').replace(/(\d+)$/, (m) => [...m].map((c) => '⁰¹²³⁴⁵⁶⁷⁸⁹'[c]).join('')) : String(x));
  const toggle = (k) => (why = { ...why, [k]: !why[k] });

  $: d = cls?.drive ?? null;
  $: pat = d?.pattern ?? null;
  // the load the drive is judged at: the heaviest, tanks full
  $: heavy = d ? d.cruise?.heaviest ?? [...d.loads].sort((a, b) => (v(b.mass_t) ?? 0) - (v(a.mass_t) ?? 0))[0] ?? null : null;
  $: heavyDry = d && heavy ? d.loads.find((r) => r.load === heavy.load && r.tanks === 'dry') : null;

  // the Overview: what the hull is, and what the simulation reads from it
  $: lightDry = d ? [...d.loads].filter((r) => r.tanks === 'dry').sort((a, b) => (v(a.mass_t) ?? 0) - (v(b.mass_t) ?? 0))[0] ?? null : null;
  $: crew = cls ? v(pickNamed(hullRow('complement'))) : null;
  $: attrs = cls ? [
    { icon: 'length', label: 'Length', value: q(pickNamed(hullRow('length_m'))), unit: 'm' },
    { icon: 'mass', label: 'Mass', value: heavy ? num(v(heavy.mass_t)) : q(pickNamed(hullRow('mass_t'))), unit: 't', sub: heavy ? 'full load' : hullRow('mass_t')?.named ? 'full' : '' },
    { icon: 'crew', label: 'Crew', value: crew != null ? num(crew) : '—', unit: 'hands' },
    { icon: 'shield', label: 'Citadel', value: (() => { const r = hullRow('protection_kgm2'); const x = r?.named?.citadel ?? r?.q; return x ? q(x) : '—'; })(), unit: 'kg/m²' },
  ] : [];
  // point defence, at each range the best the canon states
  const pdSummary = (pd) => {
    const best = {};
    for (const p of pd) if (p.at_km != null && p.kills_per_s) best[p.at_km] = Math.max(best[p.at_km] ?? 0, v(p.kills_per_s));
    return Object.entries(best).sort((a, b) => a[0] - b[0]).map(([km, k]) => `${num(k, k < 10 ? 1 : 0)}/s at ${num(+km)} km`).join(' · ');
  };
  const simValue = (x, unit, digits) => (x && x.lo != null ? (digits != null ? `${num(v(x), digits)} ${unit}` : q(x, unit)) : '—');
  $: simPrime = cls ? [
    { icon: 'thrust', label: 'Thrust', value: d ? simValue(d.thrust_mn, 'MN', 1) : '—' },
    { icon: 'dv', label: 'Δv', sub: 'full load', value: heavy?.dv_kms ? simValue(heavy.dv_kms, 'km/s', 0) : '—' },
    { icon: 'accel', label: 'Most acceleration', sub: 'full load', value: heavy?.accel_g ? `${g3(heavy.accel_g)} g` : '—' },
  ] : [];
  $: simGroups = cls ? [
    { title: 'Movement', rows: d ? [
      ['Mass, tanks full / dry', heavy && heavyDry ? `${num(v(heavy.mass_t))} / ${num(v(heavyDry.mass_t))} t` : '—'],
      ['Propellant', simValue(d.propellant_t, 't', 0)],
      ['Exhaust velocity', simValue(d.exhaust_kms, 'km/s', 0)],
      ['Most acceleration, light and dry', lightDry?.accel_g ? `${g3(lightDry.accel_g)} g` : '—'],
      ['Cruise band', d.cruise ? `${d.cruise.band_g.lo}–${d.cruise.band_g.hi} g · ${d.cruise.reaches_top ? 'holds' : d.cruise.holds ? 'holds the floor' : 'short'}` : '—', d.cruise && !d.cruise.holds],
    ] : [['Drive', 'not yet stated']] },
    { title: 'Heat and signature', rows: [
      ...(d ? [['Plume', simValue(d.jet_pw, 'PW', 2)], ['Pulse rate', simValue(d.pulse_rate_hz, 'Hz', 1)],
               ['Hull leak, flat out', d.heat ? `${num(v(d.heat.leak_gw) * 1e3, 0)} MW` : '—']] : []),
      ['Manes reject', d?.heat?.mane_gw ? q(d.heat.mane_gw, 'GW') : '—', d?.heat && d.heat.steady === false],
      ['Thermal store', (() => { const r = cls.endurance.find((x) => x.key === 'thermal_store_tj'); return r ? row(r) : '—'; })()],
    ] },
    { title: 'Combat', rows: [
      ['Aim, rated crew', cls.aim.tiers.rated ? q(cls.aim.tiers.rated, 'µrad') : '—'],
      ['Walls, rated: citadel / silhouette', cls.walls.rated ? `${num(v(cls.walls.rated.citadel))} / ${num(v(cls.walls.rated.silhouette))} km` : '—'],
      ['Point defence', cls.point_defence.length ? pdSummary(cls.point_defence) || '—' : '—'],
      ['Protection', hullRow('protection_kgm2') ? row(hullRow('protection_kgm2')) : '—'],
    ] },
  ] : [];
  // the armament: engagement range first, then how many
  const engage = (b) => (b.engage?.q ? `${num(v(b.engage.q))}` : '—');
  const KIND_MARK = { 'spinal-channel': 'SPN', gun: 'GUN', panel: 'OPT', dome: 'DOM', strip: 'STR', 'missile-cell': 'MSL', tube: 'TUB', telescope: 'TEL', sensor: 'SNS' };
  $: focusBat = cls?.batteries.find((b) => b.focus) ?? null;

  // the Drive tab: each figure the simulation reads, and how the technical values give it
  $: primary = d ? [
    { k: 'thrust', icon: 'thrust', label: 'Thrust', value: q(d.thrust_mn, 'MN'), typed: false,
      why: d.thrust_sized_g ? `sized to ${d.thrust_sized_g.lo} g at full load: ${d.thrust_sized_g.lo} × 9.80665 m/s² × ${num(v(heavy?.mass_t))} t`
        : d.thrust_mn ? `typed on drives.toml [drive.${d.module_id}]${d.count > 1 ? ` × ${d.count} modules` : ''}` : 'not yet stated: give the drive thrust_mn, or the class sized_g' },
    { k: 've', icon: 'exhaust', label: 'Exhaust velocity', value: q(d.exhaust_kms, 'km/s'), typed: d.typed.includes('exhaust_kms'),
      why: pat ? (d.typed.includes('exhaust_kms') ? `typed on the drive; the pattern gives ${num(pat.exhaust_kms)} km/s` :
        `ceiling ${num(pat.ceiling_kms)} km/s × √(k ${pat.k.toFixed(3)} × X ${pat.x.toFixed(4)}).  k = φ ${pat.phi} × η ${pat.eta}.  X = f(1 − c·f²)(1 + capture·n·(1 − f)) = ${pat.f} × (1 − ${pat.tamper.confinement} × ${pat.f}²) × (1 + ${pat.tamper.capture} × ${pat.n_frac} × ${(1 - pat.f).toFixed(2)})`) : 'typed on the drive' },
    { k: 'dv', icon: 'dv', label: 'Δv, full load', value: heavy?.dv_kms ? q(heavy.dv_kms, 'km/s') : '—',
      why: heavy?.dv_kms ? `vₑ × ln(wet ÷ dry) = ${num(v(d.exhaust_kms))} × ln(${num(v(heavy.mass_t))} ÷ ${num(v(heavyDry?.mass_t))})${d.dv_target_kms ? `; the propellant is what holds ${num(v(d.dv_target_kms))} km/s` : ''}` : 'needs propellant' },
    { k: 'acc', icon: 'accel', label: 'Most acceleration, full load', value: heavy?.accel_g ? `${g3(heavy.accel_g)} g` : '—',
      why: heavy?.accel_ms2 ? `thrust ÷ mass = ${num(v(d.thrust_mn), 1)} MN ÷ ${num(v(heavy.mass_t))} t = ${num(v(heavy.accel_ms2), 3)} m/s²` : '' },
  ] : [];
  $: other = d ? [
    { k: 'read', label: 'Hull masses read', value: d.hull_mass === 'wet' ? 'tanks full' : 'tanks dry', why: 'what the class\'s hull.mass_t means ([drive] hull_mass)' },
    ...(d.dv_target_kms ? [{ k: 'holds', label: 'Propellant holds', value: q(d.dv_target_kms, 'km/s'), why: 'the class\'s [drive] dv_kms, at the heaviest load' }] : []),
    { k: 'prop', label: 'Propellant, tanks full', value: q(d.propellant_t, 't'),
      why: d.dv_target_kms ? `the tank that holds ${num(v(d.dv_target_kms))} km/s at the heaviest load: ${d.hull_mass === 'wet' ? 'M × (1 − e^(−Δv / vₑ))' : 'M × (e^(Δv / vₑ) − 1)'}` : 'typed on the class' },
    ...(d.stores ? [
      { k: 'fuel', label: 'Capsule fuel', value: `${num(d.stores.fuel_t)} t`, sub: Object.entries(d.stores.split_t).map(([n, t]) => `${n} ${num(t)} t`).join(' · '), why: `f ${pat.f} of the propellant; split by mass from [fuel.${pat.fuel.id}]` },
      { k: 'tamper', label: 'Tamper', value: `${num(d.stores.tamper_t)} t`, sub: pat.tamper.name, why: 'the rest of the propellant' },
    ] : []),
    { k: 'flow', label: 'Mass flow, flat out', value: q(d.mass_flow_kgs, 'kg/s'), why: 'thrust ÷ exhaust velocity' },
    { k: 'jet', label: 'Jet power', value: q(d.jet_pw, 'PW'), why: '½ × thrust × exhaust velocity: the plume, constant while she burns' },
    { k: 'held', label: 'Full burn, held', value: d.held_burn_h ? q(scale(d.held_burn_h, 1 / 24), 'days') : '—', why: 'Δv ÷ the full-load acceleration, held by throttling as she lightens' },
    { k: 'flat', label: 'Tanks last, flat out', value: d.full_burn_h ? q(scale(d.full_burn_h, 1 / 24), 'days') : '—', why: 'propellant ÷ mass flow, at full thrust throughout' },
    { k: 'energy', label: 'Jet energy, whole tank', value: d.jet_energy_zj ? `${q(d.jet_energy_zj, 'ZJ')}` : '—', why: '½ × propellant × vₑ²' },
    { k: 'rate', label: 'Ship pulse rate', value: q(d.pulse_rate_hz, 'Hz'),
      why: d.block ? `${d.block.engines} engines × ${d.block.hz} Hz, phased: the plume stays constant` : 'typed on the drive' },
    ...(d.block ? [
      { k: 'eng', label: 'Per engine', value: `${num(d.block.engine_thrust_mn, 1)} MN`, sub: `${num(d.block.engine_power_tw, 1)} TW`, why: 'thrust and jet power ÷ engines' },
      { k: 'pellet', label: 'Pellet', value: `${num(d.block.pellet_kg, 3)} kg`, why: 'mass flow ÷ ship pulse rate' },
      { k: 'pulse', label: 'Energy per pulse', value: `${num(d.block.pulse_tj, 1)} TJ`, sub: `${num(d.block.pulse_t_tnt)} t TNT`, why: 'jet power ÷ ship pulse rate' },
      { k: 'pulses', label: 'Pulses per engine, whole tank', value: num(d.block.pulses_per_engine), why: 'held burn × reactions per engine per second' },
    ] : []),
    ...(d.stores?.pbar_mg ? [
      { k: 'pbar', label: 'Antiprotons', value: `${num(d.stores.pbar_mg, 3)} mg`, sub: `${num(d.stores.bunker_share * 100, 1)}% of the bunker`, why: `capsule fuel × ${pat.fuel.pbar_mg_per_t} mg per tonne` },
      { k: 'burns', label: 'Burns per bunker', value: num(d.stores.burns_per_bunker, 2), why: `the ${d.stores.bunker_mg} mg standard bunker ÷ antiprotons per tank` },
      { k: 'vol', label: 'Tank volume', value: `${num(d.stores.volume_m3)} m³`, why: `fuel at ${pat.fuel.density_tm3} t/m³, tamper at ${pat.tamper.density_tm3} t/m³` },
    ] : []),
    ...(d.heat ? [
      { k: 'leak', label: 'Hull leak, flat out', value: `${num(v(d.heat.leak_gw) * 1e3, 1)} MW`, sub: `share ${sci(v(d.hull_heat_fraction))}`, why: 'jet power × the mark\'s hull heat share' },
      ...(d.heat.mane_gw ? [
        { k: 'mane', label: 'Mane capacity', value: q(d.heat.mane_gw, 'GW'), sub: d.heat.steady ? 'holds' : 'over', bad: !d.heat.steady, why: 'what the manes reject while she burns ([endurance] mane_gw)' },
        { k: 'maxleak', label: 'Most hull heat share', value: sci(v(d.heat.max_fraction)), why: 'mane capacity ÷ jet power' },
      ] : []),
      { k: 'fills', label: 'Store full after', value: d.heat.fills_h ? q(d.heat.fills_h, 'h') : d.heat.steady ? 'never: the manes keep up' : '—',
        why: d.heat.mane_gw ? 'thermal store ÷ (leak − mane)' : 'thermal store ÷ leak' },
    ] : []),
  ] : [];

  // ---- icons: one stroke family, drawn in a 24 box -----------------------------------------------
  const ICONS = {
    overview: 'M4 5h16v14H4zM4 9h16M9 9v10',
    drive: 'M3 12h7l2-4 2 8 2-4h5M3 7v10',
    armament: 'M4 20L18 6M14 4l6 6M6 14l4 4M4 4l4 4',
    systems: 'M12 3v3M12 18v3M3 12h3M18 12h3M7 7l2 2M15 15l2 2M7 17l2-2M15 9l2-2M12 9a3 3 0 100 6 3 3 0 000-6z',
    lore: 'M5 4h10l4 4v12H5zM15 4v4h4M8 12h8M8 16h6',
    open: 'M12 4l9 16H3zM12 10v4M12 17v.5',
    length: 'M3 9h18v6H3zM7 9v3M11 9v3M15 9v3M19 9v3',
    mass: 'M8 8h8l3 12H5zM10 8a2 2 0 114 0',
    accel: 'M4 6l6 6-6 6M12 6l6 6-6 6',
    dv: 'M12 4l9 16H3z',
    thrust: 'M12 3l4 8h-3v10h-2V11H8z',
    exhaust: 'M3 12h12M11 7l5 5-5 5M18 7v10',
    crew: 'M12 4a4 4 0 100 8 4 4 0 000-8zM4 21c1-4 4-6 8-6s7 2 8 6',
    shield: 'M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6z',
    heat: 'M12 3c3 4 5 6 5 10a5 5 0 01-10 0c0-2 1-3 2-5 0 2 1 3 2 3 0-3 0-5 1-8z',
  };
</script>

<svelte:window on:keydown={key} />

<div class="reg" data-ui>
  <header class="top">
    <svg class="logo" viewBox="0 0 40 32" aria-hidden="true"><path d="M20 2l9 9-9 9-9-9zM6 18l7 7-7 7M34 18l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.4" /></svg>
    <div class="crumb">
      <p><span class="sl">//</span> Ship registry <span class="sl">/</span> {cls?.name ?? '…'} <span class="sl">/</span> <b>{TABS.find((t) => t.id === tab).label}</b></p>
      <div class="code"><i class="bars"></i><span>ARCVS · {cls?.designation ?? 'CLASSIS'} · {cls?.file ?? ''}</span></div>
    </div>
    <button class="close" on:click={onback} title="Back to the menu (Esc)"><svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17" /></svg></button>
  </header>

  <aside class="roster">
    {#if error}<p class="err">{error}</p>{/if}
    {#each groups as g}
      {#if g.first}<h3>{g.title}</h3>{/if}
      <h4>{g.sub}</h4>
      {#each g.list as c (c.id)}
        <button class="ship" class:on={c.id === current} on:click={() => open(c.id)}>
          {#if style}<canvas use:symbol={{ sym: c.symbol, size: 12, color: c.id === current ? '#9ff0ff' : null }}></canvas>{/if}
          <span class="nm">{c.name}</span>
          <span class="tm">{[c.terms.sail, c.terms.modern].filter(Boolean).join(' · ') || '—'}</span>
          {#if c.errors}<span class="flag ex">{c.errors}</span>{:else if c.blanks}<span class="flag" title="figures not yet stated">{c.blanks}</span>{/if}
        </button>
      {/each}
    {/each}
    <p class="keys"><kbd>Q</kbd><kbd>E</kbd> class · <kbd>1</kbd>–<kbd>6</kbd> tab · <kbd>Esc</kbd> back</p>
  </aside>

  <nav class="rail">
    {#each TABS as t, i}
      <button class:on={tab === t.id} on:click={() => (tab = t.id)} title="{t.label} ({i + 1})">
        <i class="no">0{i + 1}</i>
        <svg viewBox="0 0 24 24"><path d={ICONS[t.icon]} /></svg>
        <span>{t.label}</span>
        {#if t.id === 'open' && cls && (cls.blanks.length || cls.findings.length)}<b class="dot">{cls.blanks.length + cls.findings.length}</b>{/if}
      </button>
    {/each}
  </nav>

  <main bind:this={mainEl}>
    {#if cls}
      <!-- ============================== OVERVIEW ============================== -->
      {#if tab === 'overview'}
        <div class="ov">
          <section class="ov-l">
            <div class="ident">
              <div class="sym">{#if style}<canvas use:symbol={{ sym: cls.symbol, size: 30 }}></canvas>{/if}</div>
              <div>
                <h1>{cls.name}</h1>
                {#if cls.genus || cls.epithet}
                  <p class="bin"><b>{cls.genus?.word ?? ''}</b> {cls.genus?.meaning ?? ''} <span>·</span> <b>{cls.epithet?.word ?? ''}</b> {cls.epithet?.meaning ?? ''}</p>
                {/if}
              </div>
            </div>
            <div class="chips">
              <span>{cls.lineage_rules.label ?? cls.lineage}</span>
              <span class:blank={!cls.rate}>{cls.rate_rules.label ?? 'Not yet rated'}</span>
              {#if cls.terms.sail}<span>{cls.terms.sail}</span>{/if}
              {#if cls.terms.modern}<span>{cls.terms.modern}</span>{/if}
            </div>
            {#if cls.summary}<p class="summary">{cls.summary}</p>{/if}

            <div class="bar"><span>Particulars</span><button on:click={() => (tab = 'systems')} title="All particulars">•••</button></div>
            <div class="attrs">
              {#each attrs as a}
                <div class="attr">
                  <svg viewBox="0 0 24 24"><path d={ICONS[a.icon]} /></svg>
                  <span class="lb">{a.label}</span>
                  <b class:blank={a.value === '—'}>{a.value}</b>
                  <span class="un">{a.value === '—' ? '' : a.unit}{a.sub ? ` · ${a.sub}` : ''}</span>
                </div>
              {/each}
            </div>

            {#if cls.batteries.length}
              <div class="bar"><span>Armament</span><button on:click={() => (tab = 'armament')} title="Armament">•••</button></div>
              <div class="arms">
                {#each cls.batteries as b}
                  <button class="arm" class:focus={b.focus} on:click={() => (tab = 'armament')} title={b.engage ? `engages at ${engage(b)} km: ${b.engage.how}` : 'engagement range not yet stated'}>
                    <span class="hex"><span>{KIND_MARK[b.component?.kind] ?? 'BAT'}</span></span>
                    <span class="rng"><b class:blank={!b.engage}>{engage(b)}</b>{#if b.engage}<small>km</small>{/if}</span>
                    <span class="ct">{b.count != null ? `× ${b.count}` : '× —'}</span>
                    <span class="lb">{b.label}</span>
                  </button>
                {/each}
              </div>
            {/if}
            {#if d}
              <div class="bar"><span>Drive</span><button on:click={() => (tab = 'drive')} title="Drive">•••</button></div>
              <div class="chips drive">
                <span class="hl">{pat ? `${pat.mark_name} ${pat.mark_label ?? ''}` : d.module.name}</span>
                {#if pat}<span>{pat.mix_name}</span>{/if}
                {#if pat?.block_name}<span>{pat.block_name}</span>{/if}
              </div>
            {/if}
          </section>

          <section class="ov-r">
            <h2 class="uline">Simulation</h2>
            {#each simPrime as s}
              <div class="prim">
                <svg viewBox="0 0 24 24"><path d={ICONS[s.icon]} /></svg>
                <span class="lb">{s.label}{#if s.sub}<i class="lbs">{s.sub}</i>{/if}</span>
                <b class:blank={s.value === '—'}>{s.value}</b>
              </div>
            {/each}
            {#each simGroups as g}
              <h2 class="caps">{g.title}</h2>
              {#each g.rows as [label, value, bad], i}
                <div class="oth slim" class:band={i % 2}><span class="lb">{label}</span><b class:blank={value === '—'} class:bad>{value}</b></div>
              {/each}
            {/each}
          </section>
        </div>

      <!-- ============================== DRIVE ============================== -->
      {:else if tab === 'drive'}
        {#if !d}
          <p class="empty">No drive yet. Give the class a <code>[drive]</code> that names a module in <code>data/ships/drives.toml</code>.</p>
        {:else}
          <div class="st">
            <section class="cards">
              <h2 class="uline">Pattern</h2>
              {#if pat}
                <div class="card main"><p class="tag">Drive pattern</p><p class="big">{pat.mark_name}</p><p class="ft">{pat.mark_label ?? ''}</p></div>
                <div class="card"><p class="tag">Stores</p><p class="big">f {pat.f}</p><p class="ft">{pat.mix_name}</p></div>
                {#if d.block}<div class="card"><p class="tag">Engines</p><p class="big">{d.block.engines} <small>@ {d.block.hz} Hz</small></p><p class="ft">{pat.block_name}</p></div>{/if}
                <div class="card"><p class="tag">Fuel</p><p class="big">{pat.fuel.name.split(' ')[0]}</p><p class="ft">in {pat.tamper.name.toLowerCase()}</p></div>
              {:else}
                <div class="card main"><p class="tag">Typed drive</p><p class="big">{d.module.name}</p><p class="ft">figures typed on the drive</p></div>
              {/if}
            </section>

            <section class="stats">
              {#each primary as s}
                <div class="prim">
                  <svg viewBox="0 0 24 24"><path d={ICONS[s.icon]} /></svg>
                  <span class="lb">{s.label}{#if s.typed}<i class="typed">typed</i>{/if}</span>
                  <b class:blank={s.value === '—'}>{s.value}</b>
                  <button class="q" class:on={why[s.k]} on:click={() => toggle(s.k)} title="How this is worked out">?</button>
                </div>
                {#if why[s.k]}<p class="why">{s.why}</p>{/if}
              {/each}
              <h2 class="caps">Other stats</h2>
              {#each other as s, i}
                <div class="oth" class:band={i % 2}>
                  <span class="lb">{s.label}</span>
                  <span class="sub">{s.sub ?? ''}</span>
                  <b class:blank={s.value === '—'} class:bad={s.bad}>{s.value}</b>
                  <button class="q" class:on={why[s.k]} on:click={() => toggle(s.k)} title="How this is worked out">?</button>
                </div>
                {#if why[s.k]}<p class="why">{s.why}</p>{/if}
              {/each}
            </section>
          </div>

          {#if d.loads.length}
            <h2 class="caps">By load</h2>
            <table>
              <thead><tr><th>Load</th><th class="r">Mass</th><th class="r">Most acceleration</th><th class="r"></th><th class="r">Δv in the tanks</th><th class="r">Per 100 km/s</th></tr></thead>
              <tbody>
                {#each d.loads as r, i}
                  <tr class:band={i % 2} class:hl={r === heavy}>
                    <td>{loadName(r)}</td>
                    <td class="r">{q(r.mass_t, 't')}</td>
                    <td class="r strong">{g3(r.accel_g)} g</td>
                    <td class="r dim">{q(r.accel_ms2, 'm/s²')}</td>
                    <td class="r">{r.dv_kms ? q(r.dv_kms, 'km/s') : ''}</td>
                    <td class="r">{r.per_100kms_t ? q(r.per_100kms_t, 't') : ''}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
          {#if d.cruise}
            {@const c = d.cruise}
            <p class="verdict" class:short={!c.holds}>
              <b>Cruise {c.band_g.lo}–{c.band_g.hi} g</b>
              {#if c.reaches_top}holds the whole band at her heaviest ({loadName(c.heaviest)}).
              {:else if c.holds}holds the floor at her heaviest ({loadName(c.heaviest)}, {g3(c.heaviest.accel_g)} g), not the top.
              {:else}at her heaviest ({loadName(c.heaviest)}) she makes only {g3(c.heaviest.accel_g)} g.{/if}
              The band there takes {q(c.thrust_needed_mn, 'MN')}.
            </p>
          {/if}

          {#if d.ladder.length}
            <h2 class="caps">Mark ladder <span class="sub">every mark on this hull and mix · A: the same tank · B: the tank that holds {num(d.ladder_dv_kms)} km/s</span></h2>
            <table>
              <thead><tr><th>Mark</th><th class="r">k</th><th class="r">Exhaust</th><th class="r">A: Δv</th><th class="r">B: propellant</th><th class="r">B: dry</th></tr></thead>
              <tbody>
                {#each d.ladder as r, i}
                  <tr class:band={i % 2} class:cur={r.current}>
                    <td>{#if r.current}<i class="pip"></i>{/if}<b>{r.name}</b> <span class="dim">{r.label ?? ''}</span></td>
                    <td class="r">{r.k.toFixed(3)}</td>
                    <td class="r">{num(r.exhaust_kms)} km/s</td>
                    <td class="r strong">{num(r.dv_same_tank_kms)} km/s</td>
                    <td class="r">{num(r.propellant_held_t)} t</td>
                    <td class="r dim">{num(r.dry_held_t)} t</td>
                  </tr>
                {/each}
              </tbody>
            </table>
            <p class="note">Refit by changing <code>mark</code> on <code>[drive.{d.module_id}]</code>; preview any mix or block with <code>python tools/drive_bench.py {cls.id} --mark mk3</code>.</p>
          {/if}
        {/if}

      <!-- ============================== ARMAMENT ============================== -->
      {:else if tab === 'armament'}
        {#if Object.keys(cls.aim.tiers).length}
          <h2 class="caps">Aim and reach <span class="sub">the beam is fixed by the ship; the aim is made by the crew</span></h2>
          <div class="seg">
            {#each Object.entries(cls.aim.tiers) as [t, a]}
              <button class:on={t === tier} on:click={() => (tier = t)}>{tierLabel(t)} <i>{q(a, 'µrad')}</i></button>
            {/each}
            {#if cls.aim.demasted}<span class="dim">de-masted {q(cls.aim.demasted, 'µrad')}</span>{/if}
          </div>
          <table>
            <thead><tr><th>Effect</th><th class="r">Beam carries</th><th class="r">{tierLabel(tier)} crew reaches</th><th>Set by</th></tr></thead>
            <tbody>
              {#each cls.reach as r, i}
                <tr class:band={i % 2}>
                  <td>{r.label}</td>
                  <td class="r">{r.beam === 'aim' ? 'past every wall' : q(r.beam, 'km')}</td>
                  <td class="r strong">{q(r.by_tier[tier]?.q, 'km')}</td>
                  <td class:aim={r.by_tier[tier]?.set_by === 'aim'}>{r.by_tier[tier]?.set_by ?? ''}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if cls.walls[tier]}
            <p class="note">Walls at {tierLabel(tier).toLowerCase()} aim: citadel {q(cls.walls[tier].citadel, 'km')}, silhouette {q(cls.walls[tier].silhouette, 'km')}. Past a wall, salvos land less often, not never.</p>
          {/if}
        {:else if cls.reach.length}
          <h2 class="caps">Reach</h2>
          <dl class="rows">{#each cls.reach as r}<dt>{r.label}</dt><dd>{q(r.beam, 'km')}</dd>{/each}</dl>
        {/if}

        {#if cls.batteries.length}
          <h2 class="caps">Batteries <span class="sub">engagement range first; the focus is the battery her tactics are built around</span></h2>
          <div class="bats">
            {#each [...cls.batteries].sort((a, b) => b.focus - a.focus) as b}
              <div class="bat" class:focus={b.focus}>
                <header>
                  <span class="hex"><span>{KIND_MARK[b.component?.kind] ?? 'BAT'}</span></span>
                  <div><p class="tag">{b.focus ? 'Focus' : 'Battery'}</p><h3>{b.label}</h3><span>{b.component?.name ?? b.component_id}</span></div>
                  <div class="eng"><b class:blank={!b.engage}>{engage(b)}</b>{#if b.engage}<small>km</small>{/if}<i>{b.engage?.how ?? 'engagement range not yet stated'}</i></div>
                </header>
                <dl class="rows small">
                  {#each b.figures as r}<dt>{r.label}</dt><dd class:blank={r.blank}>{row(r)}</dd>{/each}
                  {#if b.component?.round}<dt>Round</dt><dd>{b.component.round}, {b.component.round_kg} kg at {b.component.velocity_kms} km/s</dd>{/if}
                  {#if b.component?.energy_gev}<dt>Channel</dt><dd>{b.component.energy_gev} GeV</dd>{/if}
                  {#if b.derived.round_mj}<dt>A round</dt><dd>{num(b.derived.round_mj, 1)} MJ</dd>{/if}
                  {#if b.derived.broadside_gj}<dt>Full broadside</dt><dd>{num(b.derived.broadside_gj, 2)} GJ</dd>{/if}
                  {#if b.derived.channels_per_stack}<dt>Channels per stack</dt><dd>{b.derived.channels_per_stack}</dd>{/if}
                  {#if b.derived.rounds_per_s}<dt>Rate of fire</dt><dd>{b.derived.rounds_per_s} rounds/s</dd>{/if}
                  {#if b.magazine}<dt>Magazine</dt><dd>{Object.entries(b.magazine).map(([k, x]) => `${num(x)} ${k}`).join(' · ')}</dd>{/if}
                  {#each Object.entries(b.reach_km ?? {}) as [what, km]}<dt>{what}</dt><dd>{num(km)} km</dd>{/each}
                </dl>
                {#if b.fire}<p class="note">{b.fire}</p>{/if}
                {#if b.arrangement}<p class="note">{b.arrangement}</p>{/if}
                {#if b.notes}<p class="note">{b.notes}</p>{/if}
              </div>
            {/each}
          </div>
        {/if}

        {#if cls.point_defence.length}
          <h2 class="caps">Point defence</h2>
          <table>
            <thead><tr><th>Bearing</th><th class="r">At</th><th class="r">Kills</th></tr></thead>
            <tbody>
              {#each cls.point_defence as p, i}<tr class:band={i % 2}><td>{p.bearing}</td><td class="r">{num(p.at_km)} km</td><td class="r strong">{q(p.kills_per_s, '/s')}</td></tr>{/each}
            </tbody>
          </table>
        {/if}
        {#if !cls.batteries.length && !cls.reach.length && !cls.point_defence.length}<p class="empty">No armament stated yet.</p>{/if}

      <!-- ============================== SYSTEMS ============================== -->
      {:else if tab === 'systems'}
        <div class="two">
          <section>
            <h2 class="caps">Particulars</h2>
            {#if cls.hull.length}
              <dl class="rows">{#each cls.hull as r}<dt>{r.label}</dt><dd class:blank={r.blank}>{row(r)}</dd>{/each}</dl>
            {:else}<p class="empty">No particulars stated yet.</p>{/if}
          </section>
          <section>
            {#each [['Endurance', cls.endurance], ['Combat', cls.combat], ['Tending', cls.tending]] as [title, rows]}
              {#if rows.length}
                <h2 class="caps">{title}</h2>
                <dl class="rows">{#each rows as r}<dt>{r.label}</dt><dd class:blank={r.blank}>{row(r)}</dd>{/each}</dl>
              {/if}
            {/each}
            {#if cls.sensors.length}
              <h2 class="caps">Sensors</h2>
              <dl class="rows">{#each cls.sensors as s}<dt>{s.what}</dt><dd>{s.reach}</dd>{/each}</dl>
            {/if}
          </section>
        </div>

      <!-- ============================== LORE ============================== -->
      {:else if tab === 'lore'}
        <div class="two">
          <section>
            <h2 class="caps">The class</h2>
            <p class="prose">{cls.summary || '—'}</p>
            {#if cls.genus || cls.epithet}
              <div class="names">
                {#if cls.genus}<div><span>Genus · the body</span><b>{cls.genus.word}</b><i>{cls.genus.meaning}</i></div>{/if}
                {#if cls.epithet}<div><span>Epithet · the vocation</span><b>{cls.epithet.word}</b><i>{cls.epithet.meaning}</i></div>{/if}
              </div>
            {/if}
            <div class="readers">
              {#each [['Sail reader', cls.terms.sail], ['Modern reader', cls.terms.modern], ['ARCVS reader', cls.terms.arcvs]] as [who, word]}
                <div><span>{who}</span><b class:blank={!word}>{word ?? '—'}</b></div>
              {/each}
            </div>
            <dl class="rows">
              {#if cls.body}<dt>Body</dt><dd>{cls.body}</dd>{/if}
              {#if cls.places.length}<dt>Places</dt><dd>{cls.places.join(', ')}</dd>{/if}
              {#if cls.history.built_as}<dt>Built as</dt><dd>{cls.history.built_as}</dd>{/if}
              {#if cls.history.serves_as}<dt>Serves as</dt><dd>{cls.history.serves_as}</dd>{/if}
              {#if cls.history.refit}<dt>Refit</dt><dd>{cls.history.refit}</dd>{/if}
            </dl>
            {#each cls.history.notable ?? [] as n}<p class="note">· {n}</p>{/each}
          </section>
          <section>
            <div class="level">
              <b>{cls.in_classis ? num(v(cls.in_classis)) : '—'}</b>
              <div>
                <span class="cap">In a Classis</span>
                <span class="sub">{cls.in_classis ? q(cls.in_classis) : 'not yet stated'}{cls.in_classis?.note ? ` · ${cls.in_classis.note}` : ''}</span>
              </div>
              <i class="wedge"></i>
            </div>
            <dl class="rows">
              {#if cls.designation}<dt>Designation</dt><dd>{cls.designation}</dd>{/if}
              {#if cls.old_rating}<dt>Old Forest rating</dt><dd class:blank={cls.old_rating === '—'}>{cls.old_rating}</dd>{/if}
              {#if cls.successor}<dt>Succeeded by</dt><dd><button class="link" on:click={() => open(cls.successor)}>{cls.successor}</button></dd>{/if}
              {#if cls.derived.successor_of}<dt>Successor of</dt><dd><button class="link" on:click={() => open(cls.derived.successor_of)}>{cls.derived.successor_of}</button></dd>{/if}
            </dl>
            <h2 class="caps">{cls.lineage_rules.label ?? 'Lineage'}</h2>
            <dl class="rows">
              {#if cls.lineage_rules.names}<dt>Names</dt><dd>{cls.lineage_rules.names}</dd>{/if}
              {#if cls.lineage_rules.order}<dt>Order</dt><dd>{cls.lineage_rules.order}</dd>{/if}
              {#if cls.lineage_rules.design}<dt>Design</dt><dd>{cls.lineage_rules.design}</dd>{/if}
            </dl>
            <h2 class="caps">{cls.rate_rules.label ?? 'Rate'}</h2>
            {#if cls.rate}
              <dl class="rows">
                {#if cls.rate_rules.commanded_by}<dt>Commanded by</dt><dd>{cls.rate_rules.commanded_by}</dd>{/if}
                {#if cls.rate_rules.hands}<dt>Hands</dt><dd>{cls.rate_rules.hands}</dd>{/if}
                {#if cls.rate_rules.covers}<dt>Covers</dt><dd>{cls.rate_rules.covers}</dd>{/if}
              </dl>
            {:else}<p class="empty">Not yet rated.</p>{/if}
          </section>
        </div>

      <!-- ============================== OPEN ============================== -->
      {:else}
        <h2 class="caps">Left for the author <span class="sub">template fields not stated, and every "—"</span></h2>
        {#if cls.blanks.length}
          {#each cls.blanks as b, i}<div class="oth" class:band={i % 2}><span class="lb">{b}</span><b class="blank">—</b></div>{/each}
        {:else}<p class="empty">Nothing left open.</p>{/if}
        {#if cls.findings.length}
          <h2 class="caps">Findings</h2>
          {#each cls.findings as f}<p class="find {f.level}"><b>{f.level}</b> {f.where}: {f.message}</p>{/each}
        {/if}
        <p class="note">data/ships/classes/{cls.file} · est. marks an estimate in the class documents; ~ is about</p>
      {/if}
    {/if}
  </main>
</div>

<style>
  /* the registry speaks its own design language: neutral dark panels, one yellow, big numerals */
  .reg {
    --y: #fa1f99; --y-ink: #ffffff; --c: #9ff0ff; --c-ink: #06141a; --t: #ececf0; --t2: #9a9aa6; --t3: #5d5d68;
    --p: rgba(20, 20, 25, 0.94); --p2: rgba(34, 34, 41, 0.9); --line: rgba(255, 255, 255, 0.1); --band: rgba(255, 255, 255, 0.035);
    --sans: 'Barlow', 'Chakra Petch', sans-serif; --cond: 'Barlow Condensed', 'Barlow', sans-serif;
    position: fixed; inset: 0; z-index: 25; color: var(--t); font-family: var(--sans); font-size: 13px;
    display: grid; grid-template-columns: 300px 1fr 88px; grid-template-rows: 68px 1fr;
    background: linear-gradient(115deg, rgba(14, 13, 20, 0.97) 0%, rgba(10, 9, 16, 0.9) 60%, rgba(26, 8, 22, 0.9) 100%);
    backdrop-filter: blur(4px);
  }
  button { background: none; border: 0; color: inherit; font: inherit; padding: 0; text-align: left; }
  code { font-family: var(--mono); font-size: 11px; color: var(--t); }
  .blank { color: var(--t3) !important; }
  .dim { color: var(--t2); }

  /* ---- header: breadcrumb, barcode, close ---- */
  .top { grid-column: 1 / -1; display: flex; align-items: center; gap: 14px; padding: 10px 22px 6px; }
  .logo { width: 34px; height: 28px; color: var(--t); }
  .crumb p { margin: 0; font-size: 20px; font-weight: 500; letter-spacing: 0.01em; }
  .crumb b { font-weight: 600; color: var(--c); }
  .sl { color: var(--t2); margin: 0 2px; }
  .code { display: flex; align-items: center; gap: 8px; margin-top: 3px; font-family: var(--mono); font-size: 9px; color: var(--t3); letter-spacing: 0.1em; }
  .bars { display: inline-block; width: 64px; height: 8px; background: repeating-linear-gradient(90deg, var(--t2) 0 1px, transparent 1px 3px, var(--t2) 3px 5px, transparent 5px 6px, var(--t2) 6px 7px, transparent 7px 10px); opacity: 0.7; }
  .close { margin-left: auto; width: 40px; height: 40px; background: var(--t); display: grid; place-items: center; clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px); }
  .close svg { width: 22px; height: 22px; stroke: #111; stroke-width: 3; fill: none; }
  .close:hover { background: var(--y); }
  .close:hover svg { stroke: #fff; }

  /* ---- roster ---- */
  .roster { overflow: auto; padding: 4px 10px 16px 22px; border-right: 1px solid var(--line); }
  .roster h3 { margin: 18px 0 2px; padding-bottom: 5px; border-bottom: 2px solid var(--t2);
               font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t); }
  .roster h4 { margin: 10px 0 4px; font-size: 11px; font-weight: 500; letter-spacing: 0.04em; color: var(--t2); }
  .roster h4::before { content: ''; display: inline-block; width: 5px; height: 5px; margin: 0 7px 1px 1px; background: var(--t2); transform: rotate(45deg); }
  .ship { position: relative; display: grid; grid-template-columns: 30px 1fr auto; grid-template-rows: auto auto; column-gap: 9px; align-items: center;
          width: 100%; padding: 6px 8px; margin: 2px 0; background: var(--band); border-left: 3px solid transparent; }
  .ship canvas { grid-row: span 2; }
  .ship:hover { background: rgba(255, 255, 255, 0.07); }
  .ship.on { background: rgba(250, 31, 153, 0.1); border-left-color: var(--y); }
  .ship .nm { font-weight: 600; font-size: 13px; letter-spacing: 0.02em; }
  .ship.on .nm { color: var(--c); }
  .ship .tm { grid-column: 2; font-size: 11px; color: var(--t2); }
  .flag { grid-row: 1 / span 2; grid-column: 3; min-width: 18px; padding: 1px 5px; font-size: 10px; text-align: center; color: var(--t2); border: 1px solid var(--line); }
  .flag.ex { color: #ff8fb8; border-color: #ff8fb8; }
  .keys { margin: 18px 0 0; color: var(--t3); font-size: 11px; }
  kbd { display: inline-block; min-width: 16px; padding: 0 4px; margin: 0 1px; border: 1px solid var(--t3); font-family: var(--mono); font-size: 10px; text-align: center; color: var(--t2); }
  .err { color: #ff8fb8; }

  /* ---- tab rail ---- */
  .rail { grid-row: 2; grid-column: 3; display: flex; flex-direction: column; gap: 6px; padding: 8px 12px 0 8px; }
  .rail button { position: relative; height: 70px; clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px)); background: var(--p2); border: 1px solid var(--line); display: grid; place-items: center; align-content: center; gap: 4px; color: var(--t2); }
  .rail button:hover { color: var(--t); border-color: rgba(255, 255, 255, 0.25); }
  .rail button.on { background: var(--y); color: var(--y-ink); border-color: var(--y); }
  .rail svg { width: 24px; height: 24px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linejoin: round; stroke-linecap: round; }
  .rail span { font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .rail .no { position: absolute; top: 3px; left: 5px; font-style: normal; font-family: var(--mono); font-size: 8px; opacity: 0.6; }
  .rail .dot { position: absolute; top: 3px; right: 4px; font-size: 9px; font-weight: 700; color: var(--c); }
  .rail button.on .dot { color: var(--y-ink); }

  /* ---- main ---- */
  main { grid-row: 2; grid-column: 2; overflow: auto; padding: 10px 28px 28px; }
  h2.caps { display: flex; align-items: baseline; gap: 12px; margin: 22px 0 8px; font-size: 13px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t); }
  h2.caps .sub { font-size: 11px; font-weight: 400; letter-spacing: 0.02em; text-transform: none; color: var(--t2); }
  h2.uline { position: relative; display: inline-block; margin: 0 0 12px; padding-bottom: 6px; font-size: 22px; font-weight: 600; border-bottom: 2px solid var(--t); }
  h2.uline::after { content: ''; position: absolute; left: -2px; bottom: -6px; width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--t); background: #111; }
  .note { margin: 8px 0 0; color: var(--t2); font-size: 12px; line-height: 1.45; }
  .empty { color: var(--t2); margin: 24px 0; }
  .link { color: var(--c); }
  .link:hover { text-decoration: underline; }
  dl.rows { display: grid; grid-template-columns: auto 1fr; margin: 0; }
  dl.rows dt, dl.rows dd { padding: 6px 10px; border-bottom: 1px solid var(--line); }
  dl.rows dt { color: var(--t2); }
  dl.rows dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }
  dl.rows.small dt, dl.rows.small dd { padding: 4px 8px; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  th { text-align: left; font-size: 10px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--t2); padding: 6px 10px; border-bottom: 1px solid var(--t3); }
  td { padding: 7px 10px; }
  .r { text-align: right; }
  tr.band, .band { background: var(--band); }
  td.strong { font-weight: 600; font-size: 14px; }
  td.aim { color: var(--c); }
  tr.hl td { box-shadow: inset 0 -1px 0 rgba(159, 240, 255, 0.4); }
  tr.cur { background: rgba(250, 31, 153, 0.12); }
  tr.cur b { color: var(--y); }
  .pip { display: inline-block; width: 7px; height: 7px; margin-right: 8px; background: var(--y); transform: rotate(45deg); }

  /* ---- overview ---- */
  .ov { display: grid; grid-template-columns: minmax(420px, 1.05fr) minmax(340px, 1fr); gap: 36px; }
  .ident { display: flex; gap: 16px; align-items: center; margin-top: 10px; }
  .sym { padding: 6px; background: var(--p2); border: 1px solid var(--line); }
  h1 { margin: 0; font-family: var(--sans); font-weight: 600; font-size: 38px; line-height: 1; letter-spacing: 0.01em; }
  .bin { margin: 6px 0 0; color: var(--t2); font-size: 14px; }
  .bin b { color: var(--t); font-weight: 600; }
  .bin span { margin: 0 6px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 14px 0 0; }
  .chips span { padding: 4px 12px; background: rgba(255, 255, 255, 0.08); border: 1px solid var(--line); font-size: 13px; }
  .chips span.hl { background: var(--c); color: var(--c-ink); border-color: var(--c); font-weight: 600; }
  .bar { display: flex; justify-content: space-between; align-items: center; margin: 20px 0 10px; padding: 6px 12px; background: rgba(255, 255, 255, 0.1); border-left: 3px solid var(--t); }
  .bar span { font-size: 16px; font-weight: 600; }
  .bar button { color: var(--t2); letter-spacing: 0.1em; }
  .bar button:hover { color: var(--c); }
  .attrs { display: grid; grid-template-columns: repeat(4, 1fr); }
  .attr { display: grid; justify-items: center; gap: 2px; padding: 4px 6px; border-right: 1px solid var(--line); text-align: center; }
  .attr:last-child { border-right: 0; }
  .attr svg { width: 30px; height: 30px; fill: none; stroke: var(--t); stroke-width: 1.7; stroke-linejoin: round; stroke-linecap: round; }
  .attr .lb { color: var(--t2); font-size: 12px; }
  .attr b { font-family: var(--cond); font-size: 26px; font-weight: 600; line-height: 1.05; font-variant-numeric: tabular-nums; }
  .attr .un { color: var(--t2); font-size: 11px; }
  .arms { display: flex; flex-wrap: wrap; gap: 14px 18px; }
  .arm { display: grid; justify-items: center; width: 96px; gap: 1px; }
  .hex { display: grid; place-items: center; width: 60px; height: 54px; background: var(--t2);
         clip-path: polygon(25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%, 0 50%); }
  .hex span { display: grid; place-items: center; width: calc(100% - 4px); height: calc(100% - 4px); background: var(--p2); color: var(--t);
              clip-path: inherit; font-family: var(--cond); font-weight: 700; font-size: 15px; letter-spacing: 0.06em; }
  .arm:hover .hex { background: var(--c); }
  .arm.focus .hex, .bat.focus .hex { background: var(--y); }
  .arm.focus .hex span, .bat.focus .hex span { background: repeating-linear-gradient(-55deg, rgba(250, 31, 153, 0.55) 0 5px, rgba(250, 31, 153, 0.85) 5px 11px); color: #fff; }
  .arm .rng { margin-top: 6px; }
  .arm .rng b { font-family: var(--cond); font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .arm.focus .rng b { color: var(--y); }
  .arm .rng small, .bat .eng small { margin-left: 3px; font-size: 11px; color: var(--t2); }
  .arm .ct { font-size: 11px; font-weight: 600; color: var(--c); }
  .arm .lb { font-size: 11px; color: var(--t2); text-align: center; }
  .chips.drive { margin-top: 0; }
  .level { position: relative; display: flex; align-items: flex-end; gap: 14px; padding: 6px 0 14px; margin-bottom: 6px; overflow: hidden; }
  .level b { font-family: var(--cond); font-size: 104px; font-weight: 700; line-height: 0.85; letter-spacing: -0.02em; }
  .level .cap { display: block; padding: 3px 10px; background: rgba(255, 255, 255, 0.12); font-size: 15px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .level .sub { display: block; margin-top: 4px; color: var(--t2); font-size: 12px; }
  .wedge { position: absolute; right: -40px; top: -20px; width: 200px; height: 160px; background: var(--y); clip-path: polygon(40% 0, 100% 0, 100% 100%); opacity: 0.85; }
  .summary { margin: 14px 0 0; font-size: 14px; line-height: 1.5; color: var(--t2); max-width: 64ch; }
  .ov-r h2.uline { margin-top: 10px; }
  .lbs { margin-left: 8px; font-style: normal; font-size: 12px; color: var(--t2); }
  .oth.slim { min-height: 30px; padding: 5px 14px; grid-template-columns: 1fr auto; }
  .oth.slim .lb { font-size: 13px; color: var(--t2); }
  .oth.slim b { font-size: 14px; }
  .readers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; margin-bottom: 12px; }
  .readers div { padding: 8px 10px; background: var(--band); }
  .readers span { display: block; font-size: 10px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--t2); }
  .readers b { font-size: 15px; font-weight: 600; }

  /* ---- drive: attribute cards and stat rows ---- */
  .st { display: grid; grid-template-columns: 330px 1fr; gap: 34px; margin-top: 10px; }
  .cards { display: grid; align-content: start; gap: 10px; }
  .card { position: relative; padding: 9px 14px 10px; background: var(--p2); border: 1px solid var(--line); overflow: hidden;
          clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 0 100%); }
  .card .tag { margin: 0; font-size: 10px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--t2); }
  .card .big { margin: 2px 0 0; font-family: var(--cond); font-size: 32px; font-weight: 600; line-height: 1.05; }
  .card .big small { font-size: 16px; font-weight: 500; color: var(--t2); }
  .card .ft { margin: 0; font-size: 12px; color: var(--t2); }
  .card.main, .bat.focus header { background: var(--y); color: var(--y-ink); border-color: var(--y); }
  .card.main::after, .bat.focus header::after { content: ''; position: absolute; right: -10px; top: 0; bottom: 0; width: 46%; opacity: 0.28; pointer-events: none;
                      background: repeating-linear-gradient(-55deg, #fff 0 6px, transparent 6px 16px); clip-path: polygon(30% 0, 100% 0, 100% 100%, 0 100%); }
  .card.main .tag, .card.main .ft, .card.main .big small { color: rgba(255, 255, 255, 0.8); }
  .prim { display: grid; grid-template-columns: 34px 1fr auto 28px; align-items: center; gap: 10px; padding: 12px 14px; margin-bottom: 6px; background: var(--p2); }
  .prim svg { width: 26px; height: 26px; fill: none; stroke: var(--t); stroke-width: 1.8; stroke-linejoin: round; stroke-linecap: round; }
  .prim .lb { font-size: 17px; font-weight: 500; }
  .prim b { font-family: var(--cond); font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .oth { display: grid; grid-template-columns: 1fr auto auto 28px; align-items: center; gap: 12px; padding: 7px 14px; min-height: 36px; }
  .oth .lb { font-size: 14px; }
  .oth .sub { color: var(--t2); font-size: 11px; text-align: right; }
  .oth b { font-weight: 600; font-size: 15px; font-variant-numeric: tabular-nums; text-align: right; }
  .oth b.bad { color: #ff8fb8; }
  .typed { margin-left: 8px; padding: 1px 6px; font-style: normal; font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--c-ink); background: var(--c); }
  .q { width: 22px; height: 22px; border: 1.5px solid var(--t3); color: var(--t2); display: grid; place-items: center; font-size: 12px; font-weight: 700; justify-self: end;
       clip-path: polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 0 100%); }
  .q:hover, .q.on { border-color: var(--c); color: var(--c); }
  .why { margin: -2px 0 8px; padding: 8px 14px 8px 16px; border-left: 2px solid var(--c); background: rgba(159, 240, 255, 0.06); font-family: var(--mono); font-size: 11px; line-height: 1.5; color: var(--t); }
  .verdict { margin: 10px 0 0; padding: 8px 12px; background: var(--band); border-left: 3px solid var(--t2); color: var(--t2); }
  .verdict b { color: var(--t); margin-right: 6px; }
  .verdict.short { border-left-color: #ff8fb8; }

  /* ---- armament, systems, lore ---- */
  .seg { display: flex; flex-wrap: wrap; gap: 0; align-items: center; margin-bottom: 10px; }
  .seg button { padding: 6px 14px; background: var(--p2); border: 1px solid var(--line); margin-right: -1px; font-weight: 600; }
  .seg button i { font-style: normal; font-weight: 400; font-size: 11px; color: var(--t2); margin-left: 4px; }
  .seg button.on { background: var(--c); color: var(--c-ink); border-color: var(--c); }
  .seg button.on i { color: rgba(6, 20, 26, 0.7); }
  .seg .dim { margin-left: 14px; font-size: 12px; }
  .bats { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 12px; }
  .bat { background: var(--p2); border: 1px solid var(--line); clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 0 100%); }
  .bat.focus { grid-column: 1 / -1; border-color: var(--y); }
  .bat header { position: relative; display: flex; gap: 14px; align-items: center; padding: 10px 14px; overflow: hidden; }
  .bat header .tag { margin: 0; font-size: 10px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--t2); }
  .bat.focus header .tag, .bat.focus header span, .bat.focus .eng i, .bat.focus .eng small { color: rgba(255, 255, 255, 0.82); }
  .bat .hex { width: 48px; height: 43px; }
  .bat .hex span { font-size: 12px; }
  .bat.focus .hex { background: #fff; }
  .bat.focus .hex span { background: #fff; color: var(--y); }
  .bat.focus dl.rows { grid-template-columns: auto 1fr auto 1fr; column-gap: 28px; }
  .bat h3 { margin: 0; font-size: 16px; font-weight: 600; }
  .bat header span { color: var(--t2); font-size: 12px; }
  .bat .eng { position: relative; z-index: 1; margin-left: auto; text-align: right; }
  .bat .eng b { font-family: var(--cond); font-size: 30px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .bat .eng i { display: block; font-style: normal; font-size: 11px; color: var(--t2); }
  .bat dl, .bat > .note { margin-left: 14px; margin-right: 14px; }
  .bat dl { margin-top: 6px; }
  .bat > .note:last-child { margin-bottom: 10px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 34px; }
  .prose { font-size: 15px; line-height: 1.55; max-width: 64ch; margin: 0 0 14px; }
  .names { display: grid; grid-template-columns: 1fr 1fr; gap: 2px; margin-bottom: 12px; }
  .names div { padding: 10px 12px; background: var(--p2); }
  .names span { display: block; font-size: 10px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--t2); }
  .names b { display: block; font-family: var(--cond); font-size: 26px; font-weight: 600; letter-spacing: 0.04em; }
  .names i { color: var(--t2); }
  .find { margin: 6px 0 0; font-size: 12px; }
  .find b { text-transform: uppercase; font-size: 10px; letter-spacing: 0.1em; margin-right: 6px; }
  .find.error { color: #ff8fb8; }
  .find.warning { color: #ffe3a6; }
</style>

<script>
  // The fleets (data/fleets, astrum/fleets.py): every fleet, its ships by class, and its order of
  // battle, formation by formation: as a table, or as a chart in the NATO manner, each unit under
  // the one above it with the map's own symbols. An admin renames units and changes a ship's hull
  // number or class, in either; the server writes it into the fleet's file. A level already
  // running keeps the copy it started with: an edit is played from the next start.
  import { onMount } from 'svelte';
  import { api } from './api.js';
  import OrgNode from './OrgNode.svelte';

  export let onback = () => {};
  export let style = null;

  let view = 'chart', top = null, ships = false;   // the chart: its top formation, ships shown or tallied

  let fleets = [], admin = false, current = null, fleet = null, error = '', saved = '';
  let edits = {};                       // unit id -> { callsign, hull_number, class }: what is changed and not saved
  $: dirty = Object.keys(edits).length > 0;

  async function load() {
    try {
      const r = await api.fleets();
      fleets = r.fleets; admin = r.admin;
      error = Object.values(r.errors ?? {}).join(' · ');
      if (!current && fleets.length) open(fleets[0].id);
    } catch (e) { error = String(e.message ?? e); }
  }
  async function open(id) {
    if (dirty && !confirm('Leave this fleet without saving its changes?')) return;
    current = id; edits = {}; saved = ''; top = null;
    try { fleet = await api.fleet(id); } catch (e) { error = String(e.message ?? e); }
  }
  onMount(load);

  // the order of battle: each unit under the one above it, depth by depth
  $: rows = fleet ? tree(fleet.units) : [];
  function tree(units) {
    const kids = {};
    for (const u of units) (kids[u.formation ?? ''] ??= []).push(u);
    const out = [];
    const walk = (id, depth) => (kids[id] ?? []).forEach((u) => { out.push({ ...u, depth }); walk(u.id, depth + 1); });
    walk('', 0);
    return out;
  }
  // the chart: from its top formation (the fleet's own, or the one chosen), its units under it
  $: nodes = fleet ? (() => {
    const by = Object.fromEntries(fleet.units.map((u) => [u.id, { ...u, kids: [] }]));
    for (const u of Object.values(by)) if (u.formation && by[u.formation]) by[u.formation].kids.push(u);
    return by;
  })() : {};
  $: roots = fleet ? (top && nodes[top] ? [nodes[top]] : fleet.units.filter((u) => !u.formation).map((u) => nodes[u.id])) : [];
  $: trail = top && nodes[top] ? (() => { const t = []; for (let u = nodes[top]; u; u = nodes[u.formation]) t.unshift(u); return t; })() : [];
  const value = (u, k) => edits[u.id]?.[k] ?? u[k];
  function change(u, k, v) {
    const e = { ...(edits[u.id] ?? {}), [k]: v };
    if (v === u[k]) delete e[k];
    edits = Object.keys(e).length ? { ...edits, [u.id]: e } : Object.fromEntries(Object.entries(edits).filter(([id]) => id !== u.id));
  }
  async function save() {
    error = ''; saved = '';
    try {
      fleet = await api.saveFleet(current, edits);
      saved = `Saved: ${Object.keys(edits).length} units. A level already running keeps its copy; the next start plays this.`;
      edits = {};
      load();
    } catch (e) { error = String(e.message ?? e); }
  }
  function key(e) {
    if (e.key === 'Escape' && !['INPUT', 'SELECT'].includes(e.target.tagName)) onback();
  }
</script>

<svelte:window on:keydown={key} />

<div class="fm" data-ui>
  <header class="top">
    <p><span class="sl">//</span> Fleets <span class="sl">/</span> <b>{fleet?.name ?? '…'}</b></p>
    <span class="who">{admin ? 'admin: editing' : 'viewing'}</span>
    <button class="close" on:click={onback} title="Back to the menu (Esc)"><svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17" /></svg></button>
  </header>

  <aside class="roster">
    <h3>Fleets</h3>
    {#each fleets as f (f.id)}
      <button class="item" class:on={f.id === current} on:click={() => open(f.id)}>
        <span class="nm">{f.name}</span>
        <span class="sub">{f.faction_name} · {f.ships} ships</span>
      </button>
    {/each}
    <p class="note">data/fleets: each a file. A scenario brings fleets in with [[fleet]] id.</p>
  </aside>

  <main>
    {#if error}<p class="err">{error}</p>{/if}
    {#if fleet}
      <section class="head">
        <h2>{fleet.name}</h2>
        <p class="dim">{fleet.faction_name} · {fleet.formations} formations, {fleet.ships} ships · {fleet.scenarios.map((s) => `${s.id}: ${s.placed} placed${s.placed < fleet.ships ? `, ${fleet.ships - s.placed} undeployed` : ''}`).join(' · ') || 'in no scenario'}</p>
        {#if fleet.notes}<p>{fleet.notes}</p>{/if}
      </section>

      <section class="deck">
        {#each Object.entries(fleet.by_class) as [cid, n]}
          <div class="card"><b>{n}</b><span>{fleet.classes.find((c) => c.id === cid)?.name ?? cid}</span></div>
        {/each}
      </section>

      <section class="oob">
        <div class="bar">
          <h3>Order of battle</h3>
          <span class="tabs">
            <button class:on={view === 'chart'} on:click={() => (view = 'chart')}>Chart</button>
            <button class:on={view === 'table'} on:click={() => (view = 'table')}>Table</button>
          </span>
          {#if view === 'chart'}<button class="act" class:on={ships} on:click={() => (ships = !ships)}>{ships ? 'Ships shown' : 'Ships tallied'}</button>{/if}
          {#if admin}
            {#if saved}<span class="ok">{saved}</span>{/if}
            <button class="act" disabled={!dirty} on:click={save}>Save {dirty ? `(${Object.keys(edits).length})` : ''}</button>
            <button class="act" disabled={!dirty} on:click={() => (edits = {})}>Undo</button>
          {/if}
        </div>
        {#if view === 'chart'}
          {#if trail.length}
            <p class="trail">{#each trail.slice(0, -1) as t, i}{#if i}<span class="sl">/</span>{/if}<button on:click={() => (top = t.formation ? t.id : null)}>{value(t, 'callsign')}</button>{/each}<span class="sl">/</span><b>{value(trail[trail.length - 1], 'callsign')}</b></p>
          {/if}
          <p class="hint">A formation's symbol makes it the chart's top.</p>
          {#each roots as r (r.id)}
            <div class="chart">
              <div class="root"><OrgNode unit={{ ...r, kids: [] }} {style} {admin} ships {value} {change} changed={edits} classes={fleet.classes} onfocus={(id) => (top = id)} /></div>
              <div class="cols">
                {#each (ships ? r.kids : r.kids.filter((k) => !k.class)) as col (col.id)}
                  <div class="col"><OrgNode unit={col} {style} {admin} {ships} {value} {change} changed={edits} classes={fleet.classes} onfocus={(id) => (top = id)} /></div>
                {/each}
              </div>
            </div>
          {/each}
        {:else}
        <table>
          <thead><tr><th>Unit</th><th>Class</th><th>Hull</th><th class="dim">id</th></tr></thead>
          <tbody>
            {#each rows as u (u.id)}
              <tr class:ship={u.class} class:changed={edits[u.id]}>
                <td style="padding-left: {8 + u.depth * 18}px">
                  {#if !u.class}<span class="ech">{u.echelon}</span>{/if}
                  {#if admin}<input value={value(u, 'callsign')} on:input={(e) => change(u, 'callsign', e.target.value)} />
                  {:else}<span class:fm-name={!u.class}>{u.callsign}</span>{/if}
                </td>
                <td>
                  {#if u.class}
                    {#if admin}
                      <select value={value(u, 'class')} on:change={(e) => change(u, 'class', e.target.value)}>
                        {#each fleet.classes as c}<option value={c.id}>{c.name}</option>{/each}
                      </select>
                    {:else}{u.class_name || u.class}{/if}
                  {/if}
                </td>
                <td>
                  {#if u.class}
                    {#if admin}<input class="hull" value={value(u, 'hull_number')} placeholder="—" on:input={(e) => change(u, 'hull_number', e.target.value)} />
                    {:else}{u.hull_number || '—'}{/if}
                  {/if}
                </td>
                <td class="dim id">{u.id}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {/if}
      </section>
    {/if}
  </main>
</div>

<style>
  .fm {
    --y: #fa1f99; --c: #9ff0ff; --t: #ececf0; --t2: #9a9aa6; --t3: #5d5d68; --line: rgba(255, 255, 255, 0.1); --band: rgba(255, 255, 255, 0.035);
    position: fixed; inset: 0; z-index: 25; color: var(--t); font-family: 'Barlow', 'Chakra Petch', sans-serif; font-size: 13px;
    display: grid; grid-template-columns: 280px 1fr; grid-template-rows: 56px 1fr;
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
  .close:hover { background: var(--y); }

  .roster { overflow: auto; padding: 6px 12px 16px 22px; border-right: 1px solid var(--line); }
  .roster h3, .oob h3 { margin: 14px 0 6px; font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t2); }
  .item { display: grid; width: 100%; padding: 8px 10px; border-left: 2px solid transparent; }
  .item:hover { background: var(--band); }
  .item.on { background: rgba(250, 31, 153, 0.1); border-left-color: var(--y); }
  .nm { font-weight: 600; letter-spacing: 0.04em; }
  .sub { color: var(--t2); font-size: 11px; }
  .note { color: var(--t3); font-size: 11px; margin-top: 18px; line-height: 1.4; }

  main { overflow: auto; padding: 14px 26px 30px; }
  .err { color: #ffd27a; }
  .ok { color: var(--c); font-size: 12px; margin-right: 10px; }
  .head h2 { margin: 0 0 4px; font-size: 26px; font-weight: 600; }
  .head p { margin: 2px 0; }
  .deck { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
  .card { display: grid; place-items: center; min-width: 120px; padding: 10px 12px; background: rgba(255, 255, 255, 0.05); border-top: 2px solid var(--y); }
  .card b { font-size: 24px; font-weight: 600; }
  .card span { color: var(--t2); font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; text-align: center; }
  .bar { display: flex; align-items: center; gap: 8px; }
  .bar h3 { flex: 1; }
  .tabs { display: flex; margin-right: 12px; }
  .tabs button { padding: 5px 12px; color: var(--t2); border-bottom: 2px solid transparent; }
  .tabs button.on { color: var(--t); border-bottom-color: var(--y); }
  .act.on { background: rgba(250, 31, 153, 0.25); }
  .trail { margin: 10px 0 0; font-size: 13px; }
  .trail button { color: var(--c); }
  .hint { color: var(--t3); font-size: 11px; margin: 6px 0 0; }

  /* the chart: the top in the middle, the units under it in columns, joined by a bar */
  .chart { margin: 18px 0 30px; }
  .root { display: flex; justify-content: center; padding-bottom: 14px; position: relative; }
  .root::after { content: ''; position: absolute; left: 50%; bottom: 0; height: 14px; border-left: 1px solid var(--t3); }
  .cols { display: flex; gap: 28px; padding-top: 14px; overflow-x: auto; }
  .col { position: relative; flex: 0 0 auto; }
  .col::before { content: ''; position: absolute; top: -14px; left: 26px; height: 14px; border-left: 1px solid var(--t3); }
  .col::after { content: ''; position: absolute; top: -14px; left: 0; right: -28px; border-top: 1px solid var(--t3); }
  .col:first-child::after { left: 26px; }
  .col:last-child::after { right: auto; width: 27px; }
  .col:only-child::after { display: none; }
  .act { padding: 5px 12px; background: rgba(255, 255, 255, 0.08); }
  .act:hover:not(:disabled) { background: var(--y); }
  .act:disabled { opacity: 0.35; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-weight: 500; color: var(--t2); font-size: 11px; padding: 4px 8px; border-bottom: 1px solid var(--line); }
  td { padding: 3px 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
  tr:not(.ship) td { padding-top: 9px; }
  tr.changed td:first-child { box-shadow: inset 2px 0 0 var(--c); }
  .ech { display: inline-block; min-width: 70px; color: var(--t3); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; }
  .fm-name { font-weight: 600; }
  .id { font-family: monospace; font-size: 11px; }
  input, select { background: rgba(0, 0, 0, 0.3); border: 1px solid var(--line); color: var(--t); font: inherit; padding: 3px 6px; }
  input:focus, select:focus { outline: none; border-color: var(--y); }
  input { width: 220px; }
  input.hull { width: 110px; }
</style>

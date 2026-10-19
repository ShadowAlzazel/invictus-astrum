<script>
  // The system workshop: edit a system document, see it built live on the map, save it as a level.
  // The server judges every change (POST /workshop/check); this panel only edits the document.
  import { onDestroy } from 'svelte';
  import { api, Rejected } from './api.js';
  import UnitField from './UnitField.svelte';
  import OrbitFields from './OrbitFields.svelte';

  export let schema;
  export let doc;                       // { system, frame, body[], binary[] }, edited in place
  export let onpreview = () => {};      // the draft built: show it
  export let onsaved = () => {};
  export let onexit = () => {};

  let findings = [], ok = false, timer, open = null, armed = null, preset = '', status = '', confirm = false;

  $: bodies = doc.body;
  $: binaries = doc.binary;
  $: ids = [...bodies.map((b) => b.id), ...binaries.map((b) => b.id)];
  $: components = Object.fromEntries(binaries.flatMap((b) => [[b.primary, b.id], [b.secondary, b.id]]));
  $: errors = findings.filter((f) => f.level === 'error');
  $: warnings = findings.filter((f) => f.level === 'warning');
  $: presetGroups = groupPresets(schema.presets);

  function groupPresets(p) {
    const g = {};
    for (const [id, v] of Object.entries(p)) (g[v.kind] ??= []).push([id, v.label]);
    return g;
  }

  // every edit: rebuild on the server, a moment after typing stops
  function changed() {
    doc = doc;
    status = ''; confirm = false;
    clearTimeout(timer);
    timer = setTimeout(check, 350);
  }
  async function check() {
    const r = await api.workshop.check(clean(doc));
    findings = r.findings; ok = r.ok;
    if (ok) onpreview(r.draft);
  }
  check();
  onDestroy(() => clearTimeout(timer));

  // blank fields are absent fields
  function clean(v) {
    if (Array.isArray(v)) return v.map(clean);
    if (v && typeof v === 'object') {
      const o = {};
      for (const [k, x] of Object.entries(v)) if (x !== null && x !== undefined && x !== '') o[k] = clean(x);
      return o;
    }
    return v;
  }

  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'body';
  function uniqueId(base) {
    let id = slug(base), n = 2;
    while (ids.includes(id)) id = `${slug(base)}-${n++}`;
    return id;
  }

  // a new body orbits whatever is open (if it can hold one), else the root
  function addBody() {
    if (!preset) return;
    const p = structuredClone(schema.presets[preset]);
    const label = p.label; delete p.label;
    const host = bodies.find((b) => b.id === open) ?? null;
    const root = bodies.find((b) => !b.parent && !components[b.id]) ?? binaries.find((b) => !b.parent);
    const parent = host && host.kind !== 'moon' ? host.id : root?.id ?? null;
    const nameBase = label.split(':').pop().trim().replace(/-like$/, '');
    const b = { id: uniqueId(nameBase), name: nameBase, ...p };
    if (parent) {
      b.parent = parent;
      const pk = bodies.find((x) => x.id === parent)?.kind;
      b.orbit = p.kind === 'moon' || pk === 'planet' ? { a_km: 400000, e: 0, m0_deg: 0 } : { a_au: 1, e: 0, m0_deg: 0 };
    }
    doc.body = [...bodies, b];
    open = b.id;
    changed();
  }

  function addBinary() {
    const stars = bodies.filter((b) => !components[b.id] && !b.parent);
    const [a, c] = [stars[0]?.id ?? '', stars[1]?.id ?? ''];
    const bin = { id: uniqueId('binary'), name: 'Barycentre', primary: a, secondary: c, relative: { a_au: 20, e: 0.3, m0_deg: 0 } };
    for (const b of bodies) if (b.id === a || b.id === c) delete b.parent;
    doc.binary = [...binaries, bin];
    open = bin.id;
    changed();
  }

  function remove(id) {
    if (armed !== id) { armed = id; return; }
    doc.body = bodies.filter((b) => b.id !== id);
    doc.binary = binaries.filter((b) => b.id !== id);
    armed = null; open = null;
    changed();
  }

  // renaming an id carries every reference to it
  function rename(obj, e) {
    const old = obj.id, id = slug(e.target.value);
    if (!id || id === old) { e.target.value = old; return; }
    obj.id = id;
    for (const b of bodies) if (b.parent === old) b.parent = id;
    for (const b of binaries) {
      if (b.parent === old) b.parent = id;
      if (b.primary === old) b.primary = id;
      if (b.secondary === old) b.secondary = id;
    }
    if (doc.frame?.of === old) doc.frame.of = id;
    open = id;
    changed();
  }

  function setParent(b, v) {
    if (v) b.parent = v; else delete b.parent;
    if (v && !b.orbit) b.orbit = { a_au: 1, e: 0, m0_deg: 0 };
    changed();
  }

  async function save(overwrite = false) {
    status = 'Saving…';
    try {
      const r = await api.workshop.save(clean(doc), overwrite);
      status = `Saved as data/systems/${r.saved}`;
      confirm = false;
      onsaved(r.id);
    } catch (e) {
      status = e instanceof Rejected ? e.message : 'The server did not answer';
      confirm = e instanceof Rejected && e.message.includes('confirm');
    }
  }

  const where = (f) => f.where.split(' ')[0];
  const ROLE_FOR = { star: 'star', planet: 'world', dwarf: 'dwarf', moon: 'moon', station: 'station' };
</script>

<aside data-ui>
  <header>
    <h1>Workshop</h1>
    <button class="x" on:click={onexit} title="Back to levels">✕</button>
  </header>

  <section>
    <h2>System</h2>
    <label class="f"><span>Id (file name)</span><input bind:value={doc.system.id} on:change={changed} /></label>
    <label class="f"><span>Name</span><input bind:value={doc.system.name} on:change={changed} /></label>
    <label class="f"><span>Clock starts</span><input bind:value={doc.system.epoch} placeholder="J2000 or 2026-10-19T00:00:00Z" on:change={changed} /></label>
    <label class="f"><span>Frame</span>
      <select value={doc.frame?.kind ?? 'untied'} on:change={(e) => { doc.frame = { ...(doc.frame ?? {}), kind: e.target.value }; changed(); }}>
        {#each schema.frame_kinds as k}<option value={k}>{k}</option>{/each}
      </select>
    </label>
    {#if doc.frame?.kind === 'orbit'}
      <label class="f"><span>Plane of</span>
        <select value={doc.frame.of ?? ''} on:change={(e) => { doc.frame.of = e.target.value; changed(); }}>
          {#each binaries as b}<option value={b.id}>{b.name}</option>{/each}
        </select>
      </label>
    {/if}
    <details>
      <summary>Sky position (for sky-plane orbits and arcseconds)</summary>
      {#each [['ra_deg', 'RA °'], ['dec_deg', 'Dec °'], ['distance_pc', 'Distance pc']] as [k, lab]}
        <label class="f"><span>{lab}</span>
          <input type="number" step="any" value={doc.frame?.[k] ?? ''}
            on:change={(e) => { doc.frame ??= { kind: 'untied' }; e.target.value === '' ? delete doc.frame[k] : (doc.frame[k] = Number(e.target.value)); changed(); }} />
        </label>
      {/each}
    </details>
  </section>

  <section>
    <h2>Bodies <span class="n">{bodies.length}</span></h2>
    {#each bodies as b (b)}
      <div class="card" class:open={open === b.id} class:bad={errors.some((f) => where(f) === b.id)}>
        <button class="row" on:click={() => (open = open === b.id ? null : b.id)}>
          <i style="background:{b.display?.color ?? '#8a82a6'}"></i>
          <span class="nm">{b.name ?? b.id}</span>
          <span class="dim">{b.kind}{components[b.id] ? ` · in ${components[b.id]}` : b.parent ? ` · of ${b.parent}` : ' · root'}</span>
        </button>
        {#if open === b.id}
          <div class="body">
            <label class="f"><span>Id</span><input value={b.id} on:change={(e) => rename(b, e)} /></label>
            <label class="f"><span>Name</span><input bind:value={b.name} on:change={changed} /></label>
            <label class="f"><span>Kind</span>
              <select bind:value={b.kind} on:change={changed}>{#each schema.kinds as k}<option value={k}>{k}</option>{/each}</select>
            </label>
            {#if components[b.id]}
              <p class="dim">Orbits through the binary {components[b.id]}.</p>
            {:else}
              <label class="f"><span>Orbits</span>
                <select value={b.parent ?? ''} on:change={(e) => setParent(b, e.target.value)}>
                  <option value="">nothing: the root</option>
                  {#each ids.filter((i) => i !== b.id) as i}<option value={i}>{i}</option>{/each}
                </select>
              </label>
            {/if}
            <UnitField obj={b} units={schema.units.mass} label="Mass" onchange={changed} />
            <UnitField obj={b} units={schema.units.radius} label="Radius" onchange={changed} />
            {#if b.kind === 'star'}
              <label class="f"><span>Luminosity L☉</span><input type="number" step="any" bind:value={b.luminosity_lsun} on:change={changed} /></label>
              <label class="f"><span>Temperature K</span><input type="number" step="any" bind:value={b.teff_k} on:change={changed} /></label>
            {:else}
              <label class="f"><span>Orbis edge km</span><input type="number" step="any" placeholder="altitude; blank = none" bind:value={b.orbis_altitude_km} on:change={changed} /></label>
              <label class="f"><span>Inhabited</span><input type="checkbox" bind:checked={b.inhabited} on:change={changed} /></label>
            {/if}
            <label class="f"><span>Day, hours</span><input type="number" step="any" placeholder="negative = retrograde" bind:value={b.rotation_period_h} on:change={changed} /></label>
            <label class="f"><span>Display</span>
              <span class="pair">
                <select value={b.display?.role ?? ROLE_FOR[b.kind]} on:change={(e) => { b.display = { ...(b.display ?? {}), role: e.target.value }; changed(); }}>
                  {#each schema.roles as r}<option value={r}>{r}</option>{/each}
                </select>
                <input type="color" value={b.display?.color ?? '#8a82a6'} on:change={(e) => { b.display = { ...(b.display ?? {}), color: e.target.value }; changed(); }} />
              </span>
            </label>
            {#if b.parent && !components[b.id]}
              <h3>Orbit about {b.parent}</h3>
              <OrbitFields orbit={b.orbit} {schema} onchange={changed} />
            {/if}
            <button class="del" on:click={() => remove(b.id)}>{armed === b.id ? 'Click again to delete' : 'Delete body'}</button>
          </div>
        {/if}
      </div>
    {/each}
    <div class="add">
      <select bind:value={preset}>
        <option value="">Add a body from a preset…</option>
        {#each Object.entries(presetGroups) as [kind, list]}
          <optgroup label={kind}>{#each list as [id, label]}<option value={id}>{label}</option>{/each}</optgroup>
        {/each}
      </select>
      <button on:click={addBody} disabled={!preset}>Add</button>
    </div>
    <p class="hint">A new body orbits the open card, or the root.</p>
  </section>

  <section>
    <h2>Binaries <span class="n">{binaries.length}</span></h2>
    {#each binaries as b (b)}
      <div class="card" class:open={open === b.id} class:bad={errors.some((f) => where(f) === b.id)}>
        <button class="row" on:click={() => (open = open === b.id ? null : b.id)}>
          <i class="bary"></i><span class="nm">{b.name ?? b.id}</span><span class="dim">{b.primary} + {b.secondary}</span>
        </button>
        {#if open === b.id}
          <div class="body">
            <label class="f"><span>Id</span><input value={b.id} on:change={(e) => rename(b, e)} /></label>
            <label class="f"><span>Name</span><input bind:value={b.name} on:change={changed} /></label>
            {#each [['primary', 'Primary'], ['secondary', 'Secondary']] as [k, lab]}
              <label class="f"><span>{lab}</span>
                <select value={b[k]} on:change={(e) => { b[k] = e.target.value; const c = bodies.find((x) => x.id === b[k]); if (c) delete c.parent; changed(); }}>
                  {#each bodies as x}<option value={x.id}>{x.id}</option>{/each}
                </select>
              </label>
            {/each}
            <label class="f"><span>Orbits</span>
              <select value={b.parent ?? ''} on:change={(e) => { if (e.target.value) { b.parent = e.target.value; b.orbit ??= { a_au: 1000, e: 0, m0_deg: 0 }; } else { delete b.parent; delete b.orbit; } changed(); }}>
                <option value="">nothing: the root</option>
                {#each ids.filter((i) => i !== b.id && i !== b.primary && i !== b.secondary) as i}<option value={i}>{i}</option>{/each}
              </select>
            </label>
            <h3>{b.secondary} about {b.primary}</h3>
            <OrbitFields orbit={b.relative} {schema} onchange={changed} />
            {#if b.parent}
              <h3>Barycentre about {b.parent}</h3>
              <OrbitFields orbit={b.orbit} {schema} onchange={changed} />
            {/if}
            <button class="del" on:click={() => remove(b.id)}>{armed === b.id ? 'Click again to delete' : 'Delete binary'}</button>
          </div>
        {/if}
      </div>
    {/each}
    <button class="act" on:click={addBinary}>+ Binary pair</button>
  </section>

  <section class="check">
    {#if ok && !warnings.length}<p class="good">Builds cleanly.</p>{/if}
    {#each errors as f}<button class="err" on:click={() => (open = where(f))}><b>{f.where}</b> {f.message}</button>{/each}
    {#each warnings as f}<button class="warn" on:click={() => (open = where(f))}><b>{f.where}</b> {f.message}</button>{/each}
  </section>

  <footer>
    <button class="save" disabled={!ok} on:click={() => save(false)}>Save as {doc.system.id}.toml</button>
    {#if confirm}<button class="save over" on:click={() => save(true)}>Overwrite</button>{/if}
    {#if status}<p class="status">{status}</p>{/if}
  </footer>
</aside>

<style>
  aside {
    position: fixed; top: 64px; left: 20px; bottom: 20px; width: 420px; overflow: auto; z-index: 25;
    background: var(--panel); border-left: 1px solid var(--fuchsia); padding: 14px 16px; backdrop-filter: blur(6px);
  }
  header { display: flex; justify-content: space-between; align-items: baseline; }
  h1 { font-family: var(--display); font-weight: 600; font-size: 22px; margin: 0; }
  h2 { font-family: var(--display); font-weight: 400; font-size: 14px; color: var(--dim); margin: 0 0 8px; }
  h3 { font-family: var(--display); font-weight: 400; font-size: 12px; color: var(--dim); margin: 8px 0 2px; }
  .n { color: var(--violet); filter: brightness(1.5); margin-left: 6px; }
  section { margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--rule); display: grid; gap: 5px; }
  .f { display: grid; grid-template-columns: 7.5em 1fr; gap: 6px; align-items: center; }
  .f > span { color: var(--dim); }
  input, select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 2px 4px; min-width: 0; }
  input[type='checkbox'] { justify-self: start; accent-color: var(--violet); }
  input[type='color'] { padding: 0; height: 22px; width: 44px; }
  .pair { display: grid; grid-template-columns: 1fr auto; gap: 6px; }
  details summary { color: var(--dim); font-size: 11px; cursor: none; margin: 2px 0; }
  details[open] { display: grid; gap: 5px; }
  button { background: none; border: 0; color: var(--dim); font: inherit; text-align: left; padding: 2px 0; }
  button:hover:not(:disabled) { color: var(--ink); }
  button:disabled { opacity: 0.4; }
  .x:hover { color: var(--fuchsia); }
  .card { border-left: 1px solid var(--rule); padding-left: 8px; }
  .card.open { border-left-color: var(--violet); }
  .card.bad { border-left-color: var(--fuchsia); }
  .row { display: grid; grid-template-columns: 10px auto 1fr; gap: 8px; align-items: center; width: 100%; }
  .row i { width: 7px; height: 7px; transform: rotate(45deg); }
  .row i.bary { border: 1px solid var(--dim); }
  .nm { color: var(--ink); font-family: var(--display); font-size: 13px; }
  .dim { color: var(--dim); font-size: 11px; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  p.dim { text-align: left; margin: 0; }
  .body { display: grid; gap: 5px; padding: 6px 0 8px; }
  .del { font-size: 11px; color: var(--dim); justify-self: start; }
  .del:hover { color: var(--fuchsia) !important; }
  .add { display: grid; grid-template-columns: 1fr auto; gap: 8px; margin-top: 6px; }
  .add button, .act { color: var(--violet); filter: brightness(1.5); }
  .hint { margin: 0; color: var(--dim); font-size: 10px; }
  .check { gap: 3px; }
  .check button { font-size: 11px; line-height: 1.35; }
  .err { color: #ff9fcf; }
  .warn { color: #ffe3a6; }
  .good { color: #5fd38d; margin: 0; }
  footer { margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--rule); display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
  .save { color: var(--ink); font-family: var(--display); font-size: 14px; box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .over { color: var(--fuchsia); }
  .status { flex-basis: 100%; margin: 0; color: var(--dim); font-size: 11px; overflow-wrap: anywhere; }
</style>

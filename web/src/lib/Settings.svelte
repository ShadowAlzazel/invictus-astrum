<script>
  // Settings, in tabs, all kept in this browser:
  //   Display  every setting display.toml declares, grouped by its sections (nothing here knows what
  //            one means); the server's settings.toml under it
  //   Hotkeys  the key for each action (lib/keys.js): click one, then press its new key
  //   Game     the picture's switches (config.toml [picture]), sent with every picture asked for
  //   Combat   the commander's combat profiles (astrum/profiles.py), kept by the server: the root
  //            read-only, a copy of any made their own
  //   Adjutant what the tactical adjutant calls, and how (lib/adjutant.js), kept in this browser
  import { ACTIONS, bind, cap, keymap, resetKeys } from './keys.js';
  import { CALLS, DEFAULTS, TOKENS } from './adjutant.js';

  export let rules = {};
  export let values = {};
  export let onchange = () => {};      // (section, key, value)
  export let onreset = () => {};       // (section | null)
  export let onclose = () => {};
  export let status = '';
  export let game = {};                // the picture's switches: { key: bool }
  export let gameRules = {};           // astrum/switches.py: { key: { label, default, min, max, step } }
  export let ongame = () => {};        // (key, value | null: back to its default)
  export let tab = 'display';
  export let profiles = [];            // the player's: the shared ones (root first), then their own
  export let profileRules = {};        // { stances: {id: label}, ranges: {id: what}, targets: [...] }
  export let onprofile = async () => {};      // (profile): saved (a new one has no id); resolves to the saved one
  export let ondropprofile = async () => {};  // (id)
  export let adjutant = DEFAULTS;      // lib/adjutant.js config()
  export let onadjutant = () => {};    // (config)
  const adj = (k, v) => onadjutant({ ...adjutant, [k]: v });
  const call = (k, change) => onadjutant({ ...adjutant, calls: { ...adjutant.calls, [k]: { ...adjutant.calls[k], ...change } } });

  const TABS = [['display', 'Display'], ['hotkeys', 'Hotkeys'], ['game', 'Game'], ['combat', 'Combat'], ['adjutant', 'Adjutant']];
  const short = (label) => label?.split(':')[0] ?? '';

  // the profile shown, and the draft of it being edited (a shared one is copied first)
  let pick = 'root', draft = null, problem = '';
  $: shown = profiles.find((p) => p.id === pick) ?? profiles[0];
  $: if (shown) edit(shown);
  function edit(p) { draft = p.player ? structuredClone(p) : null; problem = ''; }
  function copy(p) { draft = { ...structuredClone(p), id: undefined, name: `${p.name} (mine)`, copy: true, player: '' }; problem = ''; }
  const fixed = (r) => typeof r === 'number';
  async function save() {
    const { id, name, targets, stance, range } = draft;
    try {
      const p = await onprofile({ id, name, targets, stance, range });
      pick = p.id;
    } catch (err) { problem = String(err.message ?? err); }
  }
  async function drop() {
    try { await ondropprofile(draft.id); pick = 'root'; } catch (err) { problem = String(err.message ?? err); }
  }
  const fmt = (spec, v) => (spec.type === 'float' ? Number(v).toFixed(spec.step < 0.1 ? 2 : 1) : v);
  const changed = (sec, k) => values[sec]?.[k] !== rules[sec].settings[k].default;

  let listening = null;                // the action waiting for its new key
  function rebind(e) {
    if (!listening) return;
    e.preventDefault(); e.stopPropagation();
    if (e.key !== 'Escape' && e.key !== 'Shift' && e.key.length === 1) bind(listening, e.key);
    listening = null;
  }
</script>

<svelte:window on:keydown|capture={rebind} />

<aside data-ui>
  <header>
    <h1>Settings</h1>
    <button class="x" on:click={onclose} title="Esc">✕</button>
  </header>
  <nav>
    {#each TABS as [id, name]}<button class:on={tab === id} on:click={() => (tab = id)}>{name}</button>{/each}
  </nav>

  {#if tab === 'display'}
    {#each Object.entries(rules) as [sec, group]}
      {#if Object.keys(group.settings).length}
        <section>
          <h2>{group.label}
            {#if Object.keys(group.settings).some((k) => changed(sec, k))}
              <button class="reset" on:click={() => onreset(sec)}>reset</button>
            {/if}
          </h2>
          {#each Object.entries(group.settings) as [k, spec]}
            {#if spec.type === 'bool'}
              <button class="toggle" class:on={values[sec]?.[k]} on:click={() => onchange(sec, k, !values[sec][k])}><i></i>{spec.label}</button>
            {:else if spec.type === 'text'}
              <label class="f"><span>{spec.label}</span>
                <select value={values[sec]?.[k]} on:change={(e) => onchange(sec, k, e.target.value)}>
                  {#each spec.choices ?? [] as c}<option value={c}>{c}</option>{/each}
                </select>
              </label>
            {:else}
              <label class="f" class:mod={changed(sec, k)}><span>{spec.label}</span>
                <input type="range" min={spec.min} max={spec.max} step={spec.step ?? (spec.type === 'int' ? 1 : 0.05)}
                  value={values[sec]?.[k]} on:input={(e) => onchange(sec, k, Number(e.target.value))} />
                <output>{fmt(spec, values[sec]?.[k])}</output>
              </label>
            {/if}
          {/each}
        </section>
      {/if}
    {/each}
    <footer>
      <button class="reset" on:click={() => onreset(null)}>Reset everything</button>
      <span class="status">{status}</span>
    </footer>
    <p class="hint">Kept in this browser. Defaults and ranges are in display.toml.</p>
  {:else if tab === 'hotkeys'}
    <section>
      {#each Object.entries(ACTIONS) as [a, d]}
        <div class="key" class:mod={$keymap[a] !== d.key}>
          <span>{d.label}</span>
          <button class:listening={listening === a} on:click={() => (listening = listening === a ? null : a)}>
            {listening === a ? 'press a key' : $keymap[a] ? cap($keymap[a]) : '—'}
          </button>
        </div>
      {/each}
    </section>
    <footer><button class="reset" on:click={resetKeys}>Reset keys</button></footer>
    <p class="hint">Kept in this browser. A key taken from another action leaves that one unbound. Esc always cancels; Shift steps finer.</p>
  {:else if tab === 'combat'}
    <section>
      <h2>Combat profiles</h2>
      <div class="pills">
        {#each profiles as p}<button class:on={p.id === pick && !draft?.copy} on:click={() => { pick = p.id; edit(p); }}>{p.name}</button>{/each}
        {#if draft?.copy}<button class="on">{draft.name}</button>{/if}
      </div>
    </section>
    {#if draft}
      <section>
        <label class="f"><span>Name</span><input class="name" bind:value={draft.name} /></label>
        <label class="f"><span title="Each unit standing in this profile, when none is ordered">Stance</span>
          <select bind:value={draft.stance}>{#each Object.entries(profileRules.stances ?? {}) as [k, label]}<option value={k} title={label}>{short(label)}</option>{/each}</select></label>
        <div class="f"><span title="Whom its stances engage">Targets</span>
          <div class="checks">{#each profileRules.targets ?? [] as k}
            <button class="toggle" class:on={draft.targets.includes(k)}
              on:click={() => (draft.targets = draft.targets.includes(k) ? draft.targets.filter((x) => x !== k) : [...draft.targets, k])}><i></i>{k}</button>{/each}</div></div>
        <h2>Ranges <span class="dim">what sets each stance off</span></h2>
        {#each Object.entries(profileRules.stances ?? {}).filter(([k]) => k !== 'hold-fire') as [k, label]}
          <label class="f rng" class:mod={draft.range[k] != null}><span title={label}>{short(label)}</span>
            <select value={draft.range[k] == null ? '' : fixed(draft.range[k]) ? 'km' : draft.range[k]}
              on:change={(e) => { const v = e.target.value; draft.range[k] = v === '' ? undefined : v === 'km' ? 50000 : v; draft = draft; }}>
              <option value="">the root's ({profiles[0]?.range[k]})</option>
              {#each Object.entries(profileRules.ranges ?? {}) as [r, what]}<option value={r} title={what}>{r}</option>{/each}
              <option value="km">km</option>
            </select>
            {#if fixed(draft.range[k])}<input class="km" type="number" min="1" step="1000" bind:value={draft.range[k]} />{:else}<output></output>{/if}
          </label>
        {/each}
      </section>
      <footer>
        <span>{#if !draft.copy}<button class="reset" on:click={drop}>Delete</button>{/if}</span>
        <span><button class="reset" on:click={() => edit(shown)}>Cancel</button> · <button class="save" on:click={save}>Save</button></span>
      </footer>
      {#if problem}<p class="hint bad">{problem}</p>{/if}
    {:else if shown}
      <section>
        <dl>
          <dt>Stance</dt><dd>{short(profileRules.stances?.[shown.stance])}</dd>
          <dt>Targets</dt><dd>{shown.targets.join(', ')}</dd>
          {#each Object.entries(shown.range) as [k, r]}<dt class="sub">{short(profileRules.stances?.[k])}</dt><dd>{fixed(r) ? `${r.toLocaleString()} km` : r}</dd>{/each}
        </dl>
      </section>
      <footer><span></span><button class="save" on:click={() => copy(shown)}>Make a copy of my own</button></footer>
    {/if}
    <p class="hint">Kept by the server, for this commander. {shown?.root ? 'The root is every unit\'s fallback and is not changed here. ' : ''}A
      range is read off each ship's own figures (sensor: her passive reach on a warm ship; dazzle; weapons: her focus battery's reach), or set in km.</p>
  {:else if tab === 'adjutant'}
    <section>
      <h2>Adjutant</h2>
      {#each [['on', 'On: she reads the picture and calls what changes'], ['voice', 'Say her calls aloud'], ['estimates', 'Her heading estimates on the tracks']] as [k, label]}
        <button class="toggle" class:on={adjutant[k]} on:click={() => adj(k, !adjutant[k])}><i></i>{label}</button>
      {/each}
      <label class="f"><span>Her name</span><input class="name" value={adjutant.name} on:change={(e) => adj('name', e.target.value)} /></label>
      <label class="f"><span>She calls you</span><input class="name" value={adjutant.role} on:change={(e) => adj('role', e.target.value)} /></label>
      <label class="f" class:mod={adjutant.low_fuel_pct !== DEFAULTS.low_fuel_pct}><span>Low fuel at</span>
        <input type="range" min="1" max="50" step="1" value={adjutant.low_fuel_pct} on:input={(e) => adj('low_fuel_pct', Number(e.target.value))} />
        <output>{adjutant.low_fuel_pct}%</output></label>
      <label class="f" class:mod={adjutant.group_km !== DEFAULTS.group_km}><span title="New tracks this close together are called as one group">One group within</span>
        <input class="km" type="number" min="0" step="10000" value={adjutant.group_km} on:change={(e) => adj('group_km', Number(e.target.value))} /><output>km</output></label>
    </section>
    {#each Object.entries(CALLS) as [k, c]}
      <section>
        <button class="toggle" class:on={adjutant.calls[k].on} on:click={() => call(k, { on: !adjutant.calls[k].on })}><i></i>{c.label} <span class="dim">[{k}]</span></button>
        <textarea rows="2" value={adjutant.calls[k].text} on:change={(e) => call(k, { text: e.target.value })}></textarea>
        {#if adjutant.calls[k].text !== c.text}<button class="reset" on:click={() => call(k, { text: c.text })}>back to the default</button>{/if}
      </section>
    {/each}
    <footer><button class="reset" on:click={() => onadjutant(DEFAULTS)}>Reset the adjutant</button></footer>
    <p class="hint">Kept in this browser. She reads only what this map is sent, in a worker of her own: nothing of hers reaches the
      server. Her heading estimates are positions as seen, differenced off the active bullseye. Tokens: {TOKENS.map((t) => `[${t}]`).join(' ')}</p>
  {:else}
    <section>
      <h2>Picture</h2>
      {#each Object.entries(gameRules) as [k, spec]}
        {#if typeof spec.default === 'number'}
          <label class="f" class:mod={(game[k] ?? spec.default) !== spec.default}><span>{spec.label}</span>
            <input type="range" min={spec.min} max={spec.max} step={spec.step} value={game[k] ?? spec.default} on:input={(e) => ongame(k, Number(e.target.value))} />
            <output>{game[k] ?? spec.default}</output>
          </label>
        {:else}
          <button class="toggle" class:on={game[k] ?? spec.default} class:mod={(game[k] ?? spec.default) !== spec.default}
            on:click={() => ongame(k, !(game[k] ?? spec.default))}><i></i>{spec.label}</button>
        {/if}
      {/each}
    </section>
    <footer><button class="reset" on:click={() => Object.keys(gameRules).forEach((k) => ongame(k, null))}>Back to config.toml</button></footer>
    <p class="hint">Kept in this browser and sent with every picture asked for: the simulation keeps everything either way;
      these only say what this map is shown. Defaults are config.toml [picture].</p>
  {/if}
</aside>

<style>
  aside {
    position: fixed; top: 64px; right: 20px; width: 400px; max-height: calc(100vh - 84px); overflow: auto; z-index: 45;
    background: var(--panel); border-left: 1px solid var(--fuchsia); padding: 14px 16px; backdrop-filter: blur(6px);
  }
  header { display: flex; justify-content: space-between; align-items: baseline; }
  h1 { font-family: var(--display); font-weight: 600; font-size: 22px; margin: 0; }
  nav { display: flex; gap: 16px; margin-top: 10px; border-bottom: 1px solid var(--rule); }
  nav button { padding: 4px 0; font-family: var(--display); font-size: 13px; letter-spacing: 0.1em; text-transform: uppercase;
               border-bottom: 2px solid transparent; margin-bottom: -1px; }
  nav button.on { color: var(--ink); border-bottom-color: var(--fuchsia); }
  h2 { font-family: var(--display); font-weight: 400; font-size: 14px; color: var(--dim); margin: 0 0 6px; display: flex; justify-content: space-between; }
  section { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--rule); display: grid; gap: 4px; }
  nav + section { border-top: 0; }
  button { background: none; border: 0; color: var(--dim); font: inherit; padding: 0; text-align: left; }
  button:hover { color: var(--ink); }
  .x:hover, .reset:hover { color: var(--fuchsia); }
  .reset { font-size: 11px; font-family: var(--mono); }
  .f { display: grid; grid-template-columns: 1fr 110px 3em; gap: 8px; align-items: center; }
  .f span { color: var(--dim); }
  .f.mod span, .key.mod span, .toggle.mod { color: var(--ink); }
  output { text-align: right; font-variant-numeric: tabular-nums; }
  select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; grid-column: span 2; }
  .toggle { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
  .toggle i { width: 8px; height: 8px; border: 1px solid var(--violet); flex: none; }
  .toggle.on { color: var(--ink); }
  .toggle.on i { background: var(--violet); }
  .key { display: grid; grid-template-columns: 1fr 7em; gap: 8px; align-items: center; padding: 2px 0; }
  .key span { color: var(--dim); }
  .key button { border: 1px solid var(--rule); padding: 1px 6px; text-align: center; font-family: var(--mono); font-size: 11px; color: var(--ink); }
  .key button.listening { border-color: var(--fuchsia); color: var(--fuchsia); }
  footer { margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--rule); display: flex; justify-content: space-between; }
  .status { color: var(--dim); font-size: 11px; }
  .hint { color: var(--dim); font-size: 10px; margin: 8px 0 0; }
  .hint.bad { color: var(--fuchsia); }
  .pills { display: flex; flex-wrap: wrap; gap: 4px 12px; }
  .pills button.on { color: var(--ink); text-decoration: underline var(--fuchsia); text-underline-offset: 4px; }
  .checks { display: flex; gap: 14px; grid-column: span 2; }
  input.name, input.km { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; padding: 1px 4px; min-width: 0; }
  input.name { grid-column: span 2; }
  textarea { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: 11px var(--mono); padding: 4px 6px; resize: vertical; }
  input.km { width: 100%; }
  .f.rng { grid-template-columns: 1fr 150px 6em; }
  .f.rng select { grid-column: auto; }
  .save { color: var(--ink); }
  .save:hover { color: var(--fuchsia); }
  .dim { color: var(--dim); font-size: 11px; }
  dl { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 8px; margin: 0; }
  dt { color: var(--dim); }
  dt.sub { padding-left: 10px; }
  dd { margin: 0; }
  input[type='range'] { appearance: none; background: transparent; width: 100%; height: 18px; margin: 0; }
  input[type='range']::-webkit-slider-runnable-track { height: 1px; background: var(--rule); }
  input[type='range']::-moz-range-track { height: 1px; background: var(--rule); }
  input[type='range']::-webkit-slider-thumb {
    appearance: none; width: 10px; height: 10px; margin-top: -5px; background: var(--void);
    border: 1.5px solid var(--fuchsia); transform: rotate(45deg);
  }
  input[type='range']::-moz-range-thumb {
    width: 8px; height: 8px; background: var(--void); border: 1.5px solid var(--fuchsia); border-radius: 0; transform: rotate(45deg);
  }
</style>

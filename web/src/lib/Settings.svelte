<script>
  // Settings, in tabs, all kept in this browser:
  //   Display  every setting display.toml declares, grouped by its sections (nothing here knows what
  //            one means); the server's settings.toml under it
  //   Hotkeys  the key for each action (lib/keys.js): click one, then press its new key
  //   Game     the picture's switches (config.toml [picture]), sent with every picture asked for
  import { ACTIONS, bind, cap, keymap, resetKeys } from './keys.js';

  export let rules = {};
  export let values = {};
  export let onchange = () => {};      // (section, key, value)
  export let onreset = () => {};       // (section | null)
  export let onclose = () => {};
  export let status = '';
  export let game = {};                // the picture's switches: { key: bool }
  export let gameRules = {};           // { key: { label, default } }
  export let ongame = () => {};        // (key, value | null: back to its default)
  export let tab = 'display';

  const TABS = [['display', 'Display'], ['hotkeys', 'Hotkeys'], ['game', 'Game']];
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
  {:else}
    <section>
      <h2>Picture</h2>
      {#each Object.entries(gameRules) as [k, spec]}
        {#if typeof spec.default === 'number'}
          <label class="f" class:mod={(game[k] ?? spec.default) !== spec.default}><span>{spec.label}</span>
            <input type="range" min="0" max="30" step="0.5" value={game[k] ?? spec.default} on:input={(e) => ongame(k, Number(e.target.value))} />
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

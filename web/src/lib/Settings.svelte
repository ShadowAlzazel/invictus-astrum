<script>
  // Every setting display.toml declares, grouped by its sections. Changes apply at once and are
  // saved to settings.toml on the server; nothing here knows what a setting means.
  export let rules = {};
  export let values = {};
  export let onchange = () => {};      // (section, key, value)
  export let onreset = () => {};       // (section | null)
  export let onclose = () => {};
  export let status = '';

  const fmt = (spec, v) => (spec.type === 'float' ? Number(v).toFixed(spec.step < 0.1 ? 2 : 1) : v);
  const changed = (sec, k) => values[sec]?.[k] !== rules[sec].settings[k].default;
</script>

<aside data-ui>
  <header>
    <h1>Settings</h1>
    <button class="x" on:click={onclose} title="Esc or ,">✕</button>
  </header>
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
  <p class="hint">Saved to settings.toml. Defaults and ranges are in display.toml.</p>
</aside>

<style>
  aside {
    position: fixed; top: 64px; right: 20px; width: 380px; max-height: calc(100vh - 84px); overflow: auto; z-index: 45;
    background: var(--panel); border-left: 1px solid var(--fuchsia); padding: 14px 16px; backdrop-filter: blur(6px);
  }
  header { display: flex; justify-content: space-between; align-items: baseline; }
  h1 { font-family: var(--display); font-weight: 600; font-size: 22px; margin: 0; }
  h2 { font-family: var(--display); font-weight: 400; font-size: 14px; color: var(--dim); margin: 0 0 6px; display: flex; justify-content: space-between; }
  section { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--rule); display: grid; gap: 4px; }
  button { background: none; border: 0; color: var(--dim); font: inherit; padding: 0; text-align: left; }
  button:hover { color: var(--ink); }
  .x:hover, .reset:hover { color: var(--fuchsia); }
  .reset { font-size: 11px; font-family: var(--mono); }
  .f { display: grid; grid-template-columns: 1fr 110px 3em; gap: 8px; align-items: center; }
  .f span { color: var(--dim); }
  .f.mod span { color: var(--ink); }
  output { text-align: right; font-variant-numeric: tabular-nums; }
  select { background: var(--void); color: var(--ink); border: 1px solid var(--rule); font: inherit; grid-column: span 2; }
  .toggle { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
  .toggle i { width: 8px; height: 8px; border: 1px solid var(--violet); flex: none; }
  .toggle.on { color: var(--ink); }
  .toggle.on i { background: var(--violet); }
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

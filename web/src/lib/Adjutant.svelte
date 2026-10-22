<script>
  // The tactical adjutant on the map: her log (her calls, newest last), her voice if asked for, and
  // her heading estimates drawn on the tracks. She runs in a worker of her own (adjutant.worker.js),
  // handed every picture's text as the map receives it: off, there is no worker and no cost.
  import { onDestroy } from 'svelte';
  import { rgba } from './symbols.js';

  export let map = null;
  export let style = null;
  export let stream = null;             // the map's StateStream: she reads what it is sent
  export let cfg = null;                // adjutant.js config()
  export let context = null;            // { key, units, bullseye }: the side she serves
  export let bullseye = null;           // { id, name }: the active one
  export let state = null;              // the map's picture as it stands, merged: hers to start from
  export let onchange = () => {};       // (cfg): her settings changed here (her voice)

  let worker = null, key = null, last = null, log = [], open = false, est = {}, canvas, ctx, unhook, W = 0, H = 0;
  // folded: her panel down to its title (her calls still kept, said, and drawn); kept in this browser
  let folded = false;
  try { folded = localStorage.getItem('astrum.adjutant.folded') === '1'; } catch { /* not kept */ }
  function fold() { folded = !folded; try { localStorage.setItem('astrum.adjutant.folded', folded ? '1' : '0'); } catch { /* for this visit */ } }
  const KEEP = 60, DRAWN = 4;

  function start() {
    stop();
    worker = new Worker(new URL('./adjutant.worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = ({ data }) => {
      if (data.calls.length) {
        log = [...log, ...data.calls].slice(-KEEP);
        if (cfg.voice) data.calls.forEach(speak);
      }
      est = data.estimates ?? {};
    };
    worker.postMessage({ kind: 'start', cfg, context: { units: context.units, bullseye } });
    // what came before her, unless the side changed (the map's picture is still the other side's: a whole one follows)
    if (state && (last == null || last === context.key)) worker.postMessage({ kind: 'picture', text: JSON.stringify({ ...state, full: true }) });
    key = last = context.key; told = bullseye?.id;
    if (stream) stream.tap = (text) => worker?.postMessage({ kind: 'picture', text });
  }
  function stop() {
    worker?.terminate();
    worker = null; key = null; est = {};
    if (stream) stream.tap = null;
  }
  $: on = !!(cfg?.on && context && map);
  $: if (on && context.key !== key) { log = []; start(); } else if (!on && worker) stop();
  $: worker?.postMessage({ kind: 'cfg', cfg });
  let told = null;                       // the bullseye she was last told (a new one starts her estimates again)
  $: if (worker && bullseye && bullseye.id !== told) { told = bullseye.id; worker.postMessage({ kind: 'bullseye', bullseye }); }

  function speak(c) {
    const s = window.speechSynthesis;
    if (!s) return;
    if (s.pending) s.cancel();                         // behind: the newest call, not a queue of old ones
    const u = new SpeechSynthesisUtterance(c.text.replace(/-/g, ' '));
    u.rate = 1.1;
    s.speak(u);
  }
  // the call's moment as UTC (TDB seconds since J2000; UTC is some 69 s behind)
  const clock = (t) => new Date(Date.UTC(2000, 0, 1, 12) + (t - 69.184) * 1000).toISOString().slice(11, 16);

  // ---- her heading estimates: from each track drawn alone, along where it seems to go, to scale: a
  // notch where it would be in 10 min, 1 h and 1 day (a reticle's marks), a chevron past the last; in
  // the track's own colour (its affiliation's), as opaque as Settings, Adjutant says
  const MARKS_S = [600, 3600, 86400], MIN_PX = 26, TICK = 4, CHEVRON = 7;
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    const alpha = cfg?.estimate_alpha ?? 0;
    if (!on || alpha <= 0 || !map?.state || !style) return;
    const drawn = new Set((map.marks ?? []).map((m) => m.id));        // a track folded into a group has none of its own
    ctx.lineWidth = 1.2;
    for (const [id, v] of Object.entries(est)) {
      if (!drawn.has(id)) continue;
      const p = map.position({ kind: 'contact', id }), s = p && map.project(p);
      const marks = s && MARKS_S.map((T) => map.project([p[0] + v[0] * T, p[1] + v[1] * T, p[2] + v[2] * T]));
      if (!marks || marks.some((m) => !m)) continue;
      const day = marks[2], L = Math.hypot(day.x - s.x, day.y - s.y);
      if (L < 1e-6) continue;
      const ux = (day.x - s.x) / L, uy = (day.y - s.y) / L, reach = Math.max(L, MIN_PX) + CHEVRON + 4;
      const tip = { x: s.x + ux * reach, y: s.y + uy * reach };
      const aff = style.affiliation[map.state.tracks?.[id]?.affiliation] ?? style.affiliation.unknown;
      ctx.strokeStyle = rgba(aff.color, alpha);
      ctx.setLineDash([5, 3]);
      ctx.beginPath(); ctx.moveTo(s.x + ux * 9, s.y + uy * 9); ctx.lineTo(tip.x, tip.y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      let last = 9;                                     // notches: each far enough from the mark and the one before to read
      for (const m of marks) {
        const d = Math.hypot(m.x - s.x, m.y - s.y);
        if (d < last + 5) continue;
        ctx.moveTo(m.x - uy * TICK, m.y + ux * TICK); ctx.lineTo(m.x + uy * TICK, m.y - ux * TICK);
        last = d;
      }
      ctx.moveTo(tip.x - ux * CHEVRON - uy * CHEVRON * 0.6, tip.y - uy * CHEVRON + ux * CHEVRON * 0.6);
      ctx.lineTo(tip.x, tip.y);
      ctx.lineTo(tip.x - ux * CHEVRON + uy * CHEVRON * 0.6, tip.y - uy * CHEVRON - ux * CHEVRON * 0.6);
      ctx.stroke();
    }
  }
  $: if (canvas && !ctx) { ctx = canvas.getContext('2d'); resize(); window.addEventListener('resize', resize); }
  $: if (map && ctx && !unhook) unhook = map.onFrame(draw);
  onDestroy(() => { stop(); unhook?.(); window.removeEventListener('resize', resize); window.speechSynthesis?.cancel(); });
</script>

<canvas bind:this={canvas} aria-hidden="true"></canvas>
{#if on}
  <div class="adj" data-ui>
    <header>
      <button class="title" on:click={() => (open = !open)} title={open ? 'Fewer calls' : 'Her whole log'}>Adjutant · {cfg.name}<i class:open></i></button>
      <span class="right">
        <button class="voice" class:on={cfg.voice} on:click={() => onchange({ ...cfg, voice: !cfg.voice })} title="Say her calls aloud">voice</button>
        <button class="fold" on:click={fold} title={folded ? 'Show her calls' : 'Fold her panel away'}><i class:folded></i></button>
      </span>
    </header>
    {#if folded}
    {:else if log.length}
      <ol class:open>
        {#each open ? log : log.slice(-DRAWN) as c (c)}
          <li class={c.kind}><time>{clock(c.t)}</time>{c.text}</li>
        {/each}
      </ol>
    {:else}
      <p class="quiet">Nothing to report.</p>
    {/if}
  </div>
{/if}

<style>
  canvas { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 18; }
  .adj { background: var(--panel); border-left: 1px solid var(--cyan, #9ff0ff); padding: 8px 12px; display: grid; gap: 6px; }
  header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .title { background: none; border: 0; padding: 0; color: var(--dim); font-family: var(--display); font-size: 11px; letter-spacing: 0.14em;
           text-transform: uppercase; display: flex; align-items: center; gap: 8px; }
  .title:hover { color: var(--ink); }
  .title i { width: 5px; height: 5px; border-right: 1px solid currentColor; border-bottom: 1px solid currentColor; transform: rotate(-135deg); margin-top: 3px; }
  .title i.open { transform: rotate(45deg); margin-top: -2px; }
  .right { display: flex; align-items: center; gap: 8px; }
  .fold { background: none; border: 0; padding: 2px 3px; color: var(--dim); display: flex; }
  .fold:hover { color: var(--ink); }
  .fold i { width: 6px; height: 6px; border-right: 1px solid currentColor; border-bottom: 1px solid currentColor; transform: rotate(45deg); margin-top: -3px; }
  .fold i.folded { transform: rotate(-135deg); margin-top: 3px; }
  .voice { background: none; border: 1px solid var(--rule); color: var(--dim); font-size: 10px; padding: 0 6px; }
  .voice.on { color: var(--ink); border-color: var(--cyan, #9ff0ff); }
  ol { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; font-size: 11px; line-height: 1.35; }
  ol.open { max-height: 40vh; overflow-y: auto; }
  li { color: var(--ink); overflow-wrap: anywhere; }
  li time { color: var(--dim); font-variant-numeric: tabular-nums; margin-right: 6px; }
  li.on-unit-lost { color: var(--dim); }
  li.on-ship-low-fuel { color: #ffd27a; }
  li.on-picture { color: var(--dim); }
  .quiet { margin: 0; color: var(--dim); font-size: 11px; }
</style>

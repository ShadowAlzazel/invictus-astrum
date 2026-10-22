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

  // ---- her heading estimates: a short dashed vector from each track drawn alone, along where it seems to go
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!cfg?.estimates || !map?.state) return;
    const color = style?.palette?.cyan ?? '#9ff0ff';
    ctx.strokeStyle = rgba(color, 0.75); ctx.fillStyle = rgba(color, 0.75); ctx.lineWidth = 1.2;
    const drawn = new Set((map.marks ?? []).map((m) => m.id));        // a track folded into a group has none of its own
    for (const [id, v] of Object.entries(est)) {
      if (!drawn.has(id)) continue;
      const p = map.position({ kind: 'contact', id }), s = p && map.project(p);
      const q = s && map.project([p[0] + v[0] * 3600, p[1] + v[1] * 3600, p[2] + v[2] * 3600]);
      if (!q) continue;
      const dx = q.x - s.x, dy = q.y - s.y, n = Math.hypot(dx, dy);
      if (n < 1e-6) continue;
      const ux = dx / n, uy = dy / n, L = 34, x = s.x + ux * (10 + L), y = s.y + uy * (10 + L);
      ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.moveTo(s.x + ux * 10, s.y + uy * 10); ctx.lineTo(x, y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - ux * 7 - uy * 4, y - uy * 7 + ux * 4); ctx.lineTo(x - ux * 7 + uy * 4, y - uy * 7 - ux * 4); ctx.fill();
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
      <button class="voice" class:on={cfg.voice} on:click={() => onchange({ ...cfg, voice: !cfg.voice })} title="Say her calls aloud">voice</button>
    </header>
    {#if log.length}
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

<script>
  // Firing arcs, schematic: the hull as a line of stations (truss, citadel, stern), not a silhouette.
  // Plan view from above and profile from the side, bow to the right. The spine bears along the
  // heading inside its trim cone; turrets train freely, dorsal mounts above the hull and ventral
  // below; strips face forward from the wing edges.
  export let cls;

  const W = 640, M = 18;
  $: L = len(cls);
  $: span = (() => { const r = cls.hull.find((x) => x.key === 'wingspan_m'); const v = r?.named?.spread ?? r?.q; return v?.lo ?? L * 0.2; })();
  $: lay = cls.layout ?? {};
  $: k = (W * 0.6) / L;                                   // px per metre
  $: x = (at) => M + (L - at) * k;                        // bow (0 m) to the right
  $: stacks = cls.batteries.filter((b) => b.kind === 'stack');
  $: turrets = cls.batteries.filter((b) => b.kind === 'turret' && b.layout?.mounts?.some((m) => m.at_m != null));
  $: strips = cls.batteries.filter((b) => b.kind === 'strip');
  $: citadel = lay.citadel_m ?? null;
  $: aperture = citadel ? citadel[0] : (lay.truss_m ?? 0);

  function len(c) { const r = c.hull.find((x) => x.key === 'length_m'); return r?.q?.lo ?? 300; }
  const rad = (d) => (d * Math.PI) / 180;
  // a wedge from (cx, cy) along angle a (deg, 0 = bow, positive = up or to port) with half-width h
  function wedge(cx, cy, a, h, r) {
    const p = (t) => `${cx + r * Math.cos(rad(t))},${cy - r * Math.sin(rad(t))}`;
    const big = h * 2 > 180 ? 1 : 0;
    return `M${cx},${cy} L${p(a - h)} A${r},${r} 0 ${big} 0 ${p(a + h)} Z`;
  }
  const R_TUR = 22, R_OPT = 46;
  $: views = [['Plan', 'from above', Math.max(118, span * k + 52)], ['Profile', 'from the side, dorsal up', 104]];
  $: coneLen = W - M - x(aperture);
</script>

{#if cls.layout && (stacks.length || turrets.length || strips.length)}
  <div class="arcs">
    {#each views as [view, sub, H], vi}
      {@const y0 = H / 2}
      <figure>
        <figcaption><b>{view}</b> {sub}</figcaption>
        <svg viewBox="0 0 {W} {H}" role="img" aria-label="{view} of firing arcs">
          <!-- stations: truss, citadel, stern -->
          <line class="axis" x1={M} y1={y0} x2={W - M} y2={y0} />
          <line class="stern" x1={x(L)} y1={y0} x2={x(citadel ? citadel[1] : L)} y2={y0} />
          {#if citadel}<rect class="cit" x={x(citadel[1])} y={y0 - 3} width={(citadel[1] - citadel[0]) * k} height="6" />{/if}
          {#if lay.truss_m}<line class="truss" x1={x(lay.truss_m)} y1={y0} x2={x(0)} y2={y0} />{/if}
          {#each [[0, 'bow'], [L, 'stern']] as [m, t]}<line class="tick" x1={x(m)} y1={y0 - 7} x2={x(m)} y2={y0 + 7} /><text class="lbl" x={x(m)} y={y0 + 18} text-anchor="middle">{t}</text>{/each}

          <!-- the spine: along the heading, inside its trim cone -->
          {#each stacks as s}
            {@const h = s.layout?.trim_deg ?? 2}
            <path class="spine" d={wedge(x(aperture), y0, 0, h, coneLen)} />
            <line class="spine-line" x1={x(aperture)} y1={y0} x2={W - M} y2={y0} />
            <text class="lbl spine-t" x={W - M} y={y0 - 12} text-anchor="end">spine ±{h}°</text>
          {/each}

          <!-- turrets: free train; above and below the hull in profile -->
          {#each turrets as b}
            {#each b.layout.mounts.filter((m) => m.at_m != null) as m}
              {@const up = m.side !== 'ventral'}
              {@const cy = vi === 0 ? y0 + (m.side === 'port' ? -10 : m.side === 'starboard' ? 10 : 0) : y0 + (up ? -7 : 7)}
              {#if vi === 0}
                <circle class="tur-arc" cx={x(m.at_m)} cy={cy} r={R_TUR} />
              {:else}
                <path class="tur-arc" d={wedge(x(m.at_m), cy, up ? 90 : -90, 90, R_TUR)} />
              {/if}
              <rect class="tur" class:quad={m.guns >= 4} x={x(m.at_m) - (m.guns >= 4 ? 4 : 3)} y={cy - (m.guns >= 4 ? 4 : 3)}
                    width={m.guns >= 4 ? 8 : 6} height={m.guns >= 4 ? 8 : 6} />
            {/each}
          {/each}

          <!-- strips: forward from the wing edges -->
          {#each strips as s}
            {#if lay.wing_at_m != null}
              {#each vi === 0 ? [-1, 1] : [0] as side}
                {@const cy = y0 + side * (span / 2) * k}
                <path class="opt-arc" d={wedge(x(lay.wing_at_m), vi === 0 ? cy : y0 - 3, 0, 60, R_OPT)} />
                <circle class="opt" cx={x(lay.wing_at_m)} cy={vi === 0 ? cy : y0 - 3} r="2.5" />
              {/each}
            {/if}
          {/each}
          <text class="lbl" x={W - M} y={12} text-anchor="end">{vi ? 'dorsal' : 'port'}</text>
          <text class="lbl" x={W - M} y={H - 5} text-anchor="end">{vi ? 'ventral' : 'starboard'}</text>
        </svg>
      </figure>
    {/each}
    <div class="legend">
      {#if stacks.length}<span><i class="sw spine"></i>Spine: aimed by heading, trimmed ±{stacks[0].layout?.trim_deg ?? 2}° a channel</span>{/if}
      {#if turrets.length}<span><i class="sw tur"></i>Turrets: train freely; dorsal mounts bear above the hull, ventral below</span>{/if}
      {#if strips.length}<span><i class="sw opt"></i>Strips: ±60° off the panel normal, est.</span>{/if}
    </div>
    <p class="cap">Schematic, not a silhouette: stations along the hull in metres from the bow; mount stations est. Turret arcs ignore hull shadow.</p>
  </div>
{/if}

<style>
  .arcs { display: grid; gap: 6px; }
  figure { margin: 0; background: rgba(255, 255, 255, 0.025); border: 1px solid rgba(255, 255, 255, 0.08); }
  figcaption { padding: 5px 10px 0; font-size: 11px; color: #9a9aa6; }
  figcaption b { color: #ececf0; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; margin-right: 6px; }
  svg { display: block; width: 100%; height: auto; }
  .axis { stroke: rgba(255, 255, 255, 0.12); stroke-width: 1; }
  .truss { stroke: #9a9aa6; stroke-width: 1.5; stroke-dasharray: 4 3; }
  .stern { stroke: #9a9aa6; stroke-width: 1.5; }
  .cit { fill: rgba(236, 236, 240, 0.85); }
  .tick { stroke: #5d5d68; }
  .lbl { fill: #6f6f7a; font: 10px 'Barlow', sans-serif; }
  .spine { fill: rgba(250, 31, 153, 0.22); stroke: rgba(250, 31, 153, 0.7); stroke-width: 0.8; }
  .spine-line { stroke: #fa1f99; stroke-width: 1.4; }
  .spine-t { fill: #fa1f99; }
  .tur-arc { fill: rgba(159, 240, 255, 0.07); stroke: rgba(159, 240, 255, 0.45); stroke-width: 0.8; stroke-dasharray: 3 3; }
  .tur { fill: #9ff0ff; }
  .opt-arc { fill: rgba(236, 236, 240, 0.08); stroke: rgba(236, 236, 240, 0.45); stroke-width: 0.8; }
  .opt { fill: #ececf0; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 11px; color: #9a9aa6; }
  .sw { display: inline-block; width: 12px; height: 8px; margin-right: 6px; vertical-align: middle; }
  .sw.spine { background: #fa1f99; }
  .sw.tur { background: #9ff0ff; }
  .sw.opt { background: #ececf0; }
  .cap { margin: 0; font-size: 10px; color: #6f6f7a; }
</style>

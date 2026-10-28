// The game clock as the map shows it: TDB seconds since J2000 (as the server's), its warp in game
// seconds a wall second, and the steps [ and ] go through.
export const WARPS = [[1, '1×'], [5, '5×'], [10, '10×'], [60, '1 min/s'], [600, '10 min/s'], [1800, '30 min/s'], [3600, '1 h/s'],
                      [7200, '2 h/s'], [21600, '6 h/s'], [86400, '1 d/s'], [604800, '1 wk/s'], [2629800, '1 mo/s'], [31557600, '1 yr/s']];
export const warpLabel = (w) => WARPS.find(([s]) => s === w)?.[1] ?? `${w}×`;
// the next step up or down from any warp
export function stepWarp(w, up) {
  const next = up ? WARPS.find(([s]) => s > w + 1e-9) : [...WARPS].reverse().find(([s]) => s < w - 1e-9);
  return next ? next[0] : w;
}
// the battle tick (how often an engaged ship is looked at), as the clock says it, and the next of its choices
export const tickLabel = (s) => (s >= 60 ? `${s / 60} min` : `${s} s`);
export function nextTick(clock) {
  const ts = clock?.ticks ?? [];
  return ts.length ? ts[(ts.indexOf(clock.tick_s) + 1) % ts.length] : clock?.tick_s;
}
// a moment as UTC (TDB runs some 69 s ahead of it)
export const utcOf = (t) => new Date(Date.UTC(2000, 0, 1, 12) + (t - 69.184) * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

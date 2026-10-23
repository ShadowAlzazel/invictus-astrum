// How fast the map's frames move, off its own pictures (nothing asked of the server): each
// bullseye's origin, from the last two pictures it came in that moved the clock on (paused, or
// the clock set back, the last known stands). A point at rest in a bullseye moves as its origin.
export class Motion {
  constructor() { this.last = null; this.v = {}; }
  feed(s) {
    const was = this.last;
    if (!s.bullseyes) return;
    if (was && s.t > was.t + 1e-6) {
      for (const [bid, b] of Object.entries(s.bullseyes ?? {})) {
        const o = was.origins[bid];
        if (o) this.v[bid] = [0, 1, 2].map((k) => (b.origin[k] - o[k]) / (s.t - was.t));
      }
    }
    if (!was || s.t > was.t + 1e-6 || s.t < was.t - 1e-6) {
      this.last = { t: s.t, origins: Object.fromEntries(Object.entries(s.bullseyes ?? {}).map(([k, b]) => [k, b.origin])) };
    }
  }
  of(bid) { return this.v[bid] ?? [0, 0, 0]; }      // km/s
}

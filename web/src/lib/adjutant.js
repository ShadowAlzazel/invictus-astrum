// The tactical adjutant: reads the side's picture as the map was sent it, and says what changed in
// it, by templates the commander can rewrite (Settings, Adjutant). She lives in a worker of her own
// (adjutant.worker.js), fed every picture's text as it arrives: nothing she does touches the server,
// and she knows only what the map was told. Her heading estimates are hers alone: positions as seen,
// differenced off the active bullseye, so a ship parked at Earth holds rather than tracks east.

export const CALLS = {
  'on-picture': { label: 'The picture on taking over', text: '[role], [name]. Picture: [tracks].' },
  'on-new-track': { label: 'A new track', text: '[role], [name]. [contact-type], [bullseye], [azimuth] for [range]. [eve] [elevation]. [direction]. [declare].' },
  'on-identified': { label: 'A track identified', text: '[role], [name]. [track] identified: [class], [declare].' },
  'on-unit-lost': { label: 'A track lost', text: '[role], [name]. [track] lost, last [bullseye] [azimuth] for [range].' },
  'on-ship-low-fuel': { label: 'A ship or formation low on fuel', text: '[role], [name]. [unit], bingo fuel, [fuel] percent.' },
};
export const TOKENS = ['role', 'name', 'contact-type', 'declare', 'class', 'track', 'count', 'tracks', 'bullseye', 'azimuth', 'range',
                       'eve', 'elevation', 'direction', 'speed', 'unit', 'fuel'];

export const DEFAULTS = {
  on: true, voice: false, estimates: true, name: 'Eva', role: 'Commander',
  low_fuel_pct: 10, group_km: 100000, hold_s: 2,
  calls: Object.fromEntries(Object.entries(CALLS).map(([k, c]) => [k, { on: true, text: c.text }])),
};
export function config(saved) {             // what was kept, over the defaults
  const s = saved ?? {};
  return { ...DEFAULTS, ...s, calls: Object.fromEntries(Object.keys(CALLS).map((k) => [k, { ...DEFAULTS.calls[k], ...(s.calls?.[k] ?? {}) }])) };
}

// ---- spoken figures ------------------------------------------------------------------------------
const DIGIT = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'niner'];
const ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve',
              'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];
export const digits = (deg) => String(Math.round(((deg % 360) + 360) % 360) % 360).padStart(3, '0').split('').map((d) => DIGIT[d]).join('-');
export function words(n) {                  // 0–999, as said: three-hundred, forty-two, one-hundred-twenty
  n = Math.round(n);
  if (n < 20) return ONES[n];
  if (n < 100) return TENS[Math.floor(n / 10)] + (n % 10 ? `-${ONES[n % 10]}` : '');
  return `${ONES[Math.floor(n / 100)]}-hundred` + (n % 100 ? `-${words(n % 100)}` : '');
}
const decimal = (x) => (x >= 10 ? words(Math.min(999, Math.round(x))) : `${words(Math.floor(x))}-point-${ONES[Math.round((x % 1) * 10) % 10]}`);
const AU_KM = 149597870.7;
export function spokenRange(km) {
  if (km < 1000) return `${words(Math.round(km / 10) * 10)} kilometres`;
  if (km < 999500) return `${words(km / 1000)} thousand`;
  if (km < 0.05 * AU_KM) return `${decimal(km / 1e6)} million`;
  return `${decimal(km / AU_KM)} AU`;
}
const POINTS = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'];

// ---- the bullseye's axes: 000, 270, Eve (as the map reads them) ------------------------------------
function aer(b, d) {
  const [ref, left, up] = b.axes;
  const x = d[0] * ref[0] + d[1] * ref[1] + d[2] * ref[2], y = d[0] * left[0] + d[1] * left[1] + d[2] * left[2];
  const z = d[0] * up[0] + d[1] * up[1] + d[2] * up[2], r = Math.hypot(x, y, z);
  return { az: ((Math.atan2(-y, x) * 180) / Math.PI + 360) % 360, el: r ? (Math.asin(z / r) * 180) / Math.PI : 0, r };
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

export function fill(text, v) {             // a template with its tokens, empty sentences dropped
  const out = text.replace(/\[([a-z-]+)\]/g, (m, k) => (k in v ? v[k] ?? '' : m));
  return out.split(/(?<=[.!?])\s+/).map((s) => s.replace(/\s+/g, ' ').replace(/\s+([.,:;!?])/g, '$1').replace(/,(\s*[.,:;!?])/g, '$1').trim())
    .filter((s) => /[A-Za-z0-9]/.test(s)).map((s) => s[0].toUpperCase() + s.slice(1)).join(' ');
}

// ---- the officer: one side's picture, call by call ------------------------------------------------
const SAMPLE_S = 60, KEEP = 24, WINDOW_S = 3600, MIN_SPAN_S = 120;

export class Officer {
  constructor(cfg, context) {
    this.cfg = config(cfg);
    this.context(context ?? {});
  }
  context({ units = [], bullseye = { id: 'system', name: 'centre' } } = {}) {
    this.units = new Map(units.map((u) => [u.id, u]));       // the side's own: { id, callsign, parent, ship }
    this.bull = bullseye;
    this.ships = {}; this.tracks = {}; this.pos = {}; this.t = null; this.bulls = {};
    this.known = new Map();          // track -> { said, lost, stage, seen (wall), by }
    this.low = new Set();            // own ships called low on fuel
    this.hist = new Map();           // track -> [[t, p - bullseye origin]]
    this.started = false;
  }
  bullseye(b) { this.bull = b; this.hist.clear(); }

  // a picture as the map was sent it (ships merged one level deep, tracks when they change)
  feed(s, wall = Date.now() / 1000) {
    if (s.full) this.ships = {};
    for (const [id, d] of Object.entries(s.ships ?? {})) {
      const p = this.ships[id] ?? {}, m = { ...p };
      for (const [k, v] of Object.entries(d)) m[k] = v && typeof v === 'object' && !Array.isArray(v) && p[k] && typeof p[k] === 'object' ? { ...p[k], ...v } : v;
      this.ships[id] = m;
    }
    if (s.tracks) this.tracks = s.tracks; else if (s.full) this.tracks = {};
    this.pos = s.contacts ?? {}; this.bulls = s.bullseyes ?? {};
    if (this.t != null && s.t < this.t - 1) this.hist.clear();      // the clock went back
    this.t = s.t;
    const b = this.bulls[this.bull.id];
    if (b) for (const id of Object.keys(this.tracks)) {
      const p = this.pos[id];
      if (!p) continue;
      const h = this.hist.get(id) ?? [];
      if (!h.length || s.t - h[h.length - 1][0] >= SAMPLE_S) { h.push([s.t, sub(p, b.origin)]); if (h.length > KEEP) h.shift(); this.hist.set(id, h); }
    }
    this.wall = wall;
  }

  // her estimate of a track's motion off the bullseye (km/s, system axes), from what was seen of her
  estimate(id) {
    const h = this.hist.get(id);
    if (!h || h.length < 2) return null;
    const [t1, p1] = h[h.length - 1];
    const first = h.find(([t]) => t >= t1 - WINDOW_S) ?? h[0];
    const dt = t1 - first[0];
    return dt >= MIN_SPAN_S ? sub(p1, first[1]).map((x) => x / dt) : null;
  }
  estimates() {
    const out = {};
    for (const [id, d] of Object.entries(this.tracks)) if (!d.old && !(d.status ?? []).length) { const v = this.estimate(id); if (v) out[id] = v; }
    return out;
  }

  where(p) {                                    // bullseye, azimuth, range, eve, elevation
    const b = this.bulls[this.bull.id];
    if (!b || !p) return {};
    const { az, el, r } = aer(b, sub(p, b.origin));
    const level = Math.abs(el) < 0.5;
    return { bullseye: this.bull.name, azimuth: digits(az), range: spokenRange(r), eve: level ? 'Level' : el > 0 ? 'Eve' : 'Haid',
             elevation: level ? '' : digits(Math.abs(el)) };
  }
  direction(v) {
    const b = this.bulls[this.bull.id];
    if (!v || !b) return {};
    const { az, el } = aer(b, v), speed = Math.hypot(...v);
    if (speed < 0.05) return { direction: 'holding', speed: `${speed.toFixed(2)} km/s` };
    const dir = Math.abs(el) > 60 ? `track ${el > 0 ? 'Eve' : 'Haid'}` : `track ${POINTS[Math.round(az / 45) % 8]}`;
    return { direction: dir, speed: `${speed < 10 ? speed.toFixed(1) : Math.round(speed)} km/s` };
  }
  declare(d) { return d.affiliation === 'hostile' ? 'hostile' : d.affiliation === 'friend' ? 'friendly' : 'bogey'; }

  say(kind, v) {
    const c = this.cfg.calls[kind];
    return c?.on ? { kind, t: this.t, text: fill(c.text, { role: this.cfg.role, name: this.cfg.name, ...v }) } : null;
  }

  // what to say now: every change since she last spoke, at most once each
  calls(wall = this.wall ?? Date.now() / 1000) {
    const out = [], cfg = this.cfg;
    const live = (d) => !d.old && !(d.status ?? []).some((x) => x === 'track-lost' || x === 'old-track');
    if (!this.started) {                         // taking over: what is there already, in one line
      if (this.t == null) return out;
      this.started = true;
      let n = 0;
      for (const [id, d] of Object.entries(this.tracks)) { this.known.set(id, { said: true, lost: !live(d), stage: d.stage }); n += live(d); }
      for (const [id, s] of Object.entries(this.ships)) if (s.propellant_share != null && s.propellant_share <= cfg.low_fuel_pct / 100) this.low.add(id);
      if (n) out.push(this.say('on-picture', { count: words(Math.min(n, 999)), tracks: n === 1 ? 'one track' : `${words(Math.min(n, 999))} tracks` }));
      return out.filter(Boolean);
    }
    // tracks: new (said once she has their heading, or after hold_s), identified, lost
    const fresh = [];
    for (const [id, d] of Object.entries(this.tracks)) {
      const k = this.known.get(id);
      if (!k) { this.known.set(id, { said: false, lost: false, stage: d.stage, seen: wall }); continue; }
      if (!k.said && live(d) && (this.estimate(id) || wall - k.seen >= cfg.hold_s)) fresh.push(id);
      if (k.said && d.stage === 'identified' && k.stage !== 'identified')
        out.push(this.say('on-identified', { track: d.callsign ?? d.name, class: d.class_name || '', declare: this.declare(d) }));
      if (k.said && !k.lost && !live(d)) { k.lost = true; out.push(this.say('on-unit-lost', { track: d.callsign ?? d.name, ...this.where(this.pos[id]) })); }
      if (k.lost && live(d)) k.lost = false;
      k.stage = d.stage;
    }
    for (const [id, k] of this.known) {           // gone from the picture altogether
      if (!(id in this.tracks)) {
        if (k.said && !k.lost) out.push(this.say('on-unit-lost', { track: k.callsign ?? 'a track', ...this.where(k.last) }));
        this.known.delete(id);
      } else { k.callsign = this.tracks[id].callsign ?? this.tracks[id].name; k.last = this.pos[id] ?? k.last; }
    }
    // new tracks close together are one group
    const groups = [];
    for (const id of fresh) {
      const p = this.pos[id], g = p && groups.find((g) => Math.hypot(...sub(g.p, p)) <= cfg.group_km);
      if (g) g.ids.push(id); else groups.push({ p, ids: [id] });
    }
    for (const g of groups) {
      for (const id of g.ids) this.known.get(id).said = true;
      const ds = g.ids.map((id) => this.tracks[id]), n = g.ids.length;
      const vs = g.ids.map((id) => this.estimate(id)).filter(Boolean);
      const v = vs.length ? [0, 1, 2].map((k) => vs.reduce((a, x) => a + x[k], 0) / vs.length) : null;
      const decl = new Set(ds.map((d) => this.declare(d)));
      out.push(this.say('on-new-track', {
        'contact-type': n === 1 ? 'Single group' : `Group of ${words(n)}`, count: words(n),
        track: n === 1 ? ds[0].callsign ?? ds[0].name : '', class: n === 1 ? ds[0].class_name || '' : '',
        declare: decl.size === 1 ? [...decl][0] : 'bogey', ...this.where(g.p), ...this.direction(v) }));
    }
    // fuel: a formation whose every ship is newly low is called once; else each ship
    const lowNow = Object.entries(this.ships).filter(([id, s]) => s.propellant_share != null && s.propellant_share <= cfg.low_fuel_pct / 100).map(([id]) => id);
    for (const id of [...this.low]) if (!((this.ships[id]?.propellant_share ?? 0) <= cfg.low_fuel_pct / 100 + 0.05)) this.low.delete(id);
    const newly = new Set(lowNow.filter((id) => !this.low.has(id)));
    const share = (id) => this.ships[id]?.propellant_share ?? 0;
    const under = (u) => [...this.units.values()].filter((x) => x.ship && this.above(x.id).includes(u)).map((x) => x.id);
    const said = new Set();
    for (const id of newly) {
      if (said.has(id)) continue;
      let unit = id;                                  // the highest formation over her whose ships are all newly low
      for (const f of this.above(id)) { const ss = under(f); if (ss.length > 1 && ss.every((s) => newly.has(s) && !said.has(s))) unit = f; }
      const ships = unit === id ? [id] : under(unit);
      ships.forEach((s) => said.add(s));
      out.push(this.say('on-ship-low-fuel', { unit: this.units.get(unit)?.callsign ?? unit, fuel: words(Math.round(100 * Math.min(...ships.map(share)))) }));
    }
    for (const id of newly) this.low.add(id);
    return out.filter(Boolean);
  }
  above(id) {                                       // her formations, nearest first
    const out = [];
    for (let u = this.units.get(id)?.parent; u && !out.includes(u); u = this.units.get(u)?.parent) out.push(u);
    return out;
  }
}

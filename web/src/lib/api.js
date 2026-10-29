// Talks to the server. The server computes; this file only fetches.
async function get(path, params) {
  const q = params ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v != null)) : '';
  const r = await fetch(`/api${path}${q}`);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export const api = {
  meta: (view) => get('/meta', view ? { view } : undefined),
  levels: () => get('/levels'),
  me: () => get('/me'),
  fleets: () => get('/fleets'),
  fleet: (id) => get(`/fleets/${encodeURIComponent(id)}`),
  saveFleet: (id, units) => send('PUT', `/fleets/${encodeURIComponent(id)}`, { units }),   // an admin's

  signIn: (name, password) => post('/signin', { name, password }),
  signOut: () => post('/signout', {}),
  level: (id, req) => post(`/level/${encodeURIComponent(id)}`, req),     // the host's hand on its clock: { do, warp }
  status: () => get('/status'),
  system: (id) => get(`/system/${id}`),
  orbits: (id, t) => get(`/system/${id}/orbits`, { t }),
  probe: (id, p, t, player, bullseye) => get(`/system/${id}/probe`, { x: p[0], y: p[1], z: p[2], t, player, bullseye }),
  display: () => get('/display'),
  saveSettings: (values) => post('/display/settings', values),
  ships: () => get('/ships'),
  ship: (id) => get(`/ships/${id}`),
  gunnery: (id, q) => get(`/ships/${id}/gunnery`, q),           // a stack against a hull, by range: the server's salvos
  order: (o) => giveOrder(o),
  withdrawOrder: (scenario, id, view, player) => send('DELETE', `/order/${encodeURIComponent(scenario)}/${encodeURIComponent(id)}?${new URLSearchParams(Object.entries({ view, player }).filter(([, v]) => v != null))}`),
  dismissTrack: (scenario, id, view, player) => send('DELETE', `/track/${encodeURIComponent(scenario)}/${encodeURIComponent(id)}?${new URLSearchParams(Object.entries({ view, player }).filter(([, v]) => v != null))}`),
  makeBullseye: (b) => post('/bullseyes', b),
  dropBullseye: (player, id) => send('DELETE', `/bullseyes/${encodeURIComponent(player)}/${encodeURIComponent(id)}`),
  profiles: (player) => get('/profiles', { player }),
  saveProfile: (p) => post('/profiles', p),
  dropProfile: (player, id) => send('DELETE', `/profiles/${encodeURIComponent(player)}/${encodeURIComponent(id)}`),
  engagement: (scenario, unit, q) => get(`/engagement/${encodeURIComponent(scenario)}/${encodeURIComponent(unit)}`, q),
  workshop: {
    schema: () => get('/workshop/schema'),
    source: (id) => get(`/workshop/source/${id}`),
    check: (doc) => post('/workshop/check', doc),
    save: (doc, overwrite = false) => post(`/workshop/save?overwrite=${overwrite}`, doc),
  },
};

export class Rejected extends Error {}

// An order goes with an id of its own: the server gives it once however often it comes (a retry
// after a dropped answer is answered as the first), and keeps a user from flooding it (astrum/gate.py)
let orders = 0;
const orderId = () => `${Date.now().toString(36)}-${(++orders).toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
async function giveOrder(o) {
  const body = { ...o, id: orderId() };
  try { return await post('/order', body); }
  catch (err) { if (err instanceof Rejected) throw err; return post('/order', body); }   // (the connection dropped: once more, the same id)
}

async function post(path, body) { return send('POST', path, body); }

async function send(method, path, body) {
  const r = await fetch(`/api${path}`, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Rejected(data.detail ?? `${r.status} ${path}`);
  return data;
}

// One request in flight at a time: the latest wanted picture wins, so a fast clock never queues up.
export class StateStream {
  constructor(onstate) {
    this.onstate = onstate;
    this.want = null;
    this.busy = false;
    this.rtt = 0;                    // a picture's round trip, seconds (smoothed)
    this.tap = null;                 // (text): another reader of every picture as it came (the adjutant)
    this._open();
  }
  _open() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws.onopen = () => { if (this.watching) this.ws.send(this.watching); this._send(); };
    this.ws.onmessage = (e) => {
      if (this.busy) {                               // an answer to what was asked: its round trip (a pushed picture has none)
        const dt = (performance.now() - this._sent) / 1000;
        this.rtt = this.rtt ? 0.8 * this.rtt + 0.2 * dt : dt;
      }
      this.busy = false; this.tap?.(e.data); this.onstate(JSON.parse(e.data)); this._send();
    };
    this.ws.onclose = () => { this.busy = false; setTimeout(() => this._open(), 1000); };
  }
  request(req) { this.watching = null; this.asking = null; this.want = req; this._send(); }
  // a level's pictures, asked for ([server] pictures = "ask"): asked again the moment each lands,
  // at most 60 a second, however fast the map draws (the server says the moment: its clock's)
  ask(req) { this.watching = null; this.asking = req; this._send(); }
  // a level's pictures: asked for once (again only when what is asked changes), then sent by the
  // server some 20 times a second, unasked
  watch(req) {
    const text = JSON.stringify(req);
    if (text === this.watching) return;
    this.watching = text; this.want = null;
    if (this.ws.readyState === 1) this.ws.send(text);
  }
  _send() {
    const want = this.want ?? this.asking;
    if (this.busy || !want || this.ws.readyState !== 1) return;
    const wait = (this._sent ?? 0) + 1000 / 60 - performance.now();
    if (this.asking && wait > 0) { clearTimeout(this._later); this._later = setTimeout(() => this._send(), wait); return; }
    this.busy = true;
    this._sent = performance.now();
    this.ws.send(JSON.stringify(want));
    this.want = null;
  }
}

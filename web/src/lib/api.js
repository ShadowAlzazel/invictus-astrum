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
  level: (id, req) => post(`/level/${encodeURIComponent(id)}`, req),     // the host's hand on its clock: { do, warp }
  status: () => get('/status'),
  system: (id) => get(`/system/${id}`),
  orbits: (id, t) => get(`/system/${id}/orbits`, { t }),
  probe: (id, p, t, player, bullseye) => get(`/system/${id}/probe`, { x: p[0], y: p[1], z: p[2], t, player, bullseye }),
  display: () => get('/display'),
  saveSettings: (values) => post('/display/settings', values),
  ships: () => get('/ships'),
  ship: (id) => get(`/ships/${id}`),
  order: (o) => post('/order', o),
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
    this.ws.onopen = () => this._send();
    this.ws.onmessage = (e) => {
      const dt = (performance.now() - this._sent) / 1000;
      this.rtt = this.rtt ? 0.8 * this.rtt + 0.2 * dt : dt;
      this.busy = false; this.tap?.(e.data); this.onstate(JSON.parse(e.data)); this._send();
    };
    this.ws.onclose = () => { this.busy = false; setTimeout(() => this._open(), 1000); };
  }
  request(req) { this.want = req; this._send(); }
  _send() {
    if (this.busy || !this.want || this.ws.readyState !== 1) return;
    this.busy = true;
    this._sent = performance.now();
    this.ws.send(JSON.stringify(this.want));
    this.want = null;
  }
}

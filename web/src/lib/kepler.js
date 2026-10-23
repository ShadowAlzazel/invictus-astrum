// Two-body estimates off the map's own picture: what a free ship does with no drive lit. Pure
// functions (km, s, km³/s²), no map and nothing asked of the server, shared by the free paths, the
// unit panel and the move predictor, and tested by node (web/tests/kepler.test.mjs) against the
// simulation's own orbits. They are estimates: one body pulls (the one whose well she is in), and
// a ballistic burn is a straight line.

export const G = 6.6743e-20;                         // km³/(kg·s²)

export const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const len = (a) => Math.hypot(a[0], a[1], a[2]);
export const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];

// the body whose well a point is in: the smallest well about it; in a binary's, the component
// that pulls harder; out of every well, the star (bodies: the system's, as /api/system gives them,
// byId: the same by id, at: where each is)
export function dominant(bodies, byId, at, p) {
  let best = null;
  for (const b of bodies) {
    const s = b.zones?.soi_km, q = at[b.id];
    if (s && q && len(sub(p, q)) < s && (!best || s < best.zones.soi_km)) best = b;
  }
  const well = best && byId[best.zones.well_of ?? best.id];
  if (well?.components) {
    const pull = (b) => b.mass_kg / len(sub(p, at[b.id])) ** 2;
    return well.components.map((id) => byId[id]).filter((b) => b && at[b.id]).reduce((a, b) => (pull(b) > pull(a) ? b : a));
  }
  return best ?? bodies.find((b) => !b.parent);
}

// her conic about a body from r, v off it, as n + 1 points off it (3 a point): an ellipse whole,
// else the arc ahead out to limit; falling straight in (no turn about it), the line in. half (rad):
// only so far round it about her, either way (on a hyperbola, ahead), as when it is far larger
// than the view
export function conic(r, v, mu, limit, n = 96, half = null) {
  const rn = len(r), h = cross(r, v), hn = len(h), pts = new Float64Array(3 * (n + 1));
  if (!(mu > 0) || !(rn > 0)) return null;
  if (hn < 1e-9 * rn * Math.max(len(v), 1e-9)) {
    for (let k = 0; k <= n; k++) for (let i = 0; i < 3; i++) pts[3 * k + i] = r[i] * (1 - k / n);
    return { pts, closed: false };
  }
  const ev = sub(scale(cross(v, h), 1 / mu), scale(r, 1 / rn)), e = len(ev);
  const P = e > 1e-8 ? scale(ev, 1 / e) : scale(r, 1 / rn), Qr = cross(h, P), Q = scale(Qr, 1 / len(Qr)), p = (hn * hn) / mu;
  const put = (k, nu) => {
    const rr = p / (1 + e * Math.cos(nu)), c = Math.cos(nu) * rr, s = Math.sin(nu) * rr;
    for (let i = 0; i < 3; i++) pts[3 * k + i] = c * P[i] + s * Q[i];
  };
  const now = Math.atan2(dot(r, Q), dot(r, P));
  if (e < 1) {
    const from = half ? now - half : 0, to = half ? now + half : 2 * Math.PI;
    for (let k = 0; k <= n; k++) put(k, from + ((to - from) * k) / n);
    return { pts, closed: !half };
  }
  const far = Math.min(Math.acos(-1 / e) - 1e-3, half ? now + half : Infinity);
  let end = far;
  for (let k = 1; k <= n; k++) {
    const nu = now + ((far - now) * k) / n;
    if (p / (1 + e * Math.cos(nu)) > limit) { end = nu; break; }
  }
  if (end <= now) return null;
  for (let k = 0; k <= n; k++) put(k, now + ((end - now) * k) / n);
  return { pts, closed: false };
}

// the orbit she goes onto, going free at rel off a body of mu: circular, prograde about the
// system's up (as the simulation puts her on one, sim.Fleet._go_free); its velocity off the body
export function ontoVelocity(rel, mu) {
  const R = len(rel), up = Math.abs(rel[2]) < 0.95 * R ? [0, 0, 1] : [1, 0, 0], along = cross(up, rel);
  return scale(along, Math.sqrt(mu / R) / len(along));
}
export const onto = (rel, mu, n, half = null) => conic(rel, ontoVelocity(rel, mu), mu, 3 * len(rel), n, half);

// an orbit's figures off r, v: semi-major axis, period (Infinity unbound), apsides
export function figures(r, v, mu) {
  const rn = len(r), a = 1 / (2 / rn - dot(v, v) / mu);
  const e = len(sub(scale(cross(v, cross(r, v)), 1 / mu), scale(r, 1 / rn)));
  return { a, e, period: a > 0 ? 2 * Math.PI * Math.sqrt(a ** 3 / mu) : Infinity, peri: a * (1 - e), apo: a > 0 ? a * (1 + e) : Infinity };
}

// Stumpff's c2, c3
function stumpff(psi) {
  if (psi > 1e-6) { const s = Math.sqrt(psi); return [(1 - Math.cos(s)) / psi, (s - Math.sin(s)) / (s * psi)]; }
  if (psi < -1e-6) { const s = Math.sqrt(-psi); return [(1 - Math.cosh(s)) / psi, (Math.sinh(s) - s) / (s * -psi)]; }
  return [1 / 2, 1 / 6];
}
// where she is dt after r, v off a body of mu, on any conic (Kepler's equation in the universal
// variable, Lagrange's f and g): r off the body
export function drift(r, v, mu, dt) {
  const rn = len(r), sm = Math.sqrt(mu), rv = dot(r, v) / sm, alpha = 2 / rn - dot(v, v) / mu;
  let x = Math.abs(alpha) > 1e-12 ? sm * dt * alpha : (sm * dt) / rn;
  if (alpha < -1e-12) {                              // a hyperbola's starter
    const a = 1 / alpha, sg = Math.sign(dt) || 1;
    x = sg * Math.sqrt(-a) * Math.log((-2 * mu * alpha * dt) / (dot(r, v) + sg * Math.sqrt(-mu * a) * (1 - rn * alpha)) || 1);
  }
  for (let it = 0; it < 60; it++) {                  // Newton on x
    const psi = x * x * alpha, [c2, c3] = stumpff(psi);
    const rr = x * x * c2 + rv * x * (1 - psi * c3) + rn * (1 - psi * c2);
    const dx = (sm * dt - x * x * x * c3 - rv * x * x * c2 - rn * x * (1 - psi * c3)) / rr;
    x += dx;
    if (Math.abs(dx) < 1e-9 * (Math.abs(x) + 1)) break;
  }
  const [c2, c3] = stumpff(x * x * alpha), f = 1 - ((x * x) / rn) * c2, g = dt - ((x * x * x) / sm) * c3;
  return add(scale(r, f), scale(v, g));
}

// BALLISTIC, as the simulation aims it (simhost.ballistic_order): from r0 moving at v0, burning at
// a along one line for half the way, then coasting through P(T) (where the target is T after now)
// at the speed reached. Returns { u, tb, T }: the line, how long the burn, when she is there
export function ballisticAim(r0, v0, a, P) {
  let T = 0, D = null, tb = 0;
  for (let k = 0; k < 30; k++) {                     // until when she is there settles
    D = sub(P(T), add(r0, scale(v0, T)));
    tb = Math.sqrt(len(D) / a);
    const was = T;
    T = 1.5 * tb;
    if (Math.abs(T - was) < 1e-9 * T) break;
  }
  return { u: scale(D, 1 / len(D)), tb, T };
}
// where she is t after the order: on the burn's line while it lasts, then coasting about the body
// (at: where it is t after now, mu: its pull; null: no pull, a straight line)
export function ballisticAt(r0, v0, a, aim, t, body) {
  const tb = Math.min(t, aim.tb);
  const p = add(add(r0, scale(v0, tb)), scale(aim.u, 0.5 * a * tb * tb));
  if (t <= aim.tb) return p;
  const v = add(v0, scale(aim.u, a * aim.tb)), dt = t - aim.tb;
  if (!body) return add(p, scale(v, dt));
  const B0 = body.at(aim.tb), V = body.v;
  return add(body.at(t), drift(sub(p, B0), sub(v, V), body.mu, dt));
}

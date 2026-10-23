// The map's two-body estimates (web/src/lib/kepler.js): Kepler's drift on every conic, the
// orbit going free gives, and the ballistic aim, against what the physics says.
import { drift, conic, onto, ontoVelocity, figures, ballisticAim, ballisticAt, len, sub, cross, dot } from '../src/lib/kepler.js';
import { estimate } from '../src/lib/orders.js';
const assert = (c, m) => { if (!c) { console.error('FAIL', m); process.exitCode = 1; } };
const near = (a, b, tol) => Math.abs(a - b) <= tol * Math.max(1, Math.abs(b));
const mu = 42828.37, R = 20000;                       // Mars, km³/s²; 20,000 km out
const vc = Math.sqrt(mu / R), T = 2 * Math.PI * Math.sqrt(R ** 3 / mu);
const q = drift([R, 0, 0], [0, vc, 0], mu, T / 4);
assert(near(q[0], 0, 1e-6) && near(q[1], R, 1e-9), 'a quarter turn of a circle');
const back = drift([R, 0, 0], [0, vc, 0], mu, 3 * T);
assert(near(back[0], R, 1e-9) && Math.abs(back[1]) < 1e-5 * R, 'three turns: back where she was');
// an ellipse and a hyperbola: energy and angular momentum kept
for (const [v0, what] of [[[0.3, vc * 1.2, 0.05], 'ellipse'], [[0.5, vc * 1.8, 0.2], 'hyperbola']]) {
  const r0 = [R, 0, 0], E0 = dot(v0, v0) / 2 - mu / R, H0 = len(cross(r0, v0)), h = 1e-3;
  for (const t of [600, 3600, 5 * 3600, 2 * 86400]) {
    const p = drift(r0, v0, mu, t), v = sub(drift(r0, v0, mu, t + h), drift(r0, v0, mu, t - h)).map((x) => x / (2 * h));
    assert(near(dot(v, v) / 2 - mu / len(p), E0, 1e-5) && near(len(cross(p, v)), H0, 1e-5), `${what}: energy and angular momentum at ${t} s`);
  }
  if (what === 'hyperbola') assert(len(drift(r0, v0, mu, 86400)) > 5 * R && figures(r0, v0, mu).period === Infinity, 'a hyperbola runs away');
}
// going free: circular, prograde about up, the conic closed
const v = ontoVelocity([R, 0, 0], mu);
assert(near(len(v), vc, 1e-12) && v[1] > 0 && near(figures([R, 0, 0], v, mu).e, 0, 1e-9), 'going free: a circle, prograde');
const c = onto([R, 0, 0], mu, 48);
assert(c.closed && c.pts.length === 49 * 3 && near(Math.hypot(c.pts[30], c.pts[31], c.pts[32]), R, 1e-9), 'its conic, every point on it');
assert(!conic([R, 0, 0], [-1, 0, 0], mu, 1e9).closed, 'falling straight in: a line');
// the ballistic aim: on the line half the way burning, the rest coasting, onto a moving target
const P = (t) => [3e6 + 10 * t, 2e6, 0], a = 0.3 * 9.80665e-3;
const aim = ballisticAim([0, 0, 0], [5, 0, 0], a, P);
const there = ballisticAt([0, 0, 0], [5, 0, 0], a, aim, aim.T, null);
assert(len(sub(there, P(aim.T))) < 1e-6 * len(P(aim.T)), 'ballistic: there when the target is');
assert(near(aim.T, 1.5 * aim.tb, 1e-12), 'half the way burning');
// the order tool's quick estimate, ballistic, from rest onto a target at rest: as the aim says
const still = ballisticAim([0, 0, 0], [0, 0, 0], a, () => [3e6, 2e6, 0]);
const est = estimate({ from: [0, 0, 0], to: [3e6, 2e6, 0], standoff: 5e4 }, 0.3, true);
assert(near(est.eta, still.T, 1e-9) && near(est.dv, a * still.tb, 1e-9) && est.distance === len([3e6, 2e6, 0]), 'the ballistic estimate: the aim, at rest');

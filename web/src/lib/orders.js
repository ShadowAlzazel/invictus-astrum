// The order tool's arithmetic. The server flies the ship; this only says where she is told to go
// and what that will roughly take, for the vector drawn while the order is aimed.
const G0 = 9.80665e-3;                       // km/s² in a g
const STANDOFF_UNIT_KM = 50, STANDOFF_BODY_R = 3, STANDOFF_BODY_MIN_KM = 1000;   // as astrum/sim.py

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const len = (a) => Math.hypot(a[0], a[1], a[2]);

// What the cursor points at: a unit or a body under it (their own coordinates), else the point on
// the plane through the ship parallel to the bullseye's, tilted toward Eve (up) or Haid (down).
// `unit` is the ship, or the formation, the order is for; `ships` are the ships it goes to.
export function aimAt(map, unit, ships, cursor, tiltDeg) {
  const from = map.position({ kind: 'contact', id: unit });
  if (!from) return null;
  const h = map.hover;
  const own = h?.kind === 'contact' && (h.id === unit || ships.includes(h.id));
  if (h && !own && (h.kind === 'contact' || h.kind === 'body')) {
    const p = map.position(h);
    if (p) {
      const name = h.kind === 'body' ? map.bodies[h.id]?.name ?? h.id : map.contactName?.(h.id) ?? h.id;
      const stand = h.kind === 'body'
        ? Math.max(STANDOFF_BODY_R * (map.bodies[h.id]?.radius_eq_km || map.bodies[h.id]?.radius_km || 0), STANDOFF_BODY_MIN_KM)
        : STANDOFF_UNIT_KM;
      return { from, to: p, kind: h.kind, id: h.id, label: name, standoff: stand, target: { [h.kind === 'body' ? 'body' : 'unit']: h.id } };
    }
  }
  const flat = map.planeAt(cursor.x, cursor.y, from);
  const b = map.bullseye();
  if (!flat || !b) return null;
  const across = sub(flat, from), up = b.axes[2];
  const to = add(flat, mul(up, len(across) * Math.tan((tiltDeg * Math.PI) / 180)));
  const a = map.aer(to);
  return { from, to, kind: 'point', label: 'point', standoff: 0,
           target: { bullseye: map.bullseyeId, aer: [a.bearing, a.elevation, a.range] } };
}

// From rest, flip and burn: there in 2√(d/a), at a cost of 2√(a·d)
export function estimate(aim, g) {
  const d = Math.max(len(sub(aim.to, aim.from)) - aim.standoff, 0), a = g * G0;
  return { distance: d, eta: a > 0 ? 2 * Math.sqrt(d / a) : Infinity, dv: a > 0 ? 2 * Math.sqrt(a * d) : 0 };
}

// The vector's own bearing and elevation, in the bullseye's axes, from the ship
export function heading(map, aim) {
  const b = map.bullseye();
  if (!b) return null;
  const d = sub(aim.to, aim.from), [ref, left, up] = b.axes;
  const x = d[0] * ref[0] + d[1] * ref[1] + d[2] * ref[2], y = d[0] * left[0] + d[1] * left[1] + d[2] * left[2];
  const z = d[0] * up[0] + d[1] * up[1] + d[2] * up[2], r = Math.hypot(x, y, z);
  return { bearing: ((Math.atan2(-y, x) * 180) / Math.PI + 360) % 360, elevation: r ? (Math.asin(z / r) * 180) / Math.PI : 0 };
}

export function hms(s) {
  if (s == null || !isFinite(s)) return '—';
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 172800) { const h = Math.floor(s / 3600); return `${h} h ${String(Math.round((s - h * 3600) / 60)).padStart(2, '0')} min`; }
  return `${(s / 86400).toFixed(1)} d`;
}

// The telegraph: from her most down to stop, with the doctrine's cruise band marked
export function detents(maxG, cruise) {
  const marks = [['Full', maxG], ['Cruise', cruise?.[1]], ['Cruise floor', cruise?.[0]], ['Half', maxG / 2],
                 ['Slow', maxG / 4], ['Dead slow', maxG / 10], ['Stop', 0]];
  const out = [];
  for (const [label, g] of marks) {
    if (g == null || g > maxG + 1e-9) continue;
    if (out.some((d) => Math.abs(d.g - g) < 0.01)) continue;
    out.push({ label, g });
  }
  return out.sort((a, b) => b.g - a.g);
}

// What an order for a ship or a formation can hold: the slowest ship's most, and the cruise band
// all of them share. `ships` are ids; state.ships has what each can do now.
export function group(state, contacts, ships) {
  const now = ships.map((id) => state?.ships?.[id]).filter(Boolean);
  if (!now.length) return null;
  const specs = ships.map((id) => contacts.find((c) => c.id === id)?.ship).filter(Boolean);
  const bands = specs.map((s) => s.cruise_g).filter(Boolean);
  const maxG = Math.min(...now.map((s) => s.max_accel_g));
  const cruise = bands.length ? [Math.min(...bands.map((b) => b[0])), Math.min(...bands.map((b) => b[1]))] : null;
  const flying = now.filter((s) => s.goal);
  return { maxG, cruise, ships: now, flying, g: flying.length ? Math.max(...flying.map((s) => s.goal.g)) : null };
}

// The orders being flown by these ships, one entry per order: its label, the unit it was given
// to, all of its ships (those outside these too: an order is retuned whole), their telegraph held
// to the slowest ship's most, and when the first and the last of them arrive
export function orderGroups(state, contacts, ships) {
  const out = new Map();
  for (const id of ships) {
    const s = state?.ships?.[id];
    if (!s?.goal) continue;
    const key = s.goal.order_id ?? id;
    if (!out.has(key)) out.set(key, { id: key, label: s.goal.label, by: s.goal.by ?? id, ships: [], here: 0 });
    out.get(key).here += 1;
  }
  for (const [id, s] of Object.entries(state?.ships ?? {})) {
    const o = s.goal && out.get(s.goal.order_id ?? id);
    if (o) o.ships.push(id);
  }
  return [...out.values()].map((o) => {
    const grp = group(state, contacts, o.ships), etas = grp.flying.map((s) => s.goal.eta_s ?? Infinity);
    return { ...o, maxG: grp.maxG, cruise: grp.cruise, g: grp.g, soonest: Math.min(...etas), latest: Math.max(...etas) };
  });
}

// The ships under a unit, from the formation tree the map was sent (children of each contact)
export function shipsUnder(contacts, state, unit) {
  const byId = Object.fromEntries(contacts.map((c) => [c.id, c]));
  if (state?.ships?.[unit]) return [unit];
  const out = [], todo = [...(byId[unit]?.children ?? [])];
  while (todo.length) {
    const c = todo.shift();
    if (state?.ships?.[c]) out.push(c);
    todo.push(...(byId[c]?.children ?? []));
  }
  return out;
}

// One step of the telegraph: to the next detent up or down, or by 0.01 g
export function stepG(g, maxG, cruise, up, fine) {
  const cur = Math.min(g, maxG);
  if (fine) return Math.max(0, Math.min(maxG, Math.round((cur + (up ? 0.01 : -0.01)) * 100) / 100));
  const list = detents(maxG, cruise).map((d) => d.g);
  const next = up ? [...list].reverse().find((x) => x > cur + 1e-6) : list.find((x) => x < cur - 1e-6);
  return next ?? cur;
}

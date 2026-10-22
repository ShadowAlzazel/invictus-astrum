// Number formatting for readouts. Ranges are kilometres, as the doctrine reads them; large ones add AU.
const AU_KM = 149597870.7;
const C_KMS = 299792.458;

export const n = (v, d = 0) => (v == null || !isFinite(v) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }));

export function km(v) {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a < 10) return `${n(v, 2)} km`;
  if (a < 7.4e6) return `${n(v)} km`;                    // from 0.05 AU on, read in AU
  return `${(v / AU_KM).toLocaleString('en-US', { maximumFractionDigits: a < 1e9 ? 3 : 1 })} AU`;
}

export function kmFull(v) {
  if (v == null || !isFinite(v)) return '—';
  return Math.abs(v) < 1e7 ? km(v) : `${km(v)}  (${n(v / 1e6, 1)} Mkm)`;
}

export function lightTime(rangeKm) {
  const s = rangeKm / C_KMS;
  if (s < 1) return `${n(s * 1000, 0)} ms`;
  if (s < 120) return `${n(s, 1)} s`;
  if (s < 7200) return `${n(s / 60, 1)} min`;
  if (s < 172800) return `${n(s / 3600, 1)} h`;
  if (s < 2 * 31557600) return `${n(s / 86400, 1)} d`;
  return `${n(s / 31557600, 2)} yr`;
}

// a power, W, in the unit that reads best: 19 MW, 236 TW
export function watts(w) {
  if (w == null || !isFinite(w)) return '—';
  const [div, unit] = [[1e15, 'PW'], [1e12, 'TW'], [1e9, 'GW'], [1e6, 'MW'], [1e3, 'kW'], [1, 'W']].find(([d]) => Math.abs(w) >= d) ?? [1, 'W'];
  return `${n(w / div, w / div < 10 ? 2 : w / div < 100 ? 1 : 0)} ${unit}`;
}

// an age in seconds, as it reads: 8.0 s, 41 min 12 s, 2 h 04 min
export function age(s) {
  if (s == null || !isFinite(s)) return '—';
  if (s < 60) return `${n(s, 1)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, '0')} s`;
  return `${Math.floor(s / 3600)} h ${String(Math.round((s % 3600) / 60)).padStart(2, '0')} min`;
}

export const bearing = (deg) => String(Math.round(((deg % 360) + 360) % 360) % 360).padStart(3, '0') + '°';
// Eve above the bullseye plane, Haid below; the word carries the sign
export const elev = (deg) => (Math.abs(deg) < 0.05 ? 'Level' : `${deg > 0 ? 'Eve' : 'Haid'} ${n(Math.abs(deg), Math.abs(deg) < 10 ? 1 : 0)}°`);

export function duration(days) {
  if (days == null) return '—';
  if (days < 2) return `${n(days * 24, 2)} h`;
  if (days < 800) return `${n(days, 2)} d`;
  return `${n(days / 365.25, 2)} yr`;
}

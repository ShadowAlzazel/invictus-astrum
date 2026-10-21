// Reading the canon's figures: { lo, hi, est, approx, note } as the server sends them.
const num = (v) => (v !== 0 && Math.abs(v) < 0.1
  ? Number(v).toLocaleString('en-US', { maximumSignificantDigits: 2 })
  : Number(v).toLocaleString('en-US', { maximumFractionDigits: Math.abs(v) < 10 ? 2 : Math.abs(v) < 1000 ? 1 : 0 }));

export function q(x, unit = '') {
  if (x == null) return '—';
  if (x.lo == null) return x.note || '—';
  const v = x.lo === x.hi ? num(x.lo) : `${num(x.lo)}–${num(x.hi)}`;
  return `${x.approx ? '~' : ''}${v}${unit ? ' ' + unit : ''}${x.est ? ', est.' : ''}`;
}

export const note = (x) => (x && x.lo != null && x.note ? x.note : '');

// a figure row from the server: a value, named values, text, a list, or a blank
export function row(r) {
  if (r.blank) return '—';
  if (r.text != null) return r.text;
  if (r.list) return r.list.join(', ');
  if (r.named) return Object.entries(r.named).map(([k, v]) => `${q(v, r.unit)} ${k}`).join(' · ');
  const n = note(r.q);
  return q(r.q, r.unit) + (n ? ` (${n})` : '');
}

// The adjutant's worker: every picture's text as the map received it, parsed and read here, off the
// map's thread. She speaks at most every SPEAK_S of wall time (what changed since), and sends her
// heading estimates as often, for the map to draw.
import { Officer, config } from './adjutant.js';

const SPEAK_S = 0.5;
let officer = null, due = 0;

onmessage = ({ data: m }) => {
  if (m.kind === 'start') { officer = new Officer(m.cfg, m.context); return; }
  if (!officer) return;
  if (m.kind === 'cfg') { officer.cfg = config(m.cfg); return; }
  if (m.kind === 'bullseye') { officer.bullseye(m.bullseye); return; }
  if (m.kind === 'picture') {
    const s = JSON.parse(m.text);
    if (s.error) return;
    officer.feed(s);
    const now = Date.now() / 1000;
    if (now < due) return;
    due = now + SPEAK_S;
    const calls = officer.calls(now);
    postMessage({ kind: 'calls', calls, estimates: officer.cfg.estimates ? officer.estimates() : null });
  }
};

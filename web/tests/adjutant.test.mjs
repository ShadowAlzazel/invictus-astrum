// The adjutant (web/src/lib/adjutant.js): her figures as said, her templates, and her calls on a few pictures.
import { Officer, words, digits, spokenRange, fill, config } from '../src/lib/adjutant.js';
const assert = (c, m) => { if (!c) { console.error('FAIL', m); process.exitCode = 1; } };
assert(words(300) === 'three-hundred' && words(42) === 'forty-two' && words(120) === 'one-hundred-twenty', 'words');
assert(digits(90) === 'zero-niner-zero' && digits(359.7) === 'zero-zero-zero', 'digits');
assert(spokenRange(300000) === 'three-hundred thousand' && spokenRange(4.2e6) === 'four-point-two million' && spokenRange(1.5 * 149597870.7) === 'one-point-five AU', 'ranges');
assert(fill('[role], [name]. Level [elevation]. [direction]. [declare].', { role: 'Commander', name: 'Eva', elevation: '', direction: '', declare: 'bogey' }) === 'Commander, Eva. Level. Bogey.', 'fill drops empty sentences');
const B = { system: { origin: [0, 0, 0], axes: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] } };
const units = [{ id: 'tf', callsign: 'Task Force 3', parent: null }, { id: 'a', callsign: 'A1', parent: 'tf', ship: true }, { id: 'b', callsign: 'B1', parent: 'tf', ship: true }, { id: 'c', callsign: 'C1', parent: null, ship: true }];
const o = new Officer({ hold_s: 2 }, { units, bullseye: { id: 'system', name: 'Sol centre' } });
const pic = (t, tracks, contacts, ships, full = false) => ({ t, full, tracks, contacts, ships, bullseyes: B });
o.feed(pic(0, { T1: { callsign: 'Bogey', affiliation: 'unknown', stage: 'detected', status: [] } }, { T1: [1e6, 0, 0] },
  { a: { propellant_share: 0.5 }, b: { propellant_share: 0.5 }, c: { propellant_share: 0.5 } }, true), 0);
let c = o.calls(0); assert(c.length === 1 && c[0].kind === 'on-picture', 'picture on taking over');
// a new track to the east-ish of the bullseye: x is 000, y is 270 (so -y is 090)
o.feed(pic(60, { T1: { callsign: 'Bogey', affiliation: 'unknown', stage: 'detected', status: [] }, T2: { callsign: 'Bogey', affiliation: 'hostile', stage: 'tracked', status: [] } }, { T1: [1e6, 0, 0], T2: [0, -300000, 0] }, {}), 1);
c = o.calls(1); assert(c.length === 0, 'held: no heading yet');
o.feed(pic(240, { T1: { callsign: 'Bogey', affiliation: 'unknown', stage: 'detected', status: [] }, T2: { callsign: 'Bogey', affiliation: 'hostile', stage: 'tracked', status: [] } }, { T1: [1e6, 0, 0], T2: [0, -300000 - 1800, 0] }, {}), 1.5);
c = o.calls(1.5); assert(c.length === 1 && /zero-niner-zero for three-hundred-two thousand/.test(c[0].text) && /Track east/.test(c[0].text) && /Hostile/.test(c[0].text), 'new track with heading');
// lost, then fuel: both ships of the TF low -> the TF called once; C alone
o.feed(pic(300, { T1: { callsign: 'Bogey', affiliation: 'unknown', stage: 'detected', status: [] }, T2: { callsign: 'Bogey', affiliation: 'hostile', stage: 'tracked', status: ['track-lost'] } }, { T1: [1e6, 0, 0], T2: [0, -302000, 0] },
  { a: { propellant_share: 0.08 }, b: { propellant_share: 0.09 }, c: { propellant_share: 0.05 } }), 3);
c = o.calls(3);
assert(c.some((x) => x.kind === 'on-unit-lost') && c.filter((x) => x.kind === 'on-ship-low-fuel').length === 2 && c.some((x) => /Task Force 3, bingo fuel, eight percent/.test(x.text)), 'lost and fuel');
c = o.calls(4); assert(c.length === 0, 'said once');
assert(Object.keys(o.estimates()).join() === 'T1', 'estimates: live tracks only');
assert(config({ estimates: false }).estimate_alpha === 0 && config({}).estimate_alpha > 0 && !('estimates' in config({ estimates: true })), 'heading arrows: kept off stays off');

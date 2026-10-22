// A unit as the view knows it (the frame's seen_as, astrum/simhost.py): not seen, it is not in the
// picture (null); seen but not known for what it is, a bogey, nameless and classless; a lost
// track, uncertain (the track-lost status draws its ellipse); and its affiliation as the view's side.
export function asSeen(c, s) {
  if (!s) return c;
  if (s.shown === false) return null;
  let d = s.affiliation ? { ...c, affiliation: s.affiliation } : c;
  if (s.identified === false) {
    d = { ...d, callsign: 'Bogey', name: 'Bogey', brevity: 'bogey', unit_type: '', class_name: '', ship: null,
          role: '', hull_number: '', faction: null, pry: null };
  }
  if (s.lost) d = { ...d, status: [...(d.status ?? []).filter((x) => x !== 'track-lost'), 'track-lost'] };
  return d;
}

// Tactical symbology, drawn on a 2D canvas at fixed screen size.
//
// Units use APP-6-style frames: affiliation is told by SHAPE first (friend rectangle, hostile
// diamond, unknown quatrefoil, neutral square) and by colour second. Everything that varies
// (shapes, colours, echelon marks, status modifiers, body display sizes) comes from style.toml.
const FONT_MONO = '"Share Tech Mono", ui-monospace, monospace';
const FONT_DISPLAY = '"Chakra Petch", "Share Tech Mono", sans-serif';

export function rgba(hex, a) {
  const v = parseInt(hex.slice(1), 16);
  return `rgba(${(v >> 16) & 255},${(v >> 8) & 255},${v & 255},${a})`;
}

export function text(ctx, s, x, y, color, size = 10, font = FONT_MONO, align = 'left') {
  ctx.font = `${size}px ${font}`;
  ctx.textAlign = align;
  ctx.fillStyle = color;
  ctx.fillText(s, x, y);
  ctx.textAlign = 'left';
}

export const display = (ctx, s, x, y, color, size = 12, align = 'left') => text(ctx, s, x, y, color, size, FONT_DISPLAY, align);

// frame outline path centred on (x, y); h is the frame's height in px
function framePath(ctx, shape, x, y, h) {
  ctx.beginPath();
  if (shape === 'rect') ctx.rect(x - h * 0.75, y - h / 2, h * 1.5, h);
  else if (shape === 'square') ctx.rect(x - h / 2, y - h / 2, h, h);
  else if (shape === 'diamond') { const r = h * 0.68; ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath(); }
  else if (shape === 'circle') ctx.arc(x, y, h / 2, 0, Math.PI * 2);
  else if (shape === 'quatrefoil') {
    const r = h * 0.3, o = h * 0.24;
    ctx.arc(x, y - o, r, Math.PI * 0.85, Math.PI * 0.15);
    ctx.arc(x + o, y, r, Math.PI * 1.35, Math.PI * 0.65);
    ctx.arc(x, y + o, r, Math.PI * 1.85, Math.PI * 1.15);
    ctx.arc(x - o, y, r, Math.PI * 0.35, Math.PI * 1.65);
    ctx.closePath();
  }
}

// half-width and half-height of a frame, for placing marks around it
export function frameExtent(shape, h) {
  if (shape === 'rect') return [h * 0.75, h / 2];
  if (shape === 'diamond') return [h * 0.68, h * 0.68];
  if (shape === 'quatrefoil') return [h * 0.54, h * 0.54];
  return [h / 2, h / 2];
}

// A formation's role, as the blocks it is made of (style.toml [formation_block]), each an APP-6 mark
// drawn inside its frame: oval (armour), cross (infantry, corner to corner), slash (reconnaissance,
// lower left to upper right), bar (supply, across the bottom), stroke (motorized, down the middle),
// chevron (anti-armour, an inverted V), dome (air defence, an arc on the bottom edge), bolt (signal,
// a lightning bolt from upper left to lower right, its jog in the middle). A frame that is not a box takes them in the box
// inside it.
function stars(ctx, n, x, y, r, color) {         // n five-pointed stars in a row, centred on x, their middles at y
  ctx.fillStyle = color;
  for (let k = 0; k < n; k++) {
    const cx = x + (k - (n - 1) / 2) * r * 2.3;
    ctx.beginPath();
    for (let p = 0; p < 10; p++) {
      const a = -Math.PI / 2 + (p * Math.PI) / 5, rr = p % 2 ? r * 0.45 : r;
      ctx.lineTo(cx + rr * Math.cos(a), y + rr * Math.sin(a));
    }
    ctx.closePath(); ctx.fill();
  }
}

function roleMarks(ctx, marks, x, y, shape, ew, eh, color) {
  const box = shape === 'rect' || shape === 'square' ? 1 : 0.62;
  const w = ew * box, h = eh * box;
  ctx.strokeStyle = color; ctx.lineWidth = 1.2;
  ctx.beginPath();
  for (const m of marks) {
    if (m === 'oval') { ctx.moveTo(x + w * 0.55, y); ctx.ellipse(x, y, w * 0.55, h * 0.5, 0, 0, Math.PI * 2); }
    else if (m === 'cross') { ctx.moveTo(x - w, y - h); ctx.lineTo(x + w, y + h); ctx.moveTo(x + w, y - h); ctx.lineTo(x - w, y + h); }
    else if (m === 'slash') { ctx.moveTo(x - w, y + h); ctx.lineTo(x + w, y - h); }
    else if (m === 'bar') { ctx.moveTo(x - w, y + h * 0.5); ctx.lineTo(x + w, y + h * 0.5); }
    else if (m === 'stroke') { ctx.moveTo(x, y - h); ctx.lineTo(x, y + h); }
    else if (m === 'chevron') { ctx.moveTo(x - w, y + h); ctx.lineTo(x, y - h); ctx.lineTo(x + w, y + h); }
    else if (m === 'dome') { const r = Math.min(w * 0.5, h * 0.95); ctx.moveTo(x - r, y + h); ctx.arc(x, y + h, r, Math.PI, 0); }
    else if (m === 'bolt') {
      ctx.moveTo(x - w, y - h); ctx.lineTo(x, y + h * 0.35); ctx.lineTo(x, y - h * 0.35); ctx.lineTo(x + w, y + h);
    }
  }
  ctx.stroke();
}

// what a unit's faction is called under it: its prefix (AVC, AAG, JADF), else its frame's tag
// (style.toml [affiliation]: HOSTILE, UNKNOWN, CIVIL)
export const HARM = [null, 'damaged', 'crab', 'destroyed'];   // a ship's harm as the server says it (0 whole to 3), as a style.toml status
export const designation = (style, c) => c.faction?.prefix || (style.affiliation[c.affiliation] ?? style.affiliation.unknown).tag || '';

// one unit or formation symbol. c = contact (affiliation, echelon, unit_type, status, callsign, pry, brevity, faction)
// opts: h frame height; hot (hover/selected); label; alpha (dimming); ring (highlight colour);
// hq (draw the headquarters staff); labelPx, tagPx (text sizes); faction (its designation among the tags)
export function unitSymbol(ctx, style, c, x, y, { h = 16, hot = false, label = true, alpha: dim = 1, ring = null,
                                                   hq = false, lead = null, labelPx = 12, tagPx = 9, faction = true } = {}) {
  const aff = style.affiliation[c.affiliation] ?? style.affiliation.unknown;
  const statuses = (c.status ?? []).map((s) => style.status[s]).filter(Boolean);
  const alpha = dim * Math.min(1, ...statuses.map((s) => s.opacity ?? 1));
  const dash = statuses.find((s) => s.dash)?.dash ?? [];
  h *= Math.min(1, ...statuses.map((s) => s.scale ?? 1));
  const shape = statuses.find((s) => s.shape?.[c.affiliation])?.shape[c.affiliation] ?? aff.shape, hollow = statuses.some((s) => s.hollow);
  const col = hot ? style.palette.fuchsia : aff.color;

  if (statuses.some((s) => s.ellipse)) {                       // uncertainty: where it may be now
    ctx.setLineDash([2, 4]); ctx.strokeStyle = rgba(aff.color, 0.45 * alpha); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.ellipse(x, y, h * 1.9, h * 1.3, 0, 0, Math.PI * 2); ctx.stroke();
  }
  framePath(ctx, shape, x, y, h);
  if (!hollow) { ctx.fillStyle = rgba(aff.color, (aff.fill ?? 0.1) * alpha); ctx.fill(); }
  ctx.setLineDash(dash);
  ctx.strokeStyle = rgba(col, 0.95 * alpha);
  ctx.lineWidth = 1.4;
  ctx.stroke();
  ctx.setLineDash([]);

  const [ew, eh] = frameExtent(shape, h);
  if (hq) {                                                    // APP-6 headquarters staff: down from the left edge
    ctx.strokeStyle = rgba(col, 0.95 * alpha); ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(x - ew, y); ctx.lineTo(x - ew, y + eh + h * 0.9); ctx.stroke();
  }
  if (lead) {                                                  // a pennant from her top-right corner: a formation's leader (hollow), the fleet flagship (filled)
    const mx = x + ew, my = y - eh, top = my - h * 0.8;
    ctx.strokeStyle = rgba(col, 0.95 * alpha); ctx.fillStyle = rgba(col, 0.95 * alpha); ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(mx, my); ctx.lineTo(mx, top); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(mx, top); ctx.lineTo(mx + h * 0.5, top + h * 0.17); ctx.lineTo(mx, top + h * 0.34); ctx.closePath();
    if (lead === 'flagship') ctx.fill(); else ctx.stroke();
  }
  if (ring) {
    ctx.strokeStyle = rgba(ring, 0.9); ctx.lineWidth = 1.2; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.arc(x, y, Math.max(ew, eh) + 6, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
  }
  const cross = Math.max(0, ...statuses.map((s) => (s.cross === true ? 1 : +s.cross || 0)));
  if (cross) {                                                 // out: corner to corner, and past the frame by its share (style.toml)
    const cx = ew * cross, cy = eh * cross;
    ctx.beginPath(); ctx.moveTo(x - cx, y - cy); ctx.lineTo(x + cx, y + cy); ctx.moveTo(x + cx, y - cy); ctx.lineTo(x - cx, y + cy); ctx.stroke();
  } else if (statuses.some((s) => s.slash)) {
    ctx.beginPath(); ctx.moveTo(x - ew, y + eh); ctx.lineTo(x + ew, y - eh); ctx.stroke();
  }
  const ech = style.echelon[c.echelon] ?? '';
  if (ech) text(ctx, ech, x, y - eh - 3, rgba(col, alpha), 10, FONT_MONO, 'center');
  const vet = c.echelon === 'ship' && !c.track ? style.veterancy?.[c.veterancy] : null;   // her crew's stars (style.toml [veterancy])
  if (vet?.stars) stars(ctx, vet.stars, x, y - eh - 6, Math.max(2.5, h * 0.2), rgba(style.palette[vet.color ?? 'silver'] ?? '#c9cfd8', 0.95 * alpha));
  const role = c.echelon !== 'ship' && c.role ? style.formation_role?.[c.role] : null;
  if (hollow) { /* the frame alone */ }
  else if (role) roleMarks(ctx, role.marks, x, y, shape, ew, eh, rgba(col, 0.9 * alpha));
  else if (c.unit_type) text(ctx, c.unit_type.slice(0, 3), x, y + 3.5, rgba(col, 0.9 * alpha), 9, FONT_MONO, 'center');
  else if (c.echelon !== 'ship') {                               // a formation: a small fill of its own
    ctx.fillStyle = rgba(col, 0.8 * alpha); ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
  }
  if (!label) return;
  const lx = x + ew * Math.max(1, cross) + 6;                 // (past an out cross)
  display(ctx, c.callsign, lx, y - 1, rgba(hot ? style.palette.fuchsia : style.palette.ink, 0.92 * alpha), labelPx);
  const tags = [...new Set([faction ? designation(style, c) : null, c.pry ? `Pry-${c.pry}` : null,
                            c.brevity ? c.brevity.toUpperCase() : null].filter(Boolean))].join('  ');
  if (tags) text(ctx, tags, lx, y + 2 + tagPx, rgba(aff.color, 0.85 * alpha), tagPx);
}

// ---- bodies ------------------------------------------------------------------------------------
const images = new Map();
function image(src) {
  if (!src) return null;
  if (!images.has(src)) {
    const im = new Image();
    im.src = `/bodies/${src}`;
    images.set(src, im);
  }
  const im = images.get(src);
  return im.complete && im.naturalWidth ? im : null;
}

// the body's flat display: its image, or a flat disc; a star gets rays, a ringed planet its ring
export function bodyDisplay(ctx, style, b, x, y, r, hot = false) {
  const col = b.display.color;
  const im = image(b.display.image);
  if (b.display.rings) {
    ctx.strokeStyle = rgba(col, 0.55); ctx.lineWidth = Math.max(1, r * 0.12);
    ctx.beginPath(); ctx.ellipse(x, y, r * 1.9, r * 0.5, -0.35, 0, Math.PI * 2); ctx.stroke();
  }
  if (im) ctx.drawImage(im, x - r, y - r, r * 2, r * 2);
  else {
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(7,5,15,0.28)';                          // a flat terminator: one hard shadow
    ctx.beginPath(); ctx.arc(x, y, r, -Math.PI / 2, Math.PI / 2); ctx.ellipse(x, y, r * 0.35, r, 0, Math.PI / 2, -Math.PI / 2, true); ctx.fill();
  }
  if (b.kind === 'star') {
    ctx.strokeStyle = rgba(col, 0.5); ctx.lineWidth = 1.2;
    for (let i = 0; i < 8; i++) {
      const t = (i * Math.PI) / 4;
      ctx.beginPath(); ctx.moveTo(x + Math.cos(t) * r * 1.2, y + Math.sin(t) * r * 1.2); ctx.lineTo(x + Math.cos(t) * r * 1.55, y + Math.sin(t) * r * 1.55); ctx.stroke();
    }
  }
  if (b.display.rings) {                                          // the near half of the ring crosses in front
    ctx.strokeStyle = rgba(col, 0.75); ctx.lineWidth = Math.max(1, r * 0.12);
    ctx.beginPath(); ctx.ellipse(x, y, r * 1.9, r * 0.5, -0.35, 0, Math.PI); ctx.stroke();
  }
  ctx.strokeStyle = hot ? style.palette.fuchsia : rgba(style.palette.violet, 0.8);
  ctx.lineWidth = hot ? 1.5 : 1;
  ctx.beginPath(); ctx.arc(x, y, r + 2.5, 0, Math.PI * 2); ctx.stroke();
}

// the small mark every body keeps when its display is off or folded
export function bodyMark(ctx, style, b, x, y, s, hot = false) {
  ctx.strokeStyle = hot ? style.palette.fuchsia : b.display.color;
  ctx.lineWidth = 1.3;
  ctx.beginPath(); ctx.arc(x, y, s / 2, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = b.display.color;
  ctx.fillRect(x - 1, y - 1, 2, 2);
  if (b.kind === 'star') {
    for (let i = 0; i < 4; i++) {
      const t = (i * Math.PI) / 2 + Math.PI / 4;
      ctx.beginPath(); ctx.moveTo(x + Math.cos(t) * s * 0.7, y + Math.sin(t) * s * 0.7); ctx.lineTo(x + Math.cos(t) * s, y + Math.sin(t) * s); ctx.stroke();
    }
  }
}

export function barycentreMark(ctx, style, x, y) {
  ctx.strokeStyle = rgba(style.palette.dim, 0.7); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x - 4, y); ctx.lineTo(x + 4, y); ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4); ctx.stroke();
}

export function zoneRing(ctx, x, y, r, color, label, dash = [4, 5]) {
  if (r < 6 || r > 1e5) return;
  ctx.setLineDash(dash); ctx.strokeStyle = color; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
  if (label) text(ctx, label, x + r * 0.71 + 4, y - r * 0.71 - 4, color, 9);
}

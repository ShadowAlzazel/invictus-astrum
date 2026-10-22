// Three.js scene for one stellar system, at true scale. Draws what the server sends.
//
// Units: 1 scene unit = 1 km. The system frame (z = up, Eve) maps onto three.js as a proper
// rotation: three.x = x, three.y = z, three.z = -y.
//
// Floating origin: positions arrive as float64 km in the system frame, which the GPU (float32)
// cannot hold at system scale (a 4.5e9 km position keeps ~500 km precision in float32). So the
// camera's target is always the scene origin, and every object is placed at (position − focus),
// computed in float64 here. Near the focus, everything is exact to the metre.
import * as THREE from 'three';
import { MapControls } from 'three/examples/jsm/controls/MapControls.js';

const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
export const toThree = (v, out = new THREE.Vector3()) => out.set(v[0], v[2], -v[1]);
const fromThree = (v) => [v.x, -v.z, v.y];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const NICE = [1, 2, 5];

const AU_KM = 149597870.7;
// a round ring spacing: 1, 2 or 5 × 10ⁿ, in km below ~0.1 AU and in AU above, so labels read clean
function niceStep(x) {
  const au = x > 0.05 * AU_KM;
  const v = au ? x / AU_KM : x, p = Math.pow(10, Math.floor(Math.log10(v)));
  const step = (NICE.find((m) => m * p >= v) ?? 10) * p;
  return au ? step * AU_KM : Math.min(step, 5e6);      // km steps stop at 5 million; AU take over
}

function unitCircle(seg = 256) {
  const pts = [];
  for (let i = 0; i <= seg; i++) { const t = (i / seg) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(t), 0, Math.sin(t))); }
  return new THREE.BufferGeometry().setFromPoints(pts);
}

export class SystemMap {
  static MIN_DISTANCE = 0.01;      // km from the focus: 10 m
  static MAX_DISTANCE = 5e13;      // km: 330,000 AU, the edge of any system worth drawing

  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, logarithmicDepthBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, 1, 1e-3, 1e14);
    this.camera.position.set(0, 3e8, 2.2e8);
    this.controls = new MapControls(this.camera, canvas);
    // three's zoomToCursor drove the camera to NaN when zoomed in close, and nothing recovered from
    // that; zoom is done here instead, in log space, with the cursor anchored (see _zoomStep)
    Object.assign(this.controls, { enableDamping: true, dampingFactor: 0.12, enableZoom: false, maxPolarAngle: Math.PI });
    this._zoomPending = 0;          // log-distance still to apply; eased out over a few frames
    this._cursor = null;            // where the wheel was turned, px
    this._lastGood = this.camera.position.clone();
    this._wheel = this._wheel.bind(this);
    canvas.addEventListener('wheel', this._wheel, { passive: false });

    this.focus = [0, 0, 0];         // float64, system frame, km
    this.follow = null;             // selection the focus rides with: { kind, id }
    this.def = null;                // /api/system
    this.state = null;              // latest /ws state
    this.bullseyeId = 'system';
    this.style = null;
    this.layers = { orbits: true, bullseye: true };
    this.hover = null;              // { kind, id }
    this.selected = null;           // { kind, id } | { kind: 'point', p }
    this.marks = [];                // screen-space marks for the overlay and picking, rebuilt each frame
    this._v = new THREE.Vector3();
    this._fly = null;
    this._frames = [];              // the last few pictures from the server, oldest first
    this._clock = null;             // the moment drawn (the app's clock)
    this._hooks = new Set();

    this.bodyGroup = this._group();
    this.orbitGroup = this._group();
    this.bullGroup = this._group();
    this.meshes = new Map();
    this.orbitLines = new Map();
    this._buildBullseye();
    this.stalks = [0xfa1f99, 0x7433fa].map((c) => {
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
        new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: 0.75 }));
      l.visible = false; l.frustumCulled = false; this.scene.add(l); return l;
    });

    this.resize();
    this._loop = this._loop.bind(this);
    this._raf = requestAnimationFrame(this._loop);
  }

  _group() { const g = new THREE.Group(); this.scene.add(g); return g; }

  setStyle(style) {
    this.style = style;
    const p = style.palette;
    this.renderer.setClearColor(p.void, 1);
    this.orbitMat?.color.set(p.orbit);
    this.ringMat.color.set(p.violet);
    this.spokeMat.color.set(p.violet);
    this.northMat.color.set(p.cyan);
    this.stalks[0].material.color.set(p.fuchsia);
    this.stalks[1].material.color.set(p.violet);
  }

  // ---- the system ----------------------------------------------------------------------------
  // keepView: the same system again (a workshop edit, a live reload): leave the camera be
  setSystem(def, keepView = false) {
    keepView = keepView && this.def?.id === def.id;
    this.def = def;
    this.bodies = Object.fromEntries(def.bodies.map((b) => [b.id, b]));
    for (const m of this.meshes.values()) { this.bodyGroup.remove(m); m.geometry.dispose(); m.material.dispose(); }
    this.meshes.clear();
    for (const b of def.bodies) {
      if (!(b.radius_km > 0)) continue;
      const mat = new THREE.MeshBasicMaterial({ color: b.display.color });
      const m = new THREE.Mesh(new THREE.SphereGeometry(b.radius_km, 64, 32), mat);
      m.userData.id = b.id;
      this.bodyGroup.add(m);
      this.meshes.set(b.id, m);
    }
    if (keepView) {
      if (this.selected?.kind === 'body' && !this.bodies[this.selected.id]) this.selected = null;
      if (this.follow?.kind === 'body' && !this.bodies[this.follow.id]) this.follow = { kind: 'body', id: def.root };
      return;
    }
    this.setOrbits({});
    this.selected = null;
    this.hover = null;
    this.frameAll(false);
  }

  // look at the whole planetary system from above: the furthest orbit under 1,000 AU
  // (Proxima's 13,000 AU would shrink Alpha Centauri A–B to a dot)
  frameAll(fly = true) {
    const def = this.def;
    if (!def) return;
    const apo = def.bodies.map((b) => b.orbit?.apoapsis_km ?? 0).filter((a) => a > 0);
    const near = apo.filter((a) => a < 1.5e11);
    const rootR = this.bodies[def.root]?.radius_km ?? 0;
    const extent = Math.max(...(near.length ? near : apo), rootR * 4, 1e6);
    const root = { kind: 'body', id: def.root };
    if (fly) { this.focusOn(root, extent * 2.7); return; }
    this.follow = root;
    this.focus = [0, 0, 0];
    this.camera.position.set(0, extent * 2.2, extent * 1.6);
    this.controls.target.set(0, 0, 0);
  }

  setOrbits(orbits) {
    for (const l of this.orbitLines.values()) { this.orbitGroup.remove(l); l.geometry.dispose(); }
    this.orbitLines.clear();
    this.orbitMat ??= new THREE.LineBasicMaterial({ color: this.style?.palette.orbit ?? '#5b4a8f', transparent: true, opacity: 0.6 });
    for (const [id, o] of Object.entries(orbits)) {
      const p = o.points, pts = new Float32Array(p.length);
      for (let i = 0; i < p.length; i += 3) { pts[i] = p[i]; pts[i + 1] = p[i + 2]; pts[i + 2] = -p[i + 1]; }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pts, 3));
      const line = new THREE.Line(g, this.orbitMat);
      line.userData = { id, parent: o.parent };
      line.frustumCulled = false;
      this.orbitGroup.add(line);
      this.orbitLines.set(id, line);
    }
  }

  // Pictures are asked for a little ahead of the clock; each frame draws the clock's own moment,
  // every position drawn straight between the two pictures around it (or carried on from the last
  // two, if the next is late), so motion is smooth however the pictures arrive. A picture replaces
  // any asked for at or after its moment (an order changed what they showed). The state is made
  // once at the start of a frame, so the scene, the overlay and the cursor all draw the same instant.
  setState(state) {
    const keep = this._frames.filter((f) => f.system === state.system && f.t < state.t - 1e-6);
    this._frames = [...keep, state].slice(-3);
  }
  setClock(t) { this._clock = t; }
  onFrame(fn) { this._hooks.add(fn); return () => this._hooks.delete(fn); }
  setLayer(name, on) { this.layers[name] = on; }

  // ---- bullseye: rings and spokes in its plane, scaled to the view -----------------------------
  _buildBullseye() {
    this.ringMat = new THREE.LineBasicMaterial({ color: 0x7433fa, transparent: true, opacity: 0.24 });
    this.spokeMat = new THREE.LineBasicMaterial({ color: 0x7433fa, transparent: true, opacity: 0.14 });
    this.northMat = new THREE.LineBasicMaterial({ color: 0x9ff0ff, transparent: true, opacity: 0.55 });
    const circle = unitCircle();
    this.rings = [1, 2, 3, 4, 5].map(() => { const l = new THREE.Line(circle, this.ringMat); this.bullGroup.add(l); return l; });
    const spokes = [];
    for (let b = 30; b < 360; b += 30) {
      const t = (b * Math.PI) / 180;            // clockwise from 000 seen from Eve: local (cos, 0, sin) in three
      spokes.push(new THREE.Vector3(Math.cos(t) * 0.2, 0, Math.sin(t) * 0.2), new THREE.Vector3(Math.cos(t), 0, Math.sin(t)));
    }
    this.spokes = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(spokes), this.spokeMat);
    this.north = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0), new THREE.Vector3(1.08, 0, 0),           // 000
      new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0.25, 0)]), this.northMat);   // Eve
    this.bullGroup.add(this.spokes, this.north);
    for (const o of this.bullGroup.children) o.frustumCulled = false;
  }

  bullseye() { return this.state?.bullseyes?.[this.bullseyeId] ?? this.state?.bullseyes?.system ?? null; }

  _placeBullseye() {
    const b = this.bullseye();
    this.bullGroup.visible = !!b && this.layers.bullseye;
    if (!b) return;
    // local three axes: x = 000, y = Eve, z = 090 (clockwise from above). Columns in three coords.
    const [ref, left, up] = b.axes;
    const m = new THREE.Matrix4().makeBasis(toThree(ref), toThree(up), toThree(left).multiplyScalar(-1));
    this.bullGroup.position.copy(toThree(sub(b.origin, this.focus)));
    this.bullGroup.quaternion.setFromRotationMatrix(m);
    const d = Math.max(this.camera.position.distanceTo(this.bullGroup.position), 1);
    this.ringStep = niceStep(d / 10);
    this.rings.forEach((r, i) => r.scale.setScalar(this.ringStep * (i + 1)));
    this.spokes.scale.setScalar(this.ringStep * 5);
    this.north.scale.setScalar(this.ringStep * 5);
  }

  // ---- geometry helpers ------------------------------------------------------------------------
  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this._pxPerRad = h / 2 / Math.tan((this.camera.fov * Math.PI) / 360);
  }

  // system-frame point (km) -> screen px, or null behind the camera
  project(p) {
    toThree(sub(p, this.focus), this._v);
    const depth = this._v.clone().applyMatrix4(this.camera.matrixWorldInverse).z;
    if (depth >= 0) return null;
    this._v.project(this.camera);
    return { x: (this._v.x + 1) / 2 * this.canvas.clientWidth, y: (1 - this._v.y) / 2 * this.canvas.clientHeight, depth: -depth };
  }

  // project for many points at once: origin (system frame km) plus offsets from it (rel: 3 a point),
  // into out (2 a point, x and y px; NaN behind the camera). The camera's matrices once, nothing made
  projectMany(origin, rel, out) {
    const v = this.camera.matrixWorldInverse.elements, P = this.camera.projectionMatrix.elements;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight, n = rel.length / 3;
    const ox = origin[0] - this.focus[0], oy = origin[1] - this.focus[1], oz = origin[2] - this.focus[2];
    for (let k = 0; k < n; k++) {
      const X = ox + rel[3 * k], Y = oz + rel[3 * k + 2], Z = -(oy + rel[3 * k + 1]);      // (as toThree)
      const vx = v[0] * X + v[4] * Y + v[8] * Z + v[12], vy = v[1] * X + v[5] * Y + v[9] * Z + v[13];
      const vz = v[2] * X + v[6] * Y + v[10] * Z + v[14];
      if (vz >= 0) { out[2 * k] = out[2 * k + 1] = NaN; continue; }
      const cw = P[3] * vx + P[7] * vy + P[11] * vz + P[15];
      out[2 * k] = ((P[0] * vx + P[4] * vy + P[8] * vz + P[12]) / cw + 1) / 2 * w;
      out[2 * k + 1] = (1 - (P[1] * vx + P[5] * vy + P[9] * vz + P[13]) / cw) / 2 * h;
    }
    return out;
  }

  // a sphere of radius r km at p -> its radius on screen, px
  pxRadius(p, r) {
    const s = this.project(p);
    return s ? (r / s.depth) * this._pxPerRad : 0;
  }

  // point on the bullseye plane under the cursor, system frame km
  // the point under the cursor on the bullseye's plane, or on the plane parallel to it through `through` (km)
  planeAt(px, py, through = null) {
    const b = this.bullseye();
    if (!b) return null;
    const ndc = new THREE.Vector2(px / this.canvas.clientWidth * 2 - 1, -(py / this.canvas.clientHeight) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.camera);
    const n = toThree(b.axes[2]);
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(n, toThree(sub(through ?? b.origin, this.focus)));
    const hit = ray.ray.intersectPlane(plane, new THREE.Vector3());
    if (!hit) return null;
    const p = fromThree(hit);
    return [p[0] + this.focus[0], p[1] + this.focus[1], p[2] + this.focus[2]];
  }

  // bearing, elevation, range from the active bullseye (display geometry on server-sent axes)
  aer(p) {
    const b = this.bullseye();
    if (!b) return null;
    const d = sub(p, b.origin), [ref, left, up] = b.axes;
    const x = dot(d, ref), y = dot(d, left), z = dot(d, up), r = Math.hypot(x, y, z);
    return { bearing: ((Math.atan2(-y, x) * 180) / Math.PI + 360) % 360, elevation: r ? (Math.asin(z / r) * 180) / Math.PI : 0, range: r };
  }

  footOf(p) {
    const b = this.bullseye();
    if (!b) return null;
    const up = b.axes[2], h = dot(sub(p, b.origin), up);
    return [p[0] - up[0] * h, p[1] - up[1] * h, p[2] - up[2] * h];
  }

  ringLabels() {
    const b = this.bullseye();
    if (!b || !this.layers.bullseye) return [];
    const ref = b.axes[0];
    return [1, 2, 3, 4, 5].map((i) => {
      const r = this.ringStep * i;
      return { r, p: this.project([b.origin[0] + ref[0] * r, b.origin[1] + ref[1] * r, b.origin[2] + ref[2] * r]) };
    }).filter((o) => o.p);
  }

  bearingLabels() {
    const b = this.bullseye();
    if (!b || !this.layers.bullseye) return [];
    const [ref, left] = b.axes, R = this.ringStep * 5.4;
    const out = [];
    for (let deg = 0; deg < 360; deg += 30) {
      const t = (deg * Math.PI) / 180, c = Math.cos(t) * R, s = -Math.sin(t) * R;
      const p = this.project([b.origin[0] + ref[0] * c + left[0] * s, b.origin[1] + ref[1] * c + left[1] * s, b.origin[2] + ref[2] * c + left[2] * s]);
      if (p) out.push({ deg, p });
    }
    return out;
  }

  position(sel) {
    if (!sel || !this.state) return null;
    if (sel.kind === 'body') return this.state.bodies[sel.id] ?? null;
    if (sel.kind === 'contact') return this.state.contacts?.[sel.id] ?? null;
    if (sel.kind === 'point') return sel.p;
    return null;
  }

  // ---- camera ----------------------------------------------------------------------------------
  // glide to a body and ride with it; the view distance shrinks to suit what was chosen
  focusOn(sel, distanceKm = null) {
    const p = this.position(sel);
    if (!p) return;
    this.follow = null;
    const from = [...this.focus];
    this._fly = { from, sel, t0: performance.now(), ms: reduceMotion ? 0 : 700, distance: distanceKm, d0: this.camera.position.length() };
  }

  // ---- zoom ------------------------------------------------------------------------------------
  _wheel(e) {
    e.preventDefault();
    const dy = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
    this._zoomPending += Math.max(-1, Math.min(1, dy * 0.0016));
    this._cursor = { x: e.clientX, y: e.clientY };
  }

  // one eased step of zoom. The target sits at the scene origin, so zoom is scaling the camera's
  // offset. Zooming in with nothing followed keeps the point under the cursor under the cursor:
  // the target slides toward it (the slide becomes a focus shift in _recentre). Zooming out
  // stays centred, or repeated zoom-outs would drift the view into empty space.
  _zoomStep() {
    if (Math.abs(this._zoomPending) < 1e-4) { this._zoomPending = 0; return; }
    const step = this._zoomPending * 0.3;
    this._zoomPending -= step;
    const d = this.camera.position.length();
    const d2 = Math.min(Math.max(d * Math.exp(step), SystemMap.MIN_DISTANCE), SystemMap.MAX_DISTANCE);
    const k = d2 / d;
    if (!isFinite(k) || k === 1) return;
    let shift = null;
    if (k < 1 && !this.follow && !this._fly && this._cursor) {
      const ndc = new THREE.Vector2(this._cursor.x / this.canvas.clientWidth * 2 - 1, -(this._cursor.y / this.canvas.clientHeight) * 2 + 1);
      const ray = new THREE.Raycaster();
      ray.setFromCamera(ndc, this.camera);
      const view = this.camera.position.clone().negate().normalize();
      const c = ray.ray.direction.dot(view);
      if (c > 0.05) shift = ray.ray.origin.clone().addScaledVector(ray.ray.direction, d / c).multiplyScalar(1 - k);
    }
    this.camera.position.multiplyScalar(k);
    if (shift) { this.camera.position.add(shift); this.controls.target.add(shift); }
  }

  // nothing may sit inside a body: push the camera back out to just above the surface
  _keepOutside() {
    if (!this.state) return;
    const cam = fromThree(this.camera.position);
    const w = [cam[0] + this.focus[0], cam[1] + this.focus[1], cam[2] + this.focus[2]];
    for (const [id, m] of this.meshes) {
      const p = this.state.bodies[id];
      if (!p) continue;
      const r = m.geometry.parameters.radius, floor = r * 1.002 + 0.05;
      const d = sub(w, p), dist = Math.hypot(...d);
      if (dist >= floor) continue;
      const u = dist > 0 ? d.map((x) => x / dist) : [0, 0, 1];
      const out = [p[0] + u[0] * floor - this.focus[0], p[1] + u[1] * floor - this.focus[1], p[2] + u[2] * floor - this.focus[2]];
      toThree(out, this.camera.position);
      break;
    }
  }

  _recentre() {
    // keep the camera's target at the scene origin: move the float64 focus instead
    const t = this.controls.target;
    if (t.lengthSq() === 0) return;
    const d = fromThree(t);
    if (this.follow && !this._fly) this.follow = null;     // the user panned away from the body
    this.focus = [this.focus[0] + d[0], this.focus[1] + d[1], this.focus[2] + d[2]];
    this.camera.position.sub(t);
    t.set(0, 0, 0);
  }

  _loop(now) {
    this._raf = requestAnimationFrame(this._loop);
    this.state = this._at(this._clock);
    if (this._fly) {
      const f = this._fly, u = f.ms ? Math.min((now - f.t0) / f.ms, 1) : 1, e = 1 - (1 - u) ** 3;
      const to = this.position(f.sel) ?? f.from;
      this.focus = [f.from[0] + (to[0] - f.from[0]) * e, f.from[1] + (to[1] - f.from[1]) * e, f.from[2] + (to[2] - f.from[2]) * e];
      if (f.distance) this.camera.position.setLength(Math.exp(Math.log(f.d0) + (Math.log(f.distance) - Math.log(f.d0)) * e));
      if (u >= 1) { this._fly = null; if (f.sel.kind !== 'point') this.follow = f.sel; }
    } else if (this.follow) {
      const p = this.position(this.follow);
      if (p) this.focus = [...p];
    }
    this._zoomStep();
    this.controls.update();
    this._recentre();
    this._keepOutside();
    // last line of defence: a non-finite camera would blank the map for good
    const c = this.camera.position;
    if (!(isFinite(c.x) && isFinite(c.y) && isFinite(c.z)) || c.lengthSq() === 0 || !this.focus.every(isFinite)) {
      this.camera.position.copy(this._lastGood);
      this.controls.target.set(0, 0, 0);
      if (!this.focus.every(isFinite)) this.focus = [0, 0, 0];
      this._zoomPending = 0;
    } else this._lastGood.copy(c);
    this._place();
    this.renderer.render(this.scene, this.camera);
    for (const fn of this._hooks) fn(now);
  }

  _at(T) {
    const fs = this._frames, n = fs.length;
    if (!n) return null;
    let i = fs.findIndex((f) => f.t >= T);
    if (i < 0) i = n - 1;                                // past the last picture: carry on from the last two
    if (T == null || i === 0 || Math.abs(fs[i].t - T) < 1e-6) return fs[i];
    const a = fs[i - 1], b = fs[i], u = Math.min((T - a.t) / (b.t - a.t), 2);
    const mix = (A, B) => {
      const out = {};
      for (const k in B) { const p = A?.[k], q = B[k]; out[k] = p && q ? [p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u, p[2] + (q[2] - p[2]) * u] : q; }
      return out;
    };
    const bulls = {};
    for (const k in b.bullseyes) bulls[k] = { ...b.bullseyes[k], origin: mix({ o: a.bullseyes[k]?.origin }, { o: b.bullseyes[k].origin }).o };
    return { ...b, t: T, bodies: mix(a.bodies, b.bodies), contacts: mix(a.contacts, b.contacts), bullseyes: bulls };
  }

  _place() {
    const s = this.state;
    if (!s || !this.def) return;
    for (const [id, m] of this.meshes) {
      const p = s.bodies[id];
      m.visible = !!p;
      if (p) toThree(sub(p, this.focus), m.position);
    }
    this.orbitGroup.visible = this.layers.orbits;
    for (const l of this.orbitLines.values()) {
      const p = s.bodies[l.userData.parent];
      l.visible = !!p;
      if (p) toThree(sub(p, this.focus), l.position);
    }
    this._placeBullseye();
    this._stalk(this.stalks[0], this.position(this.selected));
    const hp = this.hover && !(this.selected && this.hover.id === this.selected.id) ? this.position(this.hover) : null;
    this._stalk(this.stalks[1], hp);
  }

  // drop line from a point to the bullseye plane: the third dimension at a glance
  _stalk(line, p) {
    const f = p && this.layers.bullseye ? this.footOf(p) : null;
    line.visible = !!f && Math.hypot(...sub(p, f)) > 1e-6 * Math.hypot(...sub(p, this.focus)) + 1;
    if (!line.visible) return;
    const a = toThree(sub(p, this.focus)), b = toThree(sub(f, this.focus));
    line.geometry.attributes.position.array.set([a.x, a.y, a.z, b.x, b.y, b.z]);
    line.geometry.attributes.position.needsUpdate = true;
  }

  dispose() {
    cancelAnimationFrame(this._raf);
    this.canvas.removeEventListener('wheel', this._wheel);
    this.controls.dispose();
    this.renderer.dispose();
  }
}

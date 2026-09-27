/**
 * PacketScene - the Packet Anatomy Explorer's 3D view.
 *
 * One real ESP packet (see data/packet.js) laid out in wire order as slabs:
 *   outer IP | ESP header | IV | encrypted payload | ICV
 *
 * Visual classes encode the deterministic-vs-ML boundary:
 *   parsed  cyan glass    read directly by deterministic code
 *   sealed  dark metal +  never decrypted; carries a padlock
 *           padlock
 *   unused  faint slate   in the clear, but carries no information (IV, ICV)
 *   measured violet       a dimension line: the payload's LENGTH is the only
 *                         thing about it that reaches the model
 *
 * Slab widths are compressed (sqrt of byte count) so 8-byte fields stay
 * visible next to the 192-byte payload; the page's byte map shows true scale.
 *
 * Interaction: drag to rotate (horizontal drags only, so vertical swipes still
 * scroll the page on touch), setExplode(0..1) to peel the layers apart,
 * select(id) to spotlight one layer. Renders only while on screen.
 */
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

const COLOR = {
  bg: 0x05070d,
  signal: 0x22d3ee,
  slate: 0x94a3b8,
  metal: 0x0c1320,
  ai: 0xa78bfa,
};
const DEPTH = 1.5; // z
const HEIGHT = 1.05; // y
const GAP = 0.62; // extra spacing per layer when fully exploded

const widthFor = (bytes) => 0.45 + 2.5 * Math.sqrt(bytes / 244);

export class PacketScene {
  constructor(canvas, labelRoot, { layers, onSelect } = {}) {
    this.canvas = canvas;
    this.labelRoot = labelRoot;
    this.layers = layers;
    this.onSelect = onSelect;
    this.explode = 0;
    this.explodeTarget = 0;
    this.yaw = -0.5;
    this.pitch = 0.32;
    this.yawTarget = this.yaw;
    this.pitchTarget = this.pitch;
    this.selected = null;
    this.visible = false;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);

    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(3, 6, 5);
    const rim = new THREE.DirectionalLight(COLOR.signal, 1.4);
    rim.position.set(-4, 2, -6);
    this.scene.add(key, rim, new THREE.AmbientLight(0x334155, 0.5));

    this.labels = new CSS2DRenderer({ element: labelRoot });

    this.group = new THREE.Group();
    this.scene.add(this.group);
    this._buildSlabs();

    this._bindPointer();
    this._ro = new ResizeObserver(() => this._resize());
    this._ro.observe(canvas);
    this._resize();
  }

  // ------------------------------------------------------------ geometry

  _buildSlabs() {
    this.slabs = [];
    const widths = this.layers.map((l) => widthFor(l.bytes));
    this.packedWidth = widths.reduce((a, b) => a + b, 0);

    this.layers.forEach((layer, i) => {
      const w = widths[i];
      const slab = new THREE.Group();
      slab.userData = { id: layer.id, index: i, width: w };

      const geo = new THREE.BoxGeometry(w * 0.985, HEIGHT, DEPTH);
      const body = new THREE.Mesh(geo, this._bodyMaterial(layer.kind));
      body.userData.layerId = layer.id;
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), this._edgeMaterial(layer.kind));
      slab.add(body, edges);
      slab.userData.body = body;
      slab.userData.edges = edges;

      // ESP header: show the SPI | sequence split on its top face.
      if (layer.id === 'esp') {
        const split = new THREE.LineSegments(
          new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(0, HEIGHT / 2 + 0.002, -DEPTH / 2),
            new THREE.Vector3(0, HEIGHT / 2 + 0.002, DEPTH / 2),
            new THREE.Vector3(0, -HEIGHT / 2, DEPTH / 2 + 0.002),
            new THREE.Vector3(0, HEIGHT / 2, DEPTH / 2 + 0.002),
          ]),
          this._edgeMaterial('parsed')
        );
        slab.add(split);
      }

      if (layer.kind === 'sealed') {
        slab.add(this._padlock());
        slab.add(this._dimension(w, `${layer.bytes} B`));
      }

      // Floating label (HTML, so it stays crisp and readable).
      const el = document.createElement('div');
      el.className = `pkt-label pkt-label--${layer.kind}`;
      const name = document.createElement('span');
      name.className = 'pkt-label__name';
      name.textContent = layer.name;
      const bytes = document.createElement('span');
      bytes.className = 'pkt-label__bytes';
      bytes.textContent = `${layer.bytes} B`;
      el.append(name, bytes);
      const label = new CSS2DObject(el);
      label.position.set(0, HEIGHT / 2 + 0.42, 0);
      slab.add(label);
      slab.userData.label = el;

      this.group.add(slab);
      this.slabs.push(slab);
    });
    this._layout();
  }

  _bodyMaterial(kind) {
    if (kind === 'sealed') {
      return new THREE.MeshStandardMaterial({ color: COLOR.metal, metalness: 0.85, roughness: 0.42, envMapIntensity: 0.5, transparent: true });
    }
    if (kind === 'parsed') {
      return new THREE.MeshStandardMaterial({
        color: COLOR.signal,
        emissive: COLOR.signal,
        emissiveIntensity: 0.18,
        roughness: 0.3,
        transparent: true,
        opacity: 0.2,
        depthWrite: false,
      });
    }
    return new THREE.MeshStandardMaterial({ color: COLOR.slate, transparent: true, opacity: 0.06, depthWrite: false });
  }

  _edgeMaterial(kind) {
    const color = kind === 'parsed' ? COLOR.signal : COLOR.slate;
    const opacity = kind === 'parsed' ? 0.95 : kind === 'sealed' ? 0.45 : 0.35;
    return new THREE.LineBasicMaterial({ color, transparent: true, opacity });
  }

  // A small, plain padlock on the payload's front face.
  _padlock() {
    const lock = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({ color: COLOR.slate, metalness: 0.6, roughness: 0.35 });
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.26, 0.07), mat);
    const shackle = new THREE.Mesh(new THREE.TorusGeometry(0.095, 0.024, 10, 24, Math.PI), mat);
    shackle.position.y = 0.13;
    const keyhole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.028, 0.028, 0.02, 16),
      new THREE.MeshBasicMaterial({ color: COLOR.metal })
    );
    keyhole.rotation.x = Math.PI / 2;
    keyhole.position.z = 0.04;
    lock.add(body, shackle, keyhole);
    lock.position.set(0, -0.04, DEPTH / 2 + 0.05);
    return lock;
  }

  // Violet dimension line under the payload: its length is what the model sees.
  _dimension(w, text) {
    const g = new THREE.Group();
    const y = -HEIGHT / 2 - 0.22;
    const z = DEPTH / 2;
    const half = (w * 0.985) / 2;
    const mat = new THREE.LineBasicMaterial({ color: COLOR.ai });
    g.add(
      new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(-half, y, z), new THREE.Vector3(half, y, z),
          new THREE.Vector3(-half, y - 0.08, z), new THREE.Vector3(-half, y + 0.08, z),
          new THREE.Vector3(half, y - 0.08, z), new THREE.Vector3(half, y + 0.08, z),
        ]),
        mat
      )
    );
    const el = document.createElement('div');
    el.className = 'pkt-dim';
    const note = document.createElement('span');
    note.className = 'pkt-dim__note';
    note.textContent = ': measured, not read';
    el.append(`length ${text}`, note);
    const label = new CSS2DObject(el);
    label.position.set(0, y - 0.34, z);
    g.add(label);
    return g;
  }

  // Wire-order placement; explode adds a gap between neighbours and a gentle
  // vertical fan so the layers read as separate objects.
  _layout() {
    const total = this.packedWidth + GAP * this.explode * (this.slabs.length - 1);
    let x = -total / 2;
    this.slabs.forEach((slab, i) => {
      const w = slab.userData.width;
      slab.position.x = x + w / 2;
      slab.position.y = Math.sin((i / (this.slabs.length - 1)) * Math.PI) * 0.18 * this.explode;
      x += w + GAP * this.explode;
    });
  }

  // ---------------------------------------------------------- selection

  select(id) {
    this.selected = id;
    this.slabs.forEach((slab) => {
      const on = !id || slab.userData.id === id;
      slab.userData.label.classList.toggle('is-dim', !on);
      slab.userData.label.classList.toggle('is-active', !!id && on);
      const body = slab.userData.body.material;
      const edges = slab.userData.edges.material;
      body.userData.base ??= body.opacity;
      edges.userData.base ??= edges.opacity;
      body.opacity = on ? body.userData.base : body.userData.base * 0.3;
      edges.opacity = on ? edges.userData.base : edges.userData.base * 0.25;
    });
  }

  setExplode(v) {
    this.explodeTarget = v;
  }

  // ------------------------------------------------------------ input

  _bindPointer() {
    const el = this.canvas;
    let drag = null;
    el.addEventListener('pointerdown', (e) => {
      drag = { x: e.clientX, y: e.clientY, moved: false, id: e.pointerId };
    });
    el.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) > 4) {
        drag.moved = true;
        el.setPointerCapture(e.pointerId);
      }
      if (!drag.moved) return;
      this.yawTarget += dx * 0.008;
      this.pitchTarget = THREE.MathUtils.clamp(this.pitchTarget + dy * 0.004, -0.2, 0.7);
      drag.x = e.clientX;
      drag.y = e.clientY;
    });
    const end = (e) => {
      if (drag && !drag.moved) this._pick(e);
      drag = null;
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', () => (drag = null));
  }

  _pick(e) {
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.camera);
    const hit = ray.intersectObjects(this.slabs.map((s) => s.userData.body))[0];
    const id = hit?.object.userData.layerId ?? null;
    this.onSelect?.(id === this.selected ? null : id);
  }

  // ----------------------------------------------------------- lifecycle

  _resize() {
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.labels.setSize(w, h);
    // Narrow stages: labels show byte counts only; the layer list has the names.
    this.labelRoot.classList.toggle('is-narrow', w < 560);
    this.camera.aspect = w / h;
    // Fit the fully exploded packet's width with a margin.
    const span = this.packedWidth + GAP * (this.slabs.length - 1) + 0.6;
    const hfov = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2)) * this.camera.aspect);
    this.distance = span / 2 / Math.tan(hfov / 2) + DEPTH;
    this.camera.updateProjectionMatrix();
    this._render();
  }

  _render() {
    const e = 1 - Math.exp(-this._dt * 7);
    this.explode += (this.explodeTarget - this.explode) * e;
    this.yaw += (this.yawTarget - this.yaw) * e;
    this.pitch += (this.pitchTarget - this.pitch) * e;
    this._layout();

    this.group.rotation.set(0, 0, 0);
    this.camera.position.set(
      Math.sin(this.yaw) * Math.cos(this.pitch) * this.distance,
      Math.sin(this.pitch) * this.distance,
      Math.cos(this.yaw) * Math.cos(this.pitch) * this.distance
    );
    this.camera.lookAt(0, 0.12, 0);
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  }

  _dt = 1 / 60;

  setVisible(v) {
    if (v === this.visible) return;
    this.visible = v;
    if (!v) return cancelAnimationFrame(this._raf);
    let last = performance.now();
    const loop = (now) => {
      this._dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      this._render();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }
}

/**
 * TunnelScene - the hero's WebGL layer.
 *
 * The metaphor, in three objects:
 *   1. TUNNEL   an opaque, dark-metal tube. It is the IPsec tunnel: you cannot
 *               see through its walls, only down its open mouth.
 *   2. PACKETS  glowing capsules flowing through it in bursts, like real traffic
 *               (a burst of large packets, then sparse small keep-alives).
 *   3. SHADOW   a translucent band cast on a wall beside the tunnel. Its height
 *               at each point along the path is driven by how many packets
 *               (weighted by size) are passing that point right now. Past the
 *               mouth you can no longer see the packets - but the wall still
 *               shows every burst. Payload is sealed; its outline leaks.
 *
 * Rendering: selective bloom. Only packets and tunnel edge lines glow. Each frame
 * the scene is rendered twice - once with every non-glowing object blacked out
 * (or hidden) into a bloom target, then normally, with the bloom added on top.
 * Low-tier devices skip bloom entirely and render once.
 */
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const COLOR = {
  bg: 0x05070d,
  signal: 0x22d3ee, // cyan: observable / cleartext data
  metal: 0x0c1320,
  shadowFill: 0x8fb3c9,
  shadowEdge: 0x67e8f9,
};

const TIERS = {
  high: { maxPackets: 700, emitScale: 1.0, bloom: true, maxDpr: 1.5, tubular: 480, radial: 48, shadowSegs: 180 },
  low: { maxPackets: 260, emitScale: 0.55, bloom: false, maxDpr: 1.25, tubular: 220, radial: 24, shadowSegs: 110 },
};

const BLOOM_LAYER = 1;
const TUNNEL_RADIUS = 1.3;
const PACKET_SPEED = 5.2; // world units / second: steady, readable, not frantic
const SHADOW_OFFSET = 3.1; // wall distance beside the tunnel axis (far side from camera)
const SHADOW_Y = 2.35; // band centre height on the wall
const SHADOW_SPAN = [0.015, 0.985]; // portion of the path the ribbon covers (u)
const LUT_SIZE = 1024; // precomputed path samples, avoids curve math per packet

// Camera keyframes. Scroll progress 0 -> 1 interpolates between them.
// Start: outside, three-quarter view of the mouth, looking down the tunnel with
// the shadow wall on the far side. End: at the mouth, looking straight in
// (never past it - packets spawn at the mouth and must stay ahead of the lens).
const CAM = {
  from: new THREE.Vector3(-3.1, 1.7, 9.6),
  to: new THREE.Vector3(0.0, 0.25, 3.1),
  lookFrom: new THREE.Vector3(-3.2, 0.7, -14),
  lookTo: new THREE.Vector3(0.3, 0.05, -24),
};
// Portrait screens: the copy sits in the lower half, so frame the tunnel
// centred in the upper half instead of to the right of the text.
const CAM_PORTRAIT = {
  from: new THREE.Vector3(-1.9, 2.3, 14),
  to: new THREE.Vector3(0.0, 0.25, 3.3),
  lookFrom: new THREE.Vector3(0.4, -4.2, -14),
  lookTo: new THREE.Vector3(0.3, -0.6, -24),
};

const easeInOutSine = (t) => -(Math.cos(Math.PI * t) - 1) / 2;
const rand = (a, b) => a + Math.random() * (b - a);

export class TunnelScene {
  constructor(canvas, { tier = 'high', onStats = null } = {}) {
    this.canvas = canvas;
    this.cfg = { ...TIERS[tier] };
    this.tier = tier;
    this.onStats = onStats;
    this.progress = 0;
    this.active = true;
    this._last = 0; // rAF timestamp of the previous frame
    this.elapsed = 0;

    this._initRenderer();
    this._initPath();
    this._initTunnel();
    this._initPackets();
    this._initShadow();
    this._initPost();
    this._resize();

    this._onResize = () => this._resize();
    window.addEventListener('resize', this._onResize);
  }

  // ---------------------------------------------------------------- setup

  _initRenderer() {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: this.tier === 'high',
      powerPreference: 'high-performance',
    });
    this.dpr = Math.min(window.devicePixelRatio || 1, this.cfg.maxDpr);
    this.renderer.setPixelRatio(this.dpr);

    this.scene = new THREE.Scene();
    this.bgColor = new THREE.Color(COLOR.bg);
    this.scene.background = this.bgColor;
    this.scene.fog = new THREE.FogExp2(COLOR.bg, 0.024);

    this.camera = new THREE.PerspectiveCamera(52, 1, 0.1, 200);

    // Low-intensity studio environment so the metal reads as metal, plus one
    // cyan light from deep inside the tunnel for the faint rim on its edges.
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();
    const rim = new THREE.DirectionalLight(COLOR.signal, 1.6);
    rim.position.set(0, 4, -30);
    this.scene.add(rim, new THREE.AmbientLight(0x1a2233, 0.6));

    this.canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      this.stop();
      this.canvas.dispatchEvent(new CustomEvent('scene-failed'));
    });
  }

  // The tunnel path: gentle S-bends so the vanishing point drifts as the camera
  // moves, instead of a dead-straight pipe.
  _initPath() {
    this.curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0, 0, 2),
      new THREE.Vector3(0, 0, -8),
      new THREE.Vector3(1.4, 0.25, -22),
      new THREE.Vector3(-1.2, -0.15, -38),
      new THREE.Vector3(0.9, 0.35, -54),
      new THREE.Vector3(0, 0, -72),
    ]);
    this.pathLength = this.curve.getLength();

    const frames = this.curve.computeFrenetFrames(LUT_SIZE - 1, false);
    this.lut = {
      pos: Array.from({ length: LUT_SIZE }, (_, i) => this.curve.getPointAt(i / (LUT_SIZE - 1))),
      tan: frames.tangents,
      nor: frames.normals,
      bin: frames.binormals,
    };
  }

  // Interpolated position on the path at u in [0,1]; returns nearest LUT index
  // (for the frame vectors).
  _sample(u, out) {
    const f = Math.min(Math.max(u, 0), 1) * (LUT_SIZE - 1);
    const i = Math.min(LUT_SIZE - 2, Math.floor(f));
    const t = f - i;
    out.lerpVectors(this.lut.pos[i], this.lut.pos[i + 1], t);
    return t < 0.5 ? i : i + 1;
  }

  _initTunnel() {
    const { tubular, radial } = this.cfg;

    // 1a. The shell: opaque dark metal, visible from inside and out.
    const tube = new THREE.Mesh(
      new THREE.TubeGeometry(this.curve, tubular, TUNNEL_RADIUS, radial, false),
      new THREE.MeshStandardMaterial({
        color: COLOR.metal,
        metalness: 0.9,
        roughness: 0.45,
        side: THREE.DoubleSide,
        envMapIntensity: 0.22,
      })
    );
    this.scene.add(tube);
    this.darkenInBloom = [tube]; // occludes glow behind it, but doesn't glow itself

    // 1b. Edge lines (glow): rings every RING_STEP units, just outside and just
    // inside the wall so they read from both the exterior and interior views,
    // plus a few faint longitudinal rails.
    const RING_STEP = 1.8;
    const RING_SEGS = 64;
    const rings = [];
    const rails = [];
    const p = new THREE.Vector3();
    const q = new THREE.Vector3();
    const ringCount = Math.floor(this.pathLength / RING_STEP);
    for (let k = 0; k <= ringCount; k++) {
      const i = this._sample((k * RING_STEP) / this.pathLength, p);
      const N = this.lut.nor[i];
      const B = this.lut.bin[i];
      for (const r of [TUNNEL_RADIUS * 1.012, TUNNEL_RADIUS * 0.985]) {
        for (let s = 0; s < RING_SEGS; s++) {
          for (const a of [(s / RING_SEGS) * Math.PI * 2, ((s + 1) / RING_SEGS) * Math.PI * 2]) {
            q.copy(p).addScaledVector(N, Math.cos(a) * r).addScaledVector(B, Math.sin(a) * r);
            rings.push(q.x, q.y, q.z);
          }
        }
      }
    }
    const RAILS = 8;
    for (let r = 0; r < RAILS; r++) {
      const a = (r / RAILS) * Math.PI * 2 + Math.PI / RAILS;
      for (let i = 0; i < LUT_SIZE - 4; i += 4) {
        for (const j of [i, i + 4]) {
          q.copy(this.lut.pos[j])
            .addScaledVector(this.lut.nor[j], Math.cos(a) * TUNNEL_RADIUS * 1.012)
            .addScaledVector(this.lut.bin[j], Math.sin(a) * TUNNEL_RADIUS * 1.012);
          rails.push(q.x, q.y, q.z);
        }
      }
    }
    const lineObj = (arr, opacity) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
      const l = new THREE.LineSegments(
        g,
        new THREE.LineBasicMaterial({ color: COLOR.signal, transparent: true, opacity, depthWrite: false })
      );
      l.layers.enable(BLOOM_LAYER);
      return l;
    };
    this.scene.add(lineObj(rings, 0.16), lineObj(rails, 0.09));

    // 1c. A brighter lip around the tunnel mouth, so the entrance reads clearly.
    const lip = new THREE.Mesh(
      new THREE.TorusGeometry(TUNNEL_RADIUS * 1.015, 0.01, 8, 128),
      new THREE.MeshBasicMaterial({ color: COLOR.signal })
    );
    lip.position.copy(this.lut.pos[0]);
    lip.lookAt(this.lut.pos[0].clone().add(this.lut.tan[0]));
    lip.layers.enable(BLOOM_LAYER);
    this.scene.add(lip);
  }

  // ------------------------------------------------------------ packets

  _initPackets() {
    const n = this.cfg.maxPackets;
    this.pk = {
      n: 0, // active count; arrays are kept compact (swap-remove)
      u: new Float32Array(n),
      speed: new Float32Array(n),
      ox: new Float32Array(n),
      oy: new Float32Array(n),
      size: new Float32Array(n),
    };
    // Burst process: alternating ON (dense, large packets) / OFF (sparse,
    // small keep-alives) phases with random durations - the "shape" of traffic.
    this.burst = { on: false, t: 0.6, size: 1, acc: 0 };
    this.stats = { pps: 0, meanBytes: 0, window: [] };

    const mesh = new THREE.InstancedMesh(
      new THREE.CapsuleGeometry(0.028, 0.16, 3, 8), // axis along +Y
      new THREE.MeshBasicMaterial({ color: new THREE.Color(COLOR.signal).multiplyScalar(1.25) }),
      n
    );
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.frustumCulled = false;
    mesh.count = 0;
    mesh.layers.enable(BLOOM_LAYER);
    this.scene.add(mesh);
    this.packetMesh = mesh;

    this._m = new THREE.Matrix4();
    this._q = new THREE.Quaternion();
    this._s = new THREE.Vector3();
    this._p = new THREE.Vector3();
    this._Y = new THREE.Vector3(0, 1, 0);

    // Pre-warm so the tunnel is already populated on first paint.
    for (let t = 0; t < 14; t += 1 / 30) this._stepPackets(1 / 30);
  }

  _emit(size) {
    const pk = this.pk;
    if (pk.n >= this.cfg.maxPackets) return;
    const i = pk.n++;
    const r = Math.sqrt(Math.random()) * TUNNEL_RADIUS * 0.5;
    const a = Math.random() * Math.PI * 2;
    pk.u[i] = 0.025; // just inside the mouth: nothing spawns next to the end-of-scroll camera
    pk.speed[i] = (PACKET_SPEED / this.pathLength) * rand(0.98, 1.02);
    pk.ox[i] = Math.cos(a) * r;
    pk.oy[i] = Math.sin(a) * r;
    pk.size[i] = size * rand(0.85, 1.15);
    this.stats.window.push([this.elapsed, pk.size[i]]);
  }

  _stepPackets(dt) {
    this.elapsed += dt;
    const b = this.burst;
    b.t -= dt;
    if (b.t <= 0) {
      b.on = !b.on;
      b.t = b.on ? rand(0.35, 1.3) : rand(0.5, 1.8);
      b.size = rand(0.9, 1.7);
    }
    b.acc += (b.on ? 42 : 2.5) * this.cfg.emitScale * dt;
    while (b.acc >= 1) {
      b.acc -= 1;
      this._emit(b.on ? b.size : 0.55);
    }

    const pk = this.pk;
    for (let i = 0; i < pk.n; i++) {
      pk.u[i] += pk.speed[i] * dt;
      if (pk.u[i] >= 1) {
        const last = --pk.n;
        pk.u[i] = pk.u[last];
        pk.speed[i] = pk.speed[last];
        pk.ox[i] = pk.ox[last];
        pk.oy[i] = pk.oy[last];
        pk.size[i] = pk.size[last];
        i--;
      }
    }
  }

  _writePacketInstances() {
    const pk = this.pk;
    for (let i = 0; i < pk.n; i++) {
      const j = this._sample(pk.u[i], this._p);
      this._p.addScaledVector(this.lut.nor[j], pk.ox[i]).addScaledVector(this.lut.bin[j], pk.oy[i]);
      this._q.setFromUnitVectors(this._Y, this.lut.tan[j]);
      this._s.set(1, pk.size[i], 1);
      this._m.compose(this._p, this._q, this._s);
      this.packetMesh.setMatrixAt(i, this._m);
    }
    this.packetMesh.count = pk.n;
    this.packetMesh.instanceMatrix.needsUpdate = true;
  }

  // ------------------------------------------------------------- shadow

  _initShadow() {
    const S = this.cfg.shadowSegs; // segments along the path
    const R = 10; // segments across the ribbon
    this.shadowS = S;
    this.shadowR = R;
    this.rawDensity = new Float32Array(S + 1);
    this.density = new Float32Array(S + 1);

    // Per-station centre point on the wall: beside the path, on the side away
    // from the camera, precomputed once. The band grows vertically from it.
    this.shadowCenters = [];
    const up = new THREE.Vector3(0, 1, 0);
    const side = new THREE.Vector3();
    for (let i = 0; i <= S; i++) {
      const u = SHADOW_SPAN[0] + ((SHADOW_SPAN[1] - SHADOW_SPAN[0]) * i) / S;
      const c = new THREE.Vector3();
      const j = this._sample(u, c);
      side.crossVectors(this.lut.tan[j], up).normalize();
      c.addScaledVector(side, SHADOW_OFFSET);
      c.y = SHADOW_Y;
      this.shadowCenters.push(c);
    }

    const verts = (S + 1) * (R + 1);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(verts * 3), 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('aDensity', new THREE.BufferAttribute(new Float32Array(verts), 1).setUsage(THREE.DynamicDrawUsage));
    const across = new Float32Array(verts);
    const along = new Float32Array(verts);
    const index = [];
    for (let i = 0; i <= S; i++) {
      for (let k = 0; k <= R; k++) {
        across[i * (R + 1) + k] = -1 + (2 * k) / R;
        along[i * (R + 1) + k] = i / S;
        if (i < S && k < R) {
          const a = i * (R + 1) + k;
          const b = a + R + 1;
          index.push(a, b, a + 1, b, b + 1, a + 1);
        }
      }
    }
    geo.setAttribute('aAcross', new THREE.BufferAttribute(across, 1));
    geo.setAttribute('aAlong', new THREE.BufferAttribute(along, 1));
    geo.setIndex(index);

    // Flat, translucent, no glow: a dim fill that brightens toward the
    // silhouette edge, faint measurement ticks, and distance fade.
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: {
        uFill: { value: new THREE.Color(COLOR.shadowFill) },
        uEdge: { value: new THREE.Color(COLOR.shadowEdge) },
        uTicks: { value: S / 6 },
      },
      vertexShader: /* glsl */ `
        attribute float aAcross;
        attribute float aAlong;
        attribute float aDensity;
        varying float vAcross;
        varying float vAlong;
        varying float vDensity;
        varying float vFade;
        void main() {
          vAcross = aAcross;
          vAlong = aAlong;
          vDensity = aDensity;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vFade = exp(-0.03 * -mv.z);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uFill;
        uniform vec3 uEdge;
        uniform float uTicks;
        varying float vAcross;
        varying float vAlong;
        varying float vDensity;
        varying float vFade;
        void main() {
          float edge = smoothstep(0.78, 1.0, abs(vAcross));
          float tick = step(0.94, fract(vAlong * uTicks)) * 0.06;
          float alpha = mix(0.07, 0.4, edge) + vDensity * 0.1 + tick;
          gl_FragColor = vec4(mix(uFill, uEdge, edge), alpha * vFade);
          #include <colorspace_fragment>
        }`,
    });
    this.shadowMesh = new THREE.Mesh(geo, mat);
    this.shadowMesh.frustumCulled = false;

    // Crisp outline along both silhouette edges (updated with the ribbon).
    const edgeMat = new THREE.LineBasicMaterial({ color: COLOR.shadowEdge, transparent: true, opacity: 0.55 });
    this.shadowEdges = [0, 1].map(() => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(new Float32Array((S + 1) * 3), 3).setUsage(THREE.DynamicDrawUsage));
      const l = new THREE.Line(g, edgeMat);
      l.frustumCulled = false;
      return l;
    });

    this.scene.add(this.shadowMesh, ...this.shadowEdges);
    this.hideInBloom = [this.shadowMesh, ...this.shadowEdges];
  }

  // Histogram packets (weighted by size) into stations along the ribbon, blur,
  // saturate, then ease toward it over time so the silhouette breathes rather
  // than flickers.
  _updateShadow(dt) {
    const S = this.shadowS;
    const R = this.shadowR;
    const raw = this.rawDensity;
    raw.fill(0);
    const [u0, u1] = SHADOW_SPAN;
    const pk = this.pk;
    for (let i = 0; i < pk.n; i++) {
      const s = Math.round(((pk.u[i] - u0) / (u1 - u0)) * S);
      if (s >= 0 && s <= S) raw[s] += pk.size[i];
    }
    const K = [0.05, 0.1, 0.16, 0.2, 0.16, 0.1, 0.05, 0.02]; // blur kernel (half-width 3 + tail)
    const ease = 1 - Math.exp(-dt * 5);
    const norm = 2.4 * this.cfg.emitScale;
    for (let i = 0; i <= S; i++) {
      let v = 0;
      for (let k = -3; k <= 3; k++) v += (raw[Math.min(S, Math.max(0, i + k))] || 0) * K[k + 3];
      const target = 1 - Math.exp(-v / norm);
      this.density[i] += (target - this.density[i]) * ease;
    }

    const pos = this.shadowMesh.geometry.attributes.position.array;
    const dens = this.shadowMesh.geometry.attributes.aDensity.array;
    const e0 = this.shadowEdges[0].geometry.attributes.position.array;
    const e1 = this.shadowEdges[1].geometry.attributes.position.array;
    for (let i = 0; i <= S; i++) {
      const d = this.density[i];
      const c = this.shadowCenters[i];
      const half = 0.06 + 1.55 * d; // a thin line when sparse, bulges under bursts
      for (let k = 0; k <= R; k++) {
        const t = -1 + (2 * k) / R;
        const idx = i * (R + 1) + k;
        pos[idx * 3] = c.x;
        pos[idx * 3 + 1] = c.y + t * half;
        pos[idx * 3 + 2] = c.z;
        dens[idx] = d;
      }
      e0[i * 3] = c.x; e0[i * 3 + 1] = c.y - half; e0[i * 3 + 2] = c.z;
      e1[i * 3] = c.x; e1[i * 3 + 1] = c.y + half; e1[i * 3 + 2] = c.z;
    }
    this.shadowMesh.geometry.attributes.position.needsUpdate = true;
    this.shadowMesh.geometry.attributes.aDensity.needsUpdate = true;
    this.shadowEdges[0].geometry.attributes.position.needsUpdate = true;
    this.shadowEdges[1].geometry.attributes.position.needsUpdate = true;
  }

  // -------------------------------------------------------- post / bloom

  _initPost() {
    this.bloomOn = this.cfg.bloom;
    if (!this.bloomOn) return;

    const renderPass = new RenderPass(this.scene, this.camera);
    this.bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.62, 0.35, 0);
    this.bloomComposer = new EffectComposer(this.renderer);
    this.bloomComposer.renderToScreen = false;
    this.bloomComposer.addPass(renderPass);
    this.bloomComposer.addPass(this.bloomPass);

    this.mixPass = new ShaderPass(
      new THREE.ShaderMaterial({
        uniforms: { baseTexture: { value: null }, bloomTexture: { value: null } },
        vertexShader: /* glsl */ `
          varying vec2 vUv;
          void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
        fragmentShader: /* glsl */ `
          uniform sampler2D baseTexture;
          uniform sampler2D bloomTexture;
          varying vec2 vUv;
          void main() { gl_FragColor = texture2D(baseTexture, vUv) + texture2D(bloomTexture, vUv); }`,
      }),
      'baseTexture'
    );
    this.mixPass.needsSwap = true;

    this.finalComposer = new EffectComposer(this.renderer);
    this.finalComposer.addPass(renderPass);
    this.finalComposer.addPass(this.mixPass);
    this.finalComposer.addPass(new OutputPass());

    this.darkMaterial = new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide });
    this.black = new THREE.Color(0x000000);
  }

  _render() {
    if (!this.bloomOn) {
      this.renderer.render(this.scene, this.camera);
      return;
    }
    // Pass 1: glow-only. Occluders go black, the shadow ribbon disappears.
    const saved = this.darkenInBloom.map((o) => o.material);
    this.darkenInBloom.forEach((o) => (o.material = this.darkMaterial));
    this.hideInBloom.forEach((o) => (o.visible = false));
    this.scene.background = this.black;
    this.bloomComposer.render();
    this.darkenInBloom.forEach((o, i) => (o.material = saved[i]));
    this.hideInBloom.forEach((o) => (o.visible = true));
    this.scene.background = this.bgColor;

    // Pass 2: the normal scene plus the glow texture.
    this.mixPass.uniforms.bloomTexture.value = this.bloomComposer.renderTarget2.texture;
    this.finalComposer.render();
  }

  // -------------------------------------------------------------- camera

  setProgress(p) {
    this.progress = p;
  }

  _updateCamera() {
    const e = easeInOutSine(this.progress);
    const t = this.elapsed;
    const cam = this.camera.aspect < 0.8 ? CAM_PORTRAIT : CAM;
    this.camera.position.lerpVectors(cam.from, cam.to, e);
    // Slow idle drift, fading out as the camera enters the tunnel.
    const drift = 1 - e;
    this.camera.position.x += Math.sin(t * 0.13) * 0.18 * drift;
    this.camera.position.y += Math.cos(t * 0.11) * 0.08 * drift;
    const roll = e * 0.06;
    this.camera.up.set(Math.sin(roll), Math.cos(roll), 0);
    this._p.lerpVectors(cam.lookFrom, cam.lookTo, e);
    this.camera.lookAt(this._p);
  }

  // ---------------------------------------------------------- lifecycle

  _resize() {
    const w = this.canvas.clientWidth || window.innerWidth;
    const h = this.canvas.clientHeight || window.innerHeight;
    this.renderer.setPixelRatio(this.dpr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    // Portrait screens get a wider lens so the tunnel and shadow both fit.
    this.camera.fov = this.camera.aspect < 0.8 ? 72 : 52;
    this.camera.updateProjectionMatrix();
    if (this.bloomComposer) {
      this.finalComposer.setPixelRatio(this.dpr);
      this.finalComposer.setSize(w, h);
      this.bloomComposer.setPixelRatio(this.dpr * 0.5); // glow at half res: soft anyway, 4x cheaper
      this.bloomComposer.setSize(w, h);
      this.bloomPass.setSize(w * this.dpr * 0.5, h * this.dpr * 0.5);
    }
  }

  // Runtime safety net for the ~50fps target: if the device tier guess was
  // optimistic, step quality down (bloom -> pixel ratio -> packet count).
  _watchPerf(dt) {
    if (this.perfDone) return;
    const pf = (this.perf ||= { warm: 0, frames: 0, time: 0, clean: 0 });
    if (pf.warm < 1.5) {
      pf.warm += dt;
      return;
    }
    if (dt > 0.25) return; // tab switch / stall, not representative
    pf.frames++;
    pf.time += dt;
    if (pf.time < 2) return;
    const fps = pf.frames / pf.time;
    pf.frames = 0;
    pf.time = 0;
    this.fps = fps;
    if (fps >= 50) {
      if (++pf.clean >= 2) this.perfDone = true;
      return;
    }
    pf.clean = 0;
    if (this.bloomOn) this.bloomOn = false;
    else if (this.dpr > 1) {
      this.dpr = 1;
      this._resize();
    } else if (this.cfg.maxPackets > 200) {
      this.cfg.maxPackets = Math.floor(this.cfg.maxPackets * 0.6);
      this.cfg.emitScale *= 0.6;
    } else this.perfDone = true;
  }

  _tick = (now = performance.now()) => {
    this.raf = requestAnimationFrame(this._tick);
    const dt = Math.min((now - (this._last || now)) / 1000, 0.1);
    this._last = now;
    if (!this.active) return;

    this._stepPackets(dt);
    this._writePacketInstances();
    this._updateShadow(dt);
    this._updateCamera();
    this._render();
    this._watchPerf(dt);
    this._reportStats();
  };

  // Observable metrics of the simulated flow - exactly what a passive
  // observer outside the tunnel could measure (rate and size, never content).
  _reportStats() {
    if (!this.onStats || this.elapsed - (this._lastStats || 0) < 0.5) return;
    this._lastStats = this.elapsed;
    const w = this.stats.window;
    while (w.length && w[0][0] < this.elapsed - 2) w.shift();
    const pps = w.length / 2;
    const meanBytes = w.length ? (w.reduce((s, x) => s + x[1], 0) / w.length) * 820 : 0;
    this.onStats({
      pps,
      meanBytes,
      burst: this.burst.on,
      fps: this.fps,
      tier: this.tier,
      bloom: this.bloomOn,
      packets: this.pk.n,
    });
  }

  start() {
    this._last = 0;
    this._tick();
  }

  stop() {
    cancelAnimationFrame(this.raf);
  }

  // Pause rendering (not the rAF loop) when the scene is scrolled offscreen.
  setActive(active) {
    this.active = active;
    if (active) this._last = 0; // don't count the paused time as one huge frame
  }

  // Render one frame to a data URL - used to capture the reduced-motion poster.
  snapshot(type = 'image/jpeg', quality = 0.86) {
    this._render();
    return this.canvas.toDataURL(type, quality);
  }
}

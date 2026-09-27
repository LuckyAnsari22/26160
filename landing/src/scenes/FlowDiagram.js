/**
 * FlowDiagram - a 2D, side-on schematic of the hero's tunnel + shadow, used by
 * the three "How it works" steps. Canvas 2D, not WebGL: three small figures
 * would otherwise mean three extra GPU contexts for what is a flat diagram.
 *
 * Same rules as the 3D scene: packets are visible only until they enter the
 * tunnel mouth; after that, the only evidence of them is the shadow band above,
 * whose height tracks packet size x density along the tunnel.
 *
 * mode:
 *   'capture'  a .pcap file feeds packets into the tunnel
 *   'classify' the model traces the shadow and names it (progress 0 -> 1)
 *   'counter'  packets are padded to a uniform size; the shadow evens out and
 *              confidence falls - but timing still leaks (progress 0 -> 1)
 */
import { CLASSIFICATION } from '../data/packet.js';

const C = {
  signal: '#22d3ee',
  signalSoft: 'rgba(34, 211, 238, 0.5)',
  edge: 'rgba(103, 232, 249, 0.75)',
  fill: 'rgba(143, 179, 201, 0.16)',
  metalA: '#0e1624',
  metalB: '#0a101b',
  ai: '#a78bfa',
  amber: '#f59e0b',
  text: '#cbd5e1',
  dim: '#64748b',
};
const MONO = '"JetBrains Mono", ui-monospace, monospace';
const SANS = '"Space Grotesk", ui-sans-serif, system-ui, sans-serif';

// Small seeded PRNG so reduced-motion stills are identical on every load.
function mulberry32(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class FlowDiagram {
  constructor(canvas, { mode, seed = 7 } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.mode = mode;
    this.progress = mode === 'capture' ? 1 : 0;
    this.rand = mulberry32(seed);
    this.packets = []; // { x (0..1 of travel), size, speed }
    this.burst = { on: true, t: 0.8, size: 1.3, acc: 0 };
    this.bins = new Float32Array(64);
    this.density = new Float32Array(64);
    this.running = false;

    this._ro = new ResizeObserver(() => this._resize());
    this._ro.observe(canvas);
    this._resize();
    // Pre-warm so the tunnel already has traffic in it.
    for (let i = 0; i < 360; i++) this._step(1 / 60);
  }

  setProgress(p) {
    this.progress = p;
    if (!this.running) this.draw();
  }

  start() {
    if (this.running) return;
    this.running = true;
    this._last = performance.now();
    const loop = (now) => {
      if (!this.running) return;
      const dt = Math.min((now - this._last) / 1000, 0.1);
      this._last = now;
      this._step(dt);
      this.draw();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() {
    this.running = false;
    cancelAnimationFrame(this._raf);
  }

  _resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = w;
    this.h = h;
    this.draw();
  }

  // Layout in CSS pixels, derived from the canvas size.
  get geo() {
    const { w, h } = this;
    const sourceX = this.mode === 'capture' ? w * 0.16 : w * 0.02;
    const mouthX = w * 0.34;
    const endX = w * 0.97;
    const tubeY = h * 0.7;
    const tubeH = Math.max(18, h * 0.15);
    const shadowY = h * 0.36;
    return { sourceX, mouthX, endX, tubeY, tubeH, shadowY };
  }

  // Padding amount (counter mode): 0 = original sizes, 1 = all padded to MTU.
  get pad() {
    return this.mode === 'counter' ? this.progress : 0;
  }

  _step(dt) {
    const r = this.rand;
    const b = this.burst;
    b.t -= dt;
    if (b.t <= 0) {
      b.on = !b.on;
      b.t = b.on ? 0.4 + r() * 0.9 : 0.5 + r() * 1.2;
      b.size = 0.9 + r() * 0.8;
    }
    b.acc += (b.on ? 20 : 2) * dt;
    while (b.acc >= 1) {
      b.acc -= 1;
      this.packets.push({ x: 0, size: b.on ? b.size * (0.85 + r() * 0.3) : 0.45, speed: 0.13 * (0.98 + r() * 0.04) });
    }
    for (const p of this.packets) p.x += p.speed * dt;
    this.packets = this.packets.filter((p) => p.x < 1);

    // Shadow density per bin along the tunnel (padded size, blurred, eased).
    const { sourceX, mouthX, endX } = this.geo;
    const span = endX - sourceX;
    const n = this.bins.length;
    this.bins.fill(0);
    for (const p of this.packets) {
      const px = sourceX + p.x * span;
      if (px < mouthX) continue;
      const i = Math.floor(((px - mouthX) / (endX - mouthX)) * (n - 1));
      this.bins[i] += this._paddedSize(p.size);
    }
    const ease = 1 - Math.exp(-dt * 6);
    for (let i = 0; i < n; i++) {
      let v = 0;
      for (let k = -2; k <= 2; k++) v += (this.bins[Math.min(n - 1, Math.max(0, i + k))] || 0) * [0.1, 0.2, 0.4, 0.2, 0.1][k + 2];
      // Padded packets are all big, so normalise by the padded scale: what's
      // left in the band is the timing rhythm, not size.
      const target = 1 - Math.exp(-v / (2.2 * (1 + this.pad * 0.9)));
      this.density[i] += (target - this.density[i]) * ease;
    }
  }

  _paddedSize(size) {
    return size + (1.75 - size) * this.pad; // MTU padding: every packet grows to the max
  }

  draw() {
    const { ctx, w, h } = this;
    if (!w) return;
    ctx.clearRect(0, 0, w, h);
    const g = this.geo;
    this._drawShadow(g);
    this._drawTunnel(g);
    this._drawPackets(g);
    if (this.mode === 'capture') this._drawFile(g);
    if (this.mode === 'classify') this._drawClassify(g);
    if (this.mode === 'counter') this._drawCounter(g);
  }

  _bandPath(g, scaleY = 1) {
    const { mouthX, endX, shadowY } = g;
    const n = this.density.length;
    const amp = this.h * 0.2;
    const top = [];
    const bottom = [];
    for (let i = 0; i < n; i++) {
      const x = mouthX + (i / (n - 1)) * (endX - mouthX);
      const half = (2 + this.density[i] * amp) * scaleY;
      top.push([x, shadowY - half]);
      bottom.push([x, shadowY + half]);
    }
    return { top, bottom };
  }

  _drawShadow(g) {
    const { ctx } = this;
    const { top, bottom } = this._bandPath(g);
    // Padding blurs the outline slightly: less signal, same rhythm.
    ctx.filter = this.pad > 0.02 ? `blur(${(this.pad * 2.5).toFixed(2)}px)` : 'none';
    ctx.beginPath();
    top.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    for (let i = bottom.length - 1; i >= 0; i--) ctx.lineTo(bottom[i][0], bottom[i][1]);
    ctx.closePath();
    ctx.fillStyle = C.fill;
    ctx.fill();
    ctx.strokeStyle = C.edge;
    ctx.lineWidth = 1;
    for (const edge of [top, bottom]) {
      ctx.beginPath();
      edge.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
    }
    ctx.filter = 'none';
  }

  _drawTunnel({ mouthX, endX, tubeY, tubeH }) {
    const { ctx } = this;
    const top = tubeY - tubeH / 2;
    const grad = ctx.createLinearGradient(0, top, 0, top + tubeH);
    grad.addColorStop(0, C.metalA);
    grad.addColorStop(1, C.metalB);
    ctx.fillStyle = grad;
    ctx.fillRect(mouthX, top, endX - mouthX, tubeH);
    // rings
    ctx.strokeStyle = 'rgba(34, 211, 238, 0.12)';
    ctx.lineWidth = 1;
    for (let x = mouthX + 18; x < endX; x += 18) {
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + tubeH);
      ctx.stroke();
    }
    // edges + mouth
    ctx.strokeStyle = C.signalSoft;
    ctx.beginPath();
    ctx.moveTo(mouthX, top);
    ctx.lineTo(endX, top);
    ctx.moveTo(mouthX, top + tubeH);
    ctx.lineTo(endX, top + tubeH);
    ctx.stroke();
    ctx.strokeStyle = C.signal;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.ellipse(mouthX, tubeY, tubeH * 0.22, tubeH / 2, 0, 0, Math.PI * 2);
    ctx.stroke();
  }

  _drawPackets({ sourceX, mouthX, endX, tubeY }) {
    const { ctx } = this;
    const span = endX - sourceX;
    for (const p of this.packets) {
      const x = sourceX + p.x * span;
      if (x > mouthX + 2) continue; // inside the tunnel: sealed, not drawn
      const len = 5 + p.size * 7;
      const padded = 5 + this._paddedSize(p.size) * 7;
      const y = tubeY + (((p.size * 97) % 1) - 0.5) * 8;
      // padding extension: hollow
      if (padded > len + 0.5) {
        ctx.strokeStyle = 'rgba(226, 232, 240, 0.7)';
        ctx.lineWidth = 1;
        roundRect(ctx, x - padded, y - 2, padded - len, 4, 2);
        ctx.stroke();
      }
      ctx.fillStyle = C.signal;
      ctx.shadowColor = C.signal;
      ctx.shadowBlur = 6;
      roundRect(ctx, x - len, y - 2, len, 4, 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  _drawFile({ sourceX, tubeY }) {
    const { ctx } = this;
    const w = 30;
    const hgt = 38;
    const x = sourceX - w - 10;
    const y = tubeY - hgt / 2;
    ctx.strokeStyle = C.text;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + w - 9, y);
    ctx.lineTo(x + w, y + 9);
    ctx.lineTo(x + w, y + hgt);
    ctx.lineTo(x, y + hgt);
    ctx.closePath();
    ctx.moveTo(x + w - 9, y);
    ctx.lineTo(x + w - 9, y + 9);
    ctx.lineTo(x + w, y + 9);
    ctx.stroke();
    ctx.fillStyle = C.signal;
    for (let i = 0; i < 3; i++) ctx.fillRect(x + 6, y + 16 + i * 6, w - 12 - i * 4, 2);
    ctx.fillStyle = C.dim;
    ctx.font = `11px ${MONO}`;
    ctx.textAlign = 'center';
    ctx.fillText('voip.pcap', x + w / 2, y + hgt + 16);
  }

  _drawClassify(g) {
    const { ctx } = this;
    const p = this.progress;
    const { top } = this._bandPath(g);
    // The model's trace: a violet contour drawn left to right as p grows.
    const upto = Math.floor(top.length * Math.min(1, p * 1.25));
    if (upto > 1) {
      ctx.strokeStyle = C.ai;
      ctx.lineWidth = 2;
      ctx.shadowColor = C.ai;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      for (let i = 0; i < upto; i++) (i ? ctx.lineTo : ctx.moveTo).call(ctx, top[i][0], top[i][1] - 3);
      ctx.stroke();
      ctx.shadowBlur = 0;
    }
    const a = Math.max(0, Math.min(1, (p - 0.55) / 0.3));
    if (a > 0) this._label(g, `${CLASSIFICATION.label} ${CLASSIFICATION.confidence.toFixed(1)}%`, 'model confidence', C.ai, a);
  }

  _drawCounter(g) {
    const p = this.progress;
    const conf = CLASSIFICATION.confidence + (CLASSIFICATION.paddedConfidence - CLASSIFICATION.confidence) * p;
    this._label(g, `${CLASSIFICATION.label} ${conf.toFixed(1)}%`, 'model confidence', C.ai, 1);
    const { ctx } = this;
    ctx.globalAlpha = Math.min(1, p * 2);
    ctx.fillStyle = C.amber;
    ctx.font = `11px ${MONO}`;
    ctx.textAlign = 'right';
    ctx.fillText(`+${(CLASSIFICATION.paddingOverheadPct * p).toFixed(1)}% bandwidth`, g.endX, this.h * 0.08 + 4);
    ctx.globalAlpha = 1;
  }

  _label(g, big, small, color, alpha) {
    const { ctx } = this;
    ctx.globalAlpha = alpha;
    ctx.textAlign = 'left';
    ctx.fillStyle = color;
    ctx.font = `600 ${Math.round(Math.max(15, this.w * 0.035))}px ${MONO}`;
    ctx.fillText(big, g.mouthX, this.h * 0.08 + 4);
    ctx.fillStyle = C.dim;
    ctx.font = `11px ${SANS}`;
    ctx.fillText(small, g.mouthX, this.h * 0.08 + 19);
    ctx.globalAlpha = 1;
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h);
}

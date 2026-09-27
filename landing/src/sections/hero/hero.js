// Hero: decides between the live WebGL scene and the static poster, then ties
// the scene's camera to scroll with GSAP ScrollTrigger (sections 1-2).
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

function showPoster() {
  document.documentElement.classList.add('no-webgl');
}

export async function initHero({ reducedMotion, webgl, tier, debug, params }) {
  const canvas = document.getElementById('scene');

  // Reduced motion or no WebGL: static poster, no scroll-linked motion at all.
  if (reducedMotion || !webgl) return showPoster();

  const readout = document.getElementById('flow-readout');
  let scene;
  try {
    // Three.js is loaded lazily so the page text paints before ~150 kB of 3D code.
    const { TunnelScene } = await import('../../scenes/TunnelScene.js');
    scene = new TunnelScene(canvas, { tier, onStats: (s) => renderReadout(readout, s, debug) });
  } catch {
    return showPoster();
  }
  canvas.addEventListener('scene-failed', showPoster, { once: true });
  document.documentElement.classList.add('webgl-ready');
  if (params.has('poster')) document.documentElement.classList.add('poster-capture');
  window.__tunnel = scene; // handy for profiling in devtools
  scene.start();

  // Camera push-in, scrubbed by scroll across the hero + problem track.
  const proxy = { p: 0 };
  gsap.to(proxy, {
    p: 1,
    ease: 'none',
    onUpdate: () => scene.setProgress(proxy.p),
    scrollTrigger: { trigger: '#scroll-track', start: 'top top', end: 'bottom bottom', scrub: 1.2 },
  });

  // Hero copy steps aside as the camera starts moving in.
  gsap.to(['#hero-copy', '#hero .hero-scrim', '#flow-readout'], {
    autoAlpha: 0,
    y: -32,
    ease: 'none',
    scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom 35%', scrub: true },
  });

  // The solid sections that follow slide over the canvas; stop rendering once
  // they cover it, resume on the way back up.
  ScrollTrigger.create({
    trigger: '#how',
    start: 'top top',
    onEnter: () => scene.setActive(false),
    onLeaveBack: () => scene.setActive(true),
  });
}

const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

function renderReadout(el, s, debug) {
  if (!el) return;
  el.querySelector('[data-rate]').textContent = `${fmt.format(s.pps)} pkt/s`;
  el.querySelector('[data-size]').textContent = `${fmt.format(s.meanBytes)} B avg`;
  el.querySelector('[data-state]').textContent = s.burst ? 'burst' : 'idle';
  el.dataset.burst = s.burst;
  if (debug) {
    el.querySelector('[data-debug]').textContent =
      `${s.fps ? s.fps.toFixed(0) : '…'} fps  tier ${s.tier}  bloom ${s.bloom ? 'on' : 'off'}  ${s.packets} pkts`;
  }
}

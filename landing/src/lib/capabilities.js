// Feature / device detection that decides whether the WebGL layer runs at all,
// and at what quality. Everything here must be silent: no console output, no
// throwing - the page has to render fine whatever these return.

export function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

// Probe for WebGL on a throwaway canvas so a failure never surfaces as a
// three.js console error. Returns null when WebGL is unavailable.
export function probeWebGL() {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    if (!gl) return null;
    const info = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return { renderer };
  } catch {
    return null;
  }
}

// Two tiers only. 'low' = fewer packets, no bloom, lower pixel ratio. The scene
// also degrades itself at runtime if measured FPS is too low (TunnelScene#_watchPerf).
export function deviceTier(gl) {
  if (/swiftshader|llvmpipe|software|basic render/i.test(gl.renderer)) return 'low';
  const cores = navigator.hardwareConcurrency || 4;
  const memory = navigator.deviceMemory || 8;
  const coarse = window.matchMedia?.('(pointer: coarse)').matches;
  if (coarse || window.innerWidth < 768 || cores < 4 || memory < 4) return 'low';
  return 'high';
}

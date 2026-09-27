// Decided once per page load and shared by every section.
// Query-string switches for testing: ?reduced  ?nowebgl  ?tier=low|high  ?debug
import { prefersReducedMotion, probeWebGL, deviceTier } from './capabilities.js';

const params = new URLSearchParams(location.search);
const gl = params.has('nowebgl') ? null : probeWebGL();

export const env = {
  params,
  reducedMotion: prefersReducedMotion() || params.has('reduced'),
  webgl: !!gl,
  tier: ['low', 'high'].includes(params.get('tier')) ? params.get('tier') : gl ? deviceTier(gl) : 'low',
  debug: params.has('debug'),
};

// Problem statement: each line lifts from dim to full as the camera keeps
// pushing in behind it. With reduced motion the lines are simply shown.
import { gsap } from 'gsap';

export function initProblem({ reducedMotion }) {
  const lines = gsap.utils.toArray('#problem [data-line]');
  if (reducedMotion) return;
  gsap.set(lines, { opacity: 0.12 });
  const tl = gsap.timeline({
    scrollTrigger: { trigger: '#problem', start: 'top 60%', end: 'bottom 90%', scrub: true },
  });
  lines.forEach((line, i) => tl.to(line, { opacity: 1, duration: 1, ease: 'none' }, i * 0.9));
}

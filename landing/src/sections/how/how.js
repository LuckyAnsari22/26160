// How it works: three 2D flow figures. Each animates only while on screen;
// steps 2 and 3 are scrubbed by scroll (the model's trace, the padding amount).
// Reduced motion: each figure is drawn once, in its finished state.
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { FlowDiagram } from '../../scenes/FlowDiagram.js';

export function initHow({ reducedMotion }) {
  document.querySelectorAll('#how canvas[data-flow]').forEach((canvas, i) => {
    const mode = canvas.dataset.flow;
    const fig = new FlowDiagram(canvas, { mode, seed: 11 + i });

    if (reducedMotion) {
      fig.setProgress(1);
      return;
    }

    ScrollTrigger.create({
      trigger: canvas,
      start: 'top bottom',
      end: 'bottom top',
      onToggle: (self) => (self.isActive ? fig.start() : fig.stop()),
    });
    if (mode !== 'capture') {
      ScrollTrigger.create({
        trigger: canvas,
        start: 'top 85%',
        end: 'center 40%',
        scrub: 0.6,
        onUpdate: (self) => fig.setProgress(self.progress),
      });
    }
  });
}

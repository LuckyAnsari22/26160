// Packet Anatomy Explorer: builds the accessible layer list and byte map from
// real packet data, then (if WebGL is available) attaches the 3D view and keeps
// list selection and 3D selection in sync.
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { PACKET } from '../../data/packet.js';

const TAGS = {
  parsed: 'rule engine',
  sealed: 'never opened',
  unused: 'ignored',
};

export function initAnatomy({ reducedMotion, webgl }) {
  const list = document.getElementById('anatomy-layers');
  const tpl = document.getElementById('layer-item');
  const buttons = new Map();
  let scene = null;

  // --- layer list (single-open disclosure) ---
  const select = (id) => {
    for (const [layerId, { btn, panel }] of buttons) {
      const open = layerId === id;
      btn.setAttribute('aria-expanded', String(open));
      panel.hidden = !open;
    }
    scene?.select(id);
  };

  for (const layer of PACKET.layers) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.kind = layer.kind;
    const btn = node.querySelector('.layer-btn');
    const panel = node.querySelector('.layer-panel');
    panel.id = `layer-${layer.id}`;
    btn.setAttribute('aria-controls', panel.id);
    node.querySelector('.layer-name').textContent = layer.name;
    node.querySelector('.layer-tag').textContent = TAGS[layer.kind];
    node.querySelector('.layer-bytes').textContent = `${layer.bytes} B`;
    node.querySelector('.layer-summary').textContent = layer.summary;
    node.querySelector('.layer-use').textContent = layer.use;
    const dl = node.querySelector('.layer-fields');
    for (const f of layer.fields) {
      const dt = document.createElement('dt');
      dt.textContent = f.k;
      const dd = document.createElement('dd');
      dd.textContent = f.v;
      if (f.measured) {
        dd.classList.add('is-measured');
        dd.title = 'Measured: this value is a model feature';
      }
      dl.append(dt, dd);
    }
    btn.addEventListener('click', () => select(btn.getAttribute('aria-expanded') === 'true' ? null : layer.id));
    buttons.set(layer.id, { btn, panel });
    list.append(node);
  }

  // --- to-scale byte map ---
  const map = document.getElementById('byte-map');
  const mapLabels = document.getElementById('byte-map-labels');
  for (const layer of PACKET.layers) {
    const seg = document.createElement('div');
    seg.className = `byte-seg byte-seg--${layer.kind}`;
    seg.style.width = `${(layer.bytes / PACKET.totalBytes) * 100}%`;
    map.append(seg);
    // Wire-order legend under the bar (8-byte segments are too thin to label in place).
    const item = document.createElement('li');
    item.className = 'flex items-center gap-2 whitespace-nowrap';
    const key = document.createElement('span');
    key.className = `byte-key byte-seg--${layer.kind}`;
    item.append(key, `${layer.name} ${layer.bytes} B`);
    mapLabels.append(item);
  }

  // --- 3D view ---
  const stage = document.querySelector('.anatomy-stage');
  const controls = document.querySelector('.anatomy-controls');
  const slider = document.getElementById('anatomy-explode');
  const hide3d = () => {
    stage.hidden = true;
    controls.hidden = true;
  };
  if (!webgl) return hide3d();

  import('../../scenes/PacketScene.js')
    .then(({ PacketScene }) => {
      scene = new PacketScene(document.getElementById('anatomy-canvas'), document.getElementById('anatomy-labels'), {
        layers: PACKET.layers,
        onSelect: select,
      });
      const setSlider = (v) => {
        slider.value = String(Math.round(v));
        scene.setExplode(v / 100);
      };
      slider.addEventListener('input', () => scene.setExplode(slider.value / 100));

      ScrollTrigger.create({
        trigger: stage,
        start: 'top bottom',
        end: 'bottom top',
        onToggle: (self) => scene.setVisible(self.isActive),
      });

      // One orchestrated reveal the first time the packet is well in view.
      ScrollTrigger.create({
        trigger: stage,
        start: 'top 65%',
        once: true,
        onEnter: () => {
          if (reducedMotion) return setSlider(72);
          const proxy = { v: 0 };
          gsap.to(proxy, { v: 72, duration: 1.8, ease: 'power2.inOut', onUpdate: () => setSlider(proxy.v) });
        },
      });
    })
    .catch(hide3d);
}

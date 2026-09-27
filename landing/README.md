# IPsecGuard AI: landing site

Static marketing site for IPsecGuard AI (Smart India Hackathon, PS 26160). It
explains the product and links to the dashboard; it has no backend of its own.

Stack: Vite, vanilla JS, Three.js, GSAP ScrollTrigger, Tailwind CSS v4.

## How it ships

The site is built inside the repo's Docker image (a Node stage runs
`npm ci && npm run build`) and served by the same FastAPI app as the dashboard:

| Path | Serves |
|---|---|
| `/` | this landing page (`dist/`, copied into the image as `landing_dist/`) |
| `/app/` | the dashboard (`frontend/index.html`) |
| `/api/v1/...` | the API |

Every dashboard link is therefore a plain same-origin `/app/`.

## Local development

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # static output in dist/
npm run preview  # serve the production build locally
```

In `npm run dev` there is no FastAPI behind Vite, so dashboard links point at
`http://localhost:8000/app/` (a backend running locally). Set
`VITE_DEV_DASHBOARD_URL` in `.env.local` to point them elsewhere. This only
affects dev builds; production always uses `/app/`.

If the backend runs outside Docker, it serves `landing/dist/` when present, so
`npm run build` here is enough to see the combined site on :8000.

## Configuration (names and links)

Build-time, from `.env` (committed, public, non-secret) or the environment:

| Variable | Used for | Default |
|---|---|---|
| `VITE_GITHUB_URL` | "Sample captures" / "Source on GitHub" links | project repo |
| `VITE_TEAM_NAME` | footer team credit | *(unset: shows `{TEAM_NAME}`)* |
| `VITE_DEV_DASHBOARD_URL` | dashboard links in `npm run dev` only | `http://localhost:8000/app/` |

## Images

- `public/assets/dashboard-preview.png`: Live Demo screenshot. Currently a real
  capture of the dashboard's CISO view for the VoIP sample; replace it with
  the same filename to update.
- `public/assets/hero-poster.jpg`: the still shown for reduced motion or no
  WebGL. A real render of the hero scene; re-capture it if the scene changes.

## Structure

```
index.html                  page shell; sections are inlined at build time
src/
  main.js                   entry: config links, header, section init
  config.js                 build-time links / names
  data/packet.js            real packet + classification values (see below)
  lib/capabilities.js       reduced-motion, WebGL probe, device tier
  lib/env.js                the above, decided once per load
  scenes/TunnelScene.js     hero Three.js scene: tunnel, packets, shadow, bloom
  scenes/FlowDiagram.js     2D tunnel/shadow figures for "How it works"
  scenes/PacketScene.js     Packet Anatomy Explorer 3D view
  sections/<name>/<name>.html + .js   one folder per page section
```

Sections are plain HTML partials (`<!-- @include sections/x/x.html -->`,
resolved by a small plugin in `vite.config.js`), so the built page is static
HTML that reads fine before any JS runs.

## The numbers are real

`src/data/packet.js` holds values read from the IPsecGuard repo's own test
fixtures (`tests/fixtures/*.pcap`) and the live dashboard's output: the
244-byte ESP packet's SPI, sequence number and layer sizes, the IKE proposal,
86.2% VoIP confidence, 68.0% after MTU padding at 435.5% bandwidth. If you
change any of them, re-derive them from the fixtures.

## Performance and fallbacks

- `prefers-reduced-motion`: hero shows the static poster; no scroll-linked
  motion; figures render their finished state. The packet explorer stays
  interactive (it only moves when the visitor drags or uses the slider).
- No WebGL: hero poster; the explorer falls back to its layer list and the
  to-scale byte map.
- Device tier (`lib/capabilities.js`): mobile / low-core / software-GPU devices
  get fewer packets, no bloom and a lower pixel ratio. At runtime the hero
  also steps quality down (bloom, then pixel ratio, then packets) if it
  measures under 50 fps.
- Three.js is lazy-loaded and shared by both 3D scenes; each scene renders
  only while on screen.

Testing switches (query string): `?reduced`, `?nowebgl`, `?tier=low|high`,
`?debug` (fps / tier readout in the hero).

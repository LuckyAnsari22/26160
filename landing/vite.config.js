import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

const root = path.dirname(fileURLToPath(import.meta.url));

// Inline <!-- @include sections/foo/foo.html --> partials into index.html, so
// each page section lives in its own folder but still ships as static HTML
// (fast first paint, readable without JS).
function htmlPartials() {
  const include = /<!--\s*@include\s+(\S+)\s*-->/g;
  return {
    name: 'html-partials',
    transformIndexHtml: {
      order: 'pre',
      handler: (html) => html.replace(include, (_, file) => fs.readFileSync(path.join(root, 'src', file), 'utf8')),
    },
    handleHotUpdate({ file, server }) {
      if (file.endsWith('.html') && file.startsWith(path.join(root, 'src'))) server.ws.send({ type: 'full-reload' });
    },
  };
}

export default defineConfig({
  plugins: [htmlPartials(), tailwindcss()],
  // three.js is lazy-loaded as its own chunk (~146 kB gzip); that's expected.
  build: { chunkSizeWarningLimit: 700 },
});

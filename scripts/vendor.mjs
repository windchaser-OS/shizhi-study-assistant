import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
await mkdir(`${root}/web/vendor/katex`, { recursive: true });
for (const file of ['katex.min.js', 'katex.min.css', 'fonts', 'contrib/auto-render.min.js']) {
  await cp(`${root}/node_modules/katex/dist/${file}`, `${root}/web/vendor/katex/${file}`, { recursive: true });
}
await cp(`${root}/node_modules/katex/LICENSE`, `${root}/web/vendor/katex/LICENSE`);
console.log('Bundled KaTeX locally for offline math rendering.');

#!/usr/bin/env node
/**
 * Builds extension/dist/ so it can be loaded as an unpacked extension in Chrome, Edge or
 * Firefox. Three independent esbuild bundles (Manifest V3 content scripts can't be ES modules,
 * so each entry point is bundled to a single self-contained IIFE) plus a copy step for the
 * static files (manifest.json, popup.html/css, icons).
 */

import * as esbuild from 'esbuild';
import { copyFileSync, cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, 'dist');

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

const shared = {
  bundle: true,
  format: /** @type {const} */ ('iife'),
  target: ['chrome100', 'firefox115'],
  sourcemap: true,
  loader: { '.css': 'text' },
  logLevel: 'info',
};

await esbuild.build({ ...shared, entryPoints: [join(root, 'src/content/content.ts')], outfile: join(dist, 'content.js') });
await esbuild.build({ ...shared, entryPoints: [join(root, 'src/background.ts')], outfile: join(dist, 'background.js') });
await esbuild.build({ ...shared, entryPoints: [join(root, 'src/popup/popup.ts')], outfile: join(dist, 'popup.js') });

copyFileSync(join(root, 'manifest.json'), join(dist, 'manifest.json'));
copyFileSync(join(root, 'src/popup/popup.html'), join(dist, 'popup.html'));
copyFileSync(join(root, 'src/popup/popup.css'), join(dist, 'popup.css'));

if (!existsSync(join(root, 'icons/16.png'))) {
  console.log('icons/*.png not built yet — running scripts/generate-icons.mjs first');
  await import('./generate-icons.mjs');
}
cpSync(join(root, 'icons'), join(dist, 'icons'), { recursive: true, filter: (src) => !src.endsWith('.svg') });

console.log(`\nBuilt ${dist} — load it as an unpacked extension (see extension/README.md).`);

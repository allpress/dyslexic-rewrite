#!/usr/bin/env node
/**
 * Zips extension/dist/ into extension/web-ext-artifacts/{chrome,firefox}.zip for store
 * submission. The two zips have identical contents today (manifest.json's MV3 shape and
 * `browser_specific_settings.gecko.id` work for both Chrome/Edge and current Firefox — see the
 * comment at the top of manifest.json) — kept as two files because the Chrome Web Store and
 * Firefox's addons.mozilla.org each want their own upload regardless. Run `npm run build` first
 * (or use `npm run zip`, which does both).
 */

import archiver from 'archiver';
import { createWriteStream, existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, 'dist');
const outDir = join(root, 'web-ext-artifacts');

if (!existsSync(dist)) {
  console.error('extension/dist does not exist — run `npm run build` first.');
  process.exit(1);
}

mkdirSync(outDir, { recursive: true });

function zipDist(name) {
  return new Promise((resolve, reject) => {
    const outPath = join(outDir, name);
    const output = createWriteStream(outPath);
    const archive = archiver('zip', { zlib: { level: 9 } });
    output.on('close', () => {
      console.log(`wrote ${outPath} (${archive.pointer()} bytes)`);
      resolve();
    });
    archive.on('error', reject);
    archive.pipe(output);
    archive.directory(dist, false);
    void archive.finalize();
  });
}

await zipDist('unwind-this-page-chrome.zip');
await zipDist('unwind-this-page-firefox.zip');

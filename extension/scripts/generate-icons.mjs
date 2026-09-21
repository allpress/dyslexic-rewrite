#!/usr/bin/env node
/**
 * Generates icons/16.png, icons/48.png, icons/128.png from scratch: an accent-coloured disc
 * (#1c5d4a, the site's --accent, see web/src/styles.css) with a plain white "U" mark — no
 * wordmark, no imitation of any other product's icon. icons/icon.svg is the readable source of
 * the same shape for anyone editing the design later; this script draws the equivalent
 * procedurally with pngjs (pure JS, no native rasterizer dependency) rather than parsing that
 * SVG, so `npm run icons` has nothing to install beyond what's already in package.json.
 */

import { PNG } from 'pngjs';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, '..', 'icons');
const SIZES = [16, 48, 128];

const ACCENT = [0x1c, 0x5d, 0x4a]; // #1c5d4a
const WHITE = [0xff, 0xff, 0xff];

/** True if the point (u, v), normalised to the glyph's own coordinate space (roughly [-0.5, 0.5]
 * with v increasing downward), falls inside the "U" stroke: two vertical bars from the open top
 * down to v=0, joined by a rounded bottom formed from the ring between two circle radii. */
function inUGlyph(u, v) {
  const outerR = 0.42;
  const innerR = 0.22;
  const top = -0.55;
  if (v < top) return false;
  const outerOk = v <= 0 ? Math.abs(u) <= outerR : u * u + v * v <= outerR * outerR;
  if (!outerOk) return false;
  const innerHollow = v <= 0 ? Math.abs(u) <= innerR : u * u + v * v <= innerR * innerR;
  return !innerHollow;
}

function renderIcon(size) {
  const png = new PNG({ width: size, height: size });
  const cx = size / 2;
  const cy = size / 2;
  const discR = size * 0.47;
  const glyphScale = discR / 0.62; // fits the glyph's [-0.55, 0.42] extent inside the disc

  // Antialias the disc edge and the glyph edge with a small supersample grid per pixel — icons
  // this small look noticeably jagged without it.
  const SAMPLES = 3;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let discHits = 0;
      let glyphHits = 0;
      for (let sy = 0; sy < SAMPLES; sy++) {
        for (let sx = 0; sx < SAMPLES; sx++) {
          const px = x + (sx + 0.5) / SAMPLES;
          const py = y + (sy + 0.5) / SAMPLES;
          const dx = px - cx;
          const dy = py - cy;
          if (dx * dx + dy * dy <= discR * discR) {
            discHits += 1;
            const u = dx / glyphScale;
            const v = dy / glyphScale;
            if (inUGlyph(u, v)) glyphHits += 1;
          }
        }
      }
      const total = SAMPLES * SAMPLES;
      const discCoverage = discHits / total;
      const glyphCoverage = glyphHits / total;
      const idx = (size * y + x) << 2;
      // Blend white glyph over accent disc over transparent background, by coverage.
      const alpha = discCoverage; // disc coverage is this pixel's overall opacity
      let r = ACCENT[0];
      let g = ACCENT[1];
      let b = ACCENT[2];
      if (discCoverage > 0) {
        const glyphFrac = glyphCoverage / discCoverage;
        r = ACCENT[0] + (WHITE[0] - ACCENT[0]) * glyphFrac;
        g = ACCENT[1] + (WHITE[1] - ACCENT[1]) * glyphFrac;
        b = ACCENT[2] + (WHITE[2] - ACCENT[2]) * glyphFrac;
      }
      png.data[idx] = Math.round(r);
      png.data[idx + 1] = Math.round(g);
      png.data[idx + 2] = Math.round(b);
      png.data[idx + 3] = Math.round(alpha * 255);
    }
  }
  return png;
}

mkdirSync(OUT_DIR, { recursive: true });
for (const size of SIZES) {
  const png = renderIcon(size);
  const buffer = PNG.sync.write(png);
  const path = join(OUT_DIR, `${size}.png`);
  writeFileSync(path, buffer);
  console.log(`wrote ${path} (${buffer.length} bytes)`);
}

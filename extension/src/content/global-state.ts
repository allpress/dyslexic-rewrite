/**
 * A tiny handoff point on `window`, used only to make the overlay toggle correctly.
 *
 * `chrome.scripting.executeScript` re-runs content.js's whole bundle from scratch on every
 * injection — each injection gets a fresh module closure, so a plain module-level variable (like
 * `let hostEl` inside overlay.ts) does NOT survive between injections even though the page's
 * `window` object does. Alt+U / the popup button re-inject the same file to toggle the overlay
 * closed, so the *close* function from the injection that opened it has to be reachable from the
 * next one — hence stashing it here instead.
 */

const KEY = '__unwindWordsOverlay';

interface OverlayHandle {
  close: () => void;
}

function withKey(): Window & Partial<Record<typeof KEY, OverlayHandle>> {
  return window as unknown as Window & Partial<Record<typeof KEY, OverlayHandle>>;
}

export function getActiveOverlay(): OverlayHandle | undefined {
  return withKey()[KEY];
}

export function setActiveOverlay(handle: OverlayHandle | undefined): void {
  withKey()[KEY] = handle;
}

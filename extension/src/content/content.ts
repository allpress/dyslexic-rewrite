/**
 * Content script entry point. Injected on demand — via the popup's "Unwind this page" button or
 * the Alt+U command (both routed through chrome.scripting.executeScript, see src/background.ts
 * and src/popup/popup.ts) — never declared as an always-on `content_scripts` entry, so the
 * extension needs no broad host permissions.
 *
 * Re-injecting into a tab that already has the overlay open toggles it closed, so Alt+U (or the
 * popup button) acts as a simple on/off switch rather than stacking a second overlay.
 */

import { openOverlay } from './overlay';

// openOverlay() itself checks src/content/global-state.ts for an already-open overlay from a
// previous injection and closes it instead of opening a second one — see the comment there for
// why that check can't just be a module-level variable in this file.
void openOverlay();

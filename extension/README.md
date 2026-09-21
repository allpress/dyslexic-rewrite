# Unwind this page

A Manifest V3 browser extension (Chrome, Edge, Firefox) that turns any article into the Unwind
Words reader — the way Helperbird's Reading Mode does, but with our rewriting: changed words
underlined with the original on hover, a phonetic map, read-aloud with word highlighting, a
reading ruler, and font size/spacing controls, all in an overlay that a page's own CSS can't
reach (it renders inside a shadow root).

No account needed — `POST /api/rewrite` works anonymously under the free quota. Signing in gets
you your own profile and Pro limits: create a personal token on unwindwords.com
(`/profile` → "API tokens / browser extension") and paste it into the extension's settings. See
`server/API.md`, "API tokens (v0.6)".

Plain TypeScript, no UI framework, bundled with esbuild. No broad host permissions — the content
script only ever runs when you ask it to (the toolbar button or Alt+U), via `activeTab` +
`scripting`, so it never has standing access to any page you visit.

## Build

```bash
cd extension
npm install
npm run build   # → extension/dist/, loadable as an unpacked extension
npm run zip     # build + extension/web-ext-artifacts/{unwind-this-page-chrome,unwind-this-page-firefox}.zip
npm test        # vitest: API client, segment renderer, Readability extraction
npm run typecheck
```

`npm run icons` regenerates `icons/{16,48,128}.png` from `scripts/generate-icons.mjs` — a plain
accent-coloured disc with a white "U" mark, drawn procedurally (no SVG rasterizer dependency).
`icons/icon.svg` is the same shape kept as a readable source for anyone editing the design.

## Load it — Chrome / Edge

1. `npm run build`.
2. Go to `chrome://extensions` (or `edge://extensions`).
3. Turn on **Developer mode** (top right).
4. **Load unpacked** → select `extension/dist/`.
5. Pin "Unwind this page" from the extensions toolbar menu if you want it always visible.

## Load it — Firefox

1. `npm run build`.
2. Go to `about:debugging#/runtime/this-firefox`.
3. **Load Temporary Add-on…** → select `extension/dist/manifest.json`.
4. Firefox unloads temporary add-ons on restart — reload it the same way next session, or install
   the signed `.zip` from `npm run zip` for anything longer-lived.

## Using it

- Click the toolbar icon → **Unwind this page**, or press **Alt+U** on any regular web page.
- Pressing the shortcut (or the button) again closes the overlay — it's a toggle, not a stack.
- **Esc** also closes it.
- The popup's **Settings** panel holds the API base (defaults to `https://unwindwords.com`), your
  personal token, phonetic-map mode, text size and line spacing. "Sign in to unwindwords.com to
  get a token" opens `/profile` on whatever API base is currently set.

### What happens on click

1. The page's article text is extracted with [Readability](https://github.com/mozilla/readability)
   (the same de-clutter engine behind Firefox's own Reader View), run against a cloned document.
2. If that fails or finds too little text (a paywall, an app-shell page with nothing
   server-rendered), it falls back to your current text **selection**, then to the whole page's
   visible text — always trimmed to a safe size before it's ever sent anywhere.
3. The text is POSTed to `{apiBase}/api/rewrite`, with `Authorization: Bearer <token>` if one is
   set. See `server/API.md` for the full contract; nothing you read is ever stored server-side.
4. The result renders into the overlay: underlined changes (hover for the original + why),
   dotted notes, and `<ruby>` phonetic respellings per the phonetic-map mode you've set.

### Errors

- **Quota exceeded** (a 402 "Pro required" response, a 413, or a 400 that's clearly about the
  paste-length limit) shows the server's own message plus a link to `{apiBase}/pricing`.
- **A bad or revoked token** (401) tells you to check it in settings, or clear it to fall back to
  the free plan.
- **Offline / unreachable API** shows a plain "couldn't reach Unwind Words" message with a retry
  button.
- **Nothing to read** (Readability, selection and body text are all empty) asks you to select
  some text first, rather than sending an empty request.

## Architecture

```
src/
  background.ts        service worker: only listens for the Alt+U command
  popup/                popup.html/css/ts — the toolbar button UI + settings form
  content/
    content.ts          injected entry point (toggles the overlay open/closed)
    overlay.ts           builds the shadow-DOM overlay, wires the toolbar, calls the API
    render.ts            Segment[] → DOM (ruby, changed/note spans) — ported from
                          web/src/components/Reader.tsx's offset math
    extract.ts            Readability extraction + selection/body-text fallback
    global-state.ts       a window-scoped handoff so re-injecting content.js toggles the
                           existing overlay closed instead of opening a second one
                           (see that file's own comment for why this can't just be a
                           module-level variable)
  lib/
    api.ts               POST /api/rewrite client + error-kind mapping
    storage.ts            chrome.storage.local wrapper for settings
    speech.ts              speechSynthesis wrapper with word-boundary callbacks
    types.ts               Segment/PhoneticMapEntry types mirroring server/API.md
```

Each of `content.ts`, `background.ts` and `popup.ts` is bundled by esbuild into its own
self-contained IIFE (`scripts/build.mjs`) — Manifest V3 content scripts can't be loaded as ES
modules, so this keeps all three entry points built the same simple way rather than special-casing
one of them.

## Permissions, explained

| Permission | Why |
| --- | --- |
| `activeTab` | Lets the content script run on the tab you're looking at, only when you invoke the toolbar button or Alt+U — never automatically, never on tabs you haven't asked about. |
| `scripting` | Needed to inject `content.js` on demand from the popup/background. |
| `storage` | Settings (API base, token, phonetic-map mode, font size/spacing) in `chrome.storage.local` — never synced, never leaves the device. |
| `optional_host_permissions: https://unwindwords.com/*` | Lets the content script's `fetch` reach the hosted API reliably from any page's origin. Optional, and only relevant if you keep the default API base; the server's own CORS policy (`server/app.py`) also allows `chrome-extension://*`/`moz-extension://*` origins directly. |

No `<all_urls>`, no always-on `content_scripts` entry, no analytics.

## Store submission checklist (Doug will publish)

- [ ] Bump `version` in `manifest.json` (and this package's `package.json`) for every submitted
      build; store review rejects a resubmission at the same version.
- [ ] `npm run build && npm test && npm run typecheck` clean.
- [ ] `npm run zip` and sanity-check both zips by loading `dist/` unpacked one more time first.
- [ ] Chrome Web Store (Developer Dashboard):
  - Upload `web-ext-artifacts/unwind-this-page-chrome.zip`.
  - Privacy practices tab: declare the single remote host contacted (`unwindwords.com`, or
    whatever API base a user sets) and that no personal data is sold/shared with third parties.
  - Screenshots: the popup, and the overlay open on a real article (before/after, if room).
  - Single-purpose description: "Turn any web page into a dyslexia-friendly reader." Justify each
    permission from the table above in the listing's permission-justification fields.
- [ ] Firefox Add-ons (addons.mozilla.org):
  - Upload `web-ext-artifacts/unwind-this-page-firefox.zip`.
  - `browser_specific_settings.gecko.id` in `manifest.json` must stay stable across releases —
    changing it creates a new listing.
  - AMO's automated review flags bundled minified code; keep sourcemaps in the zip (already the
    case — `scripts/build.mjs` builds with `sourcemap: true`) so a human reviewer can inspect the
    real source if asked.
- [ ] Edge Add-ons: the Chrome zip works as-is (Edge accepts Chrome's Manifest V3 shape); submit
      it separately through the Partner Center once the Chrome listing is approved, since Edge's
      review often asks to see the already-approved Chrome listing.
- [ ] Update the extension's listing URL(s) on unwindwords.com's `/pricing` or landing page once
      each store approves the listing.

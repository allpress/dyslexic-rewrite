# Unwind Words — web front end

Vite + React 18 + TypeScript. No UI framework: one stylesheet (`src/styles.css`).

## Develop

```sh
npm install
npm run dev
```

Runs on http://localhost:5173 and proxies `/api` to the FastAPI server on
http://localhost:8000 (see `vite.config.ts`). Start the server separately.

When the server has no email provider configured, `POST /api/auth/request-code`
returns `dev_code`; the sign-in page prints it on screen so you can sign in.

## Build

```sh
npm run build     # type-checks, then writes static files to web/dist
npm run preview   # serve the built files locally
```

The server serves `web/dist`. It must fall back to `index.html` for unknown
paths, because routing is client-side (React Router).

## Test

```sh
npm test
```

Vitest + Testing Library, jsdom environment.

## Layout

- `src/api.ts` — typed client for every endpoint in `../server/API.md`.
- `src/useMe.tsx` — fetches `/api/me` once and shares it.
- `src/components/Reader.tsx` — renders `Segment[]`; every word is a button you
  can tap to mark as tripping you up.
- `src/pages/` — Landing, SignIn, Onboarding, Test, Results, Read, Profile.

## Reading comfort

Base font 20px, line-height 1.9, extra letter and word spacing, ~62ch line
width, warm off-white background, dark mode via `prefers-color-scheme`. The font
stack is Atkinson Hyperlegible → Lexend → Verdana → Arial, all local: nothing is
loaded from a CDN.

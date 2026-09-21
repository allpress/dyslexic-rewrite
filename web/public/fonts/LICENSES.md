# Fonts offered by Reading settings

These fonts are offered purely as **comfort settings**. Our own research doc
(`docs/RESEARCH.md` §2) found no evidence that a dyslexia-specific font reads better than a
plain one — only that letter/word spacing helps a little. Nothing in this app claims otherwise;
the panel says so in one line and lets the reader pick whatever feels good to them. None of these
are vendored into this repository — they are pulled in at build/run time as noted below.

## OpenDyslexic

- **Source:** the `@fontsource/opendyslexic` npm package (a real, currently-published package —
  no CDN fallback was needed), mirroring https://github.com/antijingoist/opendyslexic
- **Licence:** SIL Open Font License, Version 1.1 (OFL-1.1)
- **Copyright:** (c) 2019-07-29, Abbie Gonzalez (https://abbiecod.es), with Reserved Font Name
  "OpenDyslexic"
- **Full licence text:** ships inside the npm package at
  `node_modules/@fontsource/opendyslexic/LICENSE`
- **Loading:** `web/src/lib/fonts.ts` dynamically `import()`s the package's CSS only once a
  reader picks "OpenDyslexic" in Reading settings, so its four woff2 files are never in the
  main bundle for readers who don't ask for it.

## Atkinson Hyperlegible

- **Source:** Google Fonts — https://fonts.google.com/specimen/Atkinson+Hyperlegible (designed
  by the Braille Institute)
- **Licence:** SIL Open Font License, Version 1.1 (OFL-1.1)
- **Loading:** a `<link rel="stylesheet">` to `fonts.googleapis.com`, added only once a reader
  picks it in Reading settings. `web/index.html` preconnects to `fonts.googleapis.com`/
  `fonts.gstatic.com` so that first load is faster, but nothing is fetched until it's selected.

## Lexend

- **Source:** Google Fonts — https://fonts.google.com/specimen/Lexend (designed by Thomas
  Jockin, developed with reading-speed research)
- **Licence:** SIL Open Font License, Version 1.1 (OFL-1.1)
- **Loading:** same as Atkinson Hyperlegible above.

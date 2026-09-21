/**
 * Reading settings ("Aa" panel): a small external store shared by `ReaderSettingsPanel` (which
 * edits it) and `Reader` (which reads it and applies it to the reader container). Using a plain
 * module-level store instead of React context means every page keeps its "mount the panel with
 * one line" shape — nothing upstream has to wrap the app in a provider.
 *
 * Persistence: a signed-in reader's settings live on their profile (`PUT /api/me/layout`,
 * debounced from `ReaderSettingsPanel`); a signed-out reader keeps them in `localStorage`
 * instead. Every localStorage access is wrapped in try/catch — private browsing, blocked site
 * data, or a test environment with no `localStorage` at all must never break the reader.
 *
 * These are comfort settings only (docs/RESEARCH.md §2): nothing here is presented as helping,
 * only as something a reader can adjust until the page feels right to them.
 */
import { useSyncExternalStore } from 'react';
import type { ReaderLayout } from '../api';

export const DEFAULT_READER_PREFS: ReaderLayout = {
  font_family: 'system',
  font_size_px: 20,
  line_height: 1.9,
  letter_spacing_em: 0.04,
  word_spacing_em: 0.16,
  max_line_chars: 62,
  paragraph_gap_em: 1.4,
  text_align: 'left',
  theme: 'light',
  tint_color: '#fef3e2',
  ruler_enabled: false,
  ruler_height_px: 56,
  ruler_dim: 0.55,
  spotlight_enabled: false,
  autoscroll_speed: 0,
  tts_voice: '',
  tts_rate: 1.0,
  tts_pitch: 1.0,
};

/** Slider/stepper bounds, mirroring `server/service.py`'s `LAYOUT_RANGES` exactly so a client
 * can never propose a value the server would reject. */
export const READER_PREF_RANGES = {
  font_size_px: [16, 32] as const,
  line_height: [1.4, 2.4] as const,
  letter_spacing_em: [0, 0.15] as const,
  word_spacing_em: [0, 0.5] as const,
  max_line_chars: [40, 90] as const,
  paragraph_gap_em: [0, 3] as const,
  ruler_height_px: [24, 160] as const,
  ruler_dim: [0, 1] as const,
  autoscroll_speed: [0, 5] as const,
  tts_rate: [0.6, 1.6] as const,
  tts_pitch: [0, 2] as const,
};

/** Eight pastel tints for the "Tint" theme's swatch picker. */
export const TINT_SWATCHES = [
  '#fef3e2', // warm sand
  '#fff4c2', // pale yellow
  '#e8f3ec', // mint
  '#e3f6f5', // seafoam
  '#e6eef8', // sky
  '#e9e6f8', // lavender
  '#f3e8ff', // lilac
  '#ffe8e0', // peach
];

const LOCAL_KEY = 'reader:prefs:v1';

function loadLocal(): Partial<ReaderLayout> {
  try {
    const raw = localStorage.getItem(LOCAL_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveLocal(prefs: ReaderLayout): void {
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(prefs));
  } catch {
    // Private browsing / blocked storage: the reader just won't remember next visit.
  }
}

type Listener = () => void;

function createStore(initial: ReaderLayout) {
  let state = initial;
  const listeners = new Set<Listener>();

  function emit() {
    listeners.forEach((l) => l());
  }

  return {
    get(): ReaderLayout {
      return state;
    },
    /** Merge a patch in, persist to localStorage, notify subscribers. */
    set(patch: Partial<ReaderLayout>): void {
      state = { ...state, ...patch };
      saveLocal(state);
      emit();
    },
    /** Replace the whole value without re-merging over what's there (e.g. hydrating from the
     * signed-in reader's saved profile layout once it arrives). */
    replace(next: ReaderLayout): void {
      state = next;
      saveLocal(state);
      emit();
    },
    subscribe(fn: Listener): () => void {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

export const readerPrefsStore = createStore({ ...DEFAULT_READER_PREFS, ...loadLocal() });

/** Live reading-settings, re-rendering whenever the panel (or anything else) changes them. */
export function useReaderPrefs(): ReaderLayout {
  return useSyncExternalStore(readerPrefsStore.subscribe, readerPrefsStore.get, () => DEFAULT_READER_PREFS);
}

/* --------------------------------------------------------------------- TTS "mode" toggle */
// Whether the reader has turned on "tap a paragraph to read from there" mode. Session-only
// (never persisted) and shared the same way, between ReaderSettingsPanel's toggle and Reader's
// per-paragraph controls and Space-bar shortcut.

function createBoolStore(initial: boolean) {
  let state = initial;
  const listeners = new Set<Listener>();
  return {
    get: () => state,
    set(next: boolean) {
      state = next;
      listeners.forEach((l) => l());
    },
    subscribe(fn: Listener) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

export const ttsModeStore = createBoolStore(false);

export function useTtsMode(): boolean {
  return useSyncExternalStore(ttsModeStore.subscribe, ttsModeStore.get, () => false);
}

/* -------------------------------------------------------------------------- CSS variables */

/** Reading-settings values as CSS custom properties for the `.reader` container. Kept scoped to
 * that one element (never written to `:root`) so they never leak into the rest of the page. */
export function readerCssVars(prefs: ReaderLayout, fontStack: string): Record<string, string> {
  return {
    '--reader-font-family': fontStack,
    '--reader-font-size': `${prefs.font_size_px}px`,
    '--reader-line-height': String(prefs.line_height),
    '--reader-letter-spacing': `${prefs.letter_spacing_em}em`,
    '--reader-word-spacing': `${prefs.word_spacing_em}em`,
    '--reader-max-width': `${prefs.max_line_chars}ch`,
    '--reader-paragraph-gap': `${prefs.paragraph_gap_em}em`,
    '--reader-text-align': prefs.text_align,
    '--reader-ruler-height': `${prefs.ruler_height_px}px`,
    '--reader-ruler-dim': String(prefs.ruler_dim),
    '--reader-tint': prefs.tint_color,
  };
}

/** Whichever `prefers-reduced-motion` says right now — checked at call time (not cached) since
 * it can change while the page is open. Returns false in an environment with no `matchMedia`
 * (older browsers, some test environments) rather than throwing. */
export function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

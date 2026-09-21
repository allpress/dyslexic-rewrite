/**
 * Mirrors the JSON contract in server/API.md ("Read anything" / phonetic map) and the types in
 * web/src/api.ts. Kept as a small independent copy here (rather than importing across the
 * package boundary) so the extension has no build-time dependency on the web app.
 */

export type PhoneticMapMode = 'off' | 'on_demand' | 'always';

export type Segment =
  | { t: 'text'; s: string }
  | { t: 'change'; s: string; orig: string; why: string; alts: string[] }
  | { t: 'note'; s: string; why: string; hint: string }
  | { t: 'para' }
  | { t: 'heading'; s: string };

export interface PhoneticMapEntry {
  start: number;
  end: number;
  word: string;
  respell: string;
  hint: string | null;
  kind: string;
  always: boolean;
}

export interface RewriteStats {
  sentences: number;
  sentences_changed: number;
  changes: number;
  load_before: number;
  load_after: number;
}

export interface RewriteResponse {
  segments: Segment[];
  stats: RewriteStats;
  phonetic_map: PhoneticMapEntry[];
  cached: boolean;
}

/** Settings held in chrome.storage.local (see src/lib/storage.ts). */
export interface ExtensionSettings {
  apiBase: string;
  token: string | null;
  phoneticMapMode: PhoneticMapMode;
  fontSize: number; // px
  spacing: 'normal' | 'relaxed';
}

export const DEFAULT_SETTINGS: ExtensionSettings = {
  apiBase: 'https://unwindwords.com',
  token: null,
  phoneticMapMode: 'on_demand',
  fontSize: 20,
  spacing: 'relaxed',
};

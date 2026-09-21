/**
 * chrome.storage.local wrapper for the extension's settings (API base, personal token, phonetic
 * map mode, font size/spacing). Shared by the popup and the content script. Defensive like
 * web/src/lib/speech.ts: every export resolves rather than throwing when `chrome.storage` is
 * unavailable (e.g. under vitest), falling back to the in-memory defaults.
 */

import { DEFAULT_SETTINGS, type ExtensionSettings } from './types';

const STORAGE_KEY = 'unwindwords_settings';

function hasChromeStorage(): boolean {
  try {
    return typeof chrome !== 'undefined' && !!chrome.storage && !!chrome.storage.local;
  } catch {
    return false;
  }
}

export async function getSettings(): Promise<ExtensionSettings> {
  if (!hasChromeStorage()) return { ...DEFAULT_SETTINGS };
  try {
    const result = await chrome.storage.local.get(STORAGE_KEY);
    const stored = result[STORAGE_KEY] as Partial<ExtensionSettings> | undefined;
    return { ...DEFAULT_SETTINGS, ...stored };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export async function saveSettings(patch: Partial<ExtensionSettings>): Promise<ExtensionSettings> {
  const current = await getSettings();
  const next = { ...current, ...patch };
  if (hasChromeStorage()) {
    try {
      await chrome.storage.local.set({ [STORAGE_KEY]: next });
    } catch {
      // Storage can throw in odd embedded contexts — the caller still gets the merged value
      // back so the UI reflects the change even if it doesn't persist.
    }
  }
  return next;
}

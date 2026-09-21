/**
 * Popup script. "Unwind this page" injects content.js into the active tab (the click that opened
 * this popup already grants `activeTab` for it); the settings panel reads/writes
 * chrome.storage.local via src/lib/storage.ts, shared with the content script.
 */

import { getSettings, saveSettings } from '../lib/storage';
import type { PhoneticMapMode } from '../lib/types';

function el<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`popup.html is missing #${id}`);
  return found as T;
}

async function init(): Promise<void> {
  const unwindBtn = el<HTMLButtonElement>('unwind-btn');
  const unwindStatus = el<HTMLParagraphElement>('unwind-status');
  const apiBaseInput = el<HTMLInputElement>('api-base');
  const tokenInput = el<HTMLInputElement>('token');
  const signinLink = el<HTMLAnchorElement>('signin-link');
  const phonSelect = el<HTMLSelectElement>('phon-mode');
  const fontSizeInput = el<HTMLInputElement>('font-size');
  const fontSizeValue = el<HTMLSpanElement>('font-size-value');
  const spacingSelect = el<HTMLSelectElement>('spacing');
  const saveBtn = el<HTMLButtonElement>('save-btn');
  const saveStatus = el<HTMLParagraphElement>('save-status');

  const settings = await getSettings();
  apiBaseInput.value = settings.apiBase;
  tokenInput.value = settings.token ?? '';
  phonSelect.value = settings.phoneticMapMode;
  fontSizeInput.value = String(settings.fontSize);
  fontSizeValue.textContent = `${settings.fontSize}px`;
  spacingSelect.value = settings.spacing;
  updateSigninLink(settings.apiBase);

  fontSizeInput.addEventListener('input', () => {
    fontSizeValue.textContent = `${fontSizeInput.value}px`;
  });
  apiBaseInput.addEventListener('input', () => updateSigninLink(apiBaseInput.value));

  function updateSigninLink(apiBase: string): void {
    const base = (apiBase || 'https://unwindwords.com').trim().replace(/\/+$/, '');
    signinLink.href = `${base}/profile`;
  }

  saveBtn.addEventListener('click', () => {
    void (async () => {
      saveStatus.textContent = 'Saving…';
      await saveSettings({
        apiBase: (apiBaseInput.value || 'https://unwindwords.com').trim(),
        token: tokenInput.value.trim() || null,
        phoneticMapMode: phonSelect.value as PhoneticMapMode,
        fontSize: parseInt(fontSizeInput.value, 10),
        spacing: spacingSelect.value as 'normal' | 'relaxed',
      });
      saveStatus.textContent = 'Saved.';
      setTimeout(() => {
        saveStatus.textContent = '';
      }, 1500);
    })();
  });

  unwindBtn.addEventListener('click', () => {
    void (async () => {
      unwindStatus.textContent = '';
      unwindBtn.disabled = true;
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab?.id) throw new Error('No active tab.');
        if (!tab.url || !/^https?:/.test(tab.url)) {
          unwindStatus.textContent = "This can't run on this kind of page (try a regular web page).";
          return;
        }
        await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
        window.close();
      } catch (err) {
        unwindStatus.textContent = err instanceof Error ? err.message : 'Something went wrong.';
      } finally {
        unwindBtn.disabled = false;
      }
    })();
  });
}

void init();

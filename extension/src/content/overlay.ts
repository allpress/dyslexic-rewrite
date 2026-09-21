/**
 * The overlay reader: a shadow-DOM host injected over the current page, so the host page's CSS
 * can never leak in and the overlay's styles can never leak out. Built once per activation by
 * content.ts; `closeOverlay()`/Esc/the close button tear it down completely.
 */

import { mapError, RewriteApiError, rewrite } from '../lib/api';
import { getSettings, saveSettings } from '../lib/storage';
import overlayCss from '../styles/overlay.css';
import { extractArticle } from './extract';
import { getActiveOverlay, setActiveOverlay } from './global-state';
import { paragraphTexts, renderSegments } from './render';
import { speakParagraphsWithHighlight, type SpeakHandle } from '../lib/speech';
import type { PhoneticMapMode, RewriteResponse } from '../lib/types';

const HOST_ID = 'unwind-words-overlay-host';
const MAX_EXTRACT_CHARS = 100_000;

let hostEl: HTMLElement | null = null;
let keydownHandler: ((e: KeyboardEvent) => void) | null = null;
let abortController: AbortController | null = null;
let speechHandle: SpeakHandle | null = null;
let rulerHandler: ((e: MouseEvent) => void) | null = null;

/** Ground truth is the real DOM node, not module state — a fresh injection of this same bundle
 * (see global-state.ts) has a brand new module closure, so `hostEl` alone would always read as
 * null on a second injection even though the overlay from the first one is still on the page. */
export function isOverlayOpen(): boolean {
  return document.getElementById(HOST_ID) !== null;
}

export function closeOverlay(): void {
  speechHandle?.stop();
  speechHandle = null;
  abortController?.abort();
  abortController = null;
  if (keydownHandler) {
    document.removeEventListener('keydown', keydownHandler, true);
    keydownHandler = null;
  }
  if (rulerHandler) {
    document.removeEventListener('mousemove', rulerHandler);
    rulerHandler = null;
  }
  hostEl?.remove();
  hostEl = null;
  document.getElementById(HOST_ID)?.remove(); // in case this call came from a fresh injection
  setActiveOverlay(undefined);
}

export async function openOverlay(): Promise<void> {
  const active = getActiveOverlay();
  if (active) {
    // Toggle: a second injection while the overlay is open closes it instead of stacking one.
    active.close();
    return;
  }
  document.getElementById(HOST_ID)?.remove(); // stale node with no tracked closer, just in case

  const host = document.createElement('div');
  host.id = HOST_ID;
  document.documentElement.appendChild(host);
  hostEl = host;
  setActiveOverlay({ close: () => closeOverlay() });
  const shadow = host.attachShadow({ mode: 'open' });

  const style = document.createElement('style');
  style.textContent = overlayCss;
  shadow.appendChild(style);

  const root = document.createElement('div');
  root.className = 'uw-root';
  shadow.appendChild(root);

  const settings = await getSettings();

  const toolbar = buildToolbar(settings.phoneticMapMode, settings.spacing, root);
  root.appendChild(toolbar.el);

  const ruler = document.createElement('div');
  ruler.className = 'uw-ruler';
  root.appendChild(ruler);

  const body = document.createElement('div');
  body.className = 'uw-body';
  const content = document.createElement('div');
  content.className = ['uw-content', settings.spacing === 'relaxed' ? 'uw-content--relaxed' : ''].join(' ').trim();
  content.style.setProperty('--uw-font-size', `${settings.fontSize}px`);
  body.appendChild(content);
  root.appendChild(body);

  keydownHandler = (e: KeyboardEvent) => {
    if (e.key === 'Escape') closeOverlay();
  };
  document.addEventListener('keydown', keydownHandler, true);

  toolbar.rulerToggle.addEventListener('click', () => {
    const on = ruler.classList.toggle('uw-ruler--on');
    toolbar.rulerToggle.setAttribute('aria-pressed', String(on));
    if (on) {
      rulerHandler = (e: MouseEvent) => {
        ruler.style.top = `${e.clientY}px`;
      };
      document.addEventListener('mousemove', rulerHandler);
    } else if (rulerHandler) {
      document.removeEventListener('mousemove', rulerHandler);
      rulerHandler = null;
    }
  });

  toolbar.closeBtn.addEventListener('click', () => closeOverlay());

  toolbar.fontDown.addEventListener('click', () => void adjustFontSize(content, -2));
  toolbar.fontUp.addEventListener('click', () => void adjustFontSize(content, 2));
  toolbar.spacingToggle.addEventListener('click', () => void toggleSpacing(content, toolbar.spacingToggle));

  showLoading(content);

  const selectionText = window.getSelection?.()?.toString() ?? '';
  const article = extractArticle(document, selectionText, MAX_EXTRACT_CHARS);

  if (!article.text.trim()) {
    showError(content, {
      kind: 'generic',
      message: "Couldn't find any readable text on this page. Try selecting some text first.",
    });
    return;
  }

  abortController = new AbortController();
  let response: RewriteResponse;
  try {
    response = await rewrite({
      apiBase: settings.apiBase,
      token: settings.token,
      text: article.text,
      signal: abortController.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return; // closed mid-request
    if (err instanceof RewriteApiError) {
      showError(content, err.info);
    } else {
      showError(content, mapError(settings.apiBase, 0, null));
    }
    return;
  }

  let showOriginalInline = false;
  let currentMode: PhoneticMapMode = settings.phoneticMapMode;

  const rerender = () =>
    renderSegments(content, response.segments, {
      phoneticMap: response.phonetic_map,
      phoneticMapMode: currentMode,
      showOriginalInline,
    });

  rerender();

  toolbar.phonSelect.addEventListener('change', () => {
    currentMode = toolbar.phonSelect.value as PhoneticMapMode;
    void saveSettings({ phoneticMapMode: currentMode });
    rerender();
  });

  toolbar.showOriginalToggle.addEventListener('click', () => {
    showOriginalInline = !showOriginalInline;
    toolbar.showOriginalToggle.setAttribute('aria-pressed', String(showOriginalInline));
    rerender();
  });

  toolbar.readAloudBtn.addEventListener('click', () => {
    if (speechHandle) {
      speechHandle.stop();
      speechHandle = null;
      toolbar.readAloudBtn.setAttribute('aria-pressed', 'false');
      toolbar.readAloudBtn.textContent = '🔊 Read aloud';
      clearSpeakingHighlight(content);
      return;
    }
    toolbar.readAloudBtn.setAttribute('aria-pressed', 'true');
    toolbar.readAloudBtn.textContent = '⏸ Stop reading';
    const paragraphs = paragraphTexts(response.segments);
    const paragraphEls = Array.from(content.children) as HTMLElement[];
    speechHandle = speakParagraphsWithHighlight(
      paragraphs,
      (blockIndex) => {
        paragraphEls[blockIndex]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      },
      (blockIndex, charIndex, charLength) => {
        highlightWord(paragraphEls[blockIndex], charIndex, charLength);
      },
      () => {
        speechHandle = null;
        toolbar.readAloudBtn.setAttribute('aria-pressed', 'false');
        toolbar.readAloudBtn.textContent = '🔊 Read aloud';
        clearSpeakingHighlight(content);
      },
    );
  });
}

function highlightWord(paragraphEl: HTMLElement | undefined, charIndex: number, charLength: number): void {
  if (!paragraphEl) return;
  clearSpeakingHighlight(paragraphEl.parentElement ?? paragraphEl);
  const words = Array.from(paragraphEl.querySelectorAll<HTMLElement>('.uw-word'));
  const target = words.find((w) => {
    const start = Number(w.dataset.segStart ?? '-1');
    const end = Number(w.dataset.segEnd ?? '-1');
    return charIndex >= start && charIndex < end + Math.max(charLength, 1) && charIndex <= end;
  });
  target?.classList.add('uw-word--speaking');
}

function clearSpeakingHighlight(root: HTMLElement): void {
  root.querySelectorAll('.uw-word--speaking').forEach((el) => el.classList.remove('uw-word--speaking'));
}

async function adjustFontSize(content: HTMLElement, delta: number): Promise<void> {
  const current = parseInt(content.style.getPropertyValue('--uw-font-size') || '20', 10);
  const next = Math.max(14, Math.min(36, current + delta));
  content.style.setProperty('--uw-font-size', `${next}px`);
  await saveSettings({ fontSize: next });
}

async function toggleSpacing(content: HTMLElement, btn: HTMLButtonElement): Promise<void> {
  const relaxed = content.classList.toggle('uw-content--relaxed');
  btn.setAttribute('aria-pressed', String(relaxed));
  await saveSettings({ spacing: relaxed ? 'relaxed' : 'normal' });
}

interface Toolbar {
  el: HTMLElement;
  closeBtn: HTMLButtonElement;
  fontDown: HTMLButtonElement;
  fontUp: HTMLButtonElement;
  spacingToggle: HTMLButtonElement;
  rulerToggle: HTMLButtonElement;
  phonSelect: HTMLSelectElement;
  showOriginalToggle: HTMLButtonElement;
  readAloudBtn: HTMLButtonElement;
}

function buildToolbar(phonMode: PhoneticMapMode, spacing: 'normal' | 'relaxed', _root: HTMLElement): Toolbar {
  const el = document.createElement('div');
  el.className = 'uw-toolbar';

  const title = document.createElement('span');
  title.className = 'uw-toolbar__title';
  title.textContent = 'Unwind Words';
  el.appendChild(title);

  const fontDown = mkBtn('A−', 'Smaller text');
  const fontUp = mkBtn('A+', 'Larger text');
  el.appendChild(fontDown);
  el.appendChild(fontUp);

  const spacingToggle = mkBtn('Spacing', 'Toggle relaxed line spacing');
  spacingToggle.setAttribute('aria-pressed', String(spacing === 'relaxed'));
  el.appendChild(spacingToggle);

  const phonLabel = document.createElement('label');
  phonLabel.textContent = 'Phonetic map';
  phonLabel.style.fontSize = '0.85rem';
  phonLabel.style.fontWeight = '700';
  phonLabel.style.display = 'inline-flex';
  phonLabel.style.alignItems = 'center';
  phonLabel.style.gap = '6px';
  const phonSelect = document.createElement('select');
  phonSelect.className = 'uw-select';
  (['off', 'on_demand', 'always'] as PhoneticMapMode[]).forEach((mode) => {
    const opt = document.createElement('option');
    opt.value = mode;
    opt.textContent = mode === 'off' ? 'Off' : mode === 'on_demand' ? 'On demand' : 'Always';
    if (mode === phonMode) opt.selected = true;
    phonSelect.appendChild(opt);
  });
  phonLabel.appendChild(phonSelect);
  el.appendChild(phonLabel);

  const showOriginalToggle = mkBtn('Show original', 'Show the original word next to each change');
  showOriginalToggle.setAttribute('aria-pressed', 'false');
  el.appendChild(showOriginalToggle);

  const rulerToggle = mkBtn('Ruler', 'Toggle a reading ruler that follows your cursor');
  rulerToggle.setAttribute('aria-pressed', 'false');
  el.appendChild(rulerToggle);

  const readAloudBtn = mkBtn('🔊 Read aloud', 'Read this page aloud');
  readAloudBtn.setAttribute('aria-pressed', 'false');
  el.appendChild(readAloudBtn);

  const closeBtn = mkBtn('✕', 'Close (Esc)');
  closeBtn.className += ' uw-btn--close';
  el.appendChild(closeBtn);

  return { el, closeBtn, fontDown, fontUp, spacingToggle, rulerToggle, phonSelect, showOriginalToggle, readAloudBtn };
}

function mkBtn(label: string, ariaLabel: string): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'uw-btn';
  btn.textContent = label;
  btn.setAttribute('aria-label', ariaLabel);
  btn.title = ariaLabel;
  return btn;
}

function showLoading(content: HTMLElement): void {
  content.innerHTML = '';
  const box = document.createElement('div');
  box.className = 'uw-state';
  const spinner = document.createElement('div');
  spinner.className = 'uw-spinner';
  const p = document.createElement('p');
  p.textContent = 'Unwinding this page…';
  box.appendChild(spinner);
  box.appendChild(p);
  content.appendChild(box);
}

function showError(content: HTMLElement, info: { kind: string; message: string; actionUrl?: string; actionLabel?: string }): void {
  content.innerHTML = '';
  const box = document.createElement('div');
  box.className = 'uw-state uw-state--error';
  const p = document.createElement('p');
  p.textContent = info.message;
  box.appendChild(p);
  if (info.actionUrl) {
    const link = document.createElement('a');
    link.className = 'uw-btn uw-btn--primary';
    link.href = info.actionUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = info.actionLabel ?? 'Learn more';
    box.appendChild(link);
  }
  const retry = document.createElement('button');
  retry.type = 'button';
  retry.className = 'uw-btn';
  retry.textContent = 'Try again';
  retry.addEventListener('click', () => {
    closeOverlay();
    void openOverlay();
  });
  box.appendChild(retry);
  content.appendChild(box);
}

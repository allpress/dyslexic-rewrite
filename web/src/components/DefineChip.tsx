import { useEffect, useRef, useState, type RefObject } from 'react';
import { ApiError, defineWord, type DefinitionResponse } from '../api';
import { speak, speechSupported } from '../lib/speech';

/**
 * A floating "Define" affordance for any reading area (Read anything, a library chapter): select
 * a single word anywhere inside `containerRef` — including a marked/underlined word — and a small
 * chip appears near it; tap it to look the word up (GET /api/define) and show the definition in
 * place, with its own pronunciation (phonetic + speaker) alongside the meanings.
 *
 * Deliberately independent of components/Reader.tsx's own tip popover (which shows the reader's
 * phonetic-map respelling on hover/focus) — this covers the same "define a marked word" need via
 * text selection instead, so it needs no changes to Reader.tsx's internals.
 */
export interface DefineChipProps {
  containerRef: RefObject<HTMLElement | null>;
}

const WORD_RE = /^[A-Za-z][A-Za-z'-]{0,49}$/;

interface Anchor {
  top: number;
  left: number;
}

interface Prompt extends Anchor {
  word: string;
}

interface Panel extends Anchor {
  word: string;
  status: 'loading' | 'ready' | 'notfound' | 'error';
  data: DefinitionResponse | null;
  error: string | null;
}

function clampLeft(left: number): number {
  const max = (typeof window !== 'undefined' ? window.innerWidth : 400) - 300;
  return Math.max(8, Math.min(left, Math.max(8, max)));
}

export default function DefineChip({ containerRef }: DefineChipProps) {
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const panelOpen = panel !== null;
  const panelRef = useRef<HTMLDivElement>(null);

  // Track the current selection while no panel is open; once a panel is open, leave the
  // selection-driven prompt alone so opening it doesn't immediately get replaced.
  useEffect(() => {
    if (panelOpen) return;
    function onSelectionChange() {
      const container = containerRef.current;
      const sel = window.getSelection();
      const text = sel?.toString().trim() ?? '';
      if (!container || !sel || sel.rangeCount === 0 || !text || !WORD_RE.test(text)) {
        setPrompt(null);
        return;
      }
      const range = sel.getRangeAt(0);
      if (!container.contains(range.commonAncestorContainer)) {
        setPrompt(null);
        return;
      }
      const rect = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) {
        setPrompt(null);
        return;
      }
      setPrompt({
        word: text.toLowerCase(),
        top: rect.bottom + window.scrollY + 6,
        left: clampLeft(rect.left + window.scrollX),
      });
    }
    document.addEventListener('selectionchange', onSelectionChange);
    return () => document.removeEventListener('selectionchange', onSelectionChange);
  }, [containerRef, panelOpen]);

  // Close the open panel on Escape or a click/tap outside it.
  useEffect(() => {
    if (!panelOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setPanel(null);
    }
    function onPointerDown(e: PointerEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setPanel(null);
    }
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [panelOpen]);

  async function openDefinition(p: Prompt) {
    setPrompt(null);
    setPanel({ word: p.word, top: p.top, left: p.left, status: 'loading', data: null, error: null });
    try {
      const data = await defineWord(p.word);
      setPanel({ word: p.word, top: p.top, left: p.left, status: 'ready', data, error: null });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setPanel({ word: p.word, top: p.top, left: p.left, status: 'notfound', data: null, error: null });
      } else {
        setPanel({
          word: p.word, top: p.top, left: p.left, status: 'error', data: null,
          error: err instanceof ApiError ? err.message : 'We could not look that word up.',
        });
      }
    }
  }

  return (
    <>
      {prompt && !panelOpen && (
        <button
          type="button"
          className="define-chip"
          style={{ top: prompt.top, left: prompt.left }}
          onMouseDown={(e) => e.preventDefault()} // keep the text selection intact until the click fires
          onClick={() => void openDefinition(prompt)}
        >
          Define &ldquo;{prompt.word}&rdquo;
        </button>
      )}

      {panel && (
        <div className="define-panel" role="dialog" aria-label={`Definition of ${panel.word}`} style={{ top: panel.top, left: panel.left }} ref={panelRef}>
          <div className="define-panel__head">
            <strong>{panel.word}</strong>
            {panel.status === 'ready' && panel.data?.phonetic && (
              <span className="define-panel__phonetic">{panel.data.phonetic}</span>
            )}
            {panel.status === 'ready' && speechSupported() && (
              <button
                type="button"
                className="tip__speak"
                aria-label={`Hear "${panel.word}"`}
                onClick={() => speak(panel.word)}
              >
                🔊
              </button>
            )}
            <button
              type="button"
              className="define-panel__close"
              aria-label="Close definition"
              onClick={() => setPanel(null)}
            >
              ×
            </button>
          </div>

          {panel.status === 'loading' && <p className="muted">Looking it up…</p>}
          {panel.status === 'notfound' && <p className="muted">No definition found for &ldquo;{panel.word}&rdquo;.</p>}
          {panel.status === 'error' && <p className="error">{panel.error}</p>}
          {panel.status === 'ready' && panel.data && (
            <ul className="define-panel__meanings">
              {panel.data.meanings.map((m, i) => (
                <li key={i}>
                  {m.pos && <span className="define-panel__pos">{m.pos}</span>} {m.definition}
                  {m.example && <span className="define-panel__example"> &ldquo;{m.example}&rdquo;</span>}
                </li>
              ))}
              {panel.data.meanings.length === 0 && <li className="muted">No meanings listed.</li>}
            </ul>
          )}
        </div>
      )}
    </>
  );
}

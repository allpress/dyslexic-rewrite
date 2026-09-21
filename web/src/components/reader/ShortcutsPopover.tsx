import { useEffect, useRef, useState } from 'react';

const SHORTCUTS: { keys: string; does: string }[] = [
  { keys: 'R', does: 'Toggle the reading ruler' },
  { keys: 'S', does: 'Toggle spotlight (dims everything but the current paragraph)' },
  { keys: '↑ / ↓', does: 'Move the ruler, or move spotlight to the paragraph before/after' },
  { keys: 'Click a paragraph', does: 'Move spotlight there, or (in text-to-speech mode) read from there' },
  { keys: 'Space', does: 'Play or pause read-aloud, once text-to-speech mode is turned on below' },
];

/** A small "?" trigger + popover documenting the reader's keyboard shortcuts. Self-contained so
 * `ReaderSettingsPanel` can mount it as one extra element without owning its open/closed state. */
export default function ShortcutsPopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="reader-shortcuts" ref={ref}>
      <button
        type="button"
        className="btn btn--plain btn--small"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">⌨ Shortcuts</span>
        <span className="sr-only">Keyboard shortcuts</span>
      </button>
      {open && (
        <div className="reader-shortcuts__popover" role="dialog" aria-label="Keyboard shortcuts">
          <dl>
            {SHORTCUTS.map((s) => (
              <div className="reader-shortcuts__row" key={s.keys}>
                <dt>
                  <kbd>{s.keys}</kbd>
                </dt>
                <dd>{s.does}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

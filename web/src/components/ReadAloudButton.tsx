import { useEffect, useRef, useState } from 'react';
import { speakParagraphs, speechSupported } from '../lib/speech';

export interface ReadAloudButtonProps {
  /** The passage, one entry per paragraph/heading, spoken in order. */
  paragraphs: string[];
  /** Fires once, the first time the reader turns read-aloud on for this passage. */
  onFirstUse?: () => void;
}

/**
 * A toggle that reads the passage aloud, paragraph by paragraph, via `window.speechSynthesis`.
 * Renders nothing when the browser has no speech synthesis. Never starts on its own — a timed
 * test attempt only gets read-aloud if the reader taps this — and stops the moment it unmounts
 * (e.g. the reader moves on to questions), so it can never keep talking in the background.
 */
export default function ReadAloudButton({ paragraphs, onFirstUse }: ReadAloudButtonProps) {
  const [active, setActive] = useState(false);
  const stopRef = useRef<(() => void) | null>(null);
  const usedRef = useRef(false);

  useEffect(
    () => () => {
      stopRef.current?.();
    },
    [],
  );

  if (!speechSupported()) return null;

  function start() {
    if (!usedRef.current) {
      usedRef.current = true;
      onFirstUse?.();
    }
    setActive(true);
    const { stop } = speakParagraphs(paragraphs, () => {
      stopRef.current = null;
      setActive(false);
    });
    stopRef.current = stop;
  }

  function stop() {
    stopRef.current?.();
    stopRef.current = null;
    setActive(false);
  }

  return (
    <button
      type="button"
      className="btn btn--plain btn--small"
      aria-pressed={active}
      onClick={() => (active ? stop() : start())}
    >
      {active ? 'Stop reading aloud' : 'Read aloud'}
    </button>
  );
}

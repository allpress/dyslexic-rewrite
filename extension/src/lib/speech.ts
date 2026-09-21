/**
 * A defensive wrapper around window.speechSynthesis, adapted from web/src/lib/speech.ts, with
 * one addition: `speakWithHighlight` reports word boundaries (via SpeechSynthesisUtterance's
 * `onboundary` event) so the overlay can highlight the word currently being read, where the
 * platform's speech engine supports boundary events (most desktop engines do; when it doesn't,
 * `onWord` simply never fires and the read just proceeds without a highlight).
 */

export function speechSupported(): boolean {
  try {
    return typeof window !== 'undefined' && 'speechSynthesis' in window && !!window.speechSynthesis;
  } catch {
    return false;
  }
}

export function cancelSpeech(): void {
  if (!speechSupported()) return;
  try {
    window.speechSynthesis.cancel();
  } catch {
    // ignore
  }
}

export interface SpeakHandle {
  stop: () => void;
}

/**
 * Speak one paragraph of text, calling `onWord(charIndex, charLength)` for each word boundary
 * the engine reports, and `onDone` once speech finishes naturally (not on manual stop).
 */
export function speakWithHighlight(
  text: string,
  onWord: (charIndex: number, charLength: number) => void,
  onDone?: () => void,
  rate = 0.85,
): SpeakHandle {
  if (!speechSupported() || !text.trim()) {
    onDone?.();
    return { stop: () => {} };
  }
  let stopped = false;
  try {
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = rate;
    utter.onboundary = (e: SpeechSynthesisEvent) => {
      if (stopped) return;
      if (e.name && e.name !== 'word') return; // some engines also fire 'sentence'
      onWord(e.charIndex, e.charLength ?? 0);
    };
    utter.onend = () => {
      if (!stopped) onDone?.();
    };
    utter.onerror = () => {
      if (!stopped) onDone?.();
    };
    window.speechSynthesis.speak(utter);
  } catch {
    onDone?.();
  }
  return {
    stop: () => {
      stopped = true;
      cancelSpeech();
    },
  };
}

/** Speak a queue of paragraphs in order, re-using speakWithHighlight per paragraph so the
 * highlight callback always gets offsets local to the paragraph currently being read. */
export function speakParagraphsWithHighlight(
  paragraphs: string[],
  onParagraph: (index: number) => void,
  onWord: (index: number, charIndex: number, charLength: number) => void,
  onDone?: () => void,
): SpeakHandle {
  let stopped = false;
  let current: SpeakHandle | null = null;
  const queue = paragraphs.map((p, i) => ({ text: p, i })).filter((p) => p.text.trim());
  let pos = 0;

  function next() {
    if (stopped) return;
    if (pos >= queue.length) {
      onDone?.();
      return;
    }
    const { text, i } = queue[pos];
    pos += 1;
    onParagraph(i);
    current = speakWithHighlight(
      text,
      (charIndex, charLength) => onWord(i, charIndex, charLength),
      () => next(),
    );
  }

  next();

  return {
    stop: () => {
      stopped = true;
      current?.stop();
      cancelSpeech();
    },
  };
}

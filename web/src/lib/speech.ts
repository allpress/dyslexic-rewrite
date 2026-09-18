/**
 * A thin, defensive wrapper around `window.speechSynthesis`. Every export is a no-op (never
 * throws) in a browser — or a test environment — that does not have it.
 */

export function speechSupported(): boolean {
  try {
    return typeof window !== 'undefined' && 'speechSynthesis' in window && !!window.speechSynthesis;
  } catch {
    return false;
  }
}

/** Speak one short phrase (e.g. a word) once, cancelling anything already queued. */
export function speak(text: string, rate = 0.85): void {
  if (!speechSupported() || !text.trim()) return;
  try {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = rate;
    window.speechSynthesis.speak(utter);
  } catch {
    // Speech synthesis can throw in odd embedded/webview contexts — never break the reader over it.
  }
}

/** Stop whatever is currently being spoken. Always safe to call. */
export function cancelSpeech(): void {
  if (!speechSupported()) return;
  try {
    window.speechSynthesis.cancel();
  } catch {
    // ignore
  }
}

/**
 * Speak a list of paragraphs one after another. Returns a `stop` function that cancels
 * immediately; `onDone` fires once every paragraph has been spoken (not on manual stop).
 */
export function speakParagraphs(paragraphs: string[], onDone?: () => void): { stop: () => void } {
  let stopped = false;
  if (!speechSupported()) {
    return { stop: () => {} };
  }
  try {
    window.speechSynthesis.cancel();
  } catch {
    // ignore
  }

  const queue = paragraphs.filter((p) => p.trim());
  let i = 0;

  function speakNext() {
    if (stopped) return;
    if (i >= queue.length) {
      onDone?.();
      return;
    }
    const text = queue[i];
    i += 1;
    try {
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = 0.85;
      utter.onend = () => speakNext();
      utter.onerror = () => speakNext();
      window.speechSynthesis.speak(utter);
    } catch {
      onDone?.();
    }
  }

  speakNext();

  return {
    stop: () => {
      stopped = true;
      try {
        window.speechSynthesis.cancel();
      } catch {
        // ignore
      }
    },
  };
}

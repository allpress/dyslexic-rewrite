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

/* --------------------------------------------------------- voices, rate, pitch, highlighting */
// The enhanced read-aloud used by the reader's "Aa" panel (word-by-word highlighting, a voice
// picker, adjustable rate/pitch, "read from here"). `speakParagraphs`/`speak` above are untouched
// so `ReadAloudButton` keeps working exactly as before.

/** Voices available right now, best-effort. Some browsers load the voice list asynchronously —
 * callers that need to react to it arriving should also listen for `voiceschanged` themselves. */
export function listVoices(): SpeechSynthesisVoice[] {
  if (!speechSupported()) return [];
  try {
    return window.speechSynthesis.getVoices() ?? [];
  } catch {
    return [];
  }
}

export interface BoundaryEvent {
  /** Character offset into the block of text currently being spoken. */
  charIndex: number;
  /** Length of the word/sentence the boundary describes, when the browser provides it. */
  charLength: number;
  /** true for a word-level boundary; false when the browser only ever gives sentence-level (or
   * unlabelled) boundaries, e.g. some Safari voices — the caller should highlight the whole
   * sentence in that case instead of a single word. */
  isWord: boolean;
}

export interface SpeakBlocksOptions {
  /** 0.6–1.6 in the panel; passed straight to `SpeechSynthesisUtterance.rate`. */
  rate?: number;
  pitch?: number;
  /** A `SpeechSynthesisVoice.voiceURI`, or falsy to let the browser pick. */
  voiceURI?: string | null;
  /** Fires once per block, right as it starts (used for a whole-block highlight fallback and to
   * track "which paragraph is currently being read"). */
  onBlockStart?: (blockIndex: number) => void;
  /** Fires on every `onboundary` event the browser gives us for the current block. */
  onBoundary?: (blockIndex: number, boundary: BoundaryEvent) => void;
  /** Fires once, after the last non-empty block has finished (not on manual stop). */
  onDone?: () => void;
}

export interface SpeakBlocksHandle {
  stop: () => void;
  pause: () => void;
  resume: () => void;
}

/**
 * Speaks a list of blocks (paragraphs/headings) starting at `startAt`, one `SpeechSynthesisUtterance`
 * per block so `onboundary` offsets stay small and simple to map back onto that block's words.
 * Word-boundary events (`onboundary` with `name === 'word'`, or no `name` at all — most engines
 * that fire boundaries only ever mean word) drive per-word highlighting; if a block finishes
 * having fired no boundary at all, the caller already has a whole-block fallback from
 * `onBlockStart` to highlight instead (see `Reader.tsx`).
 */
export function speakBlocks(blocks: string[], startAt: number, opts: SpeakBlocksOptions = {}): SpeakBlocksHandle {
  let stopped = false;
  let i = Math.max(0, Math.min(startAt, Math.max(0, blocks.length - 1)));

  if (!speechSupported() || blocks.length === 0) {
    return { stop: () => {}, pause: () => {}, resume: () => {} };
  }

  try {
    window.speechSynthesis.cancel();
  } catch {
    // ignore
  }

  function speakCurrent() {
    if (stopped) return;
    if (i >= blocks.length) {
      opts.onDone?.();
      return;
    }
    const text = blocks[i];
    if (!text.trim()) {
      i += 1;
      speakCurrent();
      return;
    }
    const blockIndex = i;
    opts.onBlockStart?.(blockIndex);
    try {
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = opts.rate ?? 1;
      utter.pitch = opts.pitch ?? 1;
      if (opts.voiceURI) {
        const voice = listVoices().find((v) => v.voiceURI === opts.voiceURI);
        if (voice) utter.voice = voice;
      }
      utter.onboundary = (e: SpeechSynthesisEvent) => {
        opts.onBoundary?.(blockIndex, {
          charIndex: e.charIndex,
          charLength: e.charLength ?? 0,
          isWord: e.name ? e.name === 'word' : true,
        });
      };
      utter.onend = () => {
        if (stopped) return;
        i += 1;
        speakCurrent();
      };
      utter.onerror = () => {
        if (stopped) return;
        i += 1;
        speakCurrent();
      };
      window.speechSynthesis.speak(utter);
    } catch {
      i += 1;
      speakCurrent();
    }
  }

  speakCurrent();

  return {
    stop: () => {
      stopped = true;
      try {
        window.speechSynthesis.cancel();
      } catch {
        // ignore
      }
    },
    pause: () => {
      try {
        window.speechSynthesis.pause();
      } catch {
        // ignore
      }
    },
    resume: () => {
      try {
        window.speechSynthesis.resume();
      } catch {
        // ignore
      }
    },
  };
}

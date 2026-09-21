/**
 * A thin, typed wrapper around the browser's SpeechRecognition API (free, in-browser dictation
 * into the paste box on Read anything). Not in TypeScript's standard DOM lib, so the shapes this
 * needs are declared locally rather than pulling in a whole @types package for a handful of
 * fields.
 */

export interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string };
}

export interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResultLike };
}

export interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

interface WindowWithSpeechRecognition {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
}

/** The constructor to use, or null when this browser has neither vendor's implementation. */
export function speechRecognitionSupported(): boolean {
  return getSpeechRecognitionCtor() !== null;
}

export function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  try {
    const w = window as unknown as WindowWithSpeechRecognition;
    return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
  } catch {
    return null;
  }
}

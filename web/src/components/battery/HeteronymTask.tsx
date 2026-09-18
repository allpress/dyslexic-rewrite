import { useEffect, useRef, useState } from 'react';
import type { BatteryHeteronymItem } from '../../api';

export interface HeteronymTrial {
  id: string;
  pair_id: string;
  condition: 'target' | 'control';
  critical_index: number;
  word_rts: number[];
}

export interface HeteronymTaskProps {
  items: BatteryHeteronymItem[];
  onComplete: (result: { trials: HeteronymTrial[] }) => void;
  onSkip: () => void;
}

/** Task H: self-paced moving-window reading (our own hypothesis, the "tricky word" probe). One
 * word is revealed per space-bar press; the previous word turns back to dashes. A comprehension
 * question follows some sentences, to keep people reading for meaning rather than just tapping
 * through. */
export default function HeteronymTask({ items, onComplete, onSkip }: HeteronymTaskProps) {
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<'reading' | 'question'>('reading');
  const [, forceRender] = useState(0);
  const pressCountRef = useRef(0);
  const lastAtRef = useRef(0);
  const wordTimesRef = useRef<number[]>([]);
  const resultsRef = useRef<HeteronymTrial[]>([]);

  const item = items[index];

  useEffect(() => {
    pressCountRef.current = 0;
    wordTimesRef.current = [];
    lastAtRef.current = performance.now();
    setPhase('reading');
    forceRender((t) => t + 1);
  }, [index]);

  function advanceSentence() {
    if (index + 1 < items.length) {
      setIndex(index + 1);
    } else {
      onComplete({ trials: resultsRef.current });
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (phase !== 'reading' || e.key !== ' ') return;
      e.preventDefault();
      const now = performance.now();
      if (pressCountRef.current >= 1) {
        wordTimesRef.current = [...wordTimesRef.current, Math.round(now - lastAtRef.current)];
      }
      lastAtRef.current = now;
      pressCountRef.current += 1;
      if (pressCountRef.current > item.words.length) {
        resultsRef.current = [
          ...resultsRef.current,
          {
            id: item.id,
            pair_id: item.pair_id,
            condition: item.condition,
            critical_index: item.critical_index,
            word_rts: wordTimesRef.current,
          },
        ];
        if (item.question) setPhase('question');
        else advanceSentence();
      } else {
        forceRender((t) => t + 1);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, index, item]);

  const shownIndex = pressCountRef.current - 1;

  return (
    <div className="stack center">
      <h1>Read the sentence</h1>
      <p>Press the space bar to reveal each word. Read at your normal pace.</p>
      <p className="progress">
        Sentence {index + 1} of {items.length}
      </p>
      {phase === 'reading' ? (
        <p className="reader" style={{ fontSize: '1.4rem', fontFamily: 'monospace', letterSpacing: '0.05em' }}>
          {item.words.map((w, i) => (i === shownIndex ? w : '-'.repeat(w.length))).join(' ')}
        </p>
      ) : (
        item.question && (
          <div className="stack">
            <p style={{ fontSize: '1.2rem', fontWeight: 700 }}>{item.question.prompt}</p>
            <div className="btn-row">
              <button className="btn" type="button" onClick={advanceSentence}>
                Yes
              </button>
              <button className="btn" type="button" onClick={advanceSentence}>
                No
              </button>
            </div>
          </div>
        )
      )}
      {index === 0 && phase === 'reading' && (
        <button className="btn btn--plain btn--small" type="button" onClick={onSkip}>
          Skip this section
        </button>
      )}
    </div>
  );
}

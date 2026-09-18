import { useEffect, useRef, useState } from 'react';
import type { BatteryChoiceItem, BatteryChoiceTrial } from '../../api';

export interface ChoiceTaskProps {
  title: string;
  instructions: string;
  items: BatteryChoiceItem[];
  onComplete: (result: { trials: BatteryChoiceTrial[] }) => void;
  onSkip: () => void;
}

/** Shared two-alternative forced-choice task for C (orthographic choice) and D (pseudohomophone
 * decision): two words, pick one, timed with `performance.now()`. Left/Right arrow keys work too. */
export default function ChoiceTask({ title, instructions, items, onComplete, onSkip }: ChoiceTaskProps) {
  const [index, setIndex] = useState(0);
  const trialsRef = useRef<BatteryChoiceTrial[]>([]);
  const shownAt = useRef(performance.now());

  const item = items[index];

  useEffect(() => {
    shownAt.current = performance.now();
  }, [index]);

  function choose(side: 'left' | 'right') {
    const rt_ms = Math.round(performance.now() - shownAt.current);
    trialsRef.current = [...trialsRef.current, { id: item.id, correct: side === item.correct, rt_ms }];
    if (index + 1 < items.length) {
      setIndex(index + 1);
    } else {
      onComplete({ trials: trialsRef.current });
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'ArrowLeft') choose('left');
      else if (e.key === 'ArrowRight') choose('right');
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  return (
    <div className="stack">
      <h1>{title}</h1>
      <p>{instructions}</p>
      <p className="progress">
        Item {index + 1} of {items.length}
      </p>
      <div className="choices" style={{ gridTemplateColumns: '1fr 1fr' }} role="group" aria-label={instructions}>
        <button
          type="button"
          className="choice center"
          style={{ fontSize: '1.5rem', fontWeight: 700 }}
          onClick={() => choose('left')}
        >
          {item.left}
        </button>
        <button
          type="button"
          className="choice center"
          style={{ fontSize: '1.5rem', fontWeight: 700 }}
          onClick={() => choose('right')}
        >
          {item.right}
        </button>
      </div>
      <p className="muted">You can also use the left and right arrow keys.</p>
      <button className="btn btn--plain btn--small" type="button" onClick={onSkip}>
        Skip this section
      </button>
    </div>
  );
}

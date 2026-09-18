import { useEffect, useRef, useState } from 'react';
import { afterMs } from '../../lib/timing';
import type { BatteryVasTrial } from '../../api';

export interface VasTaskProps {
  trials: BatteryVasTrial[];
  onComplete: (result: { trials: { id: string; correct_letters: number; practice: boolean }[] }) => void;
  onSkip: () => void;
}

type Phase = 'fixation' | 'flash' | 'input';

function lettersCorrect(target: string[], guess: string): number {
  const g = guess.toUpperCase().replace(/[^A-Z]/g, '');
  let n = 0;
  for (let i = 0; i < target.length; i++) {
    if (g[i] === target[i]) n += 1;
  }
  return n;
}

/** Task E: VAS whole report. Fixation cross (500ms) -> 5 consonants (200ms) -> type what you saw. */
export default function VasTask({ trials, onComplete, onSkip }: VasTaskProps) {
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>('fixation');
  const [response, setResponse] = useState('');
  const resultsRef = useRef<{ id: string; correct_letters: number; practice: boolean }[]>([]);

  const trial = trials[index];

  useEffect(() => {
    setPhase('fixation');
    setResponse('');
    return afterMs(500, () => setPhase('flash'));
  }, [index]);

  useEffect(() => {
    if (phase !== 'flash') return undefined;
    return afterMs(200, () => setPhase('input'));
  }, [phase]);

  function submit() {
    const correct_letters = lettersCorrect(trial.letters, response);
    resultsRef.current = [...resultsRef.current, { id: trial.id, correct_letters, practice: trial.practice }];
    if (index + 1 < trials.length) {
      setIndex(index + 1);
    } else {
      onComplete({ trials: resultsRef.current });
    }
  }

  return (
    <div className="stack center">
      <h1>What letters did you see?</h1>
      {trial.practice && <p className="muted">Practice round — this one is not scored.</p>}
      <p className="progress">
        Trial {index + 1} of {trials.length}
      </p>
      <div style={{ minHeight: 120, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {phase === 'fixation' && (
          <span style={{ fontSize: '3rem' }} aria-hidden="true">
            +
          </span>
        )}
        {phase === 'flash' && (
          <span style={{ fontFamily: 'monospace', fontSize: '2.2rem', letterSpacing: '0.5em' }}>
            {trial.letters.join('')}
          </span>
        )}
        {phase === 'input' && (
          <div className="stack" style={{ width: '100%', maxWidth: 320 }}>
            <label htmlFor="vas-response">Type the letters you saw, in order</label>
            <input
              id="vas-response"
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              autoFocus
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submit();
              }}
            />
            <button className="btn btn--wide" type="button" onClick={submit}>
              Next
            </button>
          </div>
        )}
      </div>
      {index === 0 && (
        <button className="btn btn--plain btn--small" type="button" onClick={onSkip}>
          Skip this section
        </button>
      )}
    </div>
  );
}

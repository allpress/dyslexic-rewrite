import { useEffect, useRef, useState } from 'react';
import { afterMs } from '../../lib/timing';
import type { BatteryDigitTrial } from '../../api';

export interface DigitSpanTaskProps {
  trials: BatteryDigitTrial[];
  onComplete: (result: { span: number }) => void;
  onSkip: () => void;
}

type Phase = 'show' | 'input';

/** Task F: backward digit span. Digits shown one per second, then typed back in reverse. Stops
 * once both trials at a length are failed; span = longest length with at least one correct trial. */
export default function DigitSpanTask({ trials, onComplete, onSkip }: DigitSpanTaskProps) {
  const [pos, setPos] = useState(0);
  const [phase, setPhase] = useState<Phase>('show');
  const [digitIndex, setDigitIndex] = useState(0);
  const [response, setResponse] = useState('');
  const passesRef = useRef<Record<number, boolean[]>>({});
  const spanRef = useRef(0);

  const trial = trials[pos];

  useEffect(() => {
    setPhase('show');
    setDigitIndex(0);
    setResponse('');
  }, [pos]);

  useEffect(() => {
    if (phase !== 'show' || !trial) return undefined;
    if (digitIndex >= trial.digits.length) {
      setPhase('input');
      return undefined;
    }
    return afterMs(1000, () => setDigitIndex((i) => i + 1));
  }, [phase, digitIndex, trial]);

  if (!trial) return null;

  function submit() {
    const expected = [...trial.digits].reverse().join('');
    const given = response.replace(/\D/g, '');
    const correct = given === expected;

    const flags = [...(passesRef.current[trial.length] || []), correct];
    passesRef.current = { ...passesRef.current, [trial.length]: flags };
    if (flags.some(Boolean)) spanRef.current = trial.length;

    const isSecondTrialAtLength = trial.id.endsWith('-1');
    const bothFailedAtLength = isSecondTrialAtLength && flags.length >= 2 && !flags.some(Boolean);
    const nextPos = pos + 1;

    if (bothFailedAtLength || nextPos >= trials.length) {
      onComplete({ span: spanRef.current });
      return;
    }
    setPos(nextPos);
  }

  return (
    <div className="stack center">
      <h1>Backward digit span</h1>
      <p>Watch the digits, then type them back in reverse order.</p>
      <p className="progress">{trial.length} digits</p>
      <div style={{ minHeight: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {phase === 'show' ? (
          <span style={{ fontSize: '3rem', fontWeight: 700 }} aria-live="polite">
            {digitIndex < trial.digits.length ? trial.digits[digitIndex] : ''}
          </span>
        ) : (
          <div className="stack" style={{ width: '100%', maxWidth: 320 }}>
            <label htmlFor="digit-response">Type the digits in reverse order</label>
            <input
              id="digit-response"
              type="text"
              inputMode="numeric"
              autoComplete="off"
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
      {pos === 0 && (
        <button className="btn btn--plain btn--small" type="button" onClick={onSkip}>
          Skip this section
        </button>
      )}
    </div>
  );
}

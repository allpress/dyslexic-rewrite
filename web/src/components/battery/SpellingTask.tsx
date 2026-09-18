import { useEffect, useRef, useState } from 'react';
import { cancelSpeech, speak, speechSupported } from '../../lib/speech';
import type { BatterySpelling } from '../../api';

export interface SpellingTrial {
  id: string;
  word: string;
  kind: string;
  response: string;
}

export interface SpellingTaskProps {
  items: BatterySpelling;
  onComplete: (result: { trials: SpellingTrial[] }) => void;
  onSkip: () => void;
}

/** Task B: 20 words spoken aloud, typed back. Skips itself (and says so) when the browser has
 * no speech synthesis, per the FEATURE spec. */
export default function SpellingTask({ items, onComplete, onSkip }: SpellingTaskProps) {
  const supported = useRef(speechSupported());
  const [index, setIndex] = useState(0);
  const [response, setResponse] = useState('');
  const trialsRef = useRef<SpellingTrial[]>([]);

  const item = items.items[index];

  useEffect(() => {
    if (supported.current && item) speak(item.word, items.speech_rate);
    return () => cancelSpeech();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  if (!supported.current) {
    return (
      <div className="stack">
        <h1>Spelling from dictation</h1>
        <p>Your browser cannot speak words out loud, so we will skip this part.</p>
        <button className="btn btn--wide" type="button" onClick={onSkip}>
          Continue
        </button>
      </div>
    );
  }

  function next() {
    trialsRef.current = [...trialsRef.current, { id: item.id, word: item.word, kind: item.kind, response }];
    setResponse('');
    if (index + 1 < items.items.length) {
      setIndex(index + 1);
    } else {
      onComplete({ trials: trialsRef.current });
    }
  }

  return (
    <div className="stack">
      <h1>Type the word you hear</h1>
      <p className="progress">
        Word {index + 1} of {items.items.length}
      </p>
      <button className="btn" type="button" onClick={() => speak(item.word, items.speech_rate)}>
        Play again
      </button>
      <div>
        <label htmlFor="spelling-response">Your answer</label>
        <input
          id="spelling-response"
          type="text"
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') next();
          }}
        />
      </div>
      <button className="btn btn--wide" type="button" onClick={next}>
        {index + 1 < items.items.length ? 'Next word' : 'Finish this section'}
      </button>
      <button className="btn btn--plain btn--small" type="button" onClick={onSkip}>
        Skip this section
      </button>
    </div>
  );
}

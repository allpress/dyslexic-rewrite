import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Reader from '../components/Reader';
import {
  ApiError,
  createTest,
  finishItem,
  postTriggers,
  startItem,
  type ItemResult,
  type Test,
} from '../api';
import { easeWord, verdict } from '../lib/verdict';
import { useMe } from '../useMe';

type Phase = 'loading' | 'intro' | 'reading' | 'questions' | 'ease' | 'item-done' | 'all-done';

const EASE_LABELS = ['Very hard', 'Hard', 'Okay', 'Easy', 'Very easy'];

export default function TestPage() {
  const navigate = useNavigate();
  const { setProfile } = useMe();

  const [test, setTest] = useState<Test | null>(null);
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>('loading');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Per-item working state.
  const startedAt = useRef<number>(0);
  const [seconds, setSeconds] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [qIndex, setQIndex] = useState(0);
  const [tripped, setTripped] = useState<Map<string, string>>(new Map());
  const [showMarks, setShowMarks] = useState(false); // hidden by default during a test

  const [results, setResults] = useState<(ItemResult | null)[]>([null, null]);
  const [allTripped, setAllTripped] = useState<string[]>([]);
  const [savedTriggers, setSavedTriggers] = useState(false);

  const begin = useCallback(async () => {
    setPhase('loading');
    setError(null);
    try {
      const t = await createTest();
      setTest(t);
      setIndex(0);
      setResults([null, null]);
      setAllTripped([]);
      setSavedTriggers(false);
      setPhase('intro');
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not start a test. Try again.');
      setPhase('intro');
    }
  }, []);

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void begin();
  }, [begin]);

  function resetItemState() {
    setSeconds(0);
    setAnswers({});
    setQIndex(0);
    setTripped(new Map());
    setShowMarks(false);
  }

  const item = test?.items[index];

  async function handleStartReading() {
    if (!test) return;
    setBusy(true);
    setError(null);
    try {
      await startItem(test.id, index);
      startedAt.current = Date.now();
      setPhase('reading');
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not start the passage.');
    } finally {
      setBusy(false);
    }
  }

  function handleDoneReading() {
    setSeconds(Math.max(1, Math.round((Date.now() - startedAt.current) / 1000)));
    setPhase('questions');
  }

  function toggleWord(id: string, word: string) {
    setTripped((prev) => {
      const next = new Map(prev);
      if (next.has(id)) next.delete(id);
      else next.set(id, word);
      return next;
    });
  }

  function answerQuestion(questionId: string, option: number) {
    const total = item?.questions.length ?? 0;
    setAnswers((prev) => ({ ...prev, [questionId]: option }));
    if (qIndex + 1 < total) setQIndex(qIndex + 1);
    else setPhase('ease');
  }

  async function handleEase(ease: number) {
    if (!test) return;
    setBusy(true);
    setError(null);
    const words = Array.from(new Set(tripped.values())).filter(Boolean);
    try {
      const result = await finishItem(test.id, index, { seconds, answers, tripped: words, ease });
      setResults((prev) => {
        const next = [...prev];
        next[index] = result;
        return next;
      });
      setAllTripped((prev) => Array.from(new Set([...prev, ...words])));
      setPhase('item-done');
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not save that passage.');
    } finally {
      setBusy(false);
    }
  }

  function nextItem() {
    resetItemState();
    if (test && index + 1 < test.items.length) {
      setIndex(index + 1);
      setPhase('intro');
    } else {
      setPhase('all-done');
    }
  }

  async function saveTriggers() {
    setBusy(true);
    try {
      const res = await postTriggers({ add: allTripped });
      setProfile(res.profile);
      setSavedTriggers(true);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not save those words.');
    } finally {
      setBusy(false);
    }
  }

  /* ------------------------------------------------------------ render */

  if (phase === 'loading') {
    return (
      <main className="page page--narrow stack" id="main">
        <p className="muted">Getting your passages ready…</p>
      </main>
    );
  }

  const errorBox = error && (
    <p className="error" role="alert">
      {error}
    </p>
  );

  if (phase === 'all-done' && test) {
    return (
      <main className="page stack" id="main">
        {errorBox}
        <FinalResults
          test={test}
          results={results}
          tripped={allTripped}
          saved={savedTriggers}
          busy={busy}
          onSave={saveTriggers}
          onAgain={() => {
            resetItemState();
            started.current = true;
            void begin();
          }}
          onResults={() => navigate('/results')}
        />
      </main>
    );
  }

  if (!test || !item) {
    return (
      <main className="page page--narrow stack" id="main">
        {errorBox}
        <button className="btn" type="button" onClick={() => void begin()}>
          Try again
        </button>
      </main>
    );
  }

  if (phase === 'intro') {
    return (
      <main className="page page--narrow stack" id="main">
        {errorBox}
        <p className="progress">
          Passage {index + 1} of {test.items.length}
        </p>
        <h1>{item.title}</h1>
        <p>Read at your normal pace, then answer 5 questions.</p>
        <p>Tap any word that trips you up. You can tap it again to change your mind.</p>
        <button className="btn btn--wide" type="button" onClick={handleStartReading} disabled={busy}>
          {busy ? 'One moment…' : 'Start reading'}
        </button>
      </main>
    );
  }

  if (phase === 'reading') {
    return (
      <main className="page stack" id="main">
        {errorBox}
        <div className="reader-toolbar">
          <span className="progress" style={{ margin: 0 }}>
            Passage {index + 1} of {test.items.length}
          </span>
          <span className="reader-toolbar__spacer" />
          <button
            className="btn btn--plain btn--small"
            type="button"
            aria-pressed={showMarks}
            onClick={() => setShowMarks((v) => !v)}
          >
            {showMarks ? 'Hide marks' : 'Show marks'}
          </button>
        </div>

        <Reader
          segments={item.segments}
          showMarks={showMarks}
          tripped={new Set(tripped.keys())}
          onToggleWord={toggleWord}
        />

        <button className="btn btn--wide" type="button" onClick={handleDoneReading}>
          I&rsquo;m done
        </button>
      </main>
    );
  }

  if (phase === 'questions') {
    const q = item.questions[qIndex];
    if (!q) {
      return (
        <main className="page page--narrow stack" id="main">
          <button className="btn" type="button" onClick={() => setPhase('ease')}>
            Continue
          </button>
        </main>
      );
    }
    return (
      <main className="page page--narrow stack" id="main">
        {errorBox}
        <p className="progress">
          Question {qIndex + 1} of {item.questions.length}
        </p>
        <fieldset className="question">
          <legend>{q.prompt}</legend>
          <div className="choices">
            {q.options.map((option, i) => (
              <button
                key={`${q.id}-${i}`}
                type="button"
                className="choice"
                aria-pressed={answers[q.id] === i}
                onClick={() => answerQuestion(q.id, i)}
              >
                {option}
              </button>
            ))}
          </div>
        </fieldset>
        {qIndex > 0 && (
          <button
            className="btn btn--plain btn--small"
            type="button"
            onClick={() => setQIndex(qIndex - 1)}
          >
            Back one question
          </button>
        )}
      </main>
    );
  }

  if (phase === 'ease') {
    return (
      <main className="page page--narrow stack" id="main">
        {errorBox}
        <h1>How easy was that?</h1>
        <div className="scale" role="group" aria-label="How easy was that, 1 is very hard, 5 is very easy">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => void handleEase(n)}
              disabled={busy}
              aria-label={`${n} — ${EASE_LABELS[n - 1]}`}
            >
              {n}
            </button>
          ))}
        </div>
        <p className="scale__ends">
          <span>1 — very hard</span>
          <span>5 — very easy</span>
        </p>
      </main>
    );
  }

  // phase === 'item-done'
  const result = results[index];
  const last = index + 1 >= test.items.length;
  return (
    <main className="page page--narrow stack" id="main">
      {errorBox}
      <h1>Passage {index + 1} done</h1>
      {result && (
        <dl className="facts">
          <div>
            <dt>Reading speed</dt>
            <dd>{result.wpm} words a minute</dd>
          </div>
          <div>
            <dt>Questions right</dt>
            <dd>
              {result.correct} of {result.total}
            </dd>
          </div>
          <div>
            <dt>You said it felt</dt>
            <dd>{easeWord(result.ease)}</dd>
          </div>
        </dl>
      )}
      <button className="btn btn--wide" type="button" onClick={nextItem}>
        {last ? 'See my results' : 'Next passage'}
      </button>
    </main>
  );
}

/* ------------------------------------------------------- final screen */

function FinalResults({
  test,
  results,
  tripped,
  saved,
  busy,
  onSave,
  onAgain,
  onResults,
}: {
  test: Test;
  results: (ItemResult | null)[];
  tripped: string[];
  saved: boolean;
  busy: boolean;
  onSave: () => void;
  onAgain: () => void;
  onResults: () => void;
}) {
  const rows = test.items.map((it, i) => ({ item: it, result: results[i] }));
  const original = rows.find((r) => r.item.condition === 'original');
  const rewritten = rows.find((r) => r.item.condition === 'rewritten');

  const line =
    original?.result && rewritten?.result
      ? verdict(
          {
            wpm: original.result.wpm,
            correct: original.result.correct,
            total: original.result.total,
          },
          {
            wpm: rewritten.result.wpm,
            correct: rewritten.result.correct,
            total: rewritten.result.total,
          },
        )
      : null;

  return (
    <div className="stack">
      <h1>Your results</h1>
      {line && <p style={{ fontSize: '1.15rem', fontWeight: 700 }}>{line}</p>}

      <div className="stack">
        {rows.map(({ item, result }) => (
          <div className="card" key={item.index}>
            <h2 style={{ fontSize: '1rem' }}>
              {item.condition === 'rewritten' ? 'The rewritten passage' : 'The original passage'}
            </h2>
            {result ? (
              <dl className="facts">
                <div>
                  <dt>Speed</dt>
                  <dd>{result.wpm} words a minute</dd>
                </div>
                <div>
                  <dt>Questions right</dt>
                  <dd>
                    {result.correct} of {result.total}
                  </dd>
                </div>
                <div>
                  <dt>Felt</dt>
                  <dd>{easeWord(result.ease)}</dd>
                </div>
              </dl>
            ) : (
              <p className="muted">Not finished.</p>
            )}
          </div>
        ))}
      </div>

      {tripped.length > 0 && (
        <section className="stack">
          <h2>Words that tripped you up</h2>
          <ul className="pill-list">
            {tripped.map((w) => (
              <li className="pill" key={w}>
                {w}
              </li>
            ))}
          </ul>
          {saved ? (
            <p className="notice">
              <span>Saved. We will swap these words out from now on.</span>
            </p>
          ) : (
            <button className="btn" type="button" onClick={onSave} disabled={busy}>
              Add these to my profile
            </button>
          )}
        </section>
      )}

      <div className="btn-row">
        <button className="btn" type="button" onClick={onAgain}>
          Take another test
        </button>
        <button className="btn btn--quiet" type="button" onClick={onResults}>
          See all results
        </button>
      </div>

      <p className="muted">
        <Link to="/read">Or paste something of your own to read</Link>
      </p>
    </div>
  );
}

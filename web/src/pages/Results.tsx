import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, getResults, type ResultsResponse } from '../api';
import { asPercent, totalsVerdict } from '../lib/verdict';
import FeedbackPrompt from '../components/FeedbackPrompt';

function Bar({ label, value, max, alt }: { label: string; value: number; max: number; alt?: boolean }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div>
      <p className="bar__head">
        <span>{label}</span>
        <span>{value}</span>
      </p>
      <div
        className="bar__track"
        role="img"
        aria-label={`${label}: ${value}`}
      >
        <div className={`bar__fill${alt ? ' bar__fill--alt' : ''}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function Results() {
  const [data, setData] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getResults()
      .then((r) => live && setData(r))
      .catch((err) => {
        if (err instanceof ApiError && err.isUnauthorized) return;
        if (live) setError(err instanceof ApiError ? err.message : 'We could not load your results.');
      });
    return () => {
      live = false;
    };
  }, []);

  if (error) {
    return (
      <main className="page page--narrow stack" id="main">
        <p className="error" role="alert">
          {error}
        </p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="page page--narrow stack" id="main">
        <p className="muted">Loading your results…</p>
      </main>
    );
  }

  const { original, rewritten } = data.totals;
  const done = original.n > 0 && rewritten.n > 0;

  if (!done && data.tests.length === 0) {
    return (
      <main className="page page--narrow stack" id="main">
        <h1>No results yet</h1>
        <p>Take a reading test and your numbers will show up here.</p>
        <Link className="btn" to="/test">
          Start a reading test
        </Link>
      </main>
    );
  }

  const maxWpm = Math.max(original.wpm, rewritten.wpm, 1);
  const line = done ? totalsVerdict(original, rewritten) : null;

  return (
    <main className="page stack" id="main">
      <h1>Your results</h1>

      {line && <p style={{ fontSize: '1.15rem', fontWeight: 700 }}>{line}</p>}

      <section className="stack" aria-labelledby="speed-heading">
        <h2 id="speed-heading">Reading speed</h2>
        <div className="bars">
          <Bar label="Original text" value={original.wpm} max={maxWpm} alt />
          <Bar label="Rewritten text" value={rewritten.wpm} max={maxWpm} />
        </div>
        <p className="muted">Words a minute, across {original.n + rewritten.n} passages.</p>
      </section>

      <section className="stack" aria-labelledby="comp-heading">
        <h2 id="comp-heading">Questions right</h2>
        <div className="bars">
          <Bar label="Original text" value={asPercent(original.comprehension)} max={100} alt />
          <Bar label="Rewritten text" value={asPercent(rewritten.comprehension)} max={100} />
        </div>
        <p className="muted">Out of 100.</p>
      </section>

      <section className="stack" aria-labelledby="past-heading">
        <h2 id="past-heading">Tests you have taken</h2>
        {data.tests.length === 0 ? (
          <p className="muted">None yet.</p>
        ) : (
          <ul className="test-list">
            {data.tests.map((t, index) => (
              <li className="card" key={t.id}>
                <p className="progress" style={{ margin: 0 }}>
                  {new Date(t.created_at).toLocaleDateString()}
                  {t.completed ? '' : ' — not finished'}
                </p>
                <dl className="facts">
                  {t.items.map((it, i) => (
                    <div key={`${t.id}-${i}`}>
                      <dt>
                        {it.title} ({it.condition === 'rewritten' ? 'rewritten' : 'original'})
                      </dt>
                      <dd>
                        {it.wpm} wpm · {it.correct}/{it.total}
                      </dd>
                    </div>
                  ))}
                </dl>
                {index === 0 && t.completed && (
                  <FeedbackPrompt
                    storageKey={`feedback-test-${t.id}`}
                    context={{ test_id: t.id, pair: t.pair }}
                    page="/results"
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Link className="btn" to="/test">
        Take another test
      </Link>
    </main>
  );
}

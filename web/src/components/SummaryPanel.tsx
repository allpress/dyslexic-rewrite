import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, type SummaryResponse } from '../api';

export interface SummaryPanelProps {
  /** The signed-in reader's Pro state (false for a free reader or an anonymous visitor). */
  isPro: boolean;
  /** POST /api/summaries or POST /api/books/{id}/summary, depending on the caller. */
  fetchSummary: () => Promise<SummaryResponse>;
}

/**
 * A "Summary" button that produces a short, plain-language AI summary (v0.6, Pro only) and
 * shows it under a clear label -- this is a convenience for orientation, not a substitute for
 * reading the text, and the label says so.
 */
export default function SummaryPanel({ isPro, fetchSummary }: SummaryPanelProps) {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setSummary(await fetchSummary());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not summarise that.');
    } finally {
      setBusy(false);
    }
  }

  if (!isPro) {
    return (
      <p className="muted">
        <span className="pro-badge">Pro</span> AI summaries are part of Unwind Words Pro.{' '}
        <Link to="/pricing">See Unwind Words Pro</Link>
      </p>
    );
  }

  if (summary) {
    return (
      <div className="summary-panel">
        <span className="summary-panel__label">AI summary — read the text for the details</span>
        <ul>
          {summary.bullets.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="stack">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="btn btn--plain btn--small" type="button" onClick={() => void run()} disabled={busy}>
        {busy ? 'Summarising…' : 'Summary'}
      </button>
    </div>
  );
}

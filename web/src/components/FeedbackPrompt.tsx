import { useState } from 'react';
import { submitFeedback } from '../api';

export interface FeedbackPromptProps {
  /** Unique per instance (e.g. `feedback-test-{id}`) — remembers, per browser, that this exact
   * prompt was answered or dismissed so it never nags about the same test/book twice. */
  storageKey: string;
  /** Extra context to send with the vote (e.g. `{test_id}` or `{book_id}`). */
  context: Record<string, unknown>;
  page: string;
  question?: string;
}

function alreadyDone(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

function markDone(key: string): void {
  try {
    localStorage.setItem(key, '1');
  } catch {
    // best-effort only — a per-viewer convenience, not durable state
  }
}

/**
 * A one-line "Did that read easier?" prompt with 👍/👎 and an optional comment, shown after a
 * reading test finishes (Results.tsx) or a book conversion completes (Library.tsx). 👍 sends
 * kind='praise' + rating 5, 👎 sends kind='bug' + rating 2, both carrying `context`.
 */
export default function FeedbackPrompt({ storageKey, context, page, question = 'Did that read easier?' }: FeedbackPromptProps) {
  const [dismissed, setDismissed] = useState(() => alreadyDone(storageKey));
  const [answered, setAnswered] = useState(false);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  if (dismissed) return null;

  if (answered) {
    return <p className="feedback-inline muted">Thanks — we read every one.</p>;
  }

  async function vote(good: boolean) {
    setBusy(true);
    try {
      await submitFeedback({
        kind: good ? 'praise' : 'bug',
        message: comment.trim() || (good ? "👍 — said it read easier" : "👎 — didn't read easier"),
        rating: good ? 5 : 2,
        page,
        context,
      });
    } catch {
      // A dropped vote should never block the reader; the full feedback widget is still there.
    } finally {
      markDone(storageKey);
      setBusy(false);
      setAnswered(true);
    }
  }

  function dismiss() {
    markDone(storageKey);
    setDismissed(true);
  }

  return (
    <p className="feedback-inline feedback-inline__row">
      <span>{question}</span>
      <button type="button" aria-label="Yes, easier" disabled={busy} onClick={() => void vote(true)}>
        👍
      </button>
      <button type="button" aria-label="No, not easier" disabled={busy} onClick={() => void vote(false)}>
        👎
      </button>
      <input
        type="text"
        className="feedback-inline__comment"
        placeholder="Optional comment"
        aria-label="Optional comment"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <button className="btn btn--plain btn--small" type="button" onClick={dismiss}>
        Dismiss
      </button>
    </p>
  );
}

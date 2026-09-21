import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ApiError, APP_VERSION, submitFeedback, type FeedbackKind } from '../api';
import { useMe } from '../useMe';

const KINDS: { value: FeedbackKind; label: string }[] = [
  { value: 'bug', label: 'Bug' },
  { value: 'idea', label: 'Idea' },
  { value: 'praise', label: 'Praise' },
  { value: 'question', label: 'Question' },
];

/**
 * A floating "Feedback" button, present on every page, that opens a small panel: what kind of
 * feedback, a message, an optional "how is reading going?" rating, and (signed out only) an
 * optional email. Hidden on `/test` — the one page with a running timer — so it can never
 * distract from a timed A/B attempt.
 */
export default function FeedbackWidget() {
  const location = useLocation();
  const { user } = useMe();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<FeedbackKind>('idea');
  const [message, setMessage] = useState('');
  const [rating, setRating] = useState<number | null>(null);
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (location.pathname === '/test') return null;

  function reset() {
    setKind('idea');
    setMessage('');
    setRating(null);
    setEmail('');
    setError(null);
    setDone(false);
  }

  function close() {
    setOpen(false);
    reset();
  }

  async function submit() {
    if (!message.trim()) {
      setError('Say a little about what happened.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await submitFeedback({
        kind,
        message: message.trim(),
        rating: rating ?? undefined,
        page: location.pathname,
        email: !user && email.trim() ? email.trim() : undefined,
        context: {
          plan: user?.plan.plan,
          phonetic_map: user?.phonetic_map,
          app_version: APP_VERSION,
          viewport: `${window.innerWidth}x${window.innerHeight}`,
          user_agent: navigator.userAgent,
        },
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That didn't send. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="feedback-widget">
      {open ? (
        <div className="feedback-panel card stack" role="dialog" aria-label="Send feedback">
          {done ? (
            <>
              <p className="feedback-thanks">Thanks — we read every one.</p>
              <button className="btn" type="button" onClick={close}>
                Close
              </button>
            </>
          ) : (
            <>
              <div className="feedback-panel__head">
                <h2>Feedback</h2>
                <button type="button" className="feedback-close" aria-label="Close feedback" onClick={close}>
                  ✕
                </button>
              </div>

              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}

              <div className="feedback-kinds" role="radiogroup" aria-label="What kind of feedback">
                {KINDS.map((k) => (
                  <button
                    key={k.value}
                    type="button"
                    role="radio"
                    aria-checked={kind === k.value}
                    className={`feedback-chip${kind === k.value ? ' feedback-chip--active' : ''}`}
                    onClick={() => setKind(k.value)}
                  >
                    {k.label}
                  </button>
                ))}
              </div>

              <label htmlFor="feedback-message">What&rsquo;s on your mind?</label>
              <textarea
                id="feedback-message"
                rows={4}
                maxLength={4000}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />

              <fieldset className="feedback-rating">
                <legend>How is reading going? (optional)</legend>
                <div className="scale" role="group" aria-label="How is reading going, 1 is hard, 5 is great">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      aria-pressed={rating === n}
                      onClick={() => setRating((r) => (r === n ? null : n))}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </fieldset>

              {!user && (
                <>
                  <label htmlFor="feedback-email">Your email (optional, if you&rsquo;d like a reply)</label>
                  <input
                    id="feedback-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </>
              )}

              <button className="btn btn--wide" type="button" onClick={() => void submit()} disabled={busy}>
                {busy ? 'Sending…' : 'Send'}
              </button>
            </>
          )}
        </div>
      ) : (
        <button
          type="button"
          className="feedback-fab"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          Feedback
        </button>
      )}
    </div>
  );
}

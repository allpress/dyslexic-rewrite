import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import Reader from '../components/Reader';
import { ApiError, postFeedback, rewrite, type RewriteResponse } from '../api';
import { useMe } from '../useMe';

const MAX_CHARS = 20000;

export default function ReadAnything() {
  const { user, setProfile } = useMe();

  const [text, setText] = useState('');
  const [result, setResult] = useState<RewriteResponse | null>(null);
  const [showMarks, setShowMarks] = useState(true); // on by default here
  const [showOriginalInline, setShowOriginalInline] = useState(false);
  const [tripped, setTripped] = useState<Map<string, string>>(new Map());
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const res = await rewrite(text);
      setResult(res);
      setTripped(new Map());
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not rewrite that. Try again.');
    } finally {
      setBusy(false);
    }
  }

  function toggleWord(id: string, word: string) {
    setTripped((prev) => {
      const next = new Map(prev);
      if (next.has(id)) next.delete(id);
      else next.set(id, word);
      return next;
    });
    setSaved(false);
  }

  async function saveTripped() {
    setBusy(true);
    setError(null);
    try {
      const words = Array.from(new Set(tripped.values())).filter(Boolean);
      const res = await postFeedback({ tripped: words });
      setProfile(res.profile);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not save those words.');
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    const s = result.stats;
    return (
      <main className="page stack" id="main">
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <div className="reader-toolbar">
          <button
            className="btn btn--plain btn--small"
            type="button"
            aria-pressed={showMarks}
            onClick={() => setShowMarks((v) => !v)}
          >
            {showMarks ? 'Hide marks' : 'Show marks'}
          </button>
          <button
            className="btn btn--plain btn--small"
            type="button"
            aria-pressed={showOriginalInline}
            onClick={() => setShowOriginalInline((v) => !v)}
          >
            {showOriginalInline ? 'Hide original' : 'Show original inline'}
          </button>
          <span className="reader-toolbar__spacer" />
          <button
            className="btn btn--plain btn--small"
            type="button"
            onClick={() => {
              setResult(null);
              setTripped(new Map());
            }}
          >
            Paste something else
          </button>
        </div>

        <p className="muted">
          {s.sentences_changed} of {s.sentences} sentences changed. {s.changes} word
          {s.changes === 1 ? '' : 's'} swapped. Reading load went from {Math.round(s.load_before)} to{' '}
          {Math.round(s.load_after)}.
        </p>

        <Reader
          segments={result.segments}
          showMarks={showMarks}
          showOriginalInline={showOriginalInline}
          tripped={new Set(tripped.keys())}
          onToggleWord={toggleWord}
        />

        {user ? (
          tripped.size > 0 && (
            <div className="stack">
              {saved ? (
                <p className="notice">
                  <span>Saved. We will swap those words out from now on.</span>
                </p>
              ) : (
                <button className="btn" type="button" onClick={saveTripped} disabled={busy}>
                  These words tripped me &rarr; save to my profile
                </button>
              )}
            </div>
          )
        ) : (
          <p className="muted">
            <Link to="/signin">Sign in</Link> to save the words that trip you up.
          </p>
        )}
      </main>
    );
  }

  return (
    <main className="page page--narrow stack" id="main">
      <h1>Read anything</h1>
      <p>Paste text in. We straighten the sentences and swap the words that slow you down.</p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form onSubmit={submit} className="stack">
        <div>
          <label htmlFor="text">Paste anything: an email, an article, a chapter</label>
          <textarea
            id="text"
            name="text"
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
            placeholder="Paste here…"
            required
          />
          <p className="muted">
            {text.length} of {MAX_CHARS} characters. We never store what you paste.
          </p>
        </div>
        <button className="btn btn--wide" type="submit" disabled={busy || !text.trim()}>
          {busy ? 'Rewriting…' : 'Rewrite it'}
        </button>
      </form>

      {!user && (
        <p className="muted">
          Not signed in, so we use the general profile. <Link to="/signin">Sign in</Link> for one
          built around you.
        </p>
      )}
    </main>
  );
}

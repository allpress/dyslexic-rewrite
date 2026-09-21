import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Reader, { paragraphTexts } from '../components/Reader';
import ReadAloudButton from '../components/ReadAloudButton';
import PhoneticModeSelect from '../components/PhoneticModeSelect';
import SamplePicker from '../components/SamplePicker';
import ReaderSettingsPanel from '../components/reader/ReaderSettingsPanel';
import {
  ApiError,
  getSample,
  patchMe,
  postFeedback,
  rewrite,
  type PhoneticMapMode,
  type RewriteResponse,
} from '../api';
import { useMe } from '../useMe';

/** Attribution shown under a sample passage instead of the paste-your-own flow. */
interface SampleAttribution {
  title: string;
  author: string;
  year: number;
  chapter: string;
  source: string;
}

const MAX_CHARS = 20000;

export default function ReadAnything() {
  const { user, profile, setProfile, setMe } = useMe();

  const [phoneticMapMode, setPhoneticMapMode] = useState<PhoneticMapMode>(
    user?.phonetic_map ?? 'on_demand',
  );
  const syncedPhoneticMode = useRef(false);
  useEffect(() => {
    if (user && !syncedPhoneticMode.current) {
      syncedPhoneticMode.current = true;
      setPhoneticMapMode(user.phonetic_map);
    }
  }, [user]);

  async function changePhoneticMode(mode: PhoneticMapMode) {
    setPhoneticMapMode(mode);
    if (!user) return;
    try {
      const res = await patchMe({ phonetic_map: mode });
      setMe({ user: res.user, profile });
    } catch {
      // Keep the local change even if saving the preference fails.
    }
  }

  const [text, setText] = useState('');
  const [result, setResult] = useState<RewriteResponse | null>(null);
  const [showMarks, setShowMarks] = useState(true); // on by default here
  const [showOriginalInline, setShowOriginalInline] = useState(false);
  const [tripped, setTripped] = useState<Map<string, string>>(new Map());
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showPicker, setShowPicker] = useState(false);
  const [sample, setSample] = useState<SampleAttribution | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const loadedSampleParam = useRef<string | null>(null);

  async function loadSample(slug: string) {
    setBusy(true);
    setError(null);
    setSaved(false);
    setShowPicker(false);
    try {
      const res = await getSample(slug);
      setResult(res);
      setSample({ title: res.title, author: res.author, year: res.year, chapter: res.chapter, source: res.source });
      setTripped(new Map());
      setSearchParams({ sample: slug }, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not load that sample. Try again.');
    } finally {
      setBusy(false);
    }
  }

  // Deep link: /read?sample=<slug> loads that sample directly, once.
  useEffect(() => {
    const slug = searchParams.get('sample');
    if (slug && loadedSampleParam.current !== slug) {
      loadedSampleParam.current = slug;
      void loadSample(slug);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const res = await rewrite(text);
      setResult(res);
      setSample(null);
      setTripped(new Map());
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not rewrite that. Try again.');
    } finally {
      setBusy(false);
    }
  }

  function pasteSomethingElse() {
    setResult(null);
    setSample(null);
    setTripped(new Map());
    if (searchParams.has('sample')) setSearchParams({}, { replace: true });
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
          <PhoneticModeSelect value={phoneticMapMode} onChange={(m) => void changePhoneticMode(m)} />
          <ReadAloudButton paragraphs={paragraphTexts(result.segments)} />
          <span className="reader-toolbar__spacer" />
          <ReaderSettingsPanel stats={{ segments: result.segments, sentences: s.sentences, loadBefore: s.load_before, loadAfter: s.load_after }} />
          <button className="btn btn--plain btn--small" type="button" onClick={pasteSomethingElse}>
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
          phoneticMap={result.phonetic_map}
          phoneticMapMode={phoneticMapMode}
        />

        {sample && (
          <p className="muted sample-attribution">
            From <strong>{sample.title}</strong> by {sample.author}, {sample.year} — public
            domain, via{' '}
            <a href={sample.source} target="_blank" rel="noreferrer">
              Project Gutenberg
            </a>
            .
          </p>
        )}

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
        <div className="btn-row">
          <button className="btn btn--wide" type="submit" disabled={busy || !text.trim()}>
            {busy ? 'Rewriting…' : 'Rewrite it'}
          </button>
          <button
            className="btn btn--quiet"
            type="button"
            onClick={() => setShowPicker(true)}
            disabled={busy}
          >
            Show me an example
          </button>
        </div>
      </form>

      {showPicker && (
        <SamplePicker onPick={(slug) => void loadSample(slug)} onClose={() => setShowPicker(false)} />
      )}

      {!user && (
        <p className="muted">
          Not signed in, so we use the general profile. <Link to="/signin">Sign in</Link> for one
          built around you.
        </p>
      )}
    </main>
  );
}

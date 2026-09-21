import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Reader, { paragraphTexts } from '../components/Reader';
import ReadAloudButton from '../components/ReadAloudButton';
import PhoneticModeSelect from '../components/PhoneticModeSelect';
import SamplePicker from '../components/SamplePicker';
import DefineChip from '../components/DefineChip';
import SummaryPanel from '../components/SummaryPanel';
import {
  ApiError,
  getSample,
  importUrl,
  patchMe,
  postFeedback,
  rewrite,
  summariseText,
  type PhoneticMapMode,
  type RewriteResponse,
} from '../api';
import { useMe } from '../useMe';
import { getSpeechRecognitionCtor, speechRecognitionSupported, type SpeechRecognitionLike } from '../lib/dictation';

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
  // Bumped on every new result so <SummaryPanel key={resultVersion}> remounts instead of
  // showing a stale summary of whatever was read before.
  const [resultVersion, setResultVersion] = useState(0);
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
  const readerContainerRef = useRef<HTMLDivElement>(null);

  // "From a web page" (v0.6): a URL field beside the paste box that imports an article's text
  // straight into it -- the reader still hits Rewrite themselves once it's filled in.
  const [pasteTab, setPasteTab] = useState<'paste' | 'url'>('paste');
  const [importUrlValue, setImportUrlValue] = useState('');
  const [importing, setImporting] = useState(false);
  const [importNote, setImportNote] = useState<string | null>(null);

  async function submitImportUrl(e: FormEvent) {
    e.preventDefault();
    if (!importUrlValue.trim()) return;
    setImporting(true);
    setError(null);
    setImportNote(null);
    try {
      const res = await importUrl(importUrlValue.trim());
      setText(res.text.slice(0, MAX_CHARS));
      setImportNote(res.note);
      setPasteTab('paste');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not import that page.');
    } finally {
      setImporting(false);
    }
  }

  // Dictation (v0.6): free, in-browser speech-to-text into the paste box. Hidden entirely when
  // the browser has neither vendor's SpeechRecognition implementation.
  const [dictating, setDictating] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const dictationBaseRef = useRef('');

  useEffect(() => () => recognitionRef.current?.stop(), []);

  function startDictation() {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return;
    const recognition = new Ctor();
    recognition.lang = 'en-US';
    recognition.continuous = true;
    recognition.interimResults = true;
    dictationBaseRef.current = text;
    recognition.onresult = (event) => {
      let finalPiece = '';
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalPiece += piece;
        else interim += piece;
      }
      if (finalPiece) {
        dictationBaseRef.current = `${dictationBaseRef.current} ${finalPiece}`.trim();
      }
      const combined = interim ? `${dictationBaseRef.current} ${interim}` : dictationBaseRef.current;
      setText(combined.slice(0, MAX_CHARS));
    };
    recognition.onerror = () => setDictating(false);
    recognition.onend = () => setDictating(false);
    recognition.start();
    recognitionRef.current = recognition;
    setDictating(true);
  }

  function stopDictation() {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setDictating(false);
  }

  async function loadSample(slug: string) {
    setBusy(true);
    setError(null);
    setSaved(false);
    setShowPicker(false);
    try {
      const res = await getSample(slug);
      setResult(res);
      setResultVersion((v) => v + 1);
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
      setResultVersion((v) => v + 1);
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
          <button className="btn btn--plain btn--small" type="button" onClick={pasteSomethingElse}>
            Paste something else
          </button>
        </div>

        <p className="muted">
          {s.sentences_changed} of {s.sentences} sentences changed. {s.changes} word
          {s.changes === 1 ? '' : 's'} swapped. Reading load went from {Math.round(s.load_before)} to{' '}
          {Math.round(s.load_after)}.
        </p>

        <div ref={readerContainerRef}>
          <Reader
            segments={result.segments}
            showMarks={showMarks}
            showOriginalInline={showOriginalInline}
            tripped={new Set(tripped.keys())}
            onToggleWord={toggleWord}
            phoneticMap={result.phonetic_map}
            phoneticMapMode={phoneticMapMode}
          />
        </div>
        {/* Select any single word above (including a marked one) to define it -- v0.6. */}
        <DefineChip containerRef={readerContainerRef} />

        {user?.plan.pro && (
          <SummaryPanel
            key={resultVersion}
            isPro={user.plan.pro}
            fetchSummary={() => summariseText(paragraphTexts(result.segments).join('\n\n'))}
          />
        )}

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

      <div className="paste-tabs" role="tablist" aria-label="How to bring in text">
        <button type="button" role="tab" aria-selected={pasteTab === 'paste'} onClick={() => setPasteTab('paste')}>
          Paste text
        </button>
        <button type="button" role="tab" aria-selected={pasteTab === 'url'} onClick={() => setPasteTab('url')}>
          From a web page
        </button>
      </div>

      {pasteTab === 'url' && (
        <form onSubmit={submitImportUrl} className="stack">
          <div className="import-url-row">
            <label className="sr-only" htmlFor="import-url">
              Web page address
            </label>
            <input
              id="import-url"
              type="url"
              value={importUrlValue}
              onChange={(e) => setImportUrlValue(e.target.value)}
              placeholder="https://example.com/an-article"
              required
            />
            <button className="btn" type="submit" disabled={importing || !importUrlValue.trim()}>
              {importing ? 'Importing…' : 'Import'}
            </button>
          </div>
          <p className="muted">We fetch the page on our server and pull out just the article text.</p>
        </form>
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
          {importNote && <p className="notice">{importNote}</p>}
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
          {speechRecognitionSupported() && (
            <button
              className="btn btn--plain btn--small dictation-btn"
              type="button"
              aria-pressed={dictating}
              onClick={() => (dictating ? stopDictation() : startDictation())}
            >
              {dictating ? '⏹ Stop dictating' : '🎤 Dictate'}
            </button>
          )}
        </div>
        {speechRecognitionSupported() && (
          <p className="muted">Dictate speaks your words straight into the box; works best in a quiet room.</p>
        )}
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

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Reader, { paragraphTexts } from '../components/Reader';
import ReadAloudButton from '../components/ReadAloudButton';
import PhoneticModeSelect from '../components/PhoneticModeSelect';
import ReaderSettingsPanel from '../components/reader/ReaderSettingsPanel';
import DefineChip from '../components/DefineChip';
import SummaryPanel from '../components/SummaryPanel';
import {
  ApiError,
  getBook,
  getBookChapter,
  patchMe,
  summariseBookChapter,
  type Book,
  type BookChapterResponse,
  type PhoneticMapMode,
} from '../api';
import { useMe } from '../useMe';

function lastChapterKey(id: string): string {
  return `library:last-chapter:${id}`;
}

function readLastChapter(id: string): number {
  try {
    const raw = localStorage.getItem(lastChapterKey(id));
    const n = raw ? parseInt(raw, 10) : 0;
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

function saveLastChapter(id: string, chapter: number): void {
  try {
    localStorage.setItem(lastChapterKey(id), String(chapter));
  } catch {
    // Private browsing / blocked storage: not remembering the chapter is fine.
  }
}

export default function BookReader() {
  const { id } = useParams<{ id: string }>();
  const { user, profile, setMe } = useMe();

  const [book, setBook] = useState<Book | null>(null);
  const [chapter, setChapter] = useState(0);
  const [data, setData] = useState<BookChapterResponse | null>(null);
  const [tripped, setTripped] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [phoneticMapMode, setPhoneticMapMode] = useState<PhoneticMapMode>(user?.phonetic_map ?? 'on_demand');
  const readerContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (user) setPhoneticMapMode(user.phonetic_map);
  }, [user]);

  const loadChapter = useCallback(async (bookId: string, ch: number) => {
    setBusy(true);
    setError(null);
    try {
      const res = await getBookChapter(bookId, ch);
      setData(res);
      setChapter(ch);
      setTripped(new Set());
      saveLastChapter(bookId, ch);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not load that chapter.');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      setBusy(true);
      setError(null);
      try {
        const b = await getBook(id);
        if (cancelled) return;
        setBook(b);
        if (b.status !== 'ready') {
          setError(
            b.status === 'failed'
              ? b.error || 'This book failed to process.'
              : 'This book is still being rewritten — check back soon.',
          );
          setBusy(false);
          return;
        }
        await loadChapter(id, readLastChapter(id));
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.isUnauthorized) return;
        setError(err instanceof ApiError ? err.message : 'We could not open that book.');
        setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, loadChapter]);

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

  function toggleWord(wordId: string): void {
    setTripped((prev) => {
      const next = new Set(prev);
      if (next.has(wordId)) next.delete(wordId);
      else next.add(wordId);
      return next;
    });
  }

  if (!id) return null;

  return (
    <main className="page stack" id="main">
      <p>
        <Link to="/library">&larr; Back to your library</Link>
      </p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {book && <h1>{book.title}</h1>}

      {data && (
        <>
          <div className="reader-toolbar">
            <label className="label" htmlFor="chapter-picker" style={{ margin: 0 }}>
              Chapter
            </label>
            <select
              id="chapter-picker"
              value={chapter}
              disabled={busy}
              onChange={(e) => void loadChapter(id, Number(e.target.value))}
            >
              {Array.from({ length: data.chapters }, (_, i) => i).map((i) => (
                <option key={i} value={i}>
                  {i + 1}. {i === chapter ? data.title : `Chapter ${i + 1}`}
                </option>
              ))}
            </select>
            <PhoneticModeSelect value={phoneticMapMode} onChange={(m) => void changePhoneticMode(m)} />
            <ReadAloudButton paragraphs={paragraphTexts(data.segments)} />
            <ReaderSettingsPanel stats={{ segments: data.segments }} />
            <span className="reader-toolbar__spacer" />
            <button
              className="btn btn--plain btn--small"
              type="button"
              disabled={chapter <= 0 || busy}
              onClick={() => void loadChapter(id, chapter - 1)}
            >
              Previous
            </button>
            <button
              className="btn btn--plain btn--small"
              type="button"
              disabled={chapter >= data.chapters - 1 || busy}
              onClick={() => void loadChapter(id, chapter + 1)}
            >
              Next
            </button>
          </div>

          <div ref={readerContainerRef}>
            <Reader
              segments={data.segments}
              showMarks
              tripped={tripped}
              onToggleWord={toggleWord}
              phoneticMap={data.phonetic_map}
              phoneticMapMode={phoneticMapMode}
            />
          </div>
          {/* Select any single word above (including a marked one) to define it -- v0.6. */}
          <DefineChip containerRef={readerContainerRef} />

          <SummaryPanel
            key={chapter}
            isPro={!!user?.plan.pro}
            fetchSummary={() => summariseBookChapter(id, chapter)}
          />
        </>
      )}

      {busy && !data && <p className="muted">Loading…</p>}
    </main>
  );
}

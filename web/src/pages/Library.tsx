import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  deleteBook,
  downloadBookUrl,
  getBooks,
  patchMe,
  rerunBook,
  sendToKindle,
  uploadBook,
  type Book,
} from '../api';
import { useMe } from '../useMe';
import FeedbackPrompt from '../components/FeedbackPrompt';

const POLL_MS = 3000;

const STATUS_LABEL: Record<Book['status'], string> = {
  queued: 'Queued…',
  processing: 'Rewriting…',
  ready: 'Ready',
  failed: 'Failed',
};

/** "Add your Kindle email first" comes back as a 400 with this phrase; used to show the prompt
 * inline instead of a generic error banner. */
function needsKindleEmail(err: unknown): boolean {
  return err instanceof ApiError && err.status === 400 && /kindle email/i.test(err.message);
}

export default function Library() {
  const { user } = useMe();
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quotaNotice, setQuotaNotice] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [kindlePromptFor, setKindlePromptFor] = useState<string | null>(null);
  const [kindleEmailInput, setKindleEmailInput] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  // Tracks each book's last-seen status so a fresh queued/processing -> ready transition (a
  // conversion finishing) can trigger the one-line "did that read easier?" prompt below —
  // never for a book that was already ready the first time we saw it.
  const prevStatuses = useRef<Record<string, Book['status']>>({});
  const [justReady, setJustReady] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const res = await getBooks();
      setBooks(res);
      const newlyReady = new Set<string>();
      for (const b of res) {
        const prev = prevStatuses.current[b.id];
        if (b.status === 'ready' && prev && prev !== 'ready') newlyReady.add(b.id);
        prevStatuses.current[b.id] = b.status;
      }
      if (newlyReady.size > 0) {
        setJustReady((current) => new Set([...current, ...newlyReady]));
      }
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not load your library.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll every 3s while anything is still queued or being rewritten.
  useEffect(() => {
    if (!books.some((b) => b.status === 'queued' || b.status === 'processing')) return;
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [books, load]);

  async function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setQuotaNotice(null);
    try {
      const book = await uploadBook({ file });
      setBooks((prev) => [book, ...prev]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setQuotaNotice(err.message);
      } else if (!(err instanceof ApiError && err.isUnauthorized)) {
        setError(err instanceof ApiError ? err.message : 'We could not upload that file.');
      }
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    void handleFiles(e.dataTransfer.files);
  }

  async function doKindle(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await sendToKindle(id);
      setKindlePromptFor(null);
      await load();
    } catch (err) {
      if (needsKindleEmail(err)) {
        setKindlePromptFor(id);
      } else if (err instanceof ApiError && err.status === 402) {
        setQuotaNotice(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : 'We could not send that to your Kindle.');
      }
    } finally {
      setBusyId(null);
    }
  }

  async function saveKindleEmailAndSend() {
    const id = kindlePromptFor;
    if (!id) return;
    setBusyId(id);
    setError(null);
    try {
      await patchMe({ kindle_email: kindleEmailInput.trim() });
      setKindlePromptFor(null);
      setKindleEmailInput('');
      await doKindle(id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not save that email address.');
      setBusyId(null);
    }
  }

  async function doRerun(id: string) {
    setBusyId(id);
    setError(null);
    try {
      const updated = await rerunBook(id);
      setBooks((prev) => prev.map((b) => (b.id === id ? updated : b)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setQuotaNotice(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : 'We could not re-run that book.');
      }
    } finally {
      setBusyId(null);
    }
  }

  async function doDelete(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await deleteBook(id);
      setBooks((prev) => prev.filter((b) => b.id !== id));
      setConfirmDelete(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not delete that book.');
    } finally {
      setBusyId(null);
    }
  }

  if (!user) return null;

  return (
    <main className="page stack" id="main">
      <h1>Your library</h1>
      <p>Upload a book. We rewrite it chapter by chapter — read it here, or send it to your Kindle.</p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {quotaNotice && (
        <p className="notice">
          <span>{quotaNotice} </span>
          <Link to="/pricing">See Unwind Words Pro</Link>
        </p>
      )}

      <div
        className={`upload-drop${dragOver ? ' upload-drop--over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <p>Drag a book here, or</p>
        <label className="btn btn--quiet">
          Choose a file
          <input
            ref={fileInput}
            type="file"
            accept=".epub,.txt,.md,.pdf,.docx"
            style={{ display: 'none' }}
            disabled={uploading}
            onChange={(e) => void handleFiles(e.target.files)}
          />
        </label>
        <p className="muted">
          .epub, .txt, .md, .pdf, or .docx, up to 25 MB. Your first book is free;{' '}
          <Link to="/pricing">Pro for unlimited</Link>. A scanned PDF (no selectable text) can&rsquo;t be
          read yet — OCR isn&rsquo;t supported.
        </p>
        {uploading && <p className="muted">Uploading…</p>}
      </div>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : books.length === 0 ? (
        <p className="muted">No books yet — upload your first one above.</p>
      ) : (
        <ul className="book-list">
          {books.map((b) => {
            const busy = busyId === b.id;
            const pct = b.chapters ? Math.round((b.progress / b.chapters) * 100) : 0;
            return (
              <li className="book-card" key={b.id}>
                <div className="book-card__head">
                  <h2>{b.title}</h2>
                  <span className={`book-status book-status--${b.status}`}>{STATUS_LABEL[b.status]}</span>
                </div>
                {b.author && <p className="muted">{b.author}</p>}
                {(b.status === 'queued' || b.status === 'processing') && (
                  <div
                    className="progress-bar"
                    role="progressbar"
                    aria-valuenow={b.progress}
                    aria-valuemin={0}
                    aria-valuemax={b.chapters || 1}
                    aria-label={`Rewriting ${b.title}`}
                  >
                    <div className="progress-bar__fill" style={{ width: `${pct}%` }} />
                  </div>
                )}
                {b.status === 'failed' && <p className="error">{b.error || 'Something went wrong.'}</p>}
                <p className="muted">
                  {b.words.toLocaleString()} words · {b.chapters || '?'} chapters
                </p>

                {justReady.has(b.id) && (
                  <FeedbackPrompt
                    storageKey={`feedback-book-${b.id}`}
                    context={{ book_id: b.id }}
                    page="/library"
                  />
                )}

                {kindlePromptFor === b.id && (
                  <div className="stack card">
                    <label htmlFor={`kindle-${b.id}`}>Your Kindle email address</label>
                    <input
                      id={`kindle-${b.id}`}
                      type="email"
                      value={kindleEmailInput}
                      onChange={(e) => setKindleEmailInput(e.target.value)}
                      placeholder="yourname@kindle.com"
                    />
                    <p className="muted">
                      Add this address to Amazon&rsquo;s Approved Personal Document E-mail List first
                      (Manage Your Content and Devices &gt; Preferences &gt; Personal Document Settings),
                      or the book won&rsquo;t arrive.
                    </p>
                    <div className="btn-row">
                      <button
                        className="btn btn--small"
                        type="button"
                        onClick={() => void saveKindleEmailAndSend()}
                        disabled={busy || !kindleEmailInput.trim()}
                      >
                        Save and send
                      </button>
                      <button
                        className="btn btn--plain btn--small"
                        type="button"
                        onClick={() => setKindlePromptFor(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {confirmDelete === b.id ? (
                  <div className="btn-row">
                    <span>Delete this book?</span>
                    <button
                      className="btn btn--danger btn--small"
                      type="button"
                      onClick={() => void doDelete(b.id)}
                      disabled={busy}
                    >
                      Yes, delete
                    </button>
                    <button
                      className="btn btn--plain btn--small"
                      type="button"
                      onClick={() => setConfirmDelete(null)}
                    >
                      Keep it
                    </button>
                  </div>
                ) : (
                  <div className="btn-row">
                    {b.status === 'ready' && (
                      <>
                        <Link className="btn btn--small" to={`/library/${b.id}`}>
                          Read
                        </Link>
                        <a className="btn btn--plain btn--small" href={downloadBookUrl(b.id)}>
                          Download EPUB
                        </a>
                        <button
                          className="btn btn--plain btn--small"
                          type="button"
                          onClick={() => void doKindle(b.id)}
                          disabled={busy}
                        >
                          Send to Kindle
                        </button>
                        <button
                          className="btn btn--plain btn--small"
                          type="button"
                          onClick={() => void doRerun(b.id)}
                          disabled={busy}
                        >
                          Re-run with my profile
                        </button>
                      </>
                    )}
                    <button
                      className="btn btn--danger btn--small"
                      type="button"
                      onClick={() => setConfirmDelete(b.id)}
                      disabled={busy}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

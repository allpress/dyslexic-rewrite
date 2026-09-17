import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import {
  ApiError,
  deleteRecording,
  getReadAloudPrompts,
  getRecordings,
  recordingAudioUrl,
  uploadRecording,
  type Prompt,
  type Recording,
  type RecordingKind,
} from '../api';

const MAX_SECONDS = 15 * 60; // the server's own limit; we stop before we hit it

export const STATUS_LABEL: Record<Recording['status'], string> = {
  pending_analysis: 'Waiting to be looked at',
  analyzing: 'Being looked at',
  analyzed: 'Done',
  failed: 'Something went wrong',
};

const MIME_CANDIDATES = ['audio/webm', 'audio/mp4', 'audio/ogg'];

function pickMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return null;
  for (const candidate of MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(candidate)) return candidate;
  }
  return null;
}

function extFor(mime: string): string {
  if (mime.includes('webm')) return 'webm';
  if (mime.includes('ogg')) return 'ogg';
  if (mime.includes('mp4') || mime.includes('m4a')) return 'm4a';
  if (mime.includes('wav')) return 'wav';
  return 'audio';
}

function formatTime(totalSeconds: number): string {
  const clamped = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(clamped / 60);
  const s = clamped % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

/** Read the duration of a blob by loading it into a throwaway <audio> element. */
function readDuration(url: string): Promise<number | null> {
  return new Promise((resolve) => {
    const audio = new Audio();
    const done = (value: number | null) => {
      audio.removeAttribute('src');
      resolve(value);
    };
    audio.addEventListener('loadedmetadata', () => {
      done(Number.isFinite(audio.duration) ? audio.duration : null);
    });
    audio.addEventListener('error', () => done(null));
    audio.src = url;
  });
}

type PendingClip = {
  blob: Blob;
  url: string;
  filename: string;
  seconds: number | null;
  source: 'recorded' | 'file';
};

type Phase = 'setup' | 'recording' | 'review' | 'uploading' | 'saved';

export default function Record() {
  const supportsRecording =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    typeof MediaRecorder !== 'undefined';

  const [prompts, setPrompts] = useState<Prompt[] | null>(null);
  const [promptsError, setPromptsError] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<RecordingKind>('read_aloud');
  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null);

  const [phase, setPhase] = useState<Phase>('setup');
  const [micError, setMicError] = useState<string | null>(null);
  const [autoStopped, setAutoStopped] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [pending, setPending] = useState<PendingClip | null>(null);
  const [uploadFraction, setUploadFraction] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [recordings, setRecordings] = useState<Recording[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef<number>(0);
  const mimeTypeRef = useRef<string>('audio/webm');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    getReadAloudPrompts()
      .then((res) => {
        if (!cancelled) setPrompts(res);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.isUnauthorized) return;
        setPromptsError(
          err instanceof ApiError ? err.message : 'We could not load the prompts. Try again.',
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadRecordings = useCallback(() => {
    getRecordings()
      .then((res) => setRecordings(res.recordings))
      .catch((err) => {
        if (err instanceof ApiError && err.isUnauthorized) return;
        setListError(err instanceof ApiError ? err.message : 'We could not load your recordings.');
      });
  }, []);

  useEffect(() => {
    loadRecordings();
  }, [loadRecordings]);

  const stopLevelMeter = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    setLevel(0);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  // Clean up on unmount so a left recorder does not keep the mic hot.
  useEffect(() => {
    return () => {
      stopTimer();
      stopLevelMeter();
      stopStream();
      if (pending) URL.revokeObjectURL(pending.url);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function friendlyMicError(err: unknown): string {
    const name = err instanceof DOMException ? err.name : '';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      return 'We do not have permission to use your microphone. Allow microphone access for this site in your browser, then try again — or upload a file instead.';
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      return 'We could not find a microphone on this device. You can upload a file instead.';
    }
    return 'We could not start recording. You can upload a file instead.';
  }

  async function startRecording() {
    setMicError(null);
    setAutoStopped(false);
    setUploadError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mime = pickMimeType();
      mimeTypeRef.current = mime ?? 'audio/webm';
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeTypeRef.current });
        const url = URL.createObjectURL(blob);
        const seconds = Math.round((Date.now() - startedAtRef.current) / 1000);
        setPending({
          blob,
          url,
          filename: `recording.${extFor(mimeTypeRef.current)}`,
          seconds,
          source: 'recorded',
        });
        setPhase('review');
        stopStream();
        stopLevelMeter();
        stopTimer();
      };

      mediaRecorderRef.current = recorder;
      startedAtRef.current = Date.now();
      recorder.start();
      setPhase('recording');
      setElapsed(0);

      timerRef.current = setInterval(() => {
        const secs = Math.round((Date.now() - startedAtRef.current) / 1000);
        setElapsed(secs);
        if (secs >= MAX_SECONDS) {
          setAutoStopped(true);
          mediaRecorderRef.current?.stop();
        }
      }, 250);

      // Level meter, best effort — recording still works fine without it.
      try {
        const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (AudioCtx) {
          const ctx = new AudioCtx();
          audioCtxRef.current = ctx;
          const source = ctx.createMediaStreamSource(stream);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 256;
          source.connect(analyser);
          const data = new Uint8Array(analyser.frequencyBinCount);
          const tick = () => {
            analyser.getByteFrequencyData(data);
            const avg = data.reduce((a, b) => a + b, 0) / data.length;
            setLevel(avg / 255);
            rafRef.current = requestAnimationFrame(tick);
          };
          tick();
        }
      } catch {
        // no level meter, that is fine
      }
    } catch (err) {
      setMicError(friendlyMicError(err));
      stopStream();
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
  }

  function discardPending() {
    if (pending) URL.revokeObjectURL(pending.url);
    setPending(null);
    setUploadError(null);
  }

  function recordAgain() {
    discardPending();
    setPhase('setup');
    void startRecording();
  }

  function deletePending() {
    discardPending();
    setPhase('setup');
  }

  async function onFileChosen(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const url = URL.createObjectURL(file);
    const seconds = await readDuration(url);
    setPending({ blob: file, url, filename: file.name, seconds, source: 'file' });
    setPhase('review');
  }

  async function useThisOne() {
    if (!pending) return;
    setPhase('uploading');
    setUploadFraction(0);
    setUploadError(null);
    try {
      await uploadRecording(
        {
          file: pending.blob,
          filename: pending.filename,
          kind: activeKind,
          prompt_id: selectedPromptId ?? undefined,
          seconds: pending.seconds ?? undefined,
        },
        (fraction) => setUploadFraction(fraction),
      );
      URL.revokeObjectURL(pending.url);
      setPending(null);
      setPhase('saved');
      loadRecordings();
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err.message : 'The upload failed. Check your connection and try again.',
      );
      setPhase('review');
    }
  }

  function recordAnother() {
    setPhase('setup');
    setSelectedPromptId(null);
    setAutoStopped(false);
  }

  async function confirmDelete(id: string) {
    setDeleteBusy(true);
    try {
      await deleteRecording(id);
      setRecordings((prev) => prev?.filter((r) => r.id !== id) ?? null);
      setConfirmingDeleteId(null);
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : 'We could not delete that recording.');
    } finally {
      setDeleteBusy(false);
    }
  }

  const readAloudPrompts = (prompts ?? []).filter((p) => p.kind === 'read_aloud');
  const freeSpeechPrompts = (prompts ?? []).filter((p) => p.kind === 'free_speech');
  const visiblePrompts = activeKind === 'read_aloud' ? readAloudPrompts : freeSpeechPrompts;
  const selectedPrompt = (prompts ?? []).find((p) => p.id === selectedPromptId) ?? null;

  return (
    <main className="page stack" id="main">
      <h1>Record your voice</h1>
      <p>
        People speak more naturally than they write. A short recording helps us understand how you
        put words together. <strong>We do not analyse it here.</strong> It is saved, marked as
        waiting to be looked at, and you can play it back or delete it whenever you like.
      </p>

      {phase === 'saved' && (
        <div className="notice stack">
          <p>
            <strong>Saved.</strong> Nobody has listened to it yet — it is waiting to be looked at.
            You can play it back or delete it any time in the list below.
          </p>
          <button className="btn" type="button" onClick={recordAnother}>
            Record another
          </button>
        </div>
      )}

      {phase !== 'saved' && (
        <div className="stack">
          {promptsError && (
            <p className="error" role="alert">
              {promptsError}
            </p>
          )}

          <div className="record-tabs" role="tablist" aria-label="How do you want to give a sample?">
            <button
              type="button"
              role="tab"
              aria-selected={activeKind === 'read_aloud'}
              className="record-tab"
              onClick={() => {
                setActiveKind('read_aloud');
                setSelectedPromptId(null);
              }}
              disabled={phase === 'recording' || phase === 'review' || phase === 'uploading'}
            >
              Read this out loud
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeKind === 'free_speech'}
              className="record-tab"
              onClick={() => {
                setActiveKind('free_speech');
                setSelectedPromptId(null);
              }}
              disabled={phase === 'recording' || phase === 'review' || phase === 'uploading'}
            >
              Answer in your own words
            </button>
          </div>

          {prompts === null && !promptsError && <p className="muted">Loading prompts…</p>}

          {prompts !== null && (
            <div className="stack">
              <div className="choices" role="radiogroup" aria-label="Pick a prompt">
                {visiblePrompts.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    role="radio"
                    aria-checked={selectedPromptId === p.id}
                    className="choice"
                    disabled={phase === 'recording' || phase === 'review' || phase === 'uploading'}
                    onClick={() => setSelectedPromptId(p.id)}
                  >
                    <span className="choice__title">{p.title}</span>
                    {p.kind === 'free_speech' && <span className="choice__sub">{p.text}</span>}
                  </button>
                ))}
                {visiblePrompts.length === 0 && (
                  <p className="muted">No prompts to show right now.</p>
                )}
              </div>

              {selectedPrompt && selectedPrompt.kind === 'read_aloud' && (
                <div className="record-passage" aria-label="Passage to read aloud">
                  {selectedPrompt.text}
                </div>
              )}
            </div>
          )}

          {micError && (
            <p className="error" role="alert">
              {micError}
            </p>
          )}

          {(phase === 'setup' || phase === 'recording') && supportsRecording && (
            <div className="record-stage">
              {phase === 'setup' && (
                <button className="record-button" type="button" onClick={() => void startRecording()}>
                  Record
                </button>
              )}
              {phase === 'recording' && (
                <>
                  <button
                    className="record-button record-button--active"
                    type="button"
                    onClick={stopRecording}
                  >
                    Stop
                  </button>
                  <p className="record-timer" aria-live="polite">
                    {formatTime(elapsed)}
                  </p>
                  <div className="level-meter" aria-hidden="true">
                    <div className="level-meter__track">
                      <div className="level-meter__fill" style={{ width: `${Math.round(level * 100)}%` }} />
                    </div>
                  </div>
                  <p className="sr-only" aria-live="polite">
                    Recording, {formatTime(elapsed)} so far.
                  </p>
                </>
              )}
            </div>
          )}

          {!supportsRecording && (
            <p className="muted">
              Recording is not available in this browser. Use the file upload below instead.
            </p>
          )}

          {autoStopped && (
            <p className="muted">We stopped the recording automatically at 15 minutes.</p>
          )}

          {phase === 'review' && pending && (
            <div className="stack">
              <h2>Have a listen</h2>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <audio controls src={pending.url} style={{ width: '100%' }} />
              {uploadError && (
                <p className="error" role="alert">
                  {uploadError}
                </p>
              )}
              <div className="btn-row">
                <button className="btn" type="button" onClick={() => void useThisOne()}>
                  Use this one
                </button>
                {pending.source === 'recorded' ? (
                  <button className="btn btn--plain" type="button" onClick={recordAgain}>
                    Record again
                  </button>
                ) : (
                  <button
                    className="btn btn--plain"
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Choose a different file
                  </button>
                )}
                <button className="btn btn--danger" type="button" onClick={deletePending}>
                  Delete
                </button>
              </div>
            </div>
          )}

          {phase === 'uploading' && (
            <p className="muted" aria-live="polite">
              Sending… {Math.round(uploadFraction * 100)}%
            </p>
          )}

          {(phase === 'setup' || phase === 'review') && (
            <div className="stack">
              <label htmlFor="voice-file">Or upload a file instead</label>
              <input
                id="voice-file"
                ref={fileInputRef}
                type="file"
                accept="audio/*"
                onChange={(e) => void onFileChosen(e)}
              />
              <p className="muted">
                Already have a recording — from your phone&rsquo;s voice memo app, say? Upload it
                here instead of recording again.
              </p>
            </div>
          )}
        </div>
      )}

      <section className="stack" aria-labelledby="recordings-heading">
        <h2 id="recordings-heading">Your recordings</h2>
        {listError && (
          <p className="error" role="alert">
            {listError}
          </p>
        )}
        {recordings === null && !listError && <p className="muted">Loading…</p>}
        {recordings !== null && recordings.length === 0 && (
          <p className="muted">Nothing yet. Record or upload a sample above.</p>
        )}
        {recordings !== null && recordings.length > 0 && (
          <ul className="test-list">
            {recordings.map((r) => (
              <li className="card stack" key={r.id}>
                <div className="bar__head">
                  <span>{r.prompt_title ?? (r.kind === 'read_aloud' ? 'Read aloud' : 'Free response')}</span>
                  <span className="muted">{formatWhen(r.created_at)}</span>
                </div>
                <p className="muted" style={{ margin: 0 }}>
                  {r.seconds !== null ? `${formatTime(r.seconds)} long. ` : ''}
                  Status: {STATUS_LABEL[r.status]}
                  {r.status === 'failed' && r.note ? ` — ${r.note}` : ''}
                </p>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <audio controls src={recordingAudioUrl(r.id)} style={{ width: '100%' }} />
                {confirmingDeleteId === r.id ? (
                  <div className="btn-row">
                    <button
                      className="btn btn--danger"
                      type="button"
                      disabled={deleteBusy}
                      onClick={() => void confirmDelete(r.id)}
                    >
                      Yes, delete it
                    </button>
                    <button
                      className="btn"
                      type="button"
                      disabled={deleteBusy}
                      onClick={() => setConfirmingDeleteId(null)}
                    >
                      Keep it
                    </button>
                  </div>
                ) : (
                  <button
                    className="btn btn--danger btn--small"
                    type="button"
                    onClick={() => setConfirmingDeleteId(r.id)}
                  >
                    Delete
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

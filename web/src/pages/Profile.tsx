import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ApiError,
  deleteMe,
  patchMe,
  postTriggers,
  type BaseProfile,
} from '../api';
import { useMe } from '../useMe';

const PROFILE_LABELS: Record<BaseProfile, string> = {
  default: 'Not sure / a bit of everything',
  phonological: 'Words that sound alike blur together',
  visual: 'Letters and words move or crowd on the page',
  attention: 'Long sentences lose me halfway through',
};

export default function Profile() {
  const navigate = useNavigate();
  const { user, profile, setMe, setProfile } = useMe();

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  if (!user) return null;

  async function changeBase(value: BaseProfile) {
    setBusy(true);
    setError(null);
    try {
      const res = await patchMe({ base_profile: value });
      setMe({ user: res.user, profile });
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not change that.');
    } finally {
      setBusy(false);
    }
  }

  async function removeTrigger(word: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await postTriggers({ remove: [word] });
      setProfile(res.profile);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not remove that word.');
    } finally {
      setBusy(false);
    }
  }

  async function reallyDelete() {
    setBusy(true);
    setError(null);
    try {
      await deleteMe();
      setMe(null);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not delete your account.');
      setBusy(false);
    }
  }

  const style = profile?.style;

  return (
    <main className="page stack" id="main">
      <h1>{user.name ? `Hello, ${user.name}` : 'Your profile'}</h1>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="stack" aria-labelledby="kind-heading">
        <h2 id="kind-heading">Which sounds most like you?</h2>
        <div className="choices" role="radiogroup" aria-labelledby="kind-heading">
          {(Object.keys(PROFILE_LABELS) as BaseProfile[]).map((key) => (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={user.base_profile === key}
              className="choice"
              disabled={busy}
              onClick={() => void changeBase(key)}
            >
              <span className="choice__title">{PROFILE_LABELS[key]}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="stack" aria-labelledby="trig-heading">
        <h2 id="trig-heading">Words that trip you up</h2>
        {profile && profile.trigger_words.length > 0 ? (
          <ul className="pill-list">
            {profile.trigger_words.map((w) => (
              <li className="pill" key={w}>
                <span>{w}</span>
                <button
                  type="button"
                  disabled={busy}
                  aria-label={`Remove ${w}`}
                  onClick={() => void removeTrigger(w)}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">None yet. Tap words during a reading test to add them.</p>
        )}
      </section>

      <section className="stack" aria-labelledby="safe-heading">
        <h2 id="safe-heading">Words that are fine</h2>
        {profile && profile.safe_words.length > 0 ? (
          <ul className="pill-list">
            {profile.safe_words.map((w) => (
              <li className="pill" key={w}>
                {w}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">None yet.</p>
        )}
      </section>

      <section className="stack" aria-labelledby="style-heading">
        <h2 id="style-heading">How you write</h2>
        {profile && style ? (
          <dl className="facts">
            <div>
              <dt>Words you know</dt>
              <dd>{profile.vocabulary_size}</dd>
            </div>
            <div>
              <dt>Your usual sentence</dt>
              <dd>{Math.round(style.median_sentence_words)} words</dd>
            </div>
            <div>
              <dt>Your longer sentences</dt>
              <dd>{Math.round(style.p75_sentence_words)} words</dd>
            </div>
            <div>
              <dt>We keep rewrites under</dt>
              <dd>{profile.max_sentence_words} words</dd>
            </div>
            <div>
              <dt>Sample we measured</dt>
              <dd>{style.sample_words} words</dd>
            </div>
          </dl>
        ) : (
          <p className="muted">
            We have not measured your writing yet. Take a reading test, or paste a writing sample
            during setup.
          </p>
        )}
      </section>

      <section className="stack" aria-labelledby="danger-heading">
        <h2 id="danger-heading">Delete everything</h2>
        {confirming ? (
          <div className="stack">
            <p className="error">
              This removes your account, your profile, and every test you have taken. It cannot be
              undone.
            </p>
            <div className="btn-row">
              <button className="btn btn--danger" type="button" onClick={reallyDelete} disabled={busy}>
                Yes, delete it all
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => setConfirming(false)}
                disabled={busy}
              >
                Keep my account
              </button>
            </div>
          </div>
        ) : (
          <button className="btn btn--danger" type="button" onClick={() => setConfirming(true)}>
            Delete my account and all my data
          </button>
        )}
      </section>
    </main>
  );
}

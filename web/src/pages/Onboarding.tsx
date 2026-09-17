import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, patchMe, postWritingSample, type BaseProfile, type ProfileSummary } from '../api';
import { useMe } from '../useMe';

const PROFILES: { value: BaseProfile; title: string; sub: string }[] = [
  {
    value: 'default',
    title: 'Not sure / a bit of everything',
    sub: 'Pick this if none of the others fit. You can change it later.',
  },
  {
    value: 'phonological',
    title: 'Words that sound alike blur together',
    sub: 'You read one word and mean another. Sounding out is slow work.',
  },
  {
    value: 'visual',
    title: 'Letters and words move or crowd on the page',
    sub: 'Lines swim. You lose your place. Dense text is hard.',
  },
  {
    value: 'attention',
    title: 'Long sentences lose me halfway through',
    sub: 'You reach the end and have to start over.',
  },
];

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

export default function Onboarding() {
  const navigate = useNavigate();
  const { user, setProfile, refresh } = useMe();

  const [step, setStep] = useState(1);
  const [name, setName] = useState(user?.name ?? '');
  const [base, setBase] = useState<BaseProfile>(user?.base_profile ?? 'default');
  const [sample, setSample] = useState('');
  const [summary, setSummary] = useState<ProfileSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const words = countWords(sample);

  function fail(err: unknown, fallback: string) {
    setError(err instanceof ApiError ? err.message : fallback);
  }

  async function saveName(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await patchMe({ name: name.trim() });
      setStep(2);
    } catch (err) {
      fail(err, 'We could not save your name. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile() {
    setBusy(true);
    setError(null);
    try {
      await patchMe({ base_profile: base });
      setStep(3);
    } catch (err) {
      fail(err, 'We could not save that. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function sendSample(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await postWritingSample(sample);
      setProfile(res.profile);
      setSummary(res.profile);
      setSample(''); // the text is gone from here too
      setStep(4);
    } catch (err) {
      fail(err, 'We could not read that sample. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      await patchMe({ onboarded: true });
      await refresh();
      navigate('/test', { replace: true });
    } catch (err) {
      fail(err, 'We could not finish setting up. Try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page page--narrow stack" id="main">
      <p className="progress">Step {Math.min(step, 3)} of 3</p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {step === 1 && (
        <form onSubmit={saveName} className="stack">
          <h1>What should we call you?</h1>
          <div>
            <label htmlFor="name">Your first name</label>
            <input
              id="name"
              name="name"
              type="text"
              autoComplete="given-name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <button className="btn btn--wide" type="submit" disabled={busy || !name.trim()}>
            Next
          </button>
        </form>
      )}

      {step === 2 && (
        <div className="stack">
          <h1>Which sounds most like you?</h1>
          <div className="choices" role="radiogroup" aria-label="Which sounds most like you?">
            {PROFILES.map((p) => (
              <button
                key={p.value}
                type="button"
                role="radio"
                aria-checked={base === p.value}
                className="choice"
                onClick={() => setBase(p.value)}
              >
                <span className="choice__title">{p.title}</span>
                <span className="choice__sub">{p.sub}</span>
              </button>
            ))}
          </div>
          <button className="btn btn--wide" type="button" onClick={saveProfile} disabled={busy}>
            Next
          </button>
        </div>
      )}

      {step === 3 && (
        <form onSubmit={sendSample} className="stack">
          <h1>Paste some of your own writing</h1>
          <p>
            Emails, messages, posts — anything you wrote. About 150 words is enough. This step is
            optional.
          </p>
          <div className="notice">
            <p>
              We measure how you write — sentence length, the words you reach for — and keep only
              those numbers. The text itself is thrown away the moment we are done.
            </p>
          </div>
          <div>
            <label htmlFor="sample">Your writing</label>
            <textarea
              id="sample"
              name="sample"
              value={sample}
              onChange={(e) => setSample(e.target.value)}
              placeholder="Paste here…"
            />
            <p className="muted" aria-live="polite">
              {words} word{words === 1 ? '' : 's'}
              {words < 150 ? ` — ${150 - words} more to go` : ' — that is enough'}
            </p>
          </div>
          <button className="btn btn--wide" type="submit" disabled={busy || words < 150}>
            {busy ? 'Reading…' : 'Use this sample'}
          </button>
          <button className="btn btn--plain btn--small" type="button" onClick={finish} disabled={busy}>
            Skip this step
          </button>
        </form>
      )}

      {step === 4 && (
        <div className="stack">
          <h1>Here is how you write</h1>
          {summary && <StyleSummary profile={summary} />}
          <p className="muted">Your sample is gone. Only the numbers above were kept.</p>
          <button className="btn btn--wide" type="button" onClick={finish} disabled={busy}>
            Start my reading test
          </button>
        </div>
      )}
    </main>
  );
}

function StyleSummary({ profile }: { profile: ProfileSummary }) {
  const s = profile.style;
  const lines: string[] = [];

  lines.push(`Your middle-sized sentence is about ${Math.round(s.median_sentence_words)} words long.`);
  lines.push(`Your longer ones run to about ${Math.round(s.p75_sentence_words)} words.`);

  const passive = Math.round(s.passive_rate * 100);
  if (passive <= 2) lines.push('You almost always say who did what. That is good for reading.');
  else lines.push(`About ${passive} sentences in 100 hide who did the thing.`);

  if (s.clause_depth < 1.3) lines.push('You keep one idea per sentence.');
  else lines.push('Your sentences often carry an idea inside another idea.');

  lines.push(`You used ${s.sample_words} words in the sample, and ${profile.vocabulary_size} different ones.`);

  return (
    <div className="card stack">
      {lines.map((line) => (
        <p key={line} style={{ margin: 0 }}>
          {line}
        </p>
      ))}
      <p className="muted" style={{ margin: 0 }}>
        We will keep your rewrites at about {profile.max_sentence_words} words a sentence.
      </p>
    </div>
  );
}

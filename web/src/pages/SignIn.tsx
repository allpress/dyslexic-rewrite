import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, requestCode, verifyCode } from '../api';
import { useMe } from '../useMe';

type Step = 'email' | 'code';

export default function SignIn() {
  const navigate = useNavigate();
  const { setMe, refresh } = useMe();

  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [devCode, setDevCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sendCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await requestCode(email.trim());
      setDevCode(res.dev_code ?? null);
      setStep('code');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not send the code. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { user } = await verifyCode(email.trim(), code.trim());
      // The cookie is set now; pull the profile so the rest of the app has it.
      setMe({ user, profile: null });
      void refresh();
      navigate(user.onboarded ? '/test' : '/onboarding', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'That code did not work. Try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page page--narrow stack" id="main">
      <h1>Sign in</h1>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {step === 'email' ? (
        <form onSubmit={sendCode} className="stack">
          <p>We send you a code. There is no password.</p>
          <div>
            <label htmlFor="email">Your email</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <button className="btn btn--wide" type="submit" disabled={busy || !email.trim()}>
            {busy ? 'Sending…' : 'Send me a code'}
          </button>
        </form>
      ) : (
        <form onSubmit={submitCode} className="stack">
          <p>
            We sent a 6-digit code to <strong>{email}</strong>. Type it below.
          </p>

          {devCode && (
            <div className="notice">
              <p>
                <span className="tip__label">Dev mode.</span> No email was sent. Your code is{' '}
                <strong>{devCode}</strong>.
              </p>
            </div>
          )}

          <div>
            <label htmlFor="code">Your 6-digit code</label>
            <input
              id="code"
              name="code"
              className="code-input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            />
          </div>

          <button className="btn btn--wide" type="submit" disabled={busy || code.length < 6}>
            {busy ? 'Checking…' : 'Verify'}
          </button>

          <button
            className="btn btn--plain btn--small"
            type="button"
            onClick={() => {
              setStep('email');
              setCode('');
              setDevCode(null);
              setError(null);
            }}
          >
            Use a different email
          </button>
        </form>
      )}
    </main>
  );
}

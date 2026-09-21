import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, getPlans, startCheckout, type BillingInterval, type PlansResponse } from '../api';
import { useMe } from '../useMe';

function formatAmount(cents: number, currency: string): string {
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase(),
      minimumFractionDigits: cents % 100 === 0 ? 0 : 2,
    }).format(cents / 100);
  } catch {
    return `$${(cents / 100).toFixed(2)}`;
  }
}

const FREE_FEATURES = [
  'Paste and read up to 20,000 characters at a time',
  'All four sample books, rewritten for you',
  'The phonetic map and read-aloud',
  '"Which kind of reader am I?" screening',
  'Your own A/B reading tests',
  'A profile that remembers your trigger words',
  'One book conversion, to try it for real',
];

const PRO_FEATURES = [
  'Unlimited book conversions (EPUB or TXT to a dyslexia-friendly EPUB)',
  'Your library, kept and organised',
  'Send finished books straight to Kindle',
  'Priority rewrites with the higher-quality engine',
  'Support the open-source project',
];

const FAQ: { q: string; a: string }[] = [
  { q: 'Can I cancel any time?', a: 'Yes -- there is no contract. Cancel from "Manage billing" on your profile and Pro stays active until the end of the period you already paid for.' },
  {
    q: 'Is the engine really free and open source?',
    a: 'Yes. The rewriting engine behind this site is MIT-licensed and free to run yourself, forever -- see the link in the footer. Pro is a convenience the site sells on top of it: book conversions, your library, Kindle delivery and priority rewrites. It funds the project, but nothing about the free tier is a trial.',
  },
  {
    q: 'What happens to my books if I cancel?',
    a: 'Every book you already converted stays yours -- nothing is deleted or locked. You just go back to one conversion at a time going forward.',
  },
  { q: 'Is this a diagnosis?', a: 'No. Nothing here diagnoses dyslexia or any other condition -- on the free tier or Pro. It is a reading tool and, separately, a plain-language screening that points you toward support, not a label.' },
];

export default function Pricing() {
  const { user } = useMe();
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [interval, setInterval] = useState<BillingInterval>('monthly');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPlans()
      .then((res) => {
        if (!cancelled) setPlans(res);
      })
      .catch(() => {
        if (!cancelled) setError('We could not load prices just now. Try again in a moment.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function goPro() {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startCheckout(interval);
      window.location.href = url;
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) return;
      setError(err instanceof ApiError ? err.message : 'We could not start checkout. Try again.');
    } finally {
      setBusy(false);
    }
  }

  const price = plans ? plans[interval] : null;

  return (
    <main className="page stack" id="main">
      <header>
        <h1>Simple pricing</h1>
        <p>
          The rewriting engine is free and open source, always. Pro is a convenience on top of it
          -- unlimited book conversions, your library, and support for the project.
        </p>
      </header>

      <div className="plan-toggle" role="radiogroup" aria-label="Billing interval">
        <button
          type="button"
          role="radio"
          aria-checked={interval === 'monthly'}
          className="btn btn--small"
          disabled={interval === 'monthly'}
          onClick={() => setInterval('monthly')}
        >
          Monthly
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={interval === 'yearly'}
          className="btn btn--small"
          disabled={interval === 'yearly'}
          onClick={() => setInterval('yearly')}
        >
          Yearly
        </button>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="pricing-grid">
        <div className="plan-card card stack">
          <h2>Free</h2>
          <p className="plan-card__price">$0</p>
          <p className="muted">Everything you need to try it for real, no time limit.</p>
          <ul className="plan-list">
            {FREE_FEATURES.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <Link className="btn btn--wide btn--quiet" to="/signin">
            Start free
          </Link>
        </div>

        <div className="plan-card plan-card--pro card stack">
          <h2>Pro</h2>
          <p className="plan-card__price">
            {price ? formatAmount(price.amount, price.currency) : '…'}
            <span className="plan-card__interval">/{interval === 'monthly' ? 'month' : 'year'}</span>
          </p>
          <p className="muted">Founding price, locked in for as long as you stay subscribed.</p>
          <ul className="plan-list">
            {PRO_FEATURES.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          {user ? (
            <button className="btn btn--wide" type="button" onClick={() => void goPro()} disabled={busy || !plans}>
              {busy ? 'Starting…' : 'Go Pro'}
            </button>
          ) : (
            <Link className="btn btn--wide" to="/signin?next=/pricing">
              Go Pro
            </Link>
          )}
        </div>
      </div>

      <section className="stack" aria-labelledby="faq-heading">
        <h2 id="faq-heading">Questions</h2>
        <dl className="faq">
          {FAQ.map(({ q, a }) => (
            <div key={q}>
              <dt>{q}</dt>
              <dd>{a}</dd>
            </div>
          ))}
        </dl>
      </section>
    </main>
  );
}

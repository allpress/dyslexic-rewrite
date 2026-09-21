import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, getSample, postNewsletter, type Segment } from '../api';

/** The first paragraph of a sample, as before/after node lists with changed spans marked. */
function firstParagraph(segments: Segment[], original?: string): { before: ReactNode[]; after: ReactNode[] } {
  const before: ReactNode[] = [];
  const after: ReactNode[] = [];
  let key = 0;
  for (const seg of segments) {
    if (seg.t === 'para' || seg.t === 'heading') break;
    if (seg.t === 'change') {
      before.push(
        <span className="example__changed" key={`b${key}`}>
          {seg.orig}
        </span>,
      );
      after.push(
        <span className="example__changed" key={`a${key}`}>
          {seg.s}
        </span>,
      );
    } else if (seg.t === 'text' || seg.t === 'note') {
      before.push(seg.s);
      after.push(seg.s);
    }
    key++;
  }
  // The server sends the untouched paragraph; prefer it, since splits and dropped
  // punctuation can't be reconstructed from the rewritten segments alone.
  return { before: original ? [original] : before, after };
}

export default function Landing() {
  const [before, setBefore] = useState<ReactNode[] | null>(null);
  const [after, setAfter] = useState<ReactNode[] | null>(null);
  const [sampleFailed, setSampleFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSample('wind-in-the-willows')
      .then((res) => {
        if (cancelled) return;
        const paras = firstParagraph(res.segments, res.original_first_paragraph);
        setBefore(paras.before);
        setAfter(paras.after);
      })
      .catch(() => {
        if (!cancelled) setSampleFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [email, setEmail] = useState('');
  const [nlBusy, setNlBusy] = useState(false);
  const [nlDone, setNlDone] = useState(false);
  const [nlError, setNlError] = useState<string | null>(null);

  async function submitNewsletter(e: FormEvent) {
    e.preventDefault();
    setNlBusy(true);
    setNlError(null);
    try {
      await postNewsletter({ email: email.trim(), source: 'landing' });
      setNlDone(true);
    } catch (err) {
      setNlError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.');
    } finally {
      setNlBusy(false);
    }
  }

  return (
    <main className="page stack" id="main">
      <header className="stack">
        <h1>Books and articles, rewritten so you can actually read them.</h1>
        <p>
          Trigger words defused. Sentences straightened. Hard words respelled. Tuned to how{' '}
          <em>you</em> read.
        </p>
        <p className="muted">Free to try. Open source.</p>
        <div className="btn-row">
          <Link className="btn" to="/read?sample=wind-in-the-willows">
            Try it on a sample book
          </Link>
          <Link className="btn btn--quiet" to="/assess">
            Which kind of reader am I?
          </Link>
        </div>
        <p className="muted">
          Already have a profile? <Link to="/signin">Sign in</Link>.
        </p>
      </header>

      <section aria-labelledby="example-heading" className="stack">
        <h2 id="example-heading">See it work, live</h2>
        {before && after ? (
          <>
            <div className="example">
              <div className="example__col">
                <h3>Before</h3>
                <p className="example__text">{before}</p>
              </div>
              <div className="example__col">
                <h3>After</h3>
                <p className="example__text">{after}</p>
              </div>
            </div>
            <p className="muted">
              The opening of <em>The Wind in the Willows</em>, rewritten just now by the same engine
              you'd use. Underlined words changed — nothing else did.{' '}
              <Link to="/read?sample=wind-in-the-willows">Read the whole chapter</Link>.
            </p>
          </>
        ) : sampleFailed ? (
          <p className="muted">We couldn't load the live example right now — try the sample book directly.</p>
        ) : (
          <p className="muted">Rewriting a live example…</p>
        )}
      </section>

      <section aria-labelledby="how-heading" className="stack">
        <h2 id="how-heading">How it works</h2>
        <ol className="steps">
          <li>
            <span className="steps__num" aria-hidden="true">
              1
            </span>
            <span className="steps__body">
              <strong>We find the trigger words.</strong>
              Heteronyms, words reused with a different meaning nearby, misleading phrasal verbs,
              near-homophones, rare and overly long words, sentences that overload working memory.
            </span>
          </li>
          <li>
            <span className="steps__num" aria-hidden="true">
              2
            </span>
            <span className="steps__body">
              <strong>We rewrite what's safe to rewrite.</strong>
              Every change stays visible and reversible — hover or tap any underlined word to see
              the original and why it changed. Nothing is silently deleted.
            </span>
          </li>
          <li>
            <span className="steps__num" aria-hidden="true">
              3
            </span>
            <span className="steps__body">
              <strong>We tune it to you.</strong>
              Start from a general profile or one for how your dyslexia shows up, then teach it
              from your own writing and the words that actually trip you.
            </span>
          </li>
        </ol>
      </section>

      <section aria-labelledby="today-heading" className="stack">
        <h2 id="today-heading">What it does today</h2>
        <ul>
          <li>
            Detects heteronyms, reused ambiguous words, misleading phrasal verbs, near-homophone
            clashes, rare and long words, and heavy sentence shapes.
          </li>
          <li>Built-in profiles for a general reader, and for phonological, visual and attention differences.</li>
          <li>
            A friendly phonetic respelling (<em>in-TEN-shun</em>, not IPA) over words you might
            stumble on, shown on demand or always.
          </li>
          <li>A read-aloud button, and a built-in A/B reading test to check whether a rewrite actually helps.</li>
          <li>Four free sample books to try instantly — no sign-in needed.</li>
          <li>Runs as a free command-line tool on your own computer, with no account and no cloud, if you'd rather not use the site at all.</li>
        </ul>
      </section>

      <section aria-labelledby="research-heading" className="stack">
        <h2 id="research-heading">What the research says</h2>
        <ul>
          <li>
            More frequent, shorter words read faster for dyslexic readers —{' '}
            <a href="https://link.springer.com/chapter/10.1007/978-3-642-40498-6_15">
              Rello &amp; Baeza-Yates, INTERACT 2013
            </a>
            .
          </li>
          <li>
            Text-to-speech is the most consistently positive reading accommodation in the
            literature —{' '}
            <a href="https://link.springer.com/article/10.1007/s11145-025-10738-5">
              Reading and Writing, 2025
            </a>
            .
          </li>
          <li>
            Dyslexia fits a multiple-deficit model — a handful of overlapping weaknesses, not one
            single cause —{' '}
            <a href="https://pubmed.ncbi.nlm.nih.gov/16844106/">Pennington, 2006</a>.
          </li>
        </ul>
        <p className="muted">
          The heteronym trigger this project is built around has not been studied directly in
          dyslexia yet — we say so, and we're testing it ourselves. Full sources:{' '}
          <a href="https://github.com/allpress/dyslexic-rewrite/blob/main/docs/RESEARCH.md">
            docs/RESEARCH.md
          </a>
          .
        </p>
      </section>

      <section aria-labelledby="pricing-heading" className="notice">
        <h2 id="pricing-heading" style={{ fontSize: '1rem' }}>
          Free vs Pro
        </h2>
        <p>
          Reading, rewriting, the reading test and the reader battery are free, always. A Pro tier
          is coming for uploading your own books and keeping your profile in sync everywhere.{' '}
          <Link to="/pricing">See pricing</Link>.
        </p>
      </section>

      <section aria-labelledby="newsletter-heading" className="stack">
        <h2 id="newsletter-heading">Get the launch email</h2>
        <p className="muted">
          We'll email you when the site launches, and as we add more free, dyslexia-friendly
          classics. No spam, unsubscribe any time.
        </p>
        {nlDone ? (
          <p className="notice">
            <span>You're on the list. Thank you.</span>
          </p>
        ) : (
          <form onSubmit={submitNewsletter} className="stack">
            {nlError && (
              <p className="error" role="alert">
                {nlError}
              </p>
            )}
            <div className="btn-row">
              <label htmlFor="newsletter-email" className="sr-only">
                Your email
              </label>
              <input
                id="newsletter-email"
                name="email"
                type="email"
                autoComplete="email"
                inputMode="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                style={{ flex: '1 1 220px' }}
              />
              <button className="btn" type="submit" disabled={nlBusy || !email.trim()}>
                {nlBusy ? 'Signing up…' : 'Notify me'}
              </button>
            </div>
          </form>
        )}
      </section>

      <p className="muted">
        Don't want to use the site at all? <Link to="/about">It also runs free on your own computer</Link>.
      </p>
    </main>
  );
}

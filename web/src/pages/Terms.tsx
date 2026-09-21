export default function Terms() {
  return (
    <main className="page page--narrow stack" id="main">
      <h1>Terms</h1>
      <p className="muted">Kept short on purpose.</p>

      <section className="stack">
        <h2>The service</h2>
        <p>
          Unwind Words rewrites text so it's easier for a dyslexic reader to read. It's provided
          free of charge, as-is, with no uptime guarantee. A paid Pro tier may add extra features
          later — see <a href="/pricing">pricing</a> — but the core reading tools stay free.
        </p>
      </section>

      <section className="stack">
        <h2>Not medical advice</h2>
        <p>
          This site is not a diagnosis, a medical device, or a substitute for professional
          assessment. The "which kind of reader am I?" battery is a screening exercise built from
          published research, not a clinical instrument — see{' '}
          <a href="https://github.com/allpress/dyslexic-rewrite/blob/main/docs/RESEARCH.md">
            our research notes
          </a>{' '}
          for what it can and can't tell you.
        </p>
      </section>

      <section className="stack">
        <h2>Your content</h2>
        <p>
          Text you paste in to be rewritten is processed and returned to you; we don't store it.
          Anything you upload as a Pro user (a book, a writing sample) remains yours — you can
          delete it, and your account, at any time.
        </p>
      </section>

      <section className="stack">
        <h2>Open source</h2>
        <p>
          The rewriting engine is MIT-licensed and public on{' '}
          <a href="https://github.com/allpress/dyslexic-rewrite">GitHub</a>. You're free to run it
          yourself, on your own computer, under the terms of that license.
        </p>
      </section>

      <section className="stack">
        <h2>Changes</h2>
        <p>
          We may update these terms as the site grows. If we do, the date below will change, and
          material changes will be noted on the site.
        </p>
        <p className="muted">Last updated: September 2026.</p>
      </section>

      <p className="muted">
        Questions? <a href="mailto:hello@unwindwords.com">hello@unwindwords.com</a>
      </p>
    </main>
  );
}

export default function Privacy() {
  return (
    <main className="page page--narrow stack" id="main">
      <h1>Privacy</h1>
      <p className="muted">Plain language, no legalese. If anything here is unclear, email us.</p>

      <section className="stack">
        <h2>What we store</h2>
        <p>If you sign in, we keep:</p>
        <ul>
          <li>Your email address, so you can sign back in.</li>
          <li>
            Your profile settings — which trigger words you've marked, your reading-level
            preferences, your phonetic-map mode.
          </li>
          <li>Your reading-test results — words per minute, comprehension answers, ease ratings.</li>
          <li>Any books you upload, if you're on Pro.</li>
        </ul>
        <p>
          A writing sample you paste in is measured (sentence length, vocabulary, and so on) and
          then thrown away — we keep the numbers, never the text. Free-form text you rewrite on the
          read-anything page is never stored at all.
        </p>
      </section>

      <section className="stack">
        <h2>What we don't do</h2>
        <ul>
          <li>No ads, and no ad trackers.</li>
          <li>We don't sell or share your data with anyone.</li>
          <li>No third-party analytics scripts. Page views are counted without cookies or IP addresses.</li>
        </ul>
      </section>

      <section className="stack">
        <h2>Your account</h2>
        <p>
          You can delete your account and everything tied to it — profile, results, recordings,
          uploaded books — from your <a href="/profile">profile page</a>. Deletion is immediate and
          permanent.
        </p>
      </section>

      <section className="stack">
        <h2>The engine is open source</h2>
        <p>
          The text-rewriting engine that does the actual work is public. You can read exactly how
          it decides what to change on{' '}
          <a href="https://github.com/allpress/dyslexic-rewrite">GitHub</a>.
        </p>
      </section>

      <section className="notice">
        <p>
          This site is not a medical device and does not diagnose dyslexia. Nothing here is medical
          advice.
        </p>
      </section>

      <p className="muted">
        Questions? <a href="mailto:hello@unwindwords.com">hello@unwindwords.com</a>
      </p>
    </main>
  );
}

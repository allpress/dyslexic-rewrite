import { Link } from 'react-router-dom';

/** The changed words in the example, underlined so the difference is visible. */
function Changed({ children }: { children: string }) {
  return <span className="example__changed">{children}</span>;
}

export default function Landing() {
  return (
    <main className="page stack" id="main">
      <header>
        <h1>Text that stops fighting your brain.</h1>
        <p>
          Long sentences bend and fold. Rare words snag. We straighten the shape of a sentence and
          swap the words that trip you up. The meaning stays the same.
        </p>
      </header>

      <section aria-labelledby="example-heading" className="stack">
        <h2 id="example-heading">Here is what that looks like</h2>
        <div className="example">
          <div className="example__col">
            <h3>Before</h3>
            <p className="example__text">
              Every night, Grandpa would wind up the clock before bed<Changed>, and</Changed> the
              house would go quiet. Outside, the wind blows hard across the fields
              <Changed>, which</Changed> had been bare since the harvest.
            </p>
          </div>
          <div className="example__col">
            <h3>After</h3>
            <p className="example__text">
              Every night, Grandpa would wind up the clock before bed<Changed>. The</Changed> house
              would go quiet. Outside, the wind blows hard across the fields
              <Changed>. They</Changed> had been bare since the harvest.
            </p>
          </div>
        </div>
        <p className="muted">
          Two long sentences became four short ones. No word was lost. The underlined bits are the
          only parts that moved.
        </p>
      </section>

      <section aria-labelledby="how-heading" className="stack">
        <h2 id="how-heading">How it works</h2>
        <ol className="steps">
          <li>
            <span className="steps__num" aria-hidden="true">
              1
            </span>
            <span className="steps__body">
              <strong>Sign in.</strong>
              We send a code to your email. No password to remember.
            </span>
          </li>
          <li>
            <span className="steps__num" aria-hidden="true">
              2
            </span>
            <span className="steps__body">
              <strong>Take a 10-minute reading test.</strong>
              You read two short passages and answer five questions on each.
            </span>
          </li>
          <li>
            <span className="steps__num" aria-hidden="true">
              3
            </span>
            <span className="steps__body">
              <strong>Get your own profile.</strong>
              We learn which words slow you down. Then we rewrite anything you paste in.
            </span>
          </li>
        </ol>
      </section>

      <section aria-labelledby="free-heading" className="notice">
        <h2 id="free-heading" style={{ fontSize: '1rem' }}>
          Free, open source, and yours
        </h2>
        <p>
          The site costs nothing. The code is public. Your writing never leaves your control — when
          you share a sample, we measure it, keep the numbers, and throw the text away.
        </p>
      </section>

      <div className="btn-row">
        <Link className="btn" to="/signin">
          Start a reading test
        </Link>
        <Link className="btn btn--quiet" to="/read">
          Rewrite something first
        </Link>
      </div>

      <p className="muted">
        <a href="https://github.com/allpress/dyslexic-rewrite">See the code on GitHub</a>
      </p>
    </main>
  );
}

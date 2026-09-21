export default function About() {
  return (
    <main className="page page--narrow stack" id="main">
      <h1>About</h1>

      <section className="stack">
        <p>
          Unwind Words started as a tool built for one reader: Jennifer, who is dyslexic. For her,
          the problem was rarely the whole page — it was one word. A word that sounds like another
          word, or a word used twice nearby with two different meanings, could stop a sentence cold
          and take the rest of the paragraph down with it.
        </p>
        <p>
          So the tool looks for those specific trip points — heteronyms, re-used ambiguous words,
          misleading phrasal verbs, near-homophones — and defuses them, while leaving everything
          else exactly as written. Nothing is ever silently deleted: every change is visible and
          reversible on hover.
        </p>
      </section>

      <section className="stack">
        <h2>What we know, and what we don't</h2>
        <p>
          Dyslexia isn't one thing. The research points to a handful of partly independent
          weaknesses — phonological decoding, whole-word recognition, naming speed, visual
          attention span — that overlap differently in different people. We try to be honest about
          which parts of this tool are backed by published evidence and which are still open
          questions we're testing ourselves. The full write-up, sources included, is here:{' '}
          <a href="https://github.com/allpress/dyslexic-rewrite/blob/main/docs/RESEARCH.md">
            docs/RESEARCH.md
          </a>
          .
        </p>
      </section>

      <section className="stack">
        <h2>Free and open</h2>
        <p>
          The engine that does the rewriting is MIT-licensed and public. You can run it on your own
          computer, read exactly how it decides what to change, or send a pull request. The code
          lives on{' '}
          <a href="https://github.com/allpress/dyslexic-rewrite">GitHub</a>.
        </p>
      </section>

      <p className="muted">
        Built by Doug, for Jennifer.{' '}
        <a href="mailto:hello@unwindwords.com">hello@unwindwords.com</a>
      </p>
    </main>
  );
}

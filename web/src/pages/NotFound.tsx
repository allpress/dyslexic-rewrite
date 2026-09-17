import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <main className="page page--narrow stack" id="main">
      <h1>That page is not here.</h1>
      <p>The link may be old. Start again from the front page.</p>
      <Link className="btn" to="/">
        Go to the start
      </Link>
    </main>
  );
}

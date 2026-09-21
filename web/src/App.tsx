import { useEffect } from 'react';
import { Route, Routes, useNavigate } from 'react-router-dom';
import { Link, useLocation } from 'react-router-dom';
import Nav from './components/Nav';
import RequireAuth from './components/RequireAuth';
import { setUnauthorizedHandler } from './api';
import { trackPageView } from './api';
import Landing from './pages/Landing';
import SignIn from './pages/SignIn';
import Onboarding from './pages/Onboarding';
import TestPage from './pages/Test';
import Results from './pages/Results';
import ReadAnything from './pages/Read';
import Record from './pages/Record';
import Profile from './pages/Profile';
import Assess from './pages/Assess';
import Library from './pages/Library';
import BookReader from './pages/BookReader';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';
import About from './pages/About';
import NotFound from './pages/NotFound';
import Pricing from './pages/Pricing';

export default function App() {
  const navigate = useNavigate();

  // A 401 on a signed-in-only page sends the reader to sign in. Public pages (landing, read,
  // sign-in) probe /api/me for signed-out visitors too, and that 401 is expected.
  useEffect(() => {
    const publicPaths = new Set(['/', '/signin', '/read', '/assess', '/pricing']);
    setUnauthorizedHandler(() => {
      if (!publicPaths.has(window.location.pathname)) navigate('/signin', { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  // Cookie-free page-view ping (server/API.md v0.5) — one per route change, best-effort.
  const location = useLocation();
  useEffect(() => {
    trackPageView(location.pathname);
  }, [location.pathname]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Nav />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/signin" element={<SignIn />} />
        <Route
          path="/onboarding"
          element={
            <RequireAuth>
              <Onboarding />
            </RequireAuth>
          }
        />
        <Route
          path="/test"
          element={
            <RequireAuth>
              <TestPage />
            </RequireAuth>
          }
        />
        <Route
          path="/results"
          element={
            <RequireAuth>
              <Results />
            </RequireAuth>
          }
        />
        <Route path="/read" element={<ReadAnything />} />
        <Route path="/assess" element={<Assess />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/about" element={<About />} />
        <Route
          path="/record"
          element={
            <RequireAuth>
              <Record />
            </RequireAuth>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <Profile />
            </RequireAuth>
          }
        />
        <Route path="/pricing" element={<Pricing />} />
        <Route
          path="/library"
          element={
            <RequireAuth>
              <Library />
            </RequireAuth>
          }
        />
        <Route
          path="/library/:id"
          element={
            <RequireAuth>
              <BookReader />
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <footer className="footer">
        <p style={{ margin: 0, maxWidth: 'none' }}>
          Free and open source.{' '}
          <a href="https://github.com/allpress/dyslexic-rewrite">Code on GitHub</a>
        </p>
        <p className="muted" style={{ margin: '10px 0 0', maxWidth: 'none' }}>
          <Link to="/about">About</Link> · <Link to="/privacy">Privacy</Link> ·{' '}
          <Link to="/terms">Terms</Link> ·{' '}
          <a href="mailto:hello@unwindwords.com">hello@unwindwords.com</a>
        </p>
        <p className="muted" style={{ margin: '6px 0 0', maxWidth: 'none' }}>
          Made for Jennifer.
        </p>
      </footer>
    </div>
  );
}

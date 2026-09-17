import { useEffect } from 'react';
import { Route, Routes, useNavigate } from 'react-router-dom';
import Nav from './components/Nav';
import RequireAuth from './components/RequireAuth';
import { setUnauthorizedHandler } from './api';
import Landing from './pages/Landing';
import SignIn from './pages/SignIn';
import Onboarding from './pages/Onboarding';
import TestPage from './pages/Test';
import Results from './pages/Results';
import ReadAnything from './pages/Read';
import Profile from './pages/Profile';
import NotFound from './pages/NotFound';

export default function App() {
  const navigate = useNavigate();

  // A 401 on a signed-in-only page sends the reader to sign in. Public pages (landing, read,
  // sign-in) probe /api/me for signed-out visitors too, and that 401 is expected.
  useEffect(() => {
    const publicPaths = new Set(['/', '/signin', '/read']);
    setUnauthorizedHandler(() => {
      if (!publicPaths.has(window.location.pathname)) navigate('/signin', { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

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
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <Profile />
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
      </footer>
    </div>
  );
}

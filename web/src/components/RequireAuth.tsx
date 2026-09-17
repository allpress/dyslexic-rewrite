import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useMe } from '../useMe';

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useMe();
  const location = useLocation();

  if (loading) {
    return (
      <main className="page page--narrow">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (!user) {
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

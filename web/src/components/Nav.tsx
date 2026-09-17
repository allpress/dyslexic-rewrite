import { Link, NavLink } from 'react-router-dom';
import { useMe } from '../useMe';

export default function Nav() {
  const { user, loading } = useMe();

  return (
    <nav className="nav" aria-label="Main">
      <div className="nav__inner">
        <Link to="/" className="nav__logo">
          Dyslexic Rewrite
        </Link>
        {!loading && user ? (
          <>
            <NavLink to="/test" className="nav__link">
              Test
            </NavLink>
            <NavLink to="/read" className="nav__link">
              Read
            </NavLink>
            <NavLink to="/results" className="nav__link">
              Results
            </NavLink>
            <NavLink to="/profile" className="nav__link">
              Profile
            </NavLink>
          </>
        ) : (
          <>
            <NavLink to="/read" className="nav__link">
              Read
            </NavLink>
            <NavLink to="/signin" className="nav__link">
              Sign in
            </NavLink>
          </>
        )}
      </div>
    </nav>
  );
}

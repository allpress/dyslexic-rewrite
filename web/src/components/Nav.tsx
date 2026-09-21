import { Link, NavLink } from 'react-router-dom';
import { useMe } from '../useMe';

export default function Nav() {
  const { user, loading } = useMe();

  return (
    <nav className="nav" aria-label="Main">
      <div className="nav__inner">
        <Link to="/" className="nav__logo">
          Unwind Words
        </Link>
        {!loading && user ? (
          <>
            <NavLink to="/test" className="nav__link">
              Test
            </NavLink>
            <NavLink to="/read" className="nav__link">
              Read
            </NavLink>
            <NavLink to="/record" className="nav__link">
              Record
            </NavLink>
            <NavLink to="/results" className="nav__link">
              Results
            </NavLink>
            <NavLink to="/assess" className="nav__link">
              Which kind of reader am I?
            </NavLink>
            <NavLink to="/profile" className="nav__link">
              Profile
            </NavLink>
            <NavLink to="/pricing" className="nav__link">
              Pricing
            </NavLink>
          </>
        ) : (
          <>
            <NavLink to="/read" className="nav__link">
              Read
            </NavLink>
            <NavLink to="/assess" className="nav__link">
              Which kind of reader am I?
            </NavLink>
            <NavLink to="/pricing" className="nav__link">
              Pricing
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

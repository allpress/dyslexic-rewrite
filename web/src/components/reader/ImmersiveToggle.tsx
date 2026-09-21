import { useEffect, useState } from 'react';

/**
 * A full-screen "immersive" toggle: hides the nav (via the `body.reader-immersive` CSS class in
 * styles.css) and, where supported, also requests real browser fullscreen. Falls back to the CSS
 * overlay alone when the Fullscreen API is unavailable or refuses (iOS Safari, an iframe without
 * `allow="fullscreen"`, etc.) — the toggle still works either way. Esc always exits: natively via
 * `fullscreenchange` when the Fullscreen API is doing the work, and via a key listener otherwise.
 */
export default function ImmersiveToggle() {
  const [active, setActive] = useState(false);

  useEffect(() => {
    function onFsChange() {
      if (!document.fullscreenElement) {
        document.body.classList.remove('reader-immersive');
        setActive(false);
      }
    }
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') exit();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Never leave the page stuck immersive if this control unmounts mid-session (e.g. the reader
  // navigates away by URL bar/back button while immersive).
  useEffect(() => () => document.body.classList.remove('reader-immersive'), []);

  function enter() {
    document.body.classList.add('reader-immersive');
    setActive(true);
    try {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } catch {
      // Unsupported/blocked: the CSS overlay above is the whole experience in that case.
    }
  }

  function exit() {
    document.body.classList.remove('reader-immersive');
    setActive(false);
    try {
      if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    } catch {
      // ignore
    }
  }

  return (
    <button
      type="button"
      className="btn btn--plain btn--small"
      aria-pressed={active}
      onClick={() => (active ? exit() : enter())}
    >
      {active ? 'Exit immersive' : 'Immersive mode'}
    </button>
  );
}

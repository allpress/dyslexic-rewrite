/**
 * A `requestAnimationFrame`-driven "wait `ms` then call back" helper. Every stimulus onset in the
 * battery is scheduled this way (never a bare `setTimeout`) so timing tracks the display's actual
 * paint cadence, per the FEATURE spec. Returns a cancel function -- always call it on unmount /
 * when superseded, the way a `useEffect` cleanup does.
 */
export function afterMs(ms: number, cb: () => void): () => void {
  let raf = 0;
  let cancelled = false;
  const start = performance.now();

  function tick(now: number) {
    if (cancelled) return;
    if (now - start >= ms) {
      cb();
      return;
    }
    raf = requestAnimationFrame(tick);
  }

  raf = requestAnimationFrame(tick);
  return () => {
    cancelled = true;
    cancelAnimationFrame(raf);
  };
}

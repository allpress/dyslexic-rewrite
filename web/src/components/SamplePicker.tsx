import { useEffect, useState } from 'react';
import { ApiError, getSamples, type SampleInfo } from '../api';

export interface SamplePickerProps {
  /** Called with the chosen sample's slug. */
  onPick: (slug: string) => void;
  onClose: () => void;
}

/** A small picker of the public-domain sample books ("Show me an example" on /read). */
export default function SamplePicker({ onPick, onClose }: SamplePickerProps) {
  const [samples, setSamples] = useState<SampleInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSamples()
      .then((res) => {
        if (!cancelled) setSamples(res);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'We could not load the sample books.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="sample-picker" role="dialog" aria-modal="true" aria-label="Choose a sample book">
      <div className="sample-picker__header">
        <h2>Show me an example</h2>
        <button type="button" className="btn btn--plain btn--small" onClick={onClose}>
          Close
        </button>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!samples && !error && <p className="muted">Loading samples…</p>}

      {samples && (
        <ul className="sample-picker__list">
          {samples.map((s) => (
            <li key={s.slug} className="sample-picker__item">
              <div className="sample-picker__info">
                <h3>{s.title}</h3>
                <p className="muted">
                  {s.author}, {s.year} &middot; {s.chapter} &middot; {s.words} words
                </p>
                <p>{s.blurb}</p>
                <a href={s.source} target="_blank" rel="noreferrer">
                  Project Gutenberg
                </a>
              </div>
              <button type="button" className="btn btn--small" onClick={() => onPick(s.slug)}>
                Read this
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

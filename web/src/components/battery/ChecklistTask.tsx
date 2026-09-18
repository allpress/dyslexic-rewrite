import { useState } from 'react';
import type { BatteryChecklist } from '../../api';

export interface ChecklistResult {
  answers: Record<string, number>;
  comfort: Record<string, number>;
}

export interface ChecklistTaskProps {
  items: BatteryChecklist;
  onComplete: (result: ChecklistResult) => void;
  onSkip: () => void;
}

/** Task A: 10 checklist items + 3 visual-comfort items, one at a time, on a 1-4 scale. Triage
 * only -- nothing here gates access to anything. */
export default function ChecklistTask({ items, onComplete, onSkip }: ChecklistTaskProps) {
  const all = [
    ...items.items.map((it) => ({ ...it, comfort: false })),
    ...items.comfort_items.map((it) => ({ ...it, axis: 'comfort', comfort: true })),
  ];
  const [index, setIndex] = useState(0);
  const [values, setValues] = useState<Record<string, number>>({});

  const q = all[index];

  function choose(value: number) {
    const next = { ...values, [q.id]: value };
    if (index + 1 < all.length) {
      setValues(next);
      setIndex(index + 1);
      return;
    }
    const answers: Record<string, number> = {};
    const comfort: Record<string, number> = {};
    for (const it of all) {
      const v = next[it.id];
      if (v === undefined) continue;
      if (it.comfort) comfort[it.id] = v;
      else answers[it.id] = v;
    }
    onComplete({ answers, comfort });
  }

  return (
    <div className="stack">
      <h1>{q.comfort ? 'A few questions about your eyes' : 'A few questions about reading'}</h1>
      <p className="progress">
        Question {index + 1} of {all.length}
      </p>
      <p style={{ fontSize: '1.25rem', fontWeight: 700, maxWidth: 'none' }}>{q.prompt}</p>
      <div className="choices" role="radiogroup" aria-label={q.prompt}>
        {items.scale.map((label, i) => (
          <button key={label} type="button" className="choice" onClick={() => choose(i + 1)}>
            <span className="choice__title">{label}</span>
          </button>
        ))}
      </div>
      {index === 0 && (
        <button className="btn btn--plain btn--small" type="button" onClick={onSkip}>
          Skip this section
        </button>
      )}
    </div>
  );
}

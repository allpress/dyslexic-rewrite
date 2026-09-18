import { type ReactNode, useState } from 'react';

export interface StepperStep {
  id: string;
  label: string;
  /** Whether this step can be skipped. Defaults to true. */
  skippable?: boolean;
  render: (ctx: { next: () => void; skip: () => void }) => ReactNode;
}

export interface StepperProps {
  steps: StepperStep[];
  /** Fires once, after the last step is done or skipped, with the ids of every skipped step. */
  onComplete: (skipped: string[]) => void;
}

/**
 * A generic, keyboard-first "one thing on screen at a time" stepper used by the battery page.
 * Each step renders its own content and calls `next()` (or `skip()`) when it is done -- the
 * stepper itself only tracks progress and which steps were skipped.
 */
export default function Stepper({ steps, onComplete }: StepperProps) {
  const [index, setIndex] = useState(0);
  const [skipped, setSkipped] = useState<string[]>([]);

  const step = steps[index];
  if (!step) return null;

  function advance(nextSkipped: string[]) {
    if (index + 1 < steps.length) {
      setIndex(index + 1);
    } else {
      onComplete(nextSkipped);
    }
  }

  function next() {
    advance(skipped);
  }

  function skip() {
    const nextSkipped = [...skipped, step.id];
    setSkipped(nextSkipped);
    advance(nextSkipped);
  }

  return (
    <div className="stack">
      <p className="progress">
        Step {index + 1} of {steps.length}: {step.label}
      </p>
      {step.render({ next, skip })}
    </div>
  );
}

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Stepper, { type StepperStep } from '../components/Stepper';

function makeSteps(): StepperStep[] {
  return [
    {
      id: 'one',
      label: 'First',
      render: ({ next, skip }) => (
        <div>
          <p>Step one content</p>
          <button type="button" onClick={next}>
            Next
          </button>
          <button type="button" onClick={skip}>
            Skip
          </button>
        </div>
      ),
    },
    {
      id: 'two',
      label: 'Second',
      render: ({ next, skip }) => (
        <div>
          <p>Step two content</p>
          <button type="button" onClick={next}>
            Next
          </button>
          <button type="button" onClick={skip}>
            Skip
          </button>
        </div>
      ),
    },
    {
      id: 'three',
      label: 'Third',
      render: ({ next }) => (
        <div>
          <p>Step three content</p>
          <button type="button" onClick={next}>
            Finish
          </button>
        </div>
      ),
    },
  ];
}

describe('Stepper', () => {
  it('shows the first step and progress out of the total', () => {
    render(<Stepper steps={makeSteps()} onComplete={() => {}} />);
    expect(screen.getByText('Step 1 of 3: First')).toBeInTheDocument();
    expect(screen.getByText('Step one content')).toBeInTheDocument();
  });

  it('advances to the next step when that step calls next()', async () => {
    const user = userEvent.setup();
    render(<Stepper steps={makeSteps()} onComplete={() => {}} />);

    await user.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByText('Step 2 of 3: Second')).toBeInTheDocument();
    expect(screen.getByText('Step two content')).toBeInTheDocument();
    expect(screen.queryByText('Step one content')).not.toBeInTheDocument();
  });

  it('calls onComplete with no skipped ids after finishing every step normally', async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<Stepper steps={makeSteps()} onComplete={onComplete} />);

    await user.click(screen.getByRole('button', { name: 'Next' })); // one -> two
    await user.click(screen.getByRole('button', { name: 'Next' })); // two -> three
    await user.click(screen.getByRole('button', { name: 'Finish' })); // three -> done

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith([]);
  });

  it('skip() advances and records the skipped step id in onComplete', async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<Stepper steps={makeSteps()} onComplete={onComplete} />);

    await user.click(screen.getByRole('button', { name: 'Skip' })); // skip "one"
    expect(screen.getByText('Step 2 of 3: Second')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Skip' })); // skip "two"
    expect(screen.getByText('Step 3 of 3: Third')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Finish' }));
    expect(onComplete).toHaveBeenCalledWith(['one', 'two']);
  });
});

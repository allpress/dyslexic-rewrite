import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  applyBatteryRun,
  createBatteryRun,
  finishBatteryRun,
  getBatteryItems,
  patchBatteryRun,
  scoreBattery,
  type BatteryAxisScore,
  type BatteryHeteronymResult,
  type BatteryItems,
  type BatteryRaw,
  type BatteryResult,
} from '../api';
import Radar, { type RadarAxisDatum } from '../components/Radar';
import Stepper, { type StepperStep } from '../components/Stepper';
import ChecklistTask from '../components/battery/ChecklistTask';
import ChoiceTask from '../components/battery/ChoiceTask';
import DigitSpanTask from '../components/battery/DigitSpanTask';
import HeteronymTask from '../components/battery/HeteronymTask';
import SpellingTask from '../components/battery/SpellingTask';
import VasTask from '../components/battery/VasTask';
import { useMe } from '../useMe';

type Phase = 'intro' | 'loading' | 'running' | 'scoring' | 'results';

function trickyWordLine(h: BatteryHeteronymResult): string {
  if (h.slowdown_ms == null) {
    return 'Tricky-word slowdown: not measured this time (that section was skipped).';
  }
  if (h.reliable) {
    return (
      `Tricky-word slowdown: words that can mean two different things, like "wind" (the weather) ` +
      `and "wind" (a clock), slowed you down by about ${Math.round(h.slowdown_ms)} milliseconds ` +
      `(${Math.round((h.slowdown_ratio ?? 0) * 100)}% slower) compared with ordinary words of the same shape.`
    );
  }
  return "Tricky-word slowdown: we did not see a reliable slowdown on two-meaning words this time.";
}

function whatThisMeans(axes: BatteryAxisScore[]): string {
  const scored = axes.filter((a) => a.confidence === 'normal');
  const top = [...scored].sort((a, b) => b.support - a.support)[0];
  if (!top || top.support < 30) {
    return 'Nothing here stood out much today — your reading looks fairly comfortable across the board, at least on these quick tasks.';
  }
  return (
    `"${top.label}" looked like the biggest opportunity today. That does not mean anything is ` +
    'wrong with you — everyone\'s reading has a shape, and this just points at which settings ' +
    'might help yours the most.'
  );
}

export default function Assess() {
  const { user, setProfile } = useMe();

  const [phase, setPhase] = useState<Phase>('intro');
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<BatteryItems | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [result, setResult] = useState<BatteryResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState(false);

  const rawRef = useRef<BatteryRaw>({});

  async function start() {
    setPhase('loading');
    setError(null);
    setApplied(false);
    setResult(null);
    rawRef.current = {};
    try {
      const fetched = await getBatteryItems();
      setItems(fetched);
      if (user) {
        const run = await createBatteryRun();
        setRunId(run.id);
      } else {
        setRunId(null);
      }
      setPhase('running');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not load the battery. Try again.');
      setPhase('intro');
    }
  }

  async function handleTaskDone(key: keyof BatteryRaw, data: BatteryRaw[keyof BatteryRaw], next: () => void) {
    rawRef.current = { ...rawRef.current, [key]: data };
    if (runId) {
      try {
        await patchBatteryRun(runId, { [key]: data } as BatteryRaw);
      } catch {
        // Keep going locally even if saving this task's result failed -- scoring still works,
        // and the reader is not signed out mid-battery over a flaky save.
      }
    }
    next();
  }

  async function finish() {
    setPhase('scoring');
    setError(null);
    try {
      const scores = runId ? (await finishBatteryRun(runId)).scores : await scoreBattery(rawRef.current);
      setResult(scores);
      setPhase('results');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not score that. Try again.');
      setPhase('results');
    }
  }

  const steps: StepperStep[] = useMemo(() => {
    if (!items) return [];
    return [
      {
        id: 'checklist',
        label: 'A few questions',
        render: ({ next, skip }) => (
          <ChecklistTask
            items={items.checklist}
            onComplete={(r) => void handleTaskDone('checklist', r, next)}
            onSkip={skip}
          />
        ),
      },
      {
        id: 'spelling',
        label: 'Spelling',
        render: ({ next, skip }) => (
          <SpellingTask
            items={items.spelling}
            onComplete={(r) => void handleTaskDone('spelling', r, next)}
            onSkip={skip}
          />
        ),
      },
      {
        id: 'orthographic_choice',
        label: 'Word choice',
        render: ({ next, skip }) => (
          <ChoiceTask
            title="Which one is a real word?"
            instructions="Pick the real word, as quickly as feels comfortable."
            items={items.orthographic_choice}
            onComplete={(r) => void handleTaskDone('orthographic_choice', r, next)}
            onSkip={skip}
          />
        ),
      },
      {
        id: 'pseudohomophone',
        label: 'Sounds like a word',
        render: ({ next, skip }) => (
          <ChoiceTask
            title="Which one sounds like a real word?"
            instructions="Neither is spelled correctly — pick the one that sounds right when you say it out loud."
            items={items.pseudohomophone}
            onComplete={(r) => void handleTaskDone('pseudohomophone', r, next)}
            onSkip={skip}
          />
        ),
      },
      {
        id: 'vas',
        label: 'Quick glance',
        render: ({ next, skip }) => (
          <VasTask trials={items.vas} onComplete={(r) => void handleTaskDone('vas', r, next)} onSkip={skip} />
        ),
      },
      {
        id: 'digit_span',
        label: 'Number memory',
        render: ({ next, skip }) => (
          <DigitSpanTask
            trials={items.digit_span}
            onComplete={(r) => void handleTaskDone('digit_span', r, next)}
            onSkip={skip}
          />
        ),
      },
      {
        id: 'heteronym',
        label: 'Reading',
        render: ({ next, skip }) => (
          <HeteronymTask
            items={items.heteronym}
            onComplete={(r) => void handleTaskDone('heteronym', r, next)}
            onSkip={skip}
          />
        ),
      },
    ];
  }, [items]); // eslint-disable-line react-hooks/exhaustive-deps

  async function applyResults() {
    if (!runId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await applyBatteryRun(runId);
      setProfile(res.profile);
      setApplied(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'We could not save that to your profile.');
    } finally {
      setBusy(false);
    }
  }

  const errorBox = error && (
    <p className="error" role="alert">
      {error}
    </p>
  );

  if (phase === 'intro' || phase === 'loading') {
    return (
      <main className="page page--narrow stack" id="main">
        {errorBox}
        <h1>Which kind of reader am I?</h1>
        <p>
          A short set of quick tasks — about 10 minutes — that builds a simple picture of your
          reading, drawn as a chart across five plain-language axes. It is a screening, not a
          diagnosis, and there is no single "type" of dyslexia to sort you into.
        </p>
        <p>You can skip any task and still get a result. Nothing here is timed against you on purpose — a few tasks measure speed because that is what they are testing, but there is no penalty for going at your own pace.</p>
        <ul className="steps">
          <li>
            <span className="steps__num">1</span>
            <span className="steps__body">A few questions, then some quick word and letter tasks.</span>
          </li>
          <li>
            <span className="steps__num">2</span>
            <span className="steps__body">A chart of five plain-language axes, plus a note about visual comfort.</span>
          </li>
          <li>
            <span className="steps__num">3</span>
            <span className="steps__body">
              {user ? 'Apply the result to your reading settings, if you want to.' : 'Sign in if you want to save or apply the result.'}
            </span>
          </li>
        </ul>
        <button className="btn btn--wide" type="button" onClick={() => void start()} disabled={phase === 'loading'}>
          {phase === 'loading' ? 'One moment…' : 'Start'}
        </button>
      </main>
    );
  }

  if (phase === 'running' && items) {
    return (
      <main className="page page--narrow stack" id="main">
        {errorBox}
        <Stepper steps={steps} onComplete={() => void finish()} />
      </main>
    );
  }

  if (phase === 'scoring') {
    return (
      <main className="page page--narrow stack" id="main">
        <p className="muted">Working out your results…</p>
      </main>
    );
  }

  // phase === 'results'
  if (!result) {
    return (
      <main className="page page--narrow stack" id="main">
        {errorBox}
        <button className="btn" type="button" onClick={() => void start()}>
          Try again
        </button>
      </main>
    );
  }

  const radarAxes: RadarAxisDatum[] = result.axes.map((a) => ({
    id: a.id,
    label: a.label,
    support: a.support,
    confidence: a.confidence,
  }));

  return (
    <main className="page stack" id="main">
      {errorBox}
      <h1>Your reading profile</h1>
      <Radar axes={radarAxes} />

      <div className="notice">
        <p>
          Visual comfort: {Math.round(result.comfort.support)} out of 100.{' '}
          {result.comfort.support >= 50
            ? 'Glare, movement or headaches showed up as a bigger issue for you today.'
            : 'This did not stand out much for you today.'}{' '}
          This is a comfort note on its own — the evidence for treating it as a reading-difficulty
          axis is weak, so we never fold it into the chart above.
        </p>
      </div>

      <p>{trickyWordLine(result.heteronym)}</p>
      <p>{whatThisMeans(result.axes)}</p>
      <p className="muted">
        This is a screening, not a diagnosis — only a qualified assessment can tell you that — and
        your result can shift from day to day. Treat it as a starting point, not a label.
      </p>

      <div className="btn-row">
        {user ? (
          applied ? (
            <p className="notice">
              <span>Saved. We will use these settings for your reading from now on.</span>
            </p>
          ) : (
            <button className="btn" type="button" onClick={() => void applyResults()} disabled={busy || !runId}>
              {busy ? 'Saving…' : 'Use these settings for my reading'}
            </button>
          )
        ) : (
          <Link className="btn" to="/signin">
            Sign in to save this
          </Link>
        )}
        <button className="btn btn--quiet" type="button" onClick={() => void start()}>
          Do it again
        </button>
      </div>
    </main>
  );
}

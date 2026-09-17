/** Plain-language comparisons. Short sentences, subject first, no jargon. */

export interface Side {
  wpm: number;
  correct: number;
  total: number;
}

/** Percent difference in reading speed, rounded. Positive = rewritten was faster. */
export function speedChangePercent(originalWpm: number, rewrittenWpm: number): number {
  if (!originalWpm || originalWpm <= 0) return 0;
  return Math.round(((rewrittenWpm - originalWpm) / originalWpm) * 100);
}

/**
 * One sentence about speed, one clause about comprehension.
 * e.g. "You read the rewritten passage 18% faster and got the same number right."
 */
export function verdict(original: Side, rewritten: Side): string {
  const pct = speedChangePercent(original.wpm, rewritten.wpm);
  const size = Math.abs(pct);

  let speed: string;
  if (size < 3) {
    speed = 'You read both passages at about the same speed';
  } else if (pct > 0) {
    speed = `You read the rewritten passage ${size}% faster`;
  } else {
    speed = `You read the rewritten passage ${size}% slower`;
  }

  const diff = rewritten.correct - original.correct;
  let answers: string;
  if (diff === 0) {
    answers = 'got the same number right';
  } else if (diff > 0) {
    answers = `got ${diff} more question${diff === 1 ? '' : 's'} right`;
  } else {
    const n = Math.abs(diff);
    answers = `got ${n} question${n === 1 ? '' : 's'} fewer right`;
  }

  return `${speed} and ${answers}.`;
}

/**
 * API.md does not pin the scale of `totals.*.comprehension`. Treat a value of
 * 1 or less as a 0..1 rate and anything larger as an already-scaled percentage.
 */
export function asPercent(value: number): number {
  return Math.round(value <= 1 ? value * 100 : value);
}

/** The same idea as `verdict`, but across every test, where comprehension is a percentage. */
export function totalsVerdict(
  original: { wpm: number; comprehension: number },
  rewritten: { wpm: number; comprehension: number },
): string {
  const pct = speedChangePercent(original.wpm, rewritten.wpm);
  const size = Math.abs(pct);

  let speed: string;
  if (size < 3) {
    speed = 'Across all your tests, you read both kinds of text at about the same speed';
  } else if (pct > 0) {
    speed = `Across all your tests, you read rewritten text ${size}% faster`;
  } else {
    speed = `Across all your tests, you read rewritten text ${size}% slower`;
  }

  const diff = asPercent(rewritten.comprehension) - asPercent(original.comprehension);
  let answers: string;
  if (Math.abs(diff) < 3) {
    answers = 'you got about the same share of questions right';
  } else if (diff > 0) {
    answers = `you got ${diff} in 100 more questions right`;
  } else {
    answers = `you got ${Math.abs(diff)} in 100 fewer questions right`;
  }

  return `${speed}, and ${answers}.`;
}

/** Words per minute, for the client-side timer. */
export function wordsPerMinute(words: number, seconds: number): number {
  if (seconds <= 0) return 0;
  return Math.round(words / (seconds / 60));
}

export function easeWord(ease: number): string {
  return (
    ['', 'very hard', 'hard', 'okay', 'easy', 'very easy'][Math.round(ease)] ?? 'okay'
  );
}

/** Turn a StyleReport-ish number into a sentence a person can read. */
export function rateInWords(rate: number, thing: string): string {
  const pct = Math.round(rate * 100);
  if (pct <= 0) return `You almost never use ${thing}.`;
  if (pct < 10) return `You use ${thing} now and then — about ${pct} in 100 sentences.`;
  return `You use ${thing} in about ${pct} out of 100 sentences.`;
}

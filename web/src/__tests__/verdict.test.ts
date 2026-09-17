import { describe, expect, it } from 'vitest';
import { asPercent, speedChangePercent, totalsVerdict, verdict, wordsPerMinute } from '../lib/verdict';

describe('verdict', () => {
  it('reports faster reading and equal comprehension', () => {
    const line = verdict(
      { wpm: 200, correct: 4, total: 5 },
      { wpm: 236, correct: 4, total: 5 },
    );
    expect(line).toBe('You read the rewritten passage 18% faster and got the same number right.');
  });

  it('reports slower reading and more answers right', () => {
    const line = verdict(
      { wpm: 200, correct: 3, total: 5 },
      { wpm: 180, correct: 5, total: 5 },
    );
    expect(line).toBe('You read the rewritten passage 10% slower and got 2 more questions right.');
  });

  it('calls a small difference the same speed', () => {
    const line = verdict({ wpm: 200, correct: 4, total: 5 }, { wpm: 203, correct: 3, total: 5 });
    expect(line).toBe('You read both passages at about the same speed and got 1 question fewer right.');
  });

  it('does not divide by zero', () => {
    expect(speedChangePercent(0, 150)).toBe(0);
    expect(wordsPerMinute(300, 0)).toBe(0);
    expect(wordsPerMinute(300, 60)).toBe(300);
  });
});

describe('totalsVerdict', () => {
  it('talks in shares of questions, not counts', () => {
    const line = totalsVerdict(
      { wpm: 180, comprehension: 0.8 },
      { wpm: 216, comprehension: 0.8 },
    );
    expect(line).toBe(
      'Across all your tests, you read rewritten text 20% faster, and you got about the same share of questions right.',
    );
  });

  it('reads comprehension on either scale', () => {
    expect(asPercent(0.82)).toBe(82);
    expect(asPercent(82)).toBe(82);
    expect(totalsVerdict({ wpm: 180, comprehension: 60 }, { wpm: 180, comprehension: 75 })).toBe(
      'Across all your tests, you read both kinds of text at about the same speed, and you got 15 in 100 more questions right.',
    );
  });
});

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import Radar, { axisSentence, dataPoints, type RadarAxisDatum } from '../components/Radar';

const AXES: RadarAxisDatum[] = [
  { id: 'phonological', label: 'Sounding out words', support: 62, confidence: 'normal' },
  { id: 'orthographic', label: 'Recognising whole words', support: 10, confidence: 'normal' },
  { id: 'rate', label: 'Reading speed', support: 80, confidence: 'normal' },
  { id: 'vas', label: 'Taking in letters at a glance', support: 45, confidence: 'low' },
  { id: 'attention', label: 'Holding a sentence in mind', support: 33, confidence: 'normal' },
];

describe('Radar', () => {
  it('renders all five axis labels', () => {
    render(<Radar axes={AXES} />);
    for (const axis of AXES) {
      expect(screen.getAllByText(axis.label).length).toBeGreaterThan(0);
    }
  });

  it('lists each axis as a plain-language sentence with its number', () => {
    render(<Radar axes={AXES} />);
    expect(screen.getByText(/Sounding out words: 62 out of 100/)).toBeInTheDocument();
    expect(screen.getByText(/Recognising whole words: 10 out of 100/)).toBeInTheDocument();
    expect(screen.getByText(/Reading speed: 80 out of 100/)).toBeInTheDocument();
    expect(screen.getByText(/Holding a sentence in mind: 33 out of 100/)).toBeInTheDocument();
  });

  it('notes low confidence in the accessible list', () => {
    render(<Radar axes={AXES} />);
    expect(screen.getByText(/Taking in letters at a glance: 45 out of 100/)).toHaveTextContent(
      'not have much to go on',
    );
  });

  it('draws exactly one filled polygon with one vertex per axis', () => {
    const { container } = render(<Radar axes={AXES} />);
    const fill = container.querySelector('.radar__fill');
    expect(fill).not.toBeNull();
    const points = fill!.getAttribute('points')!.trim().split(/\s+/);
    expect(points).toHaveLength(AXES.length);
  });

  it('hides the decorative chart from assistive tech (the list carries the content)', () => {
    const { container } = render(<Radar axes={AXES} />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('axisSentence', () => {
  it('describes a high-support axis without saying anything is wrong', () => {
    const s = axisSentence({ id: 'x', label: 'Reading speed', support: 90, confidence: 'normal' });
    expect(s).toContain('Reading speed: 90 out of 100');
    expect(s).toContain('a lot of extra support could help here');
  });

  it('describes a low-support axis', () => {
    const s = axisSentence({ id: 'x', label: 'Reading speed', support: 5, confidence: 'normal' });
    expect(s).toContain('not much extra support would help here');
  });
});

describe('dataPoints', () => {
  it('places a support of 0 at the centre and 100 at the full radius', () => {
    const points = dataPoints([0, 100], 50, 100, 100);
    const [p0, p1] = points.split(' ');
    expect(p0).toBe('100.0,100.0');
    // Second axis (index 1 of 2) points straight down from centre: angle = -90° + 180° = 90°.
    expect(p1).toBe('100.0,150.0');
  });

  it('clips out-of-range values to 0-100', () => {
    const points = dataPoints([-20, 500], 50, 0, 0);
    const [p0] = points.split(' ');
    expect(p0).toBe('0.0,0.0');
  });
});

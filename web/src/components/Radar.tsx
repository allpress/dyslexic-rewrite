/**
 * A plain SVG radar chart for the "which kind of reader am I?" result: five axes, 0-100, a
 * filled polygon, plain-word axis labels, no charting library. Accessible by pairing the chart
 * (decorative, `aria-hidden`) with a visible list of the same five numbers, one sentence each --
 * screen readers get the list, sighted readers get both.
 */

export interface RadarAxisDatum {
  id: string;
  label: string;
  support: number; // 0-100, higher = more support could help
  confidence: 'low' | 'normal';
}

export interface RadarProps {
  axes: RadarAxisDatum[];
  size?: number;
}

const RINGS = [25, 50, 75, 100];

function angleFor(index: number, total: number): number {
  return (Math.PI * 2 * index) / total - Math.PI / 2;
}

/** SVG `points` for a regular pentagon (or n-gon) at a given radius, one vertex per axis. */
export function ringPoints(total: number, radius: number, cx: number, cy: number): string {
  return Array.from({ length: total }, (_, i) => {
    const a = angleFor(i, total);
    return `${(cx + radius * Math.cos(a)).toFixed(1)},${(cy + radius * Math.sin(a)).toFixed(1)}`;
  }).join(' ');
}

/** SVG `points` for the filled data polygon: one vertex per axis, at its support 0-100. */
export function dataPoints(values: number[], radius: number, cx: number, cy: number): string {
  const total = values.length;
  return values
    .map((v, i) => {
      const a = angleFor(i, total);
      const dist = (Math.max(0, Math.min(100, v)) / 100) * radius;
      return `${(cx + dist * Math.cos(a)).toFixed(1)},${(cy + dist * Math.sin(a)).toFixed(1)}`;
    })
    .join(' ');
}

function supportPhrase(support: number): string {
  if (support < 25) return 'not much extra support would help here';
  if (support < 50) return 'a little extra support could help here';
  if (support < 75) return 'a fair amount of extra support could help here';
  return 'a lot of extra support could help here';
}

/** The plain-language sentence shown for one axis in the accessible list. */
export function axisSentence(axis: RadarAxisDatum): string {
  const rounded = Math.round(axis.support);
  const base = `${axis.label}: ${rounded} out of 100 — ${supportPhrase(axis.support)}.`;
  return axis.confidence === 'low' ? `${base} (We do not have much to go on here yet.)` : base;
}

/** Split a label into at most two lines so it never runs off the edge of the chart. */
export function wrapLabel(label: string, max = 16): string[] {
  const words = label.split(' ');
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    if (cur && (cur + ' ' + w).length > max) {
      lines.push(cur);
      cur = w;
    } else {
      cur = cur ? cur + ' ' + w : w;
    }
  }
  if (cur) lines.push(cur);
  // Never drop words: a long label gets two longer lines instead of three short ones.
  if (lines.length > 2) return wrapLabel(label, Math.ceil(label.length / 2) + 3);
  return lines;
}

export default function Radar({ axes, size = 300 }: RadarProps) {
  // Wider than tall so the side labels have room; the pentagon sits in the middle.
  const width = size + 240;
  const height = size + 60;
  const cx = width / 2;
  const cy = height / 2 + 6;
  const radius = size / 2 - 20;
  const total = axes.length;
  const labelRadius = radius + 18;

  return (
    <figure className="radar" style={{ margin: 0 }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-hidden="true"
        style={{ maxWidth: width, display: 'block', margin: '0 auto' }}
      >
        {RINGS.map((r) => (
          <polygon
            key={r}
            points={ringPoints(total, (r / 100) * radius, cx, cy)}
            className="radar__ring"
          />
        ))}
        {axes.map((_, i) => {
          const a = angleFor(i, total);
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={cx + radius * Math.cos(a)}
              y2={cy + radius * Math.sin(a)}
              className="radar__spoke"
            />
          );
        })}
        <polygon
          points={dataPoints(
            axes.map((a) => a.support),
            radius,
            cx,
            cy,
          )}
          className="radar__fill"
        />
        {axes.map((axis, i) => {
          const a = angleFor(i, total);
          const dist = (Math.max(0, Math.min(100, axis.support)) / 100) * radius;
          return (
            <circle
              key={axis.id}
              cx={cx + dist * Math.cos(a)}
              cy={cy + dist * Math.sin(a)}
              r={5}
              className="radar__point"
            />
          );
        })}
        {axes.map((axis, i) => {
          const a = angleFor(i, total);
          const cos = Math.cos(a);
          const sin = Math.sin(a);
          const x = cx + labelRadius * cos;
          const anchor = cos > 0.3 ? 'start' : cos < -0.3 ? 'end' : 'middle';
          const lines = wrapLabel(axis.label);
          // Above the chart: stack lines upward; below or beside: stack downward.
          const y = cy + labelRadius * sin + (sin < -0.3 ? -(lines.length - 1) * 15 : sin > 0.3 ? 14 : -4);
          return (
            <text key={axis.id} x={x} y={y} textAnchor={anchor} className="radar__label">
              {lines.map((line, li) => (
                <tspan key={li} x={x} dy={li === 0 ? 0 : 15}>
                  {line}
                </tspan>
              ))}
              <tspan x={x} dy={15} className="radar__value">
                {Math.round(axis.support)}
              </tspan>
            </text>
          );
        })}
      </svg>
      <figcaption className="sr-only">
        A radar chart of five reading axes, each from 0 to 100. The numbers are listed below.
      </figcaption>
      <ul className="radar__list">
        {axes.map((axis) => (
          <li key={axis.id}>{axisSentence(axis)}</li>
        ))}
      </ul>
    </figure>
  );
}

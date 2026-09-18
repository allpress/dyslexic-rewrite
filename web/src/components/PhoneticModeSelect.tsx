import type { PhoneticMapMode } from '../api';

const LABELS: Record<PhoneticMapMode, string> = {
  off: 'Off',
  on_demand: 'On demand',
  always: 'Always',
};

export interface PhoneticModeSelectProps {
  value: PhoneticMapMode;
  onChange: (mode: PhoneticMapMode) => void;
  disabled?: boolean;
  label?: string;
}

/** Off / On demand / Always — the phonetic-map mode selector shared by the reader and Profile. */
export default function PhoneticModeSelect({
  value,
  onChange,
  disabled,
  label = 'Phonetic map',
}: PhoneticModeSelectProps) {
  return (
    <label className="phon-mode">
      <span className="phon-mode__label">{label}</span>
      <select
        value={value}
        disabled={disabled}
        aria-label={label}
        onChange={(e) => onChange(e.target.value as PhoneticMapMode)}
      >
        {(Object.keys(LABELS) as PhoneticMapMode[]).map((key) => (
          <option key={key} value={key}>
            {LABELS[key]}
          </option>
        ))}
      </select>
    </label>
  );
}

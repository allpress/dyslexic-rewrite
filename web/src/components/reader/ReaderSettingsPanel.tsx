import { useEffect, useRef, useState } from 'react';
import type { ReaderLayout } from '../../api';
import { getLayout, putLayout } from '../../api';
import { useMe } from '../../useMe';
import { ensureFontLoaded, FONT_LABELS } from '../../lib/fonts';
import {
  DEFAULT_READER_PREFS,
  READER_PREF_RANGES,
  TINT_SWATCHES,
  readerPrefsStore,
  ttsModeStore,
  useReaderPrefs,
  useTtsMode,
} from '../../lib/readerPrefs';
import { listVoices } from '../../lib/speech';
import ShortcutsPopover from './ShortcutsPopover';
import ImmersiveToggle from './ImmersiveToggle';
import StatsChip, { type ReaderStatsInput } from './StatsChip';

export interface ReaderSettingsPanelProps {
  /** 'toolbar' (default): a small "Aa" trigger that opens a popover, meant for the reader's own
   * toolbar. 'profile': the full panel rendered inline, always open, for the Profile page. */
  variant?: 'toolbar' | 'profile';
  /** When given, a small stats chip (words, reading time, sentences, reading load) is shown
   * alongside the trigger. See `StatsChip`/`computeReaderStats`. */
  stats?: ReaderStatsInput;
}

const FONT_OPTIONS: ReaderLayout['font_family'][] = ['system', 'atkinson', 'lexend', 'opendyslexic', 'mono'];

const THEME_OPTIONS: { value: ReaderLayout['theme']; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'sepia', label: 'Sepia' },
  { value: 'high_contrast', label: 'High contrast' },
  { value: 'tint', label: 'Tint' },
];

const SAVE_DEBOUNCE_MS = 400;

/**
 * The "Aa" reading-settings panel: font, size/spacing, paragraph width, colour theme, reading
 * ruler, spotlight, auto-scroll and text-to-speech voice/rate/pitch — every one a comfort
 * setting (docs/RESEARCH.md §2), never a claim. Reads and writes the shared `readerPrefsStore`
 * (see lib/readerPrefs.ts), which `Reader` applies live, so mounting this anywhere on a page
 * with a `<Reader>` is enough to make it work — no other wiring needed.
 *
 * Persistence: a signed-in reader's settings are saved to their profile (debounced
 * `PUT /api/me/layout`); a signed-out reader keeps them in `localStorage` only.
 */
export default function ReaderSettingsPanel({ variant = 'toolbar', stats }: ReaderSettingsPanelProps) {
  const prefs = useReaderPrefs();
  const ttsMode = useTtsMode();
  const { user } = useMe();
  const [open, setOpen] = useState(variant === 'profile');
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const hydratedFor = useRef<string | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const pendingPatch = useRef<Partial<ReaderLayout>>({});
  const panelRef = useRef<HTMLDivElement>(null);

  // Hydrate from the signed-in reader's saved layout once per sign-in (a fresh anonymous
  // session, or a different account, re-hydrates too).
  useEffect(() => {
    if (!user || hydratedFor.current === user.id) return;
    hydratedFor.current = user.id;
    getLayout()
      .then((res) => {
        readerPrefsStore.replace({ ...DEFAULT_READER_PREFS, ...res.layout } as ReaderLayout);
      })
      .catch(() => {
        // Offline or the request failed: keep whatever localStorage/defaults already gave us.
      });
  }, [user]);

  // Make sure the currently-selected font is actually loaded (covers both a fresh pageload
  // with a saved font, and the hydration above landing after this component's first render).
  useEffect(() => {
    ensureFontLoaded(prefs.font_family);
  }, [prefs.font_family]);

  // The voice list is often empty until the browser fires `voiceschanged`.
  useEffect(() => {
    function refresh() {
      setVoices(listVoices());
    }
    refresh();
    const synth = typeof window !== 'undefined' ? window.speechSynthesis : undefined;
    try {
      synth?.addEventListener('voiceschanged', refresh);
      return () => synth?.removeEventListener('voiceschanged', refresh);
    } catch {
      return undefined;
    }
  }, []);

  // Close the popover on outside click / Escape (toolbar variant only -- the profile variant is
  // always open, it's a page section, not a popover).
  useEffect(() => {
    if (variant !== 'toolbar' || !open) return;
    function onDocClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, variant]);

  function update(patch: Partial<ReaderLayout>) {
    readerPrefsStore.set(patch);
    if (patch.font_family) ensureFontLoaded(patch.font_family);
    if (!user) return;
    pendingPatch.current = { ...pendingPatch.current, ...patch };
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      const toSave = pendingPatch.current;
      pendingPatch.current = {};
      putLayout(toSave).catch(() => {
        // Best-effort: the change already applied locally (and to localStorage as a fallback
        // cache) even if saving it to the profile fails.
      });
    }, SAVE_DEBOUNCE_MS);
  }

  const lang = ((typeof document !== 'undefined' && document.documentElement.lang) || 'en').slice(0, 2).toLowerCase();
  const matchingVoices = voices.filter((v) => v.lang.toLowerCase().startsWith(lang));
  const voiceList = matchingVoices.length ? matchingVoices : voices;

  const trigger = (
    <div className="reader-settings-panel__trigger-row">
      {stats && <StatsChip stats={stats} />}
      <button
        type="button"
        className="btn btn--plain btn--small reader-settings-panel__toggle"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">Aa</span>
        <span className="sr-only">Reading settings</span>
      </button>
      <ShortcutsPopover />
      <ImmersiveToggle />
    </div>
  );

  const body = (
    <div className="reader-settings">
      <p className="reader-settings__disclaimer">
        Fonts and colours are comfort settings — the research says spacing helps a little and
        special fonts don&rsquo;t, so pick what feels good.
      </p>

      <fieldset className="reader-settings__group">
        <legend>Font</legend>
        <div className="reader-settings__row">
          <label htmlFor="rs-font">Typeface</label>
          <select
            id="rs-font"
            value={prefs.font_family}
            onChange={(e) => update({ font_family: e.target.value as ReaderLayout['font_family'] })}
          >
            {FONT_OPTIONS.map((f) => (
              <option key={f} value={f}>
                {FONT_LABELS[f]}
              </option>
            ))}
          </select>
        </div>
      </fieldset>

      <fieldset className="reader-settings__group">
        <legend>Size &amp; spacing</legend>
        <SliderRow
          id="rs-size"
          label="Text size"
          unit="px"
          value={prefs.font_size_px}
          range={READER_PREF_RANGES.font_size_px}
          step={1}
          onChange={(v) => update({ font_size_px: v })}
        />
        <SliderRow
          id="rs-line"
          label="Line height"
          value={prefs.line_height}
          range={READER_PREF_RANGES.line_height}
          step={0.1}
          onChange={(v) => update({ line_height: v })}
        />
        <SliderRow
          id="rs-letter"
          label="Letter spacing"
          unit="em"
          value={prefs.letter_spacing_em}
          range={READER_PREF_RANGES.letter_spacing_em}
          step={0.01}
          onChange={(v) => update({ letter_spacing_em: v })}
        />
        <SliderRow
          id="rs-word"
          label="Word spacing"
          unit="em"
          value={prefs.word_spacing_em}
          range={READER_PREF_RANGES.word_spacing_em}
          step={0.01}
          onChange={(v) => update({ word_spacing_em: v })}
        />
      </fieldset>

      <fieldset className="reader-settings__group">
        <legend>Paragraph</legend>
        <SliderRow
          id="rs-width"
          label="Width"
          unit="ch"
          value={prefs.max_line_chars}
          range={READER_PREF_RANGES.max_line_chars}
          step={1}
          onChange={(v) => update({ max_line_chars: v })}
        />
        <SliderRow
          id="rs-gap"
          label="Paragraph gap"
          unit="em"
          value={prefs.paragraph_gap_em}
          range={READER_PREF_RANGES.paragraph_gap_em}
          step={0.1}
          onChange={(v) => update({ paragraph_gap_em: v })}
        />
        <div className="reader-settings__row">
          <span id="rs-align-label">Alignment</span>
          <div className="reader-settings__seg" role="radiogroup" aria-labelledby="rs-align-label">
            {(['left', 'justify'] as const).map((a) => (
              <button
                key={a}
                type="button"
                role="radio"
                aria-checked={prefs.text_align === a}
                className={prefs.text_align === a ? 'is-active' : ''}
                onClick={() => update({ text_align: a })}
              >
                {a === 'left' ? 'Left' : 'Justify'}
              </button>
            ))}
          </div>
        </div>
      </fieldset>

      <fieldset className="reader-settings__group">
        <legend>Colour theme</legend>
        <div className="reader-settings__seg" role="radiogroup" aria-label="Colour theme">
          {THEME_OPTIONS.map((t) => (
            <button
              key={t.value}
              type="button"
              role="radio"
              aria-checked={prefs.theme === t.value}
              className={prefs.theme === t.value ? 'is-active' : ''}
              onClick={() => update({ theme: t.value })}
            >
              {t.label}
            </button>
          ))}
        </div>
        {prefs.theme === 'tint' && (
          <div className="reader-settings__swatches" role="group" aria-label="Tint colour">
            {TINT_SWATCHES.map((c) => (
              <button
                key={c}
                type="button"
                className={`reader-settings__swatch${prefs.tint_color === c ? ' is-active' : ''}`}
                style={{ background: c }}
                aria-label={`Tint ${c}`}
                aria-pressed={prefs.tint_color === c}
                onClick={() => update({ tint_color: c })}
              />
            ))}
          </div>
        )}
      </fieldset>

      <fieldset className="reader-settings__group">
        <legend>Reading ruler &amp; spotlight</legend>
        <ToggleRow
          id="rs-ruler"
          label="Reading ruler (R)"
          checked={prefs.ruler_enabled}
          onChange={(v) => update({ ruler_enabled: v })}
        />
        {prefs.ruler_enabled && (
          <>
            <SliderRow
              id="rs-ruler-h"
              label="Ruler height"
              unit="px"
              value={prefs.ruler_height_px}
              range={READER_PREF_RANGES.ruler_height_px}
              step={4}
              onChange={(v) => update({ ruler_height_px: v })}
            />
            <SliderRow
              id="rs-ruler-dim"
              label="Dim strength"
              value={prefs.ruler_dim}
              range={READER_PREF_RANGES.ruler_dim}
              step={0.05}
              onChange={(v) => update({ ruler_dim: v })}
            />
          </>
        )}
        <ToggleRow
          id="rs-spotlight"
          label="Spotlight — dims everything but this paragraph (S)"
          checked={prefs.spotlight_enabled}
          onChange={(v) => update({ spotlight_enabled: v })}
        />
      </fieldset>

      <fieldset className="reader-settings__group">
        <legend>Auto-scroll</legend>
        <SliderRow
          id="rs-scroll"
          label="Speed"
          value={prefs.autoscroll_speed}
          range={READER_PREF_RANGES.autoscroll_speed}
          step={1}
          onChange={(v) => update({ autoscroll_speed: v })}
          formatValue={(v) => (v === 0 ? 'Off' : `${v} line${v === 1 ? '' : 's'}/s`)}
        />
      </fieldset>

      <fieldset className="reader-settings__group">
        <legend>Text-to-speech</legend>
        <ToggleRow
          id="rs-tts-mode"
          label="Tap a paragraph to read from there"
          checked={ttsMode}
          onChange={(v) => ttsModeStore.set(v)}
        />
        <div className="reader-settings__row">
          <label htmlFor="rs-voice">Voice</label>
          <select id="rs-voice" value={prefs.tts_voice} onChange={(e) => update({ tts_voice: e.target.value })}>
            <option value="">Browser default</option>
            {voiceList.map((v) => (
              <option key={v.voiceURI} value={v.voiceURI}>
                {v.name} ({v.lang})
              </option>
            ))}
          </select>
        </div>
        <SliderRow
          id="rs-rate"
          label="Rate"
          value={prefs.tts_rate}
          range={READER_PREF_RANGES.tts_rate}
          step={0.1}
          onChange={(v) => update({ tts_rate: v })}
        />
        <SliderRow
          id="rs-pitch"
          label="Pitch"
          value={prefs.tts_pitch}
          range={READER_PREF_RANGES.tts_pitch}
          step={0.1}
          onChange={(v) => update({ tts_pitch: v })}
        />
      </fieldset>

      <div className="reader-settings__footer">
        <button
          type="button"
          className="btn btn--plain btn--small"
          onClick={() => update({ ...DEFAULT_READER_PREFS })}
        >
          Reset to defaults
        </button>
      </div>
    </div>
  );

  if (variant === 'profile') {
    return (
      <div className="reader-settings-panel reader-settings-panel--profile" ref={panelRef}>
        {body}
      </div>
    );
  }

  return (
    <div className="reader-settings-panel" ref={panelRef}>
      {trigger}
      {open && (
        <div className="reader-settings-panel__popover" role="dialog" aria-label="Reading settings">
          {body}
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------- small form controls */
// Kept local to this file since they're only ever used here, but written as plain, labelled,
// big-target (44px+) controls so every reading-setting stays keyboard- and screen-reader-usable.

function SliderRow({
  id,
  label,
  value,
  range,
  step,
  unit = '',
  onChange,
  formatValue,
}: {
  id: string;
  label: string;
  value: number;
  range: readonly [number, number];
  step: number;
  unit?: string;
  onChange: (v: number) => void;
  formatValue?: (v: number) => string;
}) {
  const [lo, hi] = range;
  return (
    <div className="reader-settings__row reader-settings__row--slider">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="range"
        min={lo}
        max={hi}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {/* Plain `<span>`, not `<output>` -- `<output>`'s implicit ARIA role is "status", which
          would make every slider on the page match `getByRole('status')` elsewhere. */}
      <span className="reader-settings__value" aria-hidden="true">
        {formatValue ? formatValue(value) : `${Math.round(value * 100) / 100}${unit}`}
      </span>
    </div>
  );
}

function ToggleRow({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="reader-settings__row reader-settings__row--toggle">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </div>
  );
}

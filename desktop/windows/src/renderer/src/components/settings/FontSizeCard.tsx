import { useEffect, useState } from 'react'
import { ALargeSmall, RotateCcw } from 'lucide-react'
import { getPreferences, onPreferencesChange, setPreferences } from '../../lib/preferences'
import {
  clampFontScale,
  FONT_SCALE_DEFAULT,
  FONT_SCALE_MAX,
  FONT_SCALE_MIN
} from '../../lib/fontScale'
import { SettingRow } from './SettingRow'
import { Slider } from './controls/Slider'

// General → Font Size (macOS §3.1). Scales the whole main-window UI via the root
// rem multiplier (lib/fontScale.ts). The slider + Reset button write `fontScale`;
// the app-wide Ctrl+= / Ctrl+- / Ctrl+0 shortcuts (also in fontScale.ts) write it
// too, and the subscription below keeps this card's UI in step with either path.
export function FontSizeCard(): React.JSX.Element {
  const [scale, setScale] = useState(() => clampFontScale(getPreferences().fontScale))

  // Reflect changes from every source: this card, the keyboard shortcuts, and
  // cross-window writes (all fan out through the preferences listener set).
  useEffect(() => onPreferencesChange((p) => setScale(clampFontScale(p.fontScale))), [])

  // setPreferences clamps fontScale via normalizeFontScale and the Slider only
  // emits in-range snapped values, so no write-side clamp is needed here.
  const applyScale = (next: number): void => setPreferences({ fontScale: next })
  const isDefault = scale === FONT_SCALE_DEFAULT

  return (
    <SettingRow
      icon={ALargeSmall}
      title="Font Size"
      subtitle={`Scale: ${Math.round(scale * 100)}%`}
      keywords="font size text scale zoom larger smaller accessibility readability"
      control={
        !isDefault ? (
          <button
            type="button"
            onClick={() => applyScale(FONT_SCALE_DEFAULT)}
            className="rounded-md px-1.5 py-0.5 text-[13px] font-medium transition-colors hover:bg-white/5"
            style={{ color: 'var(--info)' }}
          >
            Reset
          </button>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-4">
        {/* Slider row: small A … slider (info-tinted) … large A */}
        <Slider
          value={scale}
          onChange={applyScale}
          min={FONT_SCALE_MIN}
          max={FONT_SCALE_MAX}
          step={0.05}
          tint="var(--info)"
          ariaLabel="Font size"
          leftLabel={<span style={{ fontSize: 12, lineHeight: 1 }}>A</span>}
          rightLabel={<span style={{ fontSize: 18, lineHeight: 1 }}>A</span>}
        />

        {/* Live preview — rem-based text scales with the applied root multiplier. */}
        <p className="text-sm text-text-secondary">The quick brown fox jumps over the lazy dog</p>

        {/* Keyboard shortcut hints */}
        <div className="flex flex-col gap-1.5">
          <ShortcutHint label="Increase font size" keys={['Ctrl', '+']} />
          <ShortcutHint label="Decrease font size" keys={['Ctrl', '−']} />
          <ShortcutHint label="Reset font size" keys={['Ctrl', '0']} />
        </div>

        {/* Reset the main window to its default size */}
        <div>
          <button
            type="button"
            onClick={() => void window.omi?.resetWindowSize?.()}
            className="inline-flex items-center gap-1.5 rounded-md bg-[color:var(--bg-tertiary)] px-2.5 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-white/10"
          >
            <RotateCcw className="h-3 w-3" strokeWidth={2} />
            Reset Window Size
          </button>
        </div>
      </div>
    </SettingRow>
  )
}

function ShortcutHint(props: { label: string; keys: string[] }): React.JSX.Element {
  return (
    <div className="flex items-center gap-2 text-[13px] text-text-tertiary">
      <span>{props.label}</span>
      <span className="flex items-center gap-1">
        {props.keys.map((k) => (
          <kbd
            key={k}
            className="rounded bg-[color:var(--bg-tertiary)] px-1.5 py-0.5 font-mono text-[13px] text-text-secondary"
          >
            {k}
          </kbd>
        ))}
      </span>
    </div>
  )
}

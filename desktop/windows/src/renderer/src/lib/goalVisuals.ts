// Shared goal progress visuals + math, consumed by the Goals page and the Home
// goals widget so both render identically.
//
// `progressColor` is ported from the macOS app (`GoalsWidget.progressColor`,
// frozen v0.12.72): a discrete 5-stage threshold ramp, NOT a continuous
// gradient. Input is a 0–1 fraction; the return value is a color string meant to
// be dropped into an inline `style={{ backgroundColor }}` on the fill div.
//
// The `isCompleted` / `progressPct` / `progressLabel` helpers were lifted here
// from `pages/Goals.tsx` (unchanged) so the widget stops re-deriving them.

// Minimal structural shape shared by the generated `GoalResponse` and the
// widget's local goal type — only the fields these helpers read.
export interface GoalProgressShape {
  is_active?: boolean | null
  target_value?: number | null
  current_value?: number | null
  unit?: string | null
}

// Ported thresholds. <0.2 maps to the same muted neutral (`text-white/30`) the
// Goals card already uses for de-emphasized text — Mac uses its `textTertiary`.
export function progressColor(fraction: number): string {
  if (fraction >= 0.8) return '#22C55E' // green
  if (fraction >= 0.6) return '#84CC16' // lime
  if (fraction >= 0.4) return '#FBBF24' // yellow
  if (fraction >= 0.2) return '#F97316' // orange
  return 'rgba(255, 255, 255, 0.3)' // neutral
}

// A goal is complete when the server has archived it (is_active === false) or
// its progress has reached the target. The backend exposes no write path for
// is_active/status (PATCH 400s, no /complete route), so progress is the only
// completion signal we can both read and drive.
export function isCompleted(g: GoalProgressShape): boolean {
  if (g.is_active === false) return true
  const target = g.target_value ?? 0
  return target > 0 && (g.current_value ?? 0) >= target
}

// 0–100 progress percentage. With a target, it's current/target clamped; with
// no target, a goal is either done (100) or not started (0).
export function progressPct(g: GoalProgressShape): number {
  if (isCompleted(g)) return 100
  const target = g.target_value ?? 0
  const current = g.current_value ?? 0
  if (target > 0) return Math.max(0, Math.min(100, Math.round((current / target) * 100)))
  return 0
}

export function progressLabel(g: GoalProgressShape): string {
  const target = g.target_value ?? 0
  const current = g.current_value ?? 0
  const unit = g.unit ? ` ${g.unit}` : ''
  if (target > 0) return `${current} / ${target}${unit}`
  return `${progressPct(g)}%`
}

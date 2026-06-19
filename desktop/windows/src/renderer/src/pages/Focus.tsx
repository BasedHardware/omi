import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Target,
  Play,
  Square,
  Trash2,
  ChevronDown,
  ChevronUp,
  Clock,
  Loader,
  Brain
} from 'lucide-react'
import type { RewindFrame } from '../../../shared/types'
import { EmptyState } from '../components/ui/EmptyState'
import { cn } from '../lib/utils'
import {
  analyzeFocus,
  loadObservations,
  saveObservations,
  type FocusObservation,
  type FocusStatus
} from '../lib/focusEngine'
import { getPreferences, onPreferencesChange } from '../lib/preferences'

// ── App classification (for Rewind activity breakdown) ──────────────────────
const FOCUS_PATTERNS = [
  'code', 'cursor', 'vim', 'neovim', 'nvim', 'emacs', 'sublime', 'notepad', 'word', 'excel',
  'outlook', 'onenote', 'notion', 'obsidian', 'rider', 'intellij', 'pycharm', 'webstorm',
  'xcode', 'android studio', 'postman', 'insomnia', 'figma', 'sketch', 'affinity',
  'terminal', 'powershell', 'pwsh', 'cmd', 'wt', 'alacritty', 'git', 'gitkraken',
  'devenv', 'studio', 'blender', 'premiere', 'resolve', 'photoshop', 'lightroom',
  'docs', 'sheets', 'slides', 'linear', 'jira', 'confluence', 'trello', 'asana'
]
const DISTRACT_PATTERNS = [
  'youtube', 'netflix', 'twitch', 'hulu', 'disneyplus', 'primevideo',
  'spotify', 'vlc', 'wmplayer', 'itunes', 'foobar',
  'discord', 'twitter', 'reddit', 'instagram', 'facebook', 'tiktok', 'snapchat',
  'steam', 'epic', 'gog', 'minecraft', 'roblox', 'valorant', 'overwatch', 'fortnite',
  'xboxapp', 'xbox', 'gamelaunchpad', 'battle.net'
]

type AppClass = 'focus' | 'distract' | 'neutral'

function classifyApp(app: string): AppClass {
  const lower = app.toLowerCase()
  if (FOCUS_PATTERNS.some((p) => lower.includes(p))) return 'focus'
  if (DISTRACT_PATTERNS.some((p) => lower.includes(p))) return 'distract'
  return 'neutral'
}

// ── Time helpers ────────────────────────────────────────────────────────────
function fmtDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function fmtTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  if (diffDays === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 1)
    return `Yesterday, ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// ── Manual session storage ──────────────────────────────────────────────────
const SESSIONS_KEY = 'omi.focus.sessions.v1'

type FocusSession = {
  id: string
  label: string
  startedAt: number
  endedAt: number
  durationMs: number
}

function loadSessions(): FocusSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY)
    return raw ? (JSON.parse(raw) as FocusSession[]) : []
  } catch {
    return []
  }
}

function saveSessions(sessions: FocusSession[]): void {
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions.slice(0, 100)))
  } catch {
    /* quota */
  }
}

// ── App activity from Rewind frames ────────────────────────────────────────
type AppStat = {
  app: string
  class: AppClass
  estimatedMs: number
  frameCount: number
}

function computeAppStats(frames: RewindFrame[], captureIntervalMs: number): AppStat[] {
  if (frames.length === 0) return []
  const map = new Map<string, { class: AppClass; estimatedMs: number; frameCount: number }>()
  const sorted = [...frames].sort((a, b) => a.ts - b.ts)

  for (let i = 0; i < sorted.length; i++) {
    const f = sorted[i]
    const app = f.app || f.processName || 'Unknown'
    const next = sorted[i + 1]
    const gapMs = next ? Math.min(next.ts - f.ts, captureIntervalMs * 2) : captureIntervalMs
    const existing = map.get(app)
    if (existing) {
      existing.estimatedMs += gapMs
      existing.frameCount += 1
    } else {
      map.set(app, { class: classifyApp(app), estimatedMs: gapMs, frameCount: 1 })
    }
  }

  return Array.from(map.entries())
    .map(([app, s]) => ({ app, ...s }))
    .sort((a, b) => b.estimatedMs - a.estimatedMs)
}

// ── UI helpers ───────────────────────────────────────────────────────────────
function StatCard({
  label,
  value,
  sub,
  color
}: {
  label: string
  value: string
  sub?: string
  color: string
}): React.JSX.Element {
  return (
    <div className="surface-card p-4">
      <p className="mb-1 text-xs font-medium uppercase tracking-wider text-text-quaternary">{label}</p>
      <p className={cn('font-display text-2xl font-bold', color)}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-text-quaternary">{sub}</p>}
    </div>
  )
}

const CLASS_BADGE: Record<AppClass, { label: string; color: string }> = {
  focus: { label: 'Focus', color: 'bg-green-500/15 text-green-400' },
  distract: { label: 'Distract', color: 'bg-orange-500/15 text-orange-400' },
  neutral: { label: 'Neutral', color: 'bg-white/10 text-white/50' }
}

function AppRow({ stat, totalMs }: { stat: AppStat; totalMs: number }): React.JSX.Element {
  const pct = totalMs > 0 ? (stat.estimatedMs / totalMs) * 100 : 0
  const badge = CLASS_BADGE[stat.class]
  return (
    <div className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-white/[0.03]">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-text-primary">{stat.app}</span>
          <span className={cn('shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium', badge.color)}>
            {badge.label}
          </span>
        </div>
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={cn(
              'h-full rounded-full transition-all',
              stat.class === 'focus'
                ? 'bg-green-500'
                : stat.class === 'distract'
                  ? 'bg-orange-500'
                  : 'bg-white/30'
            )}
            style={{ width: `${pct.toFixed(1)}%` }}
          />
        </div>
      </div>
      <span className="shrink-0 text-xs text-text-tertiary">{fmtDuration(stat.estimatedMs)}</span>
    </div>
  )
}

// ── Focus status display ────────────────────────────────────────────────────
const STATUS_CONFIG: Record<
  FocusStatus,
  { label: string; dot: string; badge: string; text: string }
> = {
  focused: {
    label: 'Focused',
    dot: 'bg-green-500 animate-pulse',
    badge: 'bg-green-500/15 text-green-400 border border-green-500/20',
    text: 'text-green-400'
  },
  distracted: {
    label: 'Distracted',
    dot: 'bg-orange-500 animate-pulse',
    badge: 'bg-orange-500/15 text-orange-400 border border-orange-500/20',
    text: 'text-orange-400'
  },
  neutral: {
    label: 'Neutral',
    dot: 'bg-white/30',
    badge: 'bg-white/[0.06] text-white/60 border border-white/10',
    text: 'text-white/60'
  }
}

const METHOD_LABEL: Record<FocusObservation['method'], string> = {
  vision: 'Vision',
  llm: 'Text-OCR',
  heuristic: 'Heuristic'
}

function ObsRow({ obs }: { obs: FocusObservation }): React.JSX.Element {
  const cfg = STATUS_CONFIG[obs.status]
  return (
    <div className="flex items-start gap-3 px-3 py-2.5">
      <div className={cn('mt-1.5 h-2 w-2 shrink-0 rounded-full', cfg.dot.replace(' animate-pulse', ''))} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={cn('text-sm font-medium', cfg.text)}>{cfg.label}</span>
          {obs.app && (
            <span className="truncate text-xs text-text-quaternary">{obs.app}</span>
          )}
          <span className="shrink-0 rounded-full bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-text-quaternary">
            {METHOD_LABEL[obs.method]}
          </span>
          <span className="ml-auto shrink-0 text-xs text-text-quaternary">{fmtTime(obs.ts)}</span>
        </div>
        {obs.reasoning && (
          <p className="mt-0.5 text-xs text-text-quaternary">{obs.reasoning}</p>
        )}
        {obs.visualEvidence && (
          <p className="mt-0.5 text-xs italic text-text-quaternary opacity-60">
            {obs.visualEvidence}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────
export function Focus(): React.JSX.Element {
  // Manual timer state
  const [timerRunning, setTimerRunning] = useState(false)
  const [timerStart, setTimerStart] = useState<number | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [label, setLabel] = useState('')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Manual sessions
  const [sessions, setSessions] = useState<FocusSession[]>(() => loadSessions())
  const [showAllSessions, setShowAllSessions] = useState(false)

  // Rewind-powered activity
  const [allFrames, setAllFrames] = useState<RewindFrame[]>([])
  const [appStats, setAppStats] = useState<AppStat[]>([])
  const [rewindEnabled, setRewindEnabled] = useState<boolean | null>(null)
  const [captureIntervalMs, setCaptureIntervalMs] = useState(10_000)
  const [loadingActivity, setLoadingActivity] = useState(false)
  const [showAllApps, setShowAllApps] = useState(false)

  // Proactive focus analysis
  const [analysisEnabled, setAnalysisEnabled] = useState(
    () => getPreferences().focusAnalysisEnabled ?? false
  )
  const [analysisIntervalMin, setAnalysisIntervalMin] = useState(
    () => getPreferences().focusAnalysisIntervalMin ?? 10
  )
  const [distractionAlert, setDistractionAlert] = useState(
    () => getPreferences().focusDistractionAlert ?? false
  )
  const [visionEnabled, setVisionEnabled] = useState(
    () => getPreferences().focusVisionEnabled ?? false
  )
  const [analyzing, setAnalyzing] = useState(false)
  const [latestObs, setLatestObs] = useState<FocusObservation | null>(null)
  const [observations, setObservations] = useState<FocusObservation[]>(() => loadObservations())
  const [showAllObs, setShowAllObs] = useState(false)
  const analysisTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const prevStatusRef = useRef<FocusStatus | null>(null)

  // Load today's Rewind activity
  useEffect(() => {
    void (async () => {
      setLoadingActivity(true)
      try {
        const rs = await window.omi.rewindGetSettings()
        setRewindEnabled(rs.captureEnabled)
        setCaptureIntervalMs(rs.intervalMs)
        if (!rs.captureEnabled) return
        const todayStart = new Date()
        todayStart.setHours(0, 0, 0, 0)
        const frames = await window.omi.rewindFrames(todayStart.getTime(), Date.now())
        setAllFrames(frames)
        setAppStats(computeAppStats(frames, rs.intervalMs))
      } catch (e) {
        console.warn('[focus] activity load failed', e)
      } finally {
        setLoadingActivity(false)
      }
    })()
  }, [])

  // Subscribe to preference changes
  useEffect(() => {
    return onPreferencesChange((p) => {
      setAnalysisEnabled(p.focusAnalysisEnabled ?? false)
      setAnalysisIntervalMin(p.focusAnalysisIntervalMin ?? 10)
      setDistractionAlert(p.focusDistractionAlert ?? false)
      setVisionEnabled(p.focusVisionEnabled ?? false)
    })
  }, [])

  // Run one analysis pass
  const runAnalysis = useCallback(async (): Promise<void> => {
    if (analyzing) return
    setAnalyzing(true)
    try {
      // Use allFrames if loaded; otherwise fetch fresh (includes imagePath for vision)
      const frames =
        allFrames.length > 0
          ? allFrames
          : await window.omi.rewindFrames(Date.now() - 10 * 60 * 1000, Date.now())

      const obs = await analyzeFocus(frames, visionEnabled)
      setLatestObs(obs)

      const next = [obs, ...observations].slice(0, 60)
      setObservations(next)
      saveObservations(next)

      // Distraction alert: if two consecutive analyses are both 'distracted'
      if (
        distractionAlert &&
        obs.status === 'distracted' &&
        prevStatusRef.current === 'distracted'
      ) {
        try {
          new window.Notification('Focus alert', {
            body: `Sustained distraction detected (${obs.app}). Time to refocus?`
          })
        } catch {
          /* notifications may be blocked */
        }
      }
      prevStatusRef.current = obs.status
    } catch (e) {
      console.warn('[focus] analysis failed', e)
    } finally {
      setAnalyzing(false)
    }
  }, [analyzing, allFrames, observations, distractionAlert, visionEnabled])

  // Periodic analysis loop
  useEffect(() => {
    if (!analysisEnabled) {
      if (analysisTimerRef.current) {
        clearTimeout(analysisTimerRef.current)
        analysisTimerRef.current = null
      }
      return
    }

    // Run on mount if enabled
    void runAnalysis()

    const schedule = (): void => {
      analysisTimerRef.current = setTimeout(
        () => {
          void runAnalysis()
          schedule()
        },
        analysisIntervalMin * 60 * 1000
      )
    }
    schedule()

    return () => {
      if (analysisTimerRef.current) {
        clearTimeout(analysisTimerRef.current)
        analysisTimerRef.current = null
      }
    }
  }, [analysisEnabled, analysisIntervalMin]) // eslint-disable-line react-hooks/exhaustive-deps

  // Timer tick
  useEffect(() => {
    if (timerRunning && timerStart !== null) {
      timerRef.current = setInterval(() => {
        setElapsed(Date.now() - timerStart)
      }, 1000)
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [timerRunning, timerStart])

  const startTimer = (): void => {
    const now = Date.now()
    setTimerStart(now)
    setElapsed(0)
    setTimerRunning(true)
  }

  const stopTimer = (): void => {
    if (!timerStart) return
    const durationMs = Date.now() - timerStart
    const session: FocusSession = {
      id: crypto.randomUUID(),
      label: label.trim() || 'Focus session',
      startedAt: timerStart,
      endedAt: Date.now(),
      durationMs
    }
    const next = [session, ...sessions]
    setSessions(next)
    saveSessions(next)
    setTimerRunning(false)
    setTimerStart(null)
    setElapsed(0)
    setLabel('')
  }

  const deleteSession = (id: string): void => {
    const next = sessions.filter((s) => s.id !== id)
    setSessions(next)
    saveSessions(next)
  }

  // Derived stats from Rewind
  const focusMs = appStats.filter((a) => a.class === 'focus').reduce((s, a) => s + a.estimatedMs, 0)
  const distractMs = appStats
    .filter((a) => a.class === 'distract')
    .reduce((s, a) => s + a.estimatedMs, 0)
  const totalTrackedMs = appStats.reduce((s, a) => s + a.estimatedMs, 0)
  const focusRate =
    focusMs + distractMs > 0 ? Math.round((focusMs / (focusMs + distractMs)) * 100) : null

  const visibleSessions = showAllSessions ? sessions : sessions.slice(0, 5)
  const visibleApps = showAllApps ? appStats : appStats.slice(0, 8)
  const visibleObs = showAllObs ? observations : observations.slice(0, 8)

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <div className="mb-6 flex items-center gap-3 px-1">
        <Target className="h-6 w-6 shrink-0 text-green-400" />
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-white">Focus</h1>
          <p className="text-sm text-white/50">Track your focus sessions and app activity</p>
        </div>
      </div>

      {/* Proactive Analysis Card ─────────────────────────────────────────── */}
      {analysisEnabled && (
        <div className="mb-6 surface-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Brain className="h-4 w-4 text-text-quaternary" />
              <h2 className="font-display text-base font-semibold text-text-primary">
                Focus Analysis
              </h2>
              {latestObs && (
                <span
                  className={cn(
                    'rounded-full px-2 py-0.5 text-xs font-medium',
                    STATUS_CONFIG[latestObs.status].badge
                  )}
                >
                  {STATUS_CONFIG[latestObs.status].label}
                </span>
              )}
            </div>
            <button
              onClick={() => void runAnalysis()}
              disabled={analyzing}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-text-quaternary hover:bg-white/[0.06] hover:text-text-tertiary disabled:opacity-40"
            >
              {analyzing ? (
                <Loader className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Brain className="h-3.5 w-3.5" />
              )}
              {analyzing ? 'Analyzing…' : 'Analyze now'}
            </button>
          </div>

          {latestObs ? (
            <div>
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    'h-2.5 w-2.5 rounded-full',
                    STATUS_CONFIG[latestObs.status].dot
                  )}
                />
                <p className={cn('text-sm font-medium', STATUS_CONFIG[latestObs.status].text)}>
                  {latestObs.app || 'Unknown app'}
                </p>
                <span className="text-xs text-text-quaternary">·</span>
                <span className="text-xs text-text-quaternary">
                  {Math.round(latestObs.confidence * 100)}% confidence
                </span>
                <span className="text-xs text-text-quaternary">·</span>
                <span className="text-xs text-text-quaternary">
                  {latestObs.method === 'vision'
                    ? 'Vision'
                    : latestObs.method === 'llm'
                      ? 'Text-OCR'
                      : 'Heuristic'}
                </span>
              </div>
              {latestObs.reasoning && (
                <p className="mt-1.5 text-xs text-text-quaternary">{latestObs.reasoning}</p>
              )}
              {latestObs.visualEvidence && (
                <p className="mt-1 text-xs italic text-text-quaternary opacity-70">
                  📷 {latestObs.visualEvidence}
                </p>
              )}
              {visionEnabled && latestObs.method !== 'vision' && (
                <p className="mt-1 text-xs text-text-quaternary opacity-50">
                  Vision unavailable — used {latestObs.method === 'llm' ? 'text-OCR' : 'heuristic'} fallback
                </p>
              )}
              <p className="mt-1.5 text-xs text-text-quaternary opacity-60">
                Last checked {fmtTime(latestObs.ts)} · checks every {analysisIntervalMin} min
              </p>
            </div>
          ) : (
            <p className="text-sm text-text-quaternary">
              {analyzing
                ? 'Analyzing recent screen activity…'
                : 'Click "Analyze now" to detect your current focus state.'}
            </p>
          )}
        </div>
      )}

      {/* Manual Timer ─────────────────────────────────────────────────────── */}
      <div className="mb-6 surface-card p-5">
        <div className="mb-4 flex items-center gap-3">
          <div
            className={cn(
              'h-2.5 w-2.5 rounded-full transition-colors',
              timerRunning ? 'animate-pulse bg-green-500' : 'bg-white/20'
            )}
          />
          <h2 className="font-display text-base font-semibold text-text-primary">
            {timerRunning ? 'Session in progress' : 'Start a focus session'}
          </h2>
        </div>

        {!timerRunning && (
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="What are you focusing on? (optional)"
            className="mb-4 w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-text-primary placeholder:text-text-quaternary focus:border-white/20 focus:outline-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter') startTimer()
            }}
          />
        )}

        <div className="flex items-center gap-4">
          <div className="font-display tabular-nums text-3xl font-bold text-text-primary">
            {fmtDuration(timerRunning ? elapsed : 0)}
          </div>
          <button
            onClick={timerRunning ? stopTimer : startTimer}
            className={cn(
              'flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-colors',
              timerRunning
                ? 'bg-orange-500/20 text-orange-400 hover:bg-orange-500/30'
                : 'bg-[color:var(--accent)] text-white hover:opacity-90'
            )}
          >
            {timerRunning ? (
              <>
                <Square className="h-4 w-4" />
                Stop
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Start
              </>
            )}
          </button>
          {timerRunning && label && (
            <span className="text-sm text-text-secondary">{label}</span>
          )}
        </div>
      </div>

      {/* Today's Activity (Rewind-powered) ────────────────────────────────── */}
      {rewindEnabled === false ? (
        <div className="mb-6 rounded-xl border border-dashed border-white/10 p-6 text-center">
          <Clock className="mx-auto mb-3 h-8 w-8 text-text-quaternary" />
          <p className="mb-1 text-sm font-medium text-text-secondary">
            App activity tracking requires Rewind
          </p>
          <p className="text-xs text-text-quaternary">
            Enable Screen Recording in the sidebar to see your app time breakdown.
          </p>
        </div>
      ) : rewindEnabled === true && appStats.length > 0 ? (
        <div className="mb-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-quaternary">
            Today&apos;s Activity
          </h2>

          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="Focus time"
              value={focusMs > 0 ? fmtDuration(focusMs) : '—'}
              color="text-green-400"
            />
            <StatCard
              label="Distraction time"
              value={distractMs > 0 ? fmtDuration(distractMs) : '—'}
              color="text-orange-400"
            />
            <StatCard
              label="Focus rate"
              value={focusRate !== null ? `${focusRate}%` : '—'}
              sub={
                focusRate !== null
                  ? focusRate >= 70
                    ? 'Great focus!'
                    : focusRate >= 40
                      ? 'Moderate'
                      : 'Low focus'
                  : undefined
              }
              color={
                focusRate === null
                  ? 'text-text-quaternary'
                  : focusRate >= 70
                    ? 'text-green-400'
                    : focusRate >= 40
                      ? 'text-yellow-400'
                      : 'text-orange-400'
              }
            />
            <StatCard
              label="Tracked time"
              value={totalTrackedMs > 0 ? fmtDuration(totalTrackedMs) : '—'}
              color="text-text-primary"
            />
          </div>

          <div className="surface-card divide-y divide-white/[0.04]">
            {visibleApps.map((stat) => (
              <AppRow key={stat.app} stat={stat} totalMs={totalTrackedMs} />
            ))}
          </div>

          {appStats.length > 8 && (
            <button
              onClick={() => setShowAllApps((v) => !v)}
              className="mt-2 flex w-full items-center justify-center gap-1.5 py-2 text-xs text-text-quaternary hover:text-text-tertiary"
            >
              {showAllApps ? (
                <>
                  <ChevronUp className="h-3.5 w-3.5" /> Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-3.5 w-3.5" /> Show all {appStats.length} apps
                </>
              )}
            </button>
          )}
          {!loadingActivity && (
            <p className="mt-2 text-center text-[10px] text-text-quaternary">
              Powered by Rewind OCR data — time estimates based on captured screen frames (
              {captureIntervalMs / 1000}s interval)
            </p>
          )}
        </div>
      ) : rewindEnabled === true && !loadingActivity && appStats.length === 0 ? (
        <div className="mb-6 rounded-xl border border-dashed border-white/10 p-6 text-center">
          <p className="text-sm text-text-quaternary">
            No screen activity captured today yet. Rewind will start tracking as you work.
          </p>
        </div>
      ) : null}

      {/* Observations History ──────────────────────────────────────────────── */}
      {observations.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-quaternary">
            Recent Analysis ({observations.length})
          </h2>
          <div className="surface-card divide-y divide-white/[0.04]">
            {visibleObs.map((obs) => (
              <ObsRow key={obs.ts} obs={obs} />
            ))}
          </div>
          {observations.length > 8 && (
            <button
              onClick={() => setShowAllObs((v) => !v)}
              className="mt-2 flex w-full items-center justify-center gap-1.5 py-2 text-xs text-text-quaternary hover:text-text-tertiary"
            >
              {showAllObs ? (
                <>
                  <ChevronUp className="h-3.5 w-3.5" /> Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-3.5 w-3.5" /> Show all {observations.length}
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* Session History ────────────────────────────────────────────────── */}
      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-quaternary">
          Session History ({sessions.length})
        </h2>

        {sessions.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No sessions yet"
            description="Start a focus timer above. Sessions are saved here so you can track your deep work over time."
          />
        ) : (
          <>
            <div className="space-y-2">
              {visibleSessions.map((s) => (
                <div
                  key={s.id}
                  className="surface-card flex items-center gap-4 px-4 py-3"
                >
                  <div
                    className="h-2 w-2 shrink-0 rounded-full bg-green-500"
                    title="Completed session"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-text-primary">{s.label}</p>
                    <p className="text-xs text-text-quaternary">{fmtTime(s.startedAt)}</p>
                  </div>
                  <span className="shrink-0 text-sm font-semibold text-text-secondary">
                    {fmtDuration(s.durationMs)}
                  </span>
                  <button
                    onClick={() => deleteSession(s.id)}
                    className="shrink-0 rounded-lg p-1.5 text-text-quaternary hover:bg-white/[0.06] hover:text-red-400"
                    aria-label="Delete session"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>

            {sessions.length > 5 && (
              <button
                onClick={() => setShowAllSessions((v) => !v)}
                className="mt-2 flex w-full items-center justify-center gap-1.5 py-2 text-xs text-text-quaternary hover:text-text-tertiary"
              >
                {showAllSessions ? (
                  <>
                    <ChevronUp className="h-3.5 w-3.5" /> Show less
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3.5 w-3.5" /> Show all {sessions.length} sessions
                  </>
                )}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}

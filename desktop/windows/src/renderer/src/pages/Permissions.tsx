import { useEffect, useState } from 'react'
import { Monitor, Mic, ShieldCheck, CheckCircle, AlertTriangle, ExternalLink } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { RewindSettings } from '../../../shared/types'
import { getPreferences, onPreferencesChange } from '../lib/preferences'

type PermStatus = 'granted' | 'denied' | 'unknown'

type PermRow = {
  id: string
  icon: typeof Monitor
  label: string
  description: string
  status: PermStatus
  enabled: boolean
  action?: () => void
  actionLabel?: string
}

export function Permissions(): React.JSX.Element {
  const navigate = useNavigate()
  const [rewind, setRewind] = useState<RewindSettings | null>(null)
  const [micOn, setMicOn] = useState(() => !!getPreferences().continuousRecording)

  useEffect(() => {
    void window.omi.rewindGetSettings().then(setRewind)
  }, [])

  useEffect(() => {
    return onPreferencesChange((p) => setMicOn(!!p.continuousRecording))
  }, [])

  const screenGranted: PermStatus =
    rewind === null ? 'unknown' : rewind.captureEnabled ? 'granted' : 'denied'
  const micGranted: PermStatus = micOn ? 'granted' : 'denied'

  const rows: PermRow[] = [
    {
      id: 'screen',
      icon: Monitor,
      label: 'Screen Recording',
      description:
        'Allows Omi to capture your screen for Rewind (local timeline) and Focus tracking. Frames are stored only on this PC and never uploaded.',
      status: screenGranted,
      enabled: !!rewind?.captureEnabled,
      action: () => navigate('/settings'),
      actionLabel: screenGranted === 'granted' ? 'Manage in Settings' : 'Enable in Settings → Rewind',
    },
    {
      id: 'mic',
      icon: Mic,
      label: 'Microphone',
      description:
        'Allows Omi to listen continuously and transcribe speech into conversations. Toggle in Settings → Rewind or use the Microphone switch in the sidebar.',
      status: micGranted,
      enabled: micOn,
      action: () => navigate('/settings'),
      actionLabel: micGranted === 'granted' ? 'Manage in Settings' : 'Enable in Settings → Rewind',
    },
  ]

  const grantedCount = rows.filter((r) => r.status === 'granted').length
  const allGranted = grantedCount === rows.length

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      {/* Header */}
      <div className="mb-8 flex items-center gap-4 px-1">
        <div
          className={[
            'flex h-11 w-11 items-center justify-center rounded-2xl',
            allGranted ? 'bg-green-500/15' : 'bg-amber-500/15',
          ].join(' ')}
        >
          <ShieldCheck
            className={['h-5 w-5', allGranted ? 'text-green-400' : 'text-amber-400'].join(' ')}
          />
        </div>
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-white">Permissions</h1>
          <p className="text-sm text-white/50">
            {allGranted
              ? 'All permissions granted — Omi is fully operational.'
              : `${grantedCount}/${rows.length} permissions granted`}
          </p>
        </div>
      </div>

      {/* Permission rows */}
      <div className="mx-auto w-full max-w-xl space-y-3">
        {rows.map((row) => {
          const Icon = row.icon
          const isGranted = row.status === 'granted'
          return (
            <div
              key={row.id}
              className={[
                'rounded-2xl border p-5 transition-colors',
                isGranted
                  ? 'border-white/[0.07] bg-white/[0.03]'
                  : 'border-amber-500/20 bg-amber-500/[0.05]',
              ].join(' ')}
            >
              <div className="flex items-start gap-4">
                <div
                  className={[
                    'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
                    isGranted ? 'bg-white/[0.06]' : 'bg-amber-500/10',
                  ].join(' ')}
                >
                  <Icon
                    className={['h-5 w-5', isGranted ? 'text-white/60' : 'text-amber-400'].join(' ')}
                    strokeWidth={1.75}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-text-primary">{row.label}</p>
                    {isGranted ? (
                      <CheckCircle className="h-4 w-4 shrink-0 text-green-400" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
                    )}
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-text-tertiary">{row.description}</p>
                  {row.action && (
                    <button
                      onClick={row.action}
                      className={[
                        'mt-3 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                        isGranted
                          ? 'bg-white/[0.06] text-text-tertiary hover:bg-white/10 hover:text-text-secondary'
                          : 'bg-amber-500/15 text-amber-300 hover:bg-amber-500/25',
                      ].join(' ')}
                    >
                      {row.actionLabel}
                      <ExternalLink className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}

        {/* Privacy note */}
        <div className="rounded-xl bg-white/[0.03] p-4 text-xs leading-relaxed text-text-quaternary">
          <p className="mb-1 font-medium text-text-tertiary">Your privacy matters</p>
          <p>
            Screen recordings are stored locally on this PC and never uploaded to the cloud unless
            you explicitly enable Screen Activity → Memories. Microphone audio is streamed to the
            Omi backend for transcription only when continuous recording is on.
          </p>
        </div>
      </div>
    </div>
  )
}

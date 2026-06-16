import { useEffect, useState } from 'react'
import { CheckCircle2, AlertCircle, Info, X, AlertTriangle } from 'lucide-react'
import { onToast, dismissToast, type Toast } from '../../lib/toast'

const toneStyle: Record<Toast['tone'], { ring: string; Icon: typeof Info }> = {
  info: { ring: 'border-white/15', Icon: Info },
  success: { ring: 'border-success/30 bg-success/5', Icon: CheckCircle2 },
  warn: { ring: 'border-warning/30 bg-warning/5', Icon: AlertTriangle },
  error: { ring: 'border-error/30 bg-error/5', Icon: AlertCircle }
}

export function ToastHost(): React.JSX.Element | null {
  const [toasts, setToasts] = useState<Toast[]>([])

  useEffect(() => onToast(setToasts), [])

  if (toasts.length === 0) return null

  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-[100] flex flex-col gap-2">
      {toasts.map((t) => {
        const { ring, Icon } = toneStyle[t.tone]
        return (
          <div
            key={t.id}
            className={`glass pointer-events-auto flex w-80 items-start gap-3 border px-4 py-3 shadow-2xl animate-fade-in ${ring}`}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-white/85" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-white/95">{t.title}</div>
              {t.body && (
                <div className="mt-0.5 break-words text-xs leading-relaxed text-white/65">
                  {t.body}
                </div>
              )}
            </div>
            <button
              onClick={() => dismissToast(t.id)}
              className="-mr-1 -mt-1 rounded-md p-1 text-white/45 hover:bg-white/10 hover:text-white"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}

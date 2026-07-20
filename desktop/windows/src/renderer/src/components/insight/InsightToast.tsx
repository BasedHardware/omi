// src/renderer/src/components/insight/InsightToast.tsx
import { useEffect, useRef, useState } from 'react'
import type { InsightPayload } from '../../../../shared/types'
import { insights } from '../../lib/native'
import './insight-toast.css'

export function InsightToast(): React.JSX.Element {
  const [insight, setInsight] = useState<InsightPayload | null>(null)
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearDismiss = (): void => {
    if (dismissTimer.current) clearTimeout(dismissTimer.current)
    dismissTimer.current = null
  }
  const scheduleDismiss = (): void => {
    clearDismiss()
    dismissTimer.current = setTimeout(() => void insights.dismiss(), 8_000)
  }

  useEffect(() => {
    document.body.classList.add('insight-toast-body')
    const off = insights.onShown(setInsight)
    return () => {
      document.body.classList.remove('insight-toast-body')
      off()
    }
  }, [])

  useEffect(() => {
    if (insight) scheduleDismiss()
    return clearDismiss
  }, [insight])

  if (!insight) return <div className="insight-toast-body" />

  return (
    <div
      className="insight-card"
      onMouseEnter={clearDismiss}
      onMouseLeave={scheduleDismiss}
    >
      <div className="insight-head">
        <span className="insight-cat">{insight.category}</span>
        <button className="insight-x" onClick={() => void insights.dismiss()} aria-label="Dismiss">
          ✕
        </button>
      </div>
      <div className="insight-headline">{insight.headline}</div>
      <div className="insight-advice">{insight.advice}</div>
      <div className="insight-foot">{insight.sourceApp}</div>
    </div>
  )
}

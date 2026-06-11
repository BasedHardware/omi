// src/renderer/src/components/insight/InsightToast.tsx
import { useEffect, useState } from 'react'
import type { InsightPayload } from '../../../../shared/types'
import './insight-toast.css'

export function InsightToast(): React.JSX.Element {
  const [insight, setInsight] = useState<InsightPayload | null>(null)

  useEffect(() => {
    document.body.classList.add('insight-toast-body')
    const off = window.omi.onInsightShow((p) => setInsight(p))
    return () => {
      document.body.classList.remove('insight-toast-body')
      off()
    }
  }, [])

  if (!insight) return <div className="insight-toast-body" />

  return (
    <div
      className="insight-card"
      onMouseEnter={() => window.omi.insightHoverStart()}
      onMouseLeave={() => window.omi.insightHoverEnd()}
    >
      <div className="insight-head">
        <span className="insight-cat">{insight.category}</span>
        <button className="insight-x" onClick={() => window.omi.insightDismiss()} aria-label="Dismiss">
          ✕
        </button>
      </div>
      <div className="insight-headline">{insight.headline}</div>
      <div className="insight-advice">{insight.advice}</div>
      <div className="insight-foot">{insight.sourceApp}</div>
    </div>
  )
}

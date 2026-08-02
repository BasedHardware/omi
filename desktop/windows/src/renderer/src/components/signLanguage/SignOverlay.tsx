import { useEffect, useRef, useState } from 'react'
import { SignAvatar } from './SignAvatar'
import { SignWritingView } from './SignWritingView'
import type { TranslationResult, SignGloss } from '../../../../shared/types'

const FALLBACK_POSE_HOLD_MS = 6000

export function SignLanguageOverlay(): React.JSX.Element {
  const [currentGloss, setCurrentGloss] = useState<string>('IDLE')
  const [currentSWR, setCurrentSWR] = useState<string>('')
  const [fullSWR, setFullSWR] = useState<string>('')
  const [poseUrl, setPoseUrl] = useState<string | null>(null)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  useEffect(() => {
    const unsubscribe = window.omi.onDeepgramSignUpdate((result: TranslationResult) => {
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []

      setFullSWR(result.swrFull || '')
      setPoseUrl(result.poseUrl || null)

      if (result.poseUrl) {
        setCurrentGloss('SIGNING')
      }

      result.glosses.forEach((g: SignGloss) => {
        timersRef.current.push(
          setTimeout(() => {
            setCurrentGloss(g.gloss)
            setCurrentSWR(g.swr || '')
          }, g.timestamp * 1000)
        )
      })

      const totalDuration =
        result.glosses.length > 0
          ? result.glosses[result.glosses.length - 1].timestamp +
            result.glosses[result.glosses.length - 1].duration
          : 0
      const resetDelay = Math.max(totalDuration * 1000, result.poseUrl ? FALLBACK_POSE_HOLD_MS : 0)

      timersRef.current.push(
        setTimeout(() => {
          setCurrentGloss('IDLE')
          setCurrentSWR('')
          setPoseUrl(null)
        }, resetDelay)
      )
    })

    return () => {
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []
      unsubscribe()
    }
  }, [])

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        width: '300px',
        height: '340px',
        zIndex: 99999,
        borderRadius: '20px',
        overflow: 'hidden',
        boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
        background: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255,255,255,0.1)',
        display: 'flex',
        flexDirection: 'column',
        pointerEvents: 'none'
      }}
    >
      <div
        style={{
          padding: '8px 10px',
          textAlign: 'center',
          color: 'white',
          fontSize: '11px',
          fontWeight: 'bold',
          background: 'rgba(0,0,0,0.3)'
        }}
      >
        {currentGloss}
      </div>
      <div style={{ flex: 1 }}>
        <SignAvatar poseUrl={poseUrl} />
      </div>
      <div
        style={{
          height: '60px',
          background: 'rgba(0,0,0,0.4)',
          borderTop: '1px solid rgba(255,255,255,0.1)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center'
        }}
      >
        <SignWritingView swr={currentSWR || fullSWR} />
      </div>
    </div>
  )
}

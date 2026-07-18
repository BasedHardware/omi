import { useEffect, useRef, useState } from 'react'
import { SignAvatar } from './SignAvatar'
import { SignWritingView } from './SignWritingView'
import { TranslationResult } from '../../../../shared/types'

const FALLBACK_POSE_HOLD_MS = 6000

export function SignLanguageOverlay() {
  const [currentGloss, setCurrentGloss] = useState<string>('IDLE')
  const [currentSWR, setCurrentSWR] = useState<string>('')
  const [fullSWR, setFullSWR] = useState<string>('')
  const [poseUrl, setPoseUrl] = useState<string | null>(null)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  useEffect(() => {
    console.log('[SignLanguageOverlay] Component mounted');
    const unsubscribe = window.omi.onDeepgramSignUpdate((result: TranslationResult) => {
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []

      console.log('[SignOverlay] Received sign update event from IPC:', result);
      setFullSWR(result.swrFull || '');
      setPoseUrl(result.poseUrl || null);
      
      if (result.poseUrl) {
        console.log('[SignOverlay] Pose URL present, setting state to SIGNING');
        setCurrentGloss('SIGNING');
      }

      // Sequence through the glosses
      result.glosses.forEach((g: any) => {
        timersRef.current.push(setTimeout(() => {
          console.log('[SignOverlay] Updating gloss to:', g.gloss);
          setCurrentGloss(g.gloss);
          setCurrentSWR(g.swr || '');
        }, g.timestamp * 1000))
      });

      // Reset to IDLE after the last sign
      const totalDuration = result.glosses.length > 0 
        ? result.glosses[result.glosses.length - 1].timestamp + result.glosses[result.glosses.length - 1].duration 
        : 0;
      const resetDelay = Math.max(totalDuration * 1000, result.poseUrl ? FALLBACK_POSE_HOLD_MS : 0)
      
      timersRef.current.push(setTimeout(() => {
        console.log('[SignOverlay] Resetting to IDLE');
        setCurrentGloss('IDLE');
        setCurrentSWR('');
        setPoseUrl(null);
      }, resetDelay))
    });

    return () => {
      console.log('[SignLanguageOverlay] Component unmounting');
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []
      unsubscribe();
    };
  }, []);

  return (
    <div style={{ 
      position: 'fixed', 
      bottom: '20px', 
      right: '20px', 
      width: '300px', 
      height: '500px', // Increased height to accommodate SWR
      zIndex: 99999,
      borderRadius: '20px',
      overflow: 'hidden',
      boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
      background: 'rgba(0,0,0,0.5)',
      backdropFilter: 'blur(10px)',
      border: '2px solid red', // DEBUG BORDER
      display: 'flex',
      flexDirection: 'column',
      pointerEvents: 'none' // Ensure it doesn't block clicks on the app
    }}>
      <div style={{ 
        padding: '10px', 
        textAlign: 'center', 
        color: 'white', 
        fontSize: '12px', 
        fontWeight: 'bold',
        background: 'rgba(0,0,0,0.3)'
      }}>
        SIGN LANGUAGE TRANSLATOR: {currentGloss}
      </div>
      <div style={{ flex: 1 }}>
        <SignAvatar poseUrl={poseUrl} />
      </div>
      <div style={{ 
        height: '100px', 
        background: 'rgba(0,0,0,0.4)', 
        borderTop: '1px solid rgba(255,255,255,0.1)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center'
      }}>
        <SignWritingView swr={currentSWR || fullSWR} />
      </div>
    </div>
  )
}

import { useEffect, useState, useRef } from 'react'

type SignVideoProps = {
  videoUrl: string | null
}

export function SignVideo({ videoUrl }: SignVideoProps) {
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    console.log('[SignVideo] Received videoUrl:', videoUrl);
    if (videoUrl) {
      // Directly use the URL to avoid potential blob issues, 
      // since CSP now allows data:
      setResolvedUrl(videoUrl);
    } else {
      setResolvedUrl(null);
    }
  }, [videoUrl]);

  useEffect(() => {
    if (videoRef.current && resolvedUrl) {
      console.log('[SignVideo] Attempting to play video with src:', resolvedUrl);
      videoRef.current.play().catch(e => {
        console.error('[SignVideo] Playback failed:', e);
      });
    }
  }, [resolvedUrl]);

  if (!videoUrl || !resolvedUrl) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-xs italic">
        Waiting for translation...
      </div>
    )
  }

  return (
    <div className="absolute inset-0 flex items-center justify-center bg-transparent">
      <video 
        ref={videoRef}
        key={resolvedUrl}
        src={resolvedUrl} 
        autoPlay 
        loop 
        muted 
        playsInline
        className="w-full h-full object-contain"
        style={{ maxHeight: '100%', maxWidth: '100%' }}
        onError={(e) => console.error('[SignVideo] Video load error:', e)}
        onCanPlay={() => console.log('[SignVideo] Video can play now')}
      />
    </div>
  )
}

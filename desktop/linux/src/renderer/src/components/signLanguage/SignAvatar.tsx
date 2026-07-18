import { useEffect, useState, useRef } from 'react'
import { resolveOmiAsset } from '../../utils/assetResolver'

type SignAvatarProps = {
  poseUrl: string | null
}

export function SignAvatar({ poseUrl }: SignAvatarProps) {
  const [error, setError] = useState<string | null>(null)
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(null)
  const viewerRef = useRef<any>(null)

  useEffect(() => {
    async function updatePose() {
      if (poseUrl) {
        try {
          let resolved: string | null = poseUrl;
          if (poseUrl.startsWith('data:')) {
            // IMPORTANT: Do NOT call fetch() on a data: URI here. In Electron/Linux
            // (and some Chromium builds) fetch() on a large data: URI throws
            // "Failed to fetch", which is exactly the bug we're fixing. Instead,
            // decode the base64 payload directly into a Blob and make an object URL.
            try {
              const comma = poseUrl.indexOf(',');
              const meta = poseUrl.slice(0, comma);
              const data = poseUrl.slice(comma + 1);
              const isBase64 = meta.includes(';base64');
              let blob: Blob;
              if (isBase64) {
                const bin = atob(data);
                const bytes = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                const mime = meta.slice(meta.indexOf(':') + 1, meta.indexOf(';')) || 'application/octet-stream';
                blob = new Blob([bytes], { type: mime });
              } else {
                blob = new Blob([decodeURIComponent(data)], { type: 'text/plain' });
              }
              resolved = URL.createObjectURL(blob);
            } catch (e) {
              console.warn('[SignAvatar] Failed to decode data URI to Blob, using original:', e);
              resolved = poseUrl;
            }
          } else {
            // For localhost URLs (our local renderer-server poses), pass
            // directly to pose-viewer — it does its own fetch() which works for
            // localhost (unlike data:/blob: URIs in this Electron build).
            if (poseUrl.startsWith('http://localhost') || poseUrl.startsWith('https://localhost')) {
              resolved = poseUrl
            } else {
              resolved = await resolveOmiAsset(poseUrl);
            }
          }
          
          setResolvedUrl(resolved);
          if (viewerRef.current && resolved) {
            viewerRef.current.setAttribute('src', resolved);
          }
        } catch (e: any) {
          console.error('[SignAvatar] updatePose FAILED:', e?.message, '| name:', e?.name);
          setError(e?.message || String(e));
        }
      } else {
        setResolvedUrl(null);
      }
    }
    updatePose();
  }, [poseUrl]);

  // Surface unhandled promise rejections from the pose-viewer web component
  // (its internal fetch/src parse can reject asynchronously and would otherwise
  // be swallowed, leaving a blank canvas with no explanation).
  useEffect(() => {
    const onReject = (e: PromiseRejectionEvent) => {
      const msg = e?.reason?.message || String(e?.reason);
      if (/pose|fetch|webgl|context|avatar/i.test(msg)) {
        console.error('[SignAvatar] unhandled rejection:', msg);
        setError(msg);
      }
    };
    window.addEventListener('unhandledrejection', onReject);
    return () => window.removeEventListener('unhandledrejection', onReject);
  }, []);


  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-500 text-xs italic p-4 text-center">
        Avatar error: {error}
      </div>
    );
  }

  if (!poseUrl) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-xs italic">
        Waiting for translation...
      </div>
    );
  }

  return (
      <div className="absolute inset-0 flex items-center justify-center bg-transparent">
        {resolvedUrl ? (
          <pose-viewer
            ref={viewerRef}
            src={resolvedUrl}
            style={{ width: '100%', height: '100%', display: 'block' }}
            onError={(e: any) => {
              const msg = e?.message || e?.detail?.message || 'pose-viewer error';
              console.error('[SignAvatar] pose-viewer element error event:', msg);
              setError(msg);
            }}
          />
        ) : (
        <div className="flex items-center justify-center text-xs italic text-gray-400">
          Loading pose asset...
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef } from 'react'

type AvatarSandboxProps = {
  poseUrl: string | null
}

async function resolveSrc(url: string | null): Promise<string | null> {
  if (!url) return null;
  if (!url.startsWith('http')) return url;

  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Fetch failed: ${response.statusText}`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  } catch (e) {
    console.error('[AvatarSandbox] Failed to resolve remote pose URL, using original:', e);
    return url;
  }
}

export function AvatarSandbox({ poseUrl }: AvatarSandboxProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    if (!iframeRef.current) return

    const html = `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="UTF-8">
          <style>
            body, html { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: transparent; font-family: sans-serif; }
            pose-viewer { 
              width: 100vw; 
              height: 100vh; 
              display: block; 
              --pv-bg-color: transparent;
            }
            #status { 
              position: absolute; top: 10px; left: 10px; 
              background: rgba(0,0,0,0.8); color: #00ff00; 
              padding: 6px 10px; border-radius: 4px; 
              font-size: 12px; z-index: 1000; pointer-events: none;
              border: 1px solid #00ff00;
              font-family: monospace;
            }
          </style>
          <script type="module">
            async function init() {
              const status = document.getElementById('status');
              console.log('[Sandbox] Starting init...');
              try {
                status.innerText = 'Loading pose-viewer...';
                const script = document.createElement('script');
                script.src = 'https://cdn.jsdelivr.net/npm/pose-viewer@1.2.0/loader.js';
                script.async = true;
                
                await new Promise((resolve, reject) => {
                  script.onload = resolve;
                  script.onerror = () => reject(new Error('Failed to load pose-viewer script from CDN'));
                  document.head.appendChild(script);
                });

                if (window.defineCustomElements) {
                  await window.defineCustomElements();
                } else {
                  const { defineCustomElements } = await import('https://cdn.jsdelivr.net/npm/pose-viewer@1.2.0/loader.js');
                  await defineCustomElements();
                }

                status.innerText = 'Pose-viewer registered';
                console.log('[Sandbox] Custom elements registered');
              } catch (e) {
                status.innerText = 'Error: ' + e.message;
                console.error('[Sandbox] Init failed:', e);
                return;
              }

              window.addEventListener('message', (event) => {
                const { type, url } = event.data;
                if (type === 'set-pose') {
                  const viewer = document.querySelector('pose-viewer');
                  if (viewer) {
                    status.innerText = 'Setting pose...';
                    viewer.src = url;
                    viewer.setAttribute('src', url);
                    console.log('[Sandbox] Pose URL set to:', url);
                    setTimeout(() => {
                      status.innerText = 'Pose updated';
                    }, 1000);
                  } else {
                    status.innerText = 'Error: pose-viewer element not found';
                  }
                }
              });
            }
            // Wrap in a try-catch to ensure we see if the script itself fails to load
            try {
              init();
            } catch (e) {
              console.error('[Sandbox] Script execution error:', e);
              document.getElementById('status').innerText = 'Script Error: ' + e.message;
            }
          </script>
        </head>
        <body>
          <div id="status">Initializing...</div>
          <pose-viewer renderer="svg"></pose-viewer>
        </body>
      </html>
    `
    
    const blob = new Blob([html], { type: 'text/html' });
    iframeRef.current.src = URL.createObjectURL(blob);

    return () => {
      if (iframeRef.current) {
        URL.revokeObjectURL(iframeRef.current.src);
      }
    }
  }, [])

  useEffect(() => {
    async function updatePose() {
      if (iframeRef.current && poseUrl) {
        const resolvedUrl = await resolveSrc(poseUrl);
        iframeRef.current.contentWindow?.postMessage({ type: 'set-pose', url: resolvedUrl }, '*')
      }
    }
    updatePose();
  }, [poseUrl])

  return (
    <iframe
      ref={iframeRef}
      style={{ width: '100%', height: '100%', border: 'none', background: 'transparent' }}
    />
  )
}

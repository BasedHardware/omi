import { useEffect, useState } from 'react'

type BrandImageProps = {
  src: string
  alt?: string
  className?: string
  style?: React.CSSProperties
  // Shown only if the image can't load at all (after the cache-bust retry). Defaults
  // to a neutral inline-SVG mark so a broken-image glyph is never what renders.
  fallback?: React.ReactNode
}

// A neutral, monochrome placeholder mark (currentColor, half opacity). Clearly a
// "logo didn't load" stand-in — never Chromium's broken-image sad-face box.
function DefaultBrandFallback({
  className,
  style
}: {
  className?: string
  style?: React.CSSProperties
}): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className={className} style={style} aria-hidden role="img">
      <rect
        x="2"
        y="2"
        width="20"
        height="20"
        rx="6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.5"
      />
      <circle cx="12" cy="12" r="4" fill="currentColor" opacity="0.5" />
    </svg>
  )
}

// Brand images (the omi mark/logo) are the app's most visible assets, and the
// most visible failure. In dev they're served by the Vite dev server as a source
// asset URL, so a dev-server restart or an HMR full-reload race can 404 that URL
// for a beat; and a GPU-process reset can drop an ALREADY-decoded image's raster
// even though its <img> loaded fine. Either way Chromium paints the broken-image
// placeholder (the white box + sad face — the same class of failure as a lost
// WebGL canvas). Guard both:
//   • onError → retry once with a cache-bust (recovers the transient 404), then
//     fall back to inline content (never a broken glyph).
//   • GPU reset → re-decode (cache-bust) since a broken raster fires no error.
export function BrandImage({
  src,
  alt = '',
  className,
  style,
  fallback
}: BrandImageProps): React.JSX.Element {
  // 0 = original URL, ≥1 = cache-busted retry.
  const [bust, setBust] = useState(0)
  const [failed, setFailed] = useState(false)

  // A new src is a fresh image — clear any prior failure/retry state. Adjusting
  // state during render on a changed prop (not in an effect) is React's
  // recommended pattern and avoids a wasted render with stale retry state.
  const [prevSrc, setPrevSrc] = useState(src)
  if (src !== prevSrc) {
    setPrevSrc(src)
    setBust(0)
    setFailed(false)
  }

  useEffect(() => {
    // A GPU reset can silently break an already-decoded image; force a re-decode.
    const off = window.omi?.onGpuContextLost?.(() => {
      setFailed(false)
      setBust((b) => b + 1)
    })
    return () => off?.()
  }, [])

  if (failed) {
    return <>{fallback ?? <DefaultBrandFallback className={className} style={style} />}</>
  }

  const url = bust > 0 ? `${src}${src.includes('?') ? '&' : '?'}r=${bust}` : src
  return (
    <img
      src={url}
      alt={alt}
      className={className}
      style={style}
      onError={() => (bust === 0 ? setBust(1) : setFailed(true))}
    />
  )
}

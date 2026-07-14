// Can this renderer actually get a WebGL context right now?
//
// This is NOT a static capability check — the answer changes at runtime. After a
// GPU-process crash (see crash.log: `child-process-gone type=GPU`, observed in
// LOOPS on hybrid-GPU laptops) Chromium can refuse new 3D contexts for the origin,
// and three.js's WebGLRenderer THROWS ("Error creating WebGL context.") when
// getContext returns null. Probing first lets a WebGL surface render a deliberate
// static fallback instead of mounting a canvas that throws or paints a black void.
//
// three (r155+) requires WebGL2, so that is what we probe — a machine with only
// WebGL1 cannot run the brain map either way.
export function isWebglAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl2') as WebGL2RenderingContext | null
    if (!gl) return false
    // Release the probe's context immediately: contexts are a scarce per-renderer
    // resource (Chromium evicts the OLDEST when the cap is hit — that would be the
    // real canvas), and a dropped <canvas> is only reclaimed at GC time. Duck-typed
    // rather than `instanceof WebGL2RenderingContext`: that global doesn't exist in
    // every host (jsdom), where the instanceof itself throws.
    gl.getExtension?.('WEBGL_lose_context')?.loseContext()
    return true
  } catch {
    // getContext can throw outright in a wedged renderer; treat as unavailable.
    return false
  }
}

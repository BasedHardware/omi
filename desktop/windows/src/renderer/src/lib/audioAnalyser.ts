/**
 * Global singleton for the live AnalyserNode.
 * Set by omiListenClient when a mic session starts; cleared on stop.
 * Read by Sidebar AudioBars to drive real-time waveform bars.
 */
let node: AnalyserNode | null = null
const listeners = new Set<() => void>()

export const audioAnalyser = {
  get(): AnalyserNode | null {
    return node
  },
  set(n: AnalyserNode | null): void {
    node = n
    listeners.forEach((cb) => cb())
  },
  subscribe(cb: () => void): () => void {
    listeners.add(cb)
    return () => listeners.delete(cb)
  }
}

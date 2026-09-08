// Minimal ambient types for d3-force-3d (no @types package published).
// Mirrors the subset of the d3-force API we use, in 3 dimensions.
declare module 'd3-force-3d' {
  export interface SimNodeDatum {
    index?: number
    x?: number
    y?: number
    z?: number
    vx?: number
    vy?: number
    vz?: number
    fx?: number | null
    fy?: number | null
    fz?: number | null
  }

  export interface Simulation<N extends SimNodeDatum> {
    nodes(): N[]
    nodes(nodes: N[]): this
    force(name: string, force: unknown): this
    force(name: string): unknown
    alpha(): number
    alpha(alpha: number): this
    alphaTarget(target: number): this
    restart(): this
    stop(): this
    tick(iterations?: number): this
    on(typenames: string, listener: (() => void) | null): this
  }

  export function forceSimulation<N extends SimNodeDatum>(
    nodes?: N[],
    numDimensions?: number
  ): Simulation<N>

  export function forceManyBody(): { strength(s: number): unknown } & unknown
  export function forceCenter(x?: number, y?: number, z?: number): unknown
  export function forceRadial(
    radius: number | ((n: unknown) => number),
    x?: number,
    y?: number,
    z?: number
  ): { strength(s: number | ((n: unknown) => number)): unknown } & unknown
  export function forceCollide(radius?: number | ((n: unknown) => number)): unknown
  export interface ForceLink<N> {
    id(fn: (n: N) => string): ForceLink<N>
    distance(d: number | ((link: unknown) => number)): ForceLink<N>
    strength(s: number | ((link: unknown) => number)): ForceLink<N>
  }
  export function forceLink<N, L = unknown>(links?: L[]): ForceLink<N>
}

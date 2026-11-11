import { useEffect, useRef, useState } from 'react'
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceRadial,
  forceCollide,
  type Simulation,
  type SimNodeDatum
} from 'd3-force-3d'
import type { KnowledgeGraph } from '../../../shared/types'

// Base distance from the center to a module. Each module's actual distance is
// this scaled by a per-node random factor (RADIUS_MIN..RADIUS_MIN+RADIUS_SPAN),
// so modules sit at varied distances rather than a perfect ring — and that
// factor is re-rolled on every screen change (see reshuffle) so the cloud
// rearranges. The distance no longer depends on node COUNT, so the overall
// scale stays constant; only the per-node offsets vary.
const RING_RADIUS = 160
const RADIUS_MIN = 0.5
const RADIUS_SPAN = 0.75 // → 0.5..1.25 × RING_RADIUS (modules sit close to center)

// Per-module size multiplier range: ±50% around the base sphere size.
const SIZE_MIN = 0.5
const SIZE_SPAN = 1.0 // → 0.5..1.5 ×

// Drawn radius of the fixed center ("you") node.
const CENTER_RADIUS = 24

// Label font: a base size varied only ±20% by the node's size, so titles stay
// fairly uniform (a big node's title is at most 20% larger than a small one's),
// rather than tracking the full ±50% node-size range. Exported so the renderer
// uses the exact same value.
const BASE_FONT = 14
const FONT_VARY = 0.4 // sizeScale deviation ±0.5 × this → font deviation ±0.2 (±20%)
export function labelFontSize(sizeScale: number): number {
  return BASE_FONT * (1 + (sizeScale - 1) * FONT_VARY)
}
// Half the on-screen width of one character, per font pixel (matches the Text in
// BrainGraph). Used to size collision/framing to the labels.
const LABEL_CHAR_HALF = 0.3

// Per-screen reshuffle steps. The radial (closer/farther) move is the main,
// substantial change in a module's distance to the center; the orbital
// (clockwise/anticlockwise) move is only 1/40 of that — barely perceptible, so
// the movement reads as in/out rather than spinning. Radial is then × a random
// 1..7 and orbital × a random 1..3, each with a random direction.
const RADIAL_STEP = 0.1
const ORBIT_STEP = RADIAL_STEP / 40 // radians — 1/40 of the radial move

// Before apps exist, the lone language node just drifts a little in all
// directions (small, balanced in/out + rotation). Smaller = stiller.
const SIMPLE_DRIFT = 0.1

export type SimNode = SimNodeDatum & {
  id: string
  label: string
  nodeType: string
  degree: number
  // Random ±50% size multiplier (stable per node) and the current random
  // distance-from-center target (re-rolled on reshuffle). Center node: 1 and 0.
  sizeScale: number
  targetRadius: number
  // Where this node first appeared (set once, never mutated again). getPositions()
  // reports this — not the live x/y/z — for a node's first frame, so the renderer's
  // per-mesh lerp has somewhere to glide FROM; the live simulation position is the
  // fixed target it glides TO. Without this split, a node's initial render position
  // and its settle target would be the same value and there'd be nothing to animate.
  seedX: number
  seedY: number
  seedZ: number
}

// Snapshot of a fully-settled layout, keyed by node id. Cached at module scope
// (survives a component remount, e.g. revisiting the Memories tab, or the
// second <BrainGraph> instance Settings.tsx mounts for its own Memories tab)
// so an unchanged graph never re-pays the settle cost.
type CachedLayout = Map<
  string,
  { x: number; y: number; z: number; sizeScale: number; targetRadius: number }
>
const layoutCache = new Map<string, CachedLayout>()
// Small cap — a session only ever produces a handful of distinct node-set
// snapshots (floor-only, floor+kg, +1 memory, ...), but bound it anyway so a
// pathological amount of add/delete churn can't grow this unboundedly.
const LAYOUT_CACHE_MAX = 20

// Test-only escape hatch: the cache is intentionally module-scoped (it must
// survive a component remount within one renderer process), which means it
// otherwise leaks across test cases in the same file. Not used by app code.
export function __clearLayoutCacheForTests(): void {
  layoutCache.clear()
}

// Ticks for the one-shot synchronous settle below. Same physics as before, but
// run as a single batch instead of spread across ~170 animation frames — that
// spread is what made the entry read as heavy (a full force pass every frame
// for seconds) and glitchy (the renderer's lerp chases a target that is itself
// still jittering under live collision/radial forces, instead of a fixed spot).
const SETTLE_TICKS = 220
type SimLink = { source: string; target: string }
export type NodePosition = {
  id: string
  label: string
  nodeType: string
  degree: number
  sizeScale: number
  x: number
  y: number
  z: number
}

// Imperative simulation wrapper. Kept framework-free so it is unit-testable in
// node. The hook below adapts it to React.
export class GraphSimulation {
  private sim: Simulation<SimNode>
  private nodes: SimNode[] = []
  private nodeMap = new Map<string, SimNode>()
  private newlyAdded: string[] = []

  // `dimensions` selects a 2D (default) or 3D layout. 2D pins every node to z=0 so
  // the camera faces it head on — what makes labels reliably readable, since two
  // nodes far apart in 3D can still project on top of each other. Onboarding + the
  // inline Memories card pass 2 (fixed camera). Only the full-screen INTERACTIVE
  // brain map passes 3, where OrbitControls lets the user rotate to disambiguate
  // depth (mirroring macOS's SceneKit force-directed MemoryGraphPage).
  constructor(
    private centerNodeId?: string,
    private dimensions: 2 | 3 = 2
  ) {
    this.sim = forceSimulation<SimNode>([], this.dimensions).stop()
  }

  private get is3D(): boolean {
    return this.dimensions === 3
  }

  // The drawn radius of a node's sphere. The center ("you") node is a fixed,
  // deliberately large size; every other node is much smaller, then scaled by
  // its random ±50% sizeScale. Kept here so collision and the renderer agree.
  private nodeRadius(n: SimNode): number {
    if (n.id === this.centerNodeId) return CENTER_RADIUS
    return (10 + Math.sqrt(n.degree) * 2) * n.sizeScale
  }

  // Collision radius is sized to the LABEL, not just the sphere, so two labels
  // can never overlap. The label scales with the node (LABEL_RATIO), so its
  // half-width is length × fontSize × LABEL_CHAR_HALF; +26 is breathing room.
  private collideRadius(n: SimNode): number {
    const fontSize = labelFontSize(n.sizeScale)
    const halfLabel = (n.label?.length ?? 0) * fontSize * LABEL_CHAR_HALF
    return Math.max(this.nodeRadius(n), halfLabel) + 26
  }

  // The farthest a node's center may sit so that the node AND its label still
  // fit within the framed radius (fullGraphRadius). Because the camera frames
  // fullGraphRadius × FRAME_MARGIN (>1), keeping every node within
  // fullGraphRadius guarantees a gap to the container border — so nodes/labels
  // can never touch it, no matter how long an app name is (long labels just sit
  // closer to the center). Clamped to the normal distance range.
  private maxRadiusFor(n: SimNode): number {
    const labelLimited = fullGraphRadius() - this.collideRadius(n)
    const rangeMax = RING_RADIUS * (RADIUS_MIN + RADIUS_SPAN)
    return Math.max(RING_RADIUS * RADIUS_MIN, Math.min(rangeMax, labelLimited))
  }

  // Diff the graph against current nodes: add new ones (seeded near a connected
  // existing node), keep existing positions, then re-tune + reheat.
  setGraph(graph: KnowledgeGraph): void {
    const degree: Record<string, number> = {}
    for (const n of graph.nodes) degree[n.id] = 0
    for (const e of graph.edges) {
      if (e.sourceId in degree) degree[e.sourceId]++
      if (e.targetId in degree && e.targetId !== e.sourceId) degree[e.targetId]++
    }

    // Prune nodes no longer in the incoming graph. Historically every caller only
    // GREW the node set (onboarding reveals more each step), so this was a no-op.
    // The knowledge-graph viewer's node cap is the first caller that can SHRINK it
    // (toggling "Show all 188" back to "Show key 120"); without pruning, getPositions()
    // would keep reporting the high-water-mark set and the scene would never shed the
    // dropped spheres. Safe for the grow-only callers (nothing to remove there).
    const incoming = new Set(graph.nodes.map((n) => n.id))
    if (this.nodes.some((n) => !incoming.has(n.id))) {
      this.nodes = this.nodes.filter((n) => incoming.has(n.id))
      for (const id of [...this.nodeMap.keys()]) {
        if (!incoming.has(id)) this.nodeMap.delete(id)
      }
    }

    this.newlyAdded = []
    for (const n of graph.nodes) {
      const existing = this.nodeMap.get(n.id)
      if (existing) {
        existing.degree = degree[n.id] ?? 0
        continue
      }
      const seed = this.seedPositionNear(n.id, graph)
      const isCenter = n.id === this.centerNodeId
      const node: SimNode = {
        id: n.id,
        label: n.label,
        nodeType: n.nodeType,
        degree: degree[n.id] ?? 0,
        sizeScale: isCenter ? 1 : SIZE_MIN + Math.random() * SIZE_SPAN,
        targetRadius: isCenter ? 0 : RING_RADIUS * (RADIUS_MIN + Math.random() * RADIUS_SPAN),
        x: seed.x,
        y: seed.y,
        z: seed.z,
        seedX: seed.x,
        seedY: seed.y,
        seedZ: seed.z
      }
      if (isCenter) {
        node.x = node.y = node.z = 0
        node.seedX = node.seedY = node.seedZ = 0
        node.fx = 0
        node.fy = 0
        if (this.is3D) node.fz = 0
      } else {
        // Keep the node + its (possibly long) label inside the frame.
        node.targetRadius = Math.min(node.targetRadius, this.maxRadiusFor(node))
      }
      this.nodes.push(node)
      this.nodeMap.set(n.id, node)
      this.newlyAdded.push(n.id)
    }

    const links: SimLink[] = graph.edges
      .filter((e) => this.nodeMap.has(e.sourceId) && this.nodeMap.has(e.targetId))
      .map((e) => ({ source: e.sourceId, target: e.targetId }))

    this.sim
      .nodes(this.nodes)
      // Low charge: a strong global repulsion makes nodes slide tangentially
      // (i.e. orbit) whenever the layout re-packs. Keep it small — just enough
      // to help the initial spread — so reshuffles read as in/out, not spinning.
      .force('charge', forceManyBody().strength(-45))
      // Weak link held to each module's own targetRadius (the radial force does
      // the real positioning); a strong link would flatten the random distances.
      .force(
        'link',
        forceLink<SimNode>(links)
          .id((d) => d.id)
          .distance((l) => (l as { target: SimNode }).target?.targetRadius ?? RING_RADIUS)
          .strength(0.2)
      )
      // Radial force: pulls every module to its own random targetRadius from the
      // (origin) center. Because each target is independent of node COUNT, the
      // overall scale stays constant; the per-node randomness just spreads the
      // modules into a varied cloud instead of a perfect ring. Replaces
      // forceCenter, which would shift an asymmetric (few-node) layout off-center.
      .force(
        'radial',
        forceRadial(
          (d) => ((d as SimNode).id === this.centerNodeId ? 0 : (d as SimNode).targetRadius),
          0,
          0
        ).strength((d) => ((d as SimNode).id === this.centerNodeId ? 0 : 0.9))
      )
      // Label-aware collision: nodes are kept apart by the size of their labels,
      // so titles never overlap no matter how many nodes are revealed. Several
      // iterations per tick make a dense ring fully resolve before the layout
      // cools, rather than leaving residual overlaps.
      .force(
        'collide',
        (
          forceCollide((d) => this.collideRadius(d as SimNode)) as {
            iterations(n: number): unknown
          }
        ).iterations(10)
      )
    const key = this.cacheKey(graph)
    const cached = layoutCache.get(key)
    const t0 = typeof performance !== 'undefined' ? performance.now() : 0
    if (cached) {
      // Exact node-set match to a layout we've already settled (a remount with
      // unchanged data) — adopt it directly, zero physics. getPositions() still
      // reports each of these as "not fresh" (they were added in an earlier
      // call), so the renderer draws them straight at rest, no fly-in replay.
      for (const n of this.nodes) {
        const c = cached.get(n.id)
        if (!c) continue
        n.x = c.x
        n.y = c.y
        n.z = c.z
        n.sizeScale = c.sizeScale
        n.targetRadius = c.targetRadius
      }
      this.sim.alpha(0).stop()
    } else {
      // Freeze everything already settled so the burst below only has to place
      // the newly-added nodes among fixed neighbors — this IS "existing settled
      // nodes barely shift when a new node is revealed" (now they don't shift at
      // all), and it means an incremental update is cheap regardless of how
      // large the existing graph has grown.
      const fresh = new Set(this.newlyAdded)
      for (const n of this.nodes) {
        if (fresh.has(n.id) || n.id === this.centerNodeId) continue
        n.fx = n.x
        n.fy = n.y
        if (this.is3D) n.fz = n.z
      }
      // One synchronous batch instead of ~170 live animation frames: same total
      // force math, but as a single fast pass, so nothing is left to visibly
      // (and jitterily) converge on screen.
      this.sim.alpha(0.6).restart().tick(SETTLE_TICKS)
      this.clampPositions()
      this.sim.stop()
      for (const n of this.nodes) {
        if (fresh.has(n.id) || n.id === this.centerNodeId) continue
        n.fx = undefined
        n.fy = undefined
        if (this.is3D) n.fz = undefined
      }
      const snapshot: CachedLayout = new Map()
      for (const n of this.nodes) {
        snapshot.set(n.id, {
          x: n.x ?? 0,
          y: n.y ?? 0,
          z: n.z ?? 0,
          sizeScale: n.sizeScale,
          targetRadius: n.targetRadius
        })
      }
      if (layoutCache.size >= LAYOUT_CACHE_MAX) {
        const oldest = layoutCache.keys().next().value
        if (oldest !== undefined) layoutCache.delete(oldest)
      }
      layoutCache.set(key, snapshot)
    }
    if (typeof performance !== 'undefined' && import.meta.env.DEV) {
      console.debug(
        `[BrainGraph] settle ${(performance.now() - t0).toFixed(1)}ms (${cached ? 'cache hit' : 'fresh'}, ${this.nodes.length} nodes, +${this.newlyAdded.length} new)`
      )
    }
  }

  // Dimensions + node-id-set + center id: two graphs with the same nodes settle
  // to the same shape, so this is enough to detect "we've already laid this out"
  // without hashing content that doesn't affect layout (labels, edge direction,
  // etc). Dimensions MUST be part of the key: the 2D card and the 3D full-screen
  // page render the same node set, and a 2D layout has every node at z=0 — a 3D
  // sim adopting it would render the "interactive 3D" scene as a flat plane with
  // zero parallax (orbiting reads as panning).
  private cacheKey(graph: KnowledgeGraph): string {
    const ids = graph.nodes
      .map((n) => n.id)
      .sort()
      .join(',')
    return `${this.dimensions}|${this.centerNodeId ?? ''}|${ids}`
  }

  private seedPositionNear(id: string, graph: KnowledgeGraph): { x: number; y: number; z: number } {
    const edge = graph.edges.find((e) => e.sourceId === id || e.targetId === id)
    const neighborId = edge ? (edge.sourceId === id ? edge.targetId : edge.sourceId) : undefined
    const neighbor = neighborId ? this.nodeMap.get(neighborId) : undefined
    // z stays 0 in 2D (only x/y are simulated); in 3D it gets the same jitter so
    // the cloud spreads through depth instead of collapsing onto one plane.
    const jitter = (): number => (Math.random() - 0.5) * 60
    const jz = (): number => (this.is3D ? jitter() : 0)
    if (neighbor) {
      return {
        x: (neighbor.x ?? 0) + jitter(),
        y: (neighbor.y ?? 0) + jitter(),
        z: (neighbor.z ?? 0) + jz()
      }
    }
    return { x: jitter(), y: jitter(), z: jz() }
  }

  // Hard-clamp every node's actual position so the node AND its label always
  // stay within the framed radius — even when the collision force transiently
  // shoves a node past its target distance. This is what guarantees nodes/labels
  // can never leave the container (the radial target cap alone can be overshot).
  private clampPositions(): void {
    const frame = fullGraphRadius()
    for (const n of this.nodes) {
      if (n.id === this.centerNodeId) continue
      const x = n.x ?? 0
      const y = n.y ?? 0
      const z = n.z ?? 0
      // In 3D clamp to a sphere (include z); in 2D the plane radius as before.
      const r = this.is3D ? Math.hypot(x, y, z) : Math.hypot(x, y)
      const maxR = Math.max(RING_RADIUS * RADIUS_MIN, frame - this.collideRadius(n))
      if (r > maxR && r > 0) {
        const k = maxR / r
        n.x = x * k
        n.y = y * k
        n.vx = 0
        n.vy = 0
        if (this.is3D) {
          n.z = z * k
          n.vz = 0
        }
      }
    }
  }

  // Advance the layout synchronously (used for initial settle / bursts).
  settle(ticks: number): void {
    this.sim.tick(ticks)
    this.clampPositions()
  }

  // Advance one tick per render frame, but only while the layout is still warm.
  // Once alpha decays the layout is settled and ticking stops (no idle CPU).
  settleFrame(): boolean {
    if (this.sim.alpha() > 0.01) {
      this.sim.tick(1)
      this.clampPositions()
      return this.sim.alpha() > 0.01
    }
    return false
  }

  // Live simulation node (positions mutate in place each tick). The renderer
  // reads this every frame instead of going through React state.
  liveNode(id: string): SimNode | undefined {
    return this.nodeMap.get(id)
  }

  // World-space radius that encloses every node AND its label. The camera rig
  // uses this to frame the whole graph so all titles stay on screen, easing the
  // zoom out smoothly as new nodes are revealed.
  boundingRadius(): number {
    let max = 0
    for (const n of this.nodes) {
      const d =
        (this.is3D ? Math.hypot(n.x ?? 0, n.y ?? 0, n.z ?? 0) : Math.hypot(n.x ?? 0, n.y ?? 0)) +
        this.collideRadius(n)
      if (d > max) max = d
    }
    return max
  }

  // Gently shift the modules on a screen change — NOT a full rearrangement.
  // Each module only drifts a little closer to / farther from the center and
  // gets a small left/right nudge, keeping roughly its current place. The radial
  // force then settles it to the new distance (and the nudge becomes a small
  // angular shift), and the renderer eases the sphere across. A modest reheat
  // keeps the motion subtle.
  reshuffle(): void {
    // The full radial/orbital movement only kicks in once there are apps on the
    // map (added at the disk screen). Before that — when only the center +
    // language node exist — use a small, simple drift in all directions.
    const hasApps = this.nodes.some((n) => n.nodeType === 'thing')

    if (!hasApps) {
      for (const n of this.nodes) {
        if (n.id === this.centerNodeId) continue
        const x = n.x ?? 0
        const y = n.y ?? 0
        const r = Math.hypot(x, y) || n.targetRadius || RING_RADIUS
        // Small, balanced in/out + rotation → a little drift in all directions.
        const f = r / RING_RADIUS + (Math.random() - 0.5) * SIMPLE_DRIFT
        n.targetRadius = RING_RADIUS * Math.max(RADIUS_MIN, Math.min(RADIUS_MIN + RADIUS_SPAN, f))
        n.targetRadius = Math.min(n.targetRadius, this.maxRadiusFor(n))
        const a = (Math.random() - 0.5) * SIMPLE_DRIFT
        const c = Math.cos(a)
        const s = Math.sin(a)
        n.x = x * c - y * s
        n.y = x * s + y * c
        n.vx = 0
        n.vy = 0
      }
      this.sim.nodes(this.nodes)
      this.sim.alpha(0.4).restart().stop()
      return
    }

    for (const n of this.nodes) {
      if (n.id === this.centerNodeId) continue
      const x = n.x ?? 0
      const y = n.y ?? 0
      const r = Math.hypot(x, y) || n.targetRadius || RING_RADIUS

      // Radial (closer/farther): pick a new target distance — base step × a
      // random 1..7, random direction. The radial force eases the node to it.
      const radialDir = Math.random() < 0.5 ? -1 : 1
      const radialMag = RADIAL_STEP * (1 + Math.random() * 6) * radialDir
      const factor = r / RING_RADIUS + radialMag
      const clamped = Math.max(RADIUS_MIN, Math.min(RADIUS_MIN + RADIUS_SPAN, factor))
      n.targetRadius = Math.min(RING_RADIUS * clamped, this.maxRadiusFor(n))

      // Orbital (clockwise/anticlockwise): rotate the current position by a tiny
      // angle (base × a random 1..3, random direction). Rotation keeps the
      // radius, so the radial force above is what changes the distance.
      const orbitDir = Math.random() < 0.5 ? -1 : 1
      const orbitMag = ORBIT_STEP * (1 + Math.random() * 2) * orbitDir
      const cos = Math.cos(orbitMag)
      const sin = Math.sin(orbitMag)
      n.x = x * cos - y * sin
      n.y = x * sin + y * cos
      n.vx = 0
      n.vy = 0
    }
    // Re-seat the nodes so every force re-reads the new targetRadius (d3 caches
    // it at initialize time, otherwise the radial force would keep pulling each
    // module back to its old distance — i.e. it would never move in/out).
    this.sim.nodes(this.nodes)
    this.sim.alpha(0.4).restart().stop()
  }

  // For a node added in the most recent setGraph() call, report its SEED spot
  // (not its already-settled final one) so the renderer's initial render — and
  // thus the per-mesh lerp's starting point — is the fly-in origin, while
  // liveNode() (read every frame) already returns the final, fixed target.
  // Nodes from an earlier call report their current (already on-screen, at
  // rest) position, so they never re-play the fly-in on a later update.
  getPositions(): NodePosition[] {
    const fresh = new Set(this.newlyAdded)
    return this.nodes.map((n) => {
      const useSeed = fresh.has(n.id)
      return {
        id: n.id,
        label: n.label,
        nodeType: n.nodeType,
        degree: n.degree,
        sizeScale: n.sizeScale,
        x: useSeed ? n.seedX : (n.x ?? 0),
        y: useSeed ? n.seedY : (n.y ?? 0),
        z: useSeed ? n.seedZ : (n.z ?? 0)
      }
    })
  }

  // Returns and clears the list of node ids added since the last call, so the
  // renderer can fade/scale them in once.
  consumeNewlyAdded(): string[] {
    const out = this.newlyAdded
    this.newlyAdded = []
    return out
  }
}

// React adapter: keeps a single GraphSimulation alive across renders. It updates
// React state (the `nodes` list) ONLY when the graph's node set changes — never
// per frame. The actual physics ticking happens in the render loop (the caller's
// useFrame calls sim.settleFrame()), and meshes/edges read live positions via
// sim.liveNode(), so there are zero per-frame React re-renders.
export function useGraphSimulation(
  graph: KnowledgeGraph,
  centerNodeId?: string,
  dimensions: 2 | 3 = 2
): { nodes: NodePosition[]; sim: GraphSimulation; reduced: boolean } {
  const simRef = useRef<GraphSimulation>(undefined)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref / lazy-init (reads newest value in once-registered listeners & imperative loops, avoids stale closures)
  if (!simRef.current) simRef.current = new GraphSimulation(centerNodeId, dimensions)
  const reducedRef = useRef(
    typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
  )
  const [nodes, setNodes] = useState<NodePosition[]>([])

  useEffect(() => {
    const sim = simRef.current!
    sim.setGraph(graph)
    // Reduced motion: settle fully up front so the render loop has nothing to
    // animate and the graph appears in its final layout.
    if (reducedRef.current) sim.settle(300)
    setNodes(sim.getPositions())
  }, [graph])

  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref / lazy-init (reads newest value in once-registered listeners & imperative loops, avoids stale closures)
  return { nodes, sim: simRef.current, reduced: reducedRef.current }
}

// The constant world-space radius the camera frames to. Computed analytically
// (not measured) from the worst case so it never depends on a random draw: the
// furthest a module can be pushed (RING_RADIUS × max factor) plus the room a
// long, large-sized label needs. This keeps the camera distance identical on
// every screen — even as reshuffle re-rolls distances — and never clips.
export function fullGraphRadius(): number {
  const farthest = RING_RADIUS * (RADIUS_MIN + RADIUS_SPAN)
  // Collision reach of a worst-case node: a long app name at the largest size,
  // whose label is at most +20% (labelFontSize at the max sizeScale).
  const longestLabel = 'Visual Studio Code'
  const maxSphere = (10 + Math.sqrt(1) * 2) * (SIZE_MIN + SIZE_SPAN)
  const maxFont = labelFontSize(SIZE_MIN + SIZE_SPAN)
  const halfLabel = longestLabel.length * maxFont * LABEL_CHAR_HALF
  const labelReach = Math.max(maxSphere, halfLabel) + 26
  return farthest + labelReach
}

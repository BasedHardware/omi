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
}
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

  constructor(private centerNodeId?: string) {
    // 2D layout: every node lives on the z=0 plane so the camera faces it head
    // on. This is what makes labels reliably readable — in 3D, two nodes far
    // apart in space can still project on top of each other; on a plane they
    // cannot, and label-aware collision (below) keeps titles from touching.
    this.sim = forceSimulation<SimNode>([], 2).stop()
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
        z: seed.z
      }
      if (isCenter) {
        node.x = node.y = node.z = 0
        node.fx = 0
        node.fy = 0
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
        (forceCollide((d) => this.collideRadius(d as SimNode)) as {
          iterations(n: number): unknown
        }).iterations(10)
      )
      // Gentle reheat (not 0.9): existing settled nodes barely shift when a new
      // node is revealed, so the reveal reads as an addition, not an upheaval.
      .alpha(0.6)
      .restart()
      .stop()
  }

  private seedPositionNear(id: string, graph: KnowledgeGraph): { x: number; y: number; z: number } {
    const edge = graph.edges.find((e) => e.sourceId === id || e.targetId === id)
    const neighborId = edge ? (edge.sourceId === id ? edge.targetId : edge.sourceId) : undefined
    const neighbor = neighborId ? this.nodeMap.get(neighborId) : undefined
    // z stays 0 — the layout is 2D (see constructor). Only x/y are simulated.
    const jitter = (): number => (Math.random() - 0.5) * 60
    if (neighbor) {
      return { x: (neighbor.x ?? 0) + jitter(), y: (neighbor.y ?? 0) + jitter(), z: 0 }
    }
    return { x: jitter(), y: jitter(), z: 0 }
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
      const r = Math.hypot(x, y)
      const maxR = Math.max(RING_RADIUS * RADIUS_MIN, frame - this.collideRadius(n))
      if (r > maxR && r > 0) {
        const k = maxR / r
        n.x = x * k
        n.y = y * k
        n.vx = 0
        n.vy = 0
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
  settleFrame(): void {
    if (this.sim.alpha() > 0.01) {
      this.sim.tick(1)
      this.clampPositions()
    }
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
      const d = Math.hypot(n.x ?? 0, n.y ?? 0) + this.collideRadius(n)
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

  getPositions(): NodePosition[] {
    return this.nodes.map((n) => ({
      id: n.id,
      label: n.label,
      nodeType: n.nodeType,
      degree: n.degree,
      sizeScale: n.sizeScale,
      x: n.x ?? 0,
      y: n.y ?? 0,
      z: n.z ?? 0
    }))
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
  centerNodeId?: string
): { nodes: NodePosition[]; sim: GraphSimulation; reduced: boolean } {
  const simRef = useRef<GraphSimulation>(undefined)
  if (!simRef.current) simRef.current = new GraphSimulation(centerNodeId)
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

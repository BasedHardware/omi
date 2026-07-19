import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Billboard, Text } from '@react-three/drei'
import * as THREE from 'three'
import { LineSegments2, LineSegmentsGeometry, LineMaterial } from 'three-stdlib'
import { InstancedUniformsMesh } from 'three-instanced-uniforms-mesh'
import type { KnowledgeGraph } from '../../../../shared/types'
import {
  useGraphSimulation,
  fullGraphRadius,
  labelFontSize,
  type GraphSimulation,
  type NodePosition
} from '../../lib/useGraphSimulation'
import { nodeColor } from './nodeColor'
import { topRankedIds, DEFAULT_LABEL_TOPK } from '../../lib/graphDisplay'
import { useWebglRecovery } from '../../lib/useWebglRecovery'
import { BrainGraphFallback } from './BrainGraphFallback'
import { ErrorBoundary } from '../ui/ErrorBoundary'
import { trackEvent } from '../../lib/analytics'

export type BrainGraphProps = {
  graph: KnowledgeGraph
  centerNodeId?: string
  interactive?: boolean
  // Changing this re-rolls the module positions with an animation (used to
  // rearrange the graph on every onboarding screen change).
  shuffleKey?: number | string
  // When true, the whole WebGL canvas is UNMOUNTED while the host is off-screen
  // (e.g. on a hidden MainViews tab) so it costs zero GPU, then remounts fresh
  // when shown. Use for the Memories tab. Leave false (default) for onboarding,
  // where the map is deliberately kept mounted across steps and must not blank.
  pauseWhenHidden?: boolean
  // Use demand for idle-heavy surfaces such as Memories so the WebGL canvas
  // stops rendering once layout/easing has settled.
  frameLoop?: 'always' | 'demand'
  // Fired once the WebGL context/scene is created (r3f's Canvas onCreated) —
  // the cheapest available "first frame is imminent" signal. Callers use this
  // to swap a loading placeholder for the canvas without guessing at timing.
  onReady?: () => void
  // Fired whenever the canvas mounts/unmounts under pauseWhenHidden (e.g. the
  // host tab going hidden then shown again tears down and recreates the WebGL
  // context). A caller tracking readiness from onReady alone would otherwise
  // treat that recreation as a no-op and show nothing during the gap — this
  // lets it fall back to its loading state for that window instead of a blank
  // pane. Not called when pauseWhenHidden is false (the canvas never toggles).
  onVisibleChange?: (visible: boolean) => void
  // Label strategy. 'all' (default) draws a title on every node — right for the
  // small onboarding/inline-card graphs. 'declutter' draws titles only for the
  // DEFAULT_LABEL_TOPK most-connected nodes plus whatever the user hovers or
  // selects, which is what keeps the large interactive brain map from becoming an
  // unreadable wall of overlapping text. Interaction (hover/select) is only
  // wired when interactive is true.
  labelMode?: 'all' | 'declutter'
}

// Must match GraphSimulation.nodeRadius so the spheres and the collision force
// agree on size. The center ("you") node is fixed-large; others much smaller,
// then scaled by the node's random ±50% sizeScale.
function radiusFor(node: NodePosition, isCenter: boolean): number {
  return isCenter ? 24 : (10 + Math.sqrt(node.degree) * 2) * node.sizeScale
}

// A stable 0..2π phase derived from the node id, so each module pulses on its
// own offset and the ring twinkles rather than breathing in unison.
function hashPhase(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 997
  return (h / 997) * Math.PI * 2
}

// Per-node visual constants, memo-derived from the node list. Kept out of the
// frame loop (color/phase/radius never change once a node exists).
type NodeVisual = { id: string; color: THREE.Color; phase: number; radius: number }
// Reused scratch objects for the per-frame matrix compose (never allocate in a loop).
const IDENTITY_QUAT = new THREE.Quaternion()
const scratchMat = new THREE.Matrix4()
const scratchScale = new THREE.Vector3()

// ALL node spheres, drawn as THREE InstancedMeshes (core / glow / bloom) instead
// of 3 meshes per node. This makes the sphere draw calls CONSTANT (3) regardless
// of node count. The per-node emissive pulse and glow opacity/scale — which would
// otherwise force one shared material value for every node — are kept per-node by
// `three-instanced-uniforms-mesh` (setUniformAt patches the material shader to
// read a per-instance attribute), so the twinkle stays byte-identical to the
// per-mesh version: same lerp, same sin(t*2+phase) per-node phase, same flare on
// entry, same grow-in. One consolidated useFrame owns all the math (the r3f
// "mutate imperatively in one loop" pattern) and also writes each node's eased
// position into posMap so edges/labels follow.
function GraphNodes({
  sim,
  nodes,
  centerNodeId,
  reduced,
  posMap,
  frameLoop,
  interactive,
  onHover,
  onSelect
}: {
  sim: GraphSimulation
  nodes: NodePosition[]
  centerNodeId?: string
  reduced: boolean
  posMap: Map<string, THREE.Vector3>
  frameLoop: 'always' | 'demand'
  interactive: boolean
  onHover?: (id: string | null) => void
  onSelect?: (id: string) => void
}): React.JSX.Element {
  const invalidate = useThree((state) => state.invalidate)
  const count = Math.max(1, nodes.length)

  // Static per-node visuals (color/phase/radius). Rebuilt only when the node list
  // changes — never inside the frame loop.
  const visuals = useMemo<NodeVisual[]>(
    () =>
      nodes.map((n) => {
        const isFixed = n.id === centerNodeId
        return {
          id: n.id,
          color: new THREE.Color(nodeColor(n.nodeType, isFixed)),
          phase: hashPhase(n.id),
          radius: radiusFor(n, isFixed)
        }
      }),
    [nodes, centerNodeId]
  )

  // Three instanced layers. Core is lit (MeshStandard, per-instance emissive
  // pulse); glow + bloom are additive-ish MeshBasic shells. Core/glow use
  // InstancedUniformsMesh so emissiveIntensity/opacity vary per instance; bloom's
  // opacity is constant so a plain InstancedMesh suffices.
  const layers = useMemo(() => {
    const coreGeo = new THREE.SphereGeometry(1, 16, 16)
    const coreMat = new THREE.MeshStandardMaterial({ roughness: 0.3, metalness: 0.1 })
    const core = new InstancedUniformsMesh(coreGeo, coreMat, count)
    const glowGeo = new THREE.SphereGeometry(1, 12, 12)
    const glowMat = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false })
    const glow = new InstancedUniformsMesh(glowGeo, glowMat, count)
    const bloomGeo = new THREE.SphereGeometry(1, 8, 8)
    const bloomMat = new THREE.MeshBasicMaterial({
      transparent: true,
      opacity: 0.04,
      depthWrite: false
    })
    const bloom = new THREE.InstancedMesh(bloomGeo, bloomMat, count)
    for (const m of [core, glow, bloom]) {
      m.frustumCulled = false
      m.matrixAutoUpdate = false
    }
    return { coreGeo, coreMat, core, glowGeo, glowMat, glow, bloomGeo, bloomMat, bloom }
  }, [count])
  useEffect(
    () => () => {
      for (const g of [layers.coreGeo, layers.glowGeo, layers.bloomGeo]) g.dispose()
      for (const m of [layers.coreMat, layers.glowMat, layers.bloomMat]) m.dispose()
    },
    [layers]
  )

  // Set per-instance colors once per node-list change: diffuse via instanceColor,
  // and the core's emissive color to match (the pulse only scales its intensity).
  useEffect(() => {
    const { core, glow, bloom } = layers
    for (let i = 0; i < visuals.length; i++) {
      const c = visuals[i].color
      core.setColorAt(i, c)
      glow.setColorAt(i, c)
      bloom.setColorAt(i, c)
      core.setUniformAt('emissive', i, c)
    }
    /* eslint-disable react-hooks/immutability -- r3f: three.js instance buffers are flagged for the needsUpdate write; imperative upload by design */
    if (core.instanceColor) core.instanceColor.needsUpdate = true
    if (glow.instanceColor) glow.instanceColor.needsUpdate = true
    if (bloom.instanceColor) bloom.instanceColor.needsUpdate = true
    /* eslint-enable react-hooks/immutability */
  }, [layers, visuals])

  // Per-node animation state, keyed by id so an existing node keeps its eased
  // position + grown-in scale when the node list changes (only genuinely new
  // nodes fly in from their seed and grow 0→1) — matching the keyed-mesh version.
  const stateRef = useRef(new Map<string, { eased: THREE.Vector3; grow: number }>())
  const target = useRef(new THREE.Vector3())

  // r3f imperative loop: mutate three.js instance buffers/uniforms in place every
  // frame (never React state). The immutability rule flags the needsUpdate writes
  // on the memo'd meshes — that is exactly the sanctioned r3f pattern here.
  /* eslint-disable react-hooks/immutability */
  useFrame((frame) => {
    const { core, glow, bloom } = layers
    const store = stateRef.current
    const t = frame.clock.elapsedTime
    let anyMoving = false

    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i]
      const vis = visuals[i]
      let st = store.get(n.id)
      if (!st) {
        st = { eased: new THREE.Vector3(n.x, n.y, n.z), grow: reduced ? 1 : 0 }
        store.set(n.id, st)
      }
      const live = sim.liveNode(n.id)
      if (live) target.current.set(live.x ?? 0, live.y ?? 0, live.z ?? 0)
      else target.current.copy(st.eased)

      if (reduced) {
        st.eased.copy(target.current)
        st.grow = 1
      } else {
        st.eased.lerp(target.current, 0.045)
        if (st.eased.distanceToSquared(target.current) < 0.01) st.eased.copy(target.current)
        if (st.grow < 1) st.grow = Math.min(1, st.grow + 0.05)
        if (st.eased.distanceToSquared(target.current) > 0.01 || st.grow < 1) anyMoving = true
      }

      // Publish eased position for edges + labels (reuse the stored Vector3).
      let v = posMap.get(n.id)
      if (!v) {
        v = new THREE.Vector3()
        posMap.set(n.id, v)
      }
      v.copy(st.eased)

      // Same shine math as the per-mesh version: per-node phase twinkle + entry flare.
      const entering = !reduced && st.grow < 1
      const pulse = reduced ? 0.6 : 0.5 + 0.5 * Math.sin(t * 2 + vis.phase)
      const flare = entering ? 1.8 : 1
      const grow = st.grow

      scratchScale.setScalar(vis.radius * grow)
      scratchMat.compose(st.eased, IDENTITY_QUAT, scratchScale)
      core.setMatrixAt(i, scratchMat)
      core.setUniformAt('emissiveIntensity', i, (0.85 + 0.45 * pulse) * flare)

      scratchScale.setScalar(vis.radius * 1.9 * grow * (1 + 0.18 * pulse))
      scratchMat.compose(st.eased, IDENTITY_QUAT, scratchScale)
      glow.setMatrixAt(i, scratchMat)
      glow.setUniformAt('opacity', i, (0.12 + 0.14 * pulse) * flare)

      scratchScale.setScalar(vis.radius * 3 * grow)
      scratchMat.compose(st.eased, IDENTITY_QUAT, scratchScale)
      bloom.setMatrixAt(i, scratchMat)
    }
    core.instanceMatrix.needsUpdate = true
    glow.instanceMatrix.needsUpdate = true
    bloom.instanceMatrix.needsUpdate = true
    if (frameLoop === 'demand' && (anyMoving || !reduced)) invalidate()
  })
  /* eslint-enable react-hooks/immutability */

  // Picking on the core layer: r3f reports the hit instanceId, which indexes the
  // node list. Only wired for interactive scenes (cursor moves). Replaces the
  // per-mesh pointer handlers with instanceId hit-testing (same behavior).
  const handlers = interactive
    ? {
        onPointerMove: (e: { stopPropagation: () => void; instanceId?: number }) => {
          e.stopPropagation()
          const id = e.instanceId != null ? nodes[e.instanceId]?.id : undefined
          if (id) {
            onHover?.(id)
            document.body.style.cursor = 'pointer'
          }
        },
        onPointerOut: (e: { stopPropagation: () => void }) => {
          e.stopPropagation()
          onHover?.(null)
          document.body.style.cursor = ''
        },
        onPointerDown: (e: { stopPropagation: () => void; instanceId?: number }) => {
          e.stopPropagation()
          const id = e.instanceId != null ? nodes[e.instanceId]?.id : undefined
          if (id) onSelect?.(id)
        }
      }
    : {}

  return (
    <>
      <primitive object={layers.core} {...handlers} />
      <primitive object={layers.glow} />
      <primitive object={layers.bloom} />
    </>
  )
}

// One troika label for a single node, positioned each frame from the node's eased
// position (published by GraphNodes into posMap). Only mounted for the nodes that
// should be labeled (top hubs + hovered/selected under declutter, or all nodes on
// the small onboarding/card graphs), so troika text count stays small. Depth-fade
// (3D only) is identical to the per-mesh version: dim a title by how far its node
// sits behind the cloud center, quantized to 1/8 so troika rarely re-syncs.
function GraphNodeLabel({
  node,
  centerNodeId,
  posMap,
  labelFade,
  frameLoop
}: {
  node: NodePosition
  centerNodeId?: string
  posMap: Map<string, THREE.Vector3>
  labelFade: boolean
  frameLoop: 'always' | 'demand'
}): React.JSX.Element {
  const groupRef = useRef<THREE.Group>(null)
  const textRef = useRef<{ fillOpacity: number; sync: () => void } | null>(null)
  const lastFade = useRef(1)
  const isFixed = node.id === centerNodeId
  const radius = radiusFor(node, isFixed)
  const labelSize = labelFontSize(node.sizeScale) * (isFixed ? 1.35 : 1)
  const fadeSpan = useMemo(() => fullGraphRadius(), [])
  const invalidate = useThree((state) => state.invalidate)

  useFrame((state) => {
    const g = groupRef.current
    if (!g) return
    const p = posMap.get(node.id)
    if (p) g.position.copy(p)
    if (labelFade && textRef.current) {
      const cam = state.camera
      const behind = Math.max(0, cam.position.distanceTo(g.position) - cam.position.length())
      const f = Math.max(0.15, 1 - behind / fadeSpan)
      const q = Math.round(f * 8) / 8
      if (q !== lastFade.current) {
        lastFade.current = q
        textRef.current.fillOpacity = q
        textRef.current.sync()
        if (frameLoop === 'demand') invalidate()
      }
    }
  })

  return (
    <group ref={groupRef} position={[node.x, node.y, node.z]}>
      <Billboard position={[0, radius + labelSize * 0.9, 0]}>
        <Text
          ref={textRef as never}
          fontSize={labelSize}
          color="#ffffff"
          anchorX="center"
          anchorY="middle"
          renderOrder={4}
          depthOffset={-1}
        >
          {node.label}
        </Text>
      </Billboard>
    </group>
  )
}

// ALL connecting lines, drawn as a SINGLE batched fat-line object (LineSegments2)
// instead of one drei <Line> per edge. At real-account scale this collapses ~474
// separate draw calls (and ~474 per-frame closures) into one geometry whose whole
// position buffer is rewritten in a single pass each frame — the dominant draw-
// call win. The look is preserved: same ~0.8px translucent lines, colored by each
// edge's target node, sitting under the glowing nodes/labels. Endpoints track the
// eased on-screen positions so lines stay glued to the spheres as they move; an
// edge whose endpoint isn't placed yet collapses to a zero-length (invisible)
// segment until it is.
function GraphEdges({
  sim,
  edges,
  posMap
}: {
  sim: GraphSimulation
  edges: KnowledgeGraph['edges']
  posMap: Map<string, THREE.Vector3>
}): React.JSX.Element | null {
  const size = useThree((s) => s.size)
  // One geometry + material + object, stable for the component's life (three.js
  // objects mutated imperatively — setPositions/setColors/resolution below).
  const gpu = useMemo(() => {
    const geom = new LineSegmentsGeometry()
    const mat = new LineMaterial({
      linewidth: 0.8,
      transparent: true,
      opacity: 0.5,
      vertexColors: true,
      depthTest: true,
      depthWrite: false
    })
    const seg = new LineSegments2(geom, mat)
    seg.renderOrder = -1
    seg.frustumCulled = false
    return { geom, mat, seg }
  }, [])
  // Dispose GPU resources on unmount.
  useEffect(
    () => () => {
      gpu.geom.dispose()
      gpu.mat.dispose()
    },
    [gpu]
  )

  // Mutable per-frame staging buffers in a ref (reallocated only when the edge
  // COUNT changes), so writing them each frame is an intentional imperative
  // update rather than React state — and never trips the no-mutate-hook-values rule.
  const staging = useRef({
    positions: new Float32Array(0),
    colors: new Float32Array(0),
    colorsSet: false,
    n: -1
  })
  const scratch = useRef(new THREE.Color())

  useFrame(() => {
    const s = staging.current
    if (s.n !== edges.length) {
      s.positions = new Float32Array(Math.max(1, edges.length) * 6)
      s.colors = new Float32Array(Math.max(1, edges.length) * 6)
      s.colorsSet = false
      s.n = edges.length
    }
    const { positions, colors } = s
    const { geom, mat } = gpu
    let allPlaced = true
    for (let i = 0; i < edges.length; i++) {
      const e = edges[i]
      const a = posMap.get(e.sourceId) ?? sim.liveNode(e.sourceId)
      const b = posMap.get(e.targetId) ?? sim.liveNode(e.targetId)
      const o = i * 6
      if (!a || !b) {
        // Not placed yet → zero-length segment (draws nothing) until it is.
        positions[o] = positions[o + 1] = positions[o + 2] = 0
        positions[o + 3] = positions[o + 4] = positions[o + 5] = 0
        allPlaced = false
        continue
      }
      positions[o] = a.x ?? 0
      positions[o + 1] = a.y ?? 0
      positions[o + 2] = a.z ?? 0
      positions[o + 3] = b.x ?? 0
      positions[o + 4] = b.y ?? 0
      positions[o + 5] = b.z ?? 0
    }
    geom.setPositions(positions)
    // Color each edge by its target node once its type is known (same scheme as
    // before). Done once, when every endpoint has resolved, so a first-frame race
    // can't bake in a default color for a node still being added.
    if (!s.colorsSet && allPlaced && edges.length > 0) {
      const c = scratch.current
      for (let i = 0; i < edges.length; i++) {
        const t = sim.liveNode(edges[i].targetId)?.nodeType ?? 'concept'
        c.set(nodeColor(t, false))
        const o = i * 6
        colors[o] = colors[o + 3] = c.r
        colors[o + 1] = colors[o + 4] = c.g
        colors[o + 2] = colors[o + 5] = c.b
      }
      geom.setColors(colors)
      s.colorsSet = true
    }
    // Fat-line width is in screen pixels, so the material needs the viewport size.
    mat.resolution.set(size.width, size.height)
  })

  if (edges.length === 0) return null
  return <primitive object={gpu.seg} />
}

// Empty-space margin around the graph. >1 pulls the camera back so there is a
// gap between the outermost node/label and the container border (even when a
// reshuffle briefly pushes a module outward). Larger = bigger gap / more zoomed
// out. Tunable.
const FRAME_MARGIN = 1.2

// Frames the graph for the non-interactive reveal at a SINGLE CONSTANT distance.
// It uses only the measured full-graph radius (the final "apps loaded" framing)
// — never the live bounds — so the camera distance is the same on every step and
// does NOT change when modules appear (e.g. the disk screen). Because the layout
// also pins every module to a constant radius (RING_RADIUS), both the zoom and
// the module spacing are invariant across the whole onboarding. We only recompute
// for the pane's aspect ratio (narrow half-width column), so a window resize
// reframes correctly. The interactive KG page drives its own camera instead.
function CameraRig(): null {
  const { camera, size } = useThree()
  useFrame(() => {
    // While the pane is hidden (display:none) the canvas has no size; skip so we
    // don't compute a NaN/Infinity camera that would flash when it reappears.
    if (size.width === 0 || size.height === 0) return
    const cam = camera as THREE.PerspectiveCamera
    const r = fullGraphRadius()
    const vfov = (cam.fov * Math.PI) / 180
    const aspect = size.width / Math.max(1, size.height)
    const fitForHeight = r / Math.tan(vfov / 2)
    const fitForWidth = r / (Math.tan(vfov / 2) * aspect)
    // eslint-disable-next-line react-hooks/immutability -- r3f: three.js objects (camera, vectors) are mutated imperatively by design
    cam.position.z = Math.max(fitForHeight, fitForWidth) * FRAME_MARGIN
    cam.lookAt(0, 0, 0)
  })
  return null
}

function GraphScene({
  graph,
  centerNodeId,
  interactive,
  shuffleKey,
  frameLoop = 'always',
  labelMode = 'all'
}: BrainGraphProps): React.JSX.Element {
  // The interactive full-screen brain map runs the layout in 3D (OrbitControls lets
  // the user rotate to read depth, mirroring macOS's SceneKit MemoryGraphPage); the
  // fixed-camera surfaces (onboarding, inline Memories card) stay 2D so their labels
  // never overlap with no way to rotate them apart.
  const { sim, nodes, reduced } = useGraphSimulation(graph, centerNodeId, interactive ? 3 : 2)
  const invalidate = useThree((state) => state.invalidate)

  // Label declutter + interaction. Under 'all' every node is labeled (small
  // graphs). Under 'declutter' only the top-K hubs are permanently labeled, plus
  // whatever the user hovers or clicks — so a large graph reads cleanly but any
  // node still names itself on demand.
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // The permanently-labeled base set is invariant to hover/selection, so it is
  // memoized on the ranking inputs only — a hover must not re-run rankNodes.
  const baseLabeled = useMemo(
    () => (labelMode === 'all' ? null : topRankedIds(graph, DEFAULT_LABEL_TOPK, centerNodeId)),
    [labelMode, graph, centerNodeId]
  )
  // Cheap per-interaction union: add the hovered/selected node to the base set.
  const labeledIds = useMemo(() => {
    if (baseLabeled === null) return null
    if (!hoveredId && !selectedId) return baseLabeled
    const ids = new Set(baseLabeled)
    if (hoveredId) ids.add(hoveredId)
    if (selectedId) ids.add(selectedId)
    return ids
  }, [baseLabeled, hoveredId, selectedId])

  // Eased on-screen position of each node, written by the meshes and read by the
  // edges so the lines stay glued to the spheres. Owned here (not on the sim) and
  // recreated on mount, so it can never go stale across hot-reloads.
  const posMapRef = useRef<Map<string, THREE.Vector3>>(undefined)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref / lazy-init (reads newest value in once-registered listeners & imperative loops, avoids stale closures)
  if (!posMapRef.current) posMapRef.current = new Map<string, THREE.Vector3>()
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref / lazy-init (reads newest value in once-registered listeners & imperative loops, avoids stale closures)
  const posMap = posMapRef.current

  // Rearrange the modules on every screen change. Skip the first run so the
  // initial reveal isn't immediately reshuffled; thereafter each new shuffleKey
  // re-rolls distances/angles and reheats, and the meshes ease to their new
  // spots. Reduced motion keeps the graph still.
  const firstShuffle = useRef(true)
  useEffect(() => {
    if (firstShuffle.current) {
      firstShuffle.current = false
      return
    }
    if (!reduced) {
      sim.reshuffle?.()
      if (frameLoop === 'demand') invalidate()
    }
  }, [shuffleKey, sim, reduced, frameLoop, invalidate])

  useEffect(() => {
    if (frameLoop === 'demand') invalidate()
  }, [graph, frameLoop, invalidate])

  // Advance the physics in the render loop (only while warm). Nothing here
  // touches React state, so the scene never re-renders frame to frame.
  useFrame(() => {
    if (!reduced && sim.settleFrame() && frameLoop === 'demand') invalidate()
  })

  // Label overlay: one troika Text per node that should be named (all nodes on
  // small graphs; top hubs + hovered/selected under declutter). Built here so the
  // posMap ref-pass disable sits on a plain statement, not inside JSX.
  const labelEls = nodes
    .filter((n) => labeledIds === null || labeledIds.has(n.id))
    // eslint-disable-next-line react-hooks/refs -- posMap is a lazy-init ref threaded to labels so they follow eased positions; intentional
    .map((n) => (
      <GraphNodeLabel
        key={n.id}
        node={n}
        centerNodeId={centerNodeId}
        posMap={posMap}
        labelFade={interactive === true}
        frameLoop={frameLoop}
      />
    ))

  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight position={[200, 300, 400]} intensity={0.6} />
      {/* Depth fog in 3D so far spheres/edges recede — a depth cue for the mesh
          layer. Billboard labels use troika's own shader and ignore scene fog, so
          the far-label declutter is handled separately by the per-node distance
          fade in GraphNodeLabel. */}
      {interactive && <AdaptiveFog />}
      {interactive && <DrawCallProbe />}
      <GraphEdges sim={sim} edges={graph.edges} posMap={posMap} />
      <GraphNodes
        sim={sim}
        nodes={nodes}
        centerNodeId={centerNodeId}
        reduced={reduced}
        posMap={posMap}
        frameLoop={frameLoop}
        interactive={interactive === true}
        onHover={setHoveredId}
        onSelect={setSelectedId}
      />
      {/* Labels are a thin overlay: only the nodes that should be named mount a
          troika Text, positioned from the eased positions GraphNodes publishes. */}
      {labelEls}
      {interactive ? (
        <>
          <OrbitControls makeDefault enablePan enableZoom enableRotate />
          <FitCamera radius={nodes.length > 0 ? sim.boundingRadius() : 0} />
        </>
      ) : (
        <CameraRig />
      )}
    </>
  )
}

// Diagnostic (interactive scene only): publish the live three.js draw-call count
// on window so the perf harness can assert draw calls stay independent of graph
// size after batching/instancing. Reading renderer.info is free; writing one
// number per frame is negligible and never affects rendering.
function DrawCallProbe(): null {
  const gl = useThree((s) => s.gl)
  useFrame(() => {
    ;(window as unknown as { __omiGraphDrawCalls?: number }).__omiGraphDrawCalls =
      gl.info.render.calls
  })
  return null
}

// Interactive 3D only: depth fog whose near/far track the CAMERA'S CURRENT
// DISTANCE from the cloud center every frame. Fixed distances cannot work here:
// FitCamera places the camera at ~4.8× the graph's bounding radius (fov 28), so
// with a real, dense graph the whole cloud sits far beyond any constant far
// plane — 100% fogged, every node near-black at the default zoom (and zooming
// with OrbitControls changes the distance anyway). Tracking the camera keeps the
// front half of the cloud unfogged at ANY zoom while the back half recedes to
// ~2/3 visibility — a depth cue, never a blackout.
function AdaptiveFog(): React.JSX.Element {
  const fogRef = useRef<THREE.Fog>(null)
  const span = useMemo(() => fullGraphRadius(), [])
  useFrame(({ camera }) => {
    const f = fogRef.current
    if (!f) return
    const d = camera.position.length()
    f.near = d
    f.far = d + span * 3
  })
  // Initial args are immediately overwritten by the first frame; color matches
  // the app's dark backdrop so fogged geometry blends into it, not to gray.
  return <fog ref={fogRef} attach="fog" args={[0x0a0a0f, 500, 1400]} />
}

// Interactive 3D only: one-shot framing of the whole cloud. Pulls the camera back
// so the 3D bounding SPHERE fits (the flat CameraRig frames a 2D radius and never
// runs here), then hands control to OrbitControls, which orbits around the origin
// where the pinned "you" node sits. Re-fits if the cloud's radius grows (new
// nodes) but never fights the user mid-orbit — it only sets the initial distance.
function FitCamera({ radius }: { radius: number }): null {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as {
    target: THREE.Vector3
    update: () => void
  } | null
  const framedFor = useRef(0)
  useEffect(() => {
    if (radius <= 0 || !controls) return
    // Only (re)frame when the radius meaningfully grows, so an incremental add
    // widens the view but a settled graph is never nudged.
    if (radius <= framedFor.current * 1.05) return
    framedFor.current = radius
    const cam = camera as THREE.PerspectiveCamera
    const vfov = (cam.fov * Math.PI) / 180
    const dist = (radius / Math.tan(vfov / 2)) * FRAME_MARGIN
    // Position + target only (method calls) — the Canvas camera's far (20000) already
    // clears any fit distance, so no projection-param writes are needed here.
    cam.position.set(0, 0, dist)
    controls.target.set(0, 0, 0)
    controls.update()
  }, [radius, controls, camera])
  return null
}

// Shared 3D knowledge-graph renderer. Used by onboarding (live local graph) and
// the Knowledge Graph page (server graph). Background is transparent so the
// host pane's dark/glass styling shows through.
//
// KG-page adoption (feat/knowledge-graph): render
//   <BrainGraph graph={useKnowledgeGraph().graph ?? { nodes: [], edges: [] }}
//               centerNodeId={graph.nodes.find(n => n.nodeType === 'person')?.id} />
// inside a positioned (relative) container. The server graph uses the same
// KGNode/KGEdge shape, so no mapping is needed.
export function BrainGraph({
  graph,
  centerNodeId,
  interactive = true,
  shuffleKey,
  pauseWhenHidden = false,
  frameLoop = 'always',
  onReady,
  onVisibleChange,
  labelMode = 'all'
}: BrainGraphProps): React.JSX.Element {
  const hostRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  // Latest-ref so the effect below can depend on just `showCanvas` (only fire
  // on real transitions) without also re-firing whenever a caller passes a
  // new inline callback identity on every render.
  const onVisibleChangeRef = useRef(onVisibleChange)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref (keeps the effect below from re-firing on every render just because the caller passed a new inline callback)
  onVisibleChangeRef.current = onVisibleChange
  const onReadyRef = useRef(onReady)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref (same reason as above: onReady is passed as an inline callback)
  onReadyRef.current = onReady

  // Off-screen GPU saving for the Memories tab only (pauseWhenHidden): UNMOUNT
  // the canvas while the host is collapsed to 0×0 (its MainViews tab is
  // display:none'd) so it costs nothing, then remount fresh when shown. We
  // unmount rather than toggle `frameloop` because toggling to 'never' across a
  // resize leaves the GL canvas cleared-but-not-repainted (and can lose the
  // context) → a permanent blank. Onboarding leaves pauseWhenHidden false: its
  // map is kept mounted across steps and must always render.
  useEffect(() => {
    if (!pauseWhenHidden) return
    const el = hostRef.current
    if (!el) return
    // Debounce HIDE decisions only, not show ones: measured on the real page,
    // a ResizeObserver tick can report a genuine 0×0 for this container —
    // observed immediately after the canvas's WebGL context is created, which
    // itself briefly perturbs the compositor — immediately followed by another
    // real tick reporting its normal size again 60-120ms later, with no actual
    // tab switch in between. Acting on that first 0×0 unmounted+remounted the
    // whole canvas — and doing that repeatedly, in quick succession, was
    // observed to lose the WebGL context outright (software rendering under
    // dev's forced-software-WebGL has a low tolerance for rapid context churn):
    // a real crash, not just a wasted rebuild. A real "tab went inactive" stays
    // at 0×0 well past this window, so (a) requiring the reading to hold for
    // 250ms before hiding, and (b) refusing to even arm that timer within 500ms
    // of the last time we showed (exactly when a just-created context's own
    // compositor blip lands) still catches a genuine hide — just slightly
    // later — while filtering out the blip that used to compound into a crash.
    // Showing is always acted on immediately — there's nothing to protect there.
    let hideTimer: ReturnType<typeof setTimeout> | undefined
    let lastShownAt = 0
    const update = (): void => {
      const hasSize = el.clientWidth > 0 && el.clientHeight > 0
      if (hasSize) {
        if (hideTimer) {
          clearTimeout(hideTimer)
          hideTimer = undefined
        }
        lastShownAt = Date.now()
        setVisible(true)
        return
      }
      if (hideTimer || Date.now() - lastShownAt < 500) return
      hideTimer = setTimeout(() => {
        hideTimer = undefined
        setVisible(el.clientWidth > 0 && el.clientHeight > 0)
      }, 250)
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => {
      if (hideTimer) clearTimeout(hideTimer)
      ro.disconnect()
    }
  }, [pauseWhenHidden])

  const showCanvas = !pauseWhenHidden || visible

  useEffect(() => {
    onVisibleChangeRef.current?.(showCanvas)
  }, [showCanvas])

  // Stable identity (reads onVisibleChangeRef, never the raw prop) so passing
  // it to useWebglRecovery doesn't re-run that hook's effect every render.
  const handleContextLost = useCallback(() => onVisibleChangeRef.current?.(false), [])

  // renderFailed: the last mount attempt could not get a live WebGL context (the
  // Canvas threw, or recovery exhausted its remount budget). It drives the heal
  // loop below; handleCreated clears it the instant a context is really obtained.
  const [renderFailed, setRenderFailed] = useState(false)
  // retryTick: bump to REMOUNT the boundary + Canvas. The remount IS the probe —
  // three.js re-attempts context creation and either succeeds (onCreated) or throws
  // (onError). We never create a throwaway probe context (that was the fail-CLOSED
  // mistake that could exhaust the pool); we just retry the real thing.
  const [retryTick, setRetryTick] = useState(0)
  const retry = useCallback(() => setRetryTick((t) => t + 1), [])

  // Remount the canvas subtree on webglcontextlost so a GPU-process crash
  // (SwiftShader included) yields a fresh context instead of Chromium's
  // broken-image placeholder. Covers direct mounts (Onboarding) that bypass
  // LazyBrainGraph's own recovery wrapper. onContextLost reports the loss to the
  // caller (e.g. Memories.tsx) immediately, ahead of the debounced remount.
  // onExhausted fires when recovery gives up (its remount cap) — we then surface the
  // fallback and force one fresh mount so a hidden/dead canvas is never left stranded.
  const handleExhausted = useCallback((): void => {
    setRenderFailed(true)
    retry()
  }, [retry])
  const recoveryKey = useWebglRecovery(hostRef, handleContextLost, handleExhausted)

  // HEAL. A recovered GPU emits NO event of its own — useWebglRecovery only re-fires
  // on another context LOSS, and its post-loss remount is debounced just 600ms, far
  // shorter than a real GPU/SwiftShader restart takes to accept new contexts. So a
  // single post-loss attempt can land while creation is still refused, and without
  // this the fallback would latch for the life of the mount (onboarding never
  // unmounts its map). While failed, retry the REAL mount on a capped backoff and
  // whenever the window/tab becomes visible again; a success clears renderFailed and
  // stops the loop. Backoff (not a fixed tight interval) so a genuinely GPU-less
  // machine isn't remounting a throwing renderer every few seconds forever.
  useEffect(() => {
    if (!renderFailed) return
    let attempt = 0
    let timer: ReturnType<typeof setTimeout>
    const schedule = (): void => {
      const delay = Math.min(3000 * 2 ** attempt, 30_000)
      attempt += 1
      timer = setTimeout(() => {
        retry()
        schedule()
      }, delay)
    }
    schedule()
    const onVisible = (): void => {
      if (document.visibilityState === 'visible') retry()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [renderFailed, retry])

  // FAIL OPEN. We do NOT pre-probe for a WebGL context to decide whether to mount
  // the graph, and must never go back to doing so. A probe has to CREATE a context
  // to answer, and live contexts are a capped, shared resource (the bar Orb and this
  // map already hold some). Near that cap the probe's own extra context is the one
  // that fails — so the probe returns "WebGL is broken" on a perfectly healthy
  // machine and suppresses a graph that would have rendered. It manufactures the
  // failure it reports. (It also asks for a bare webgl2 context, which is not the
  // request three.js makes, so its answer was never evidence about the real canvas.)
  //
  // three.js is the ground truth instead: if a context truly cannot be had,
  // WebGLRenderer THROWS on construction ("Error creating WebGL context.", pinned in
  // webglRendererThrows.test.ts) and the boundary below catches THAT. A false "GPU is
  // fine" costs nothing (the boundary still catches the real failure); a false "GPU is
  // broken" costs the user their entire brain map. So only a definite, observed
  // failure may show the fallback.
  //
  // Corollary: an empty-looking canvas must never trigger the fallback either. The
  // graph currently paints nothing on some healthy contexts — a separate render bug —
  // and a fallback that fired on "looks blank" would mask it permanently.
  const degraded = useRef(false)
  const reportMode = useCallback((webgl: boolean, reason: string): void => {
    if (degraded.current === !webgl) return
    degraded.current = !webgl
    trackEvent('fallback_triggered', {
      component: 'brain_graph_render',
      from: webgl ? 'static' : 'webgl',
      to: webgl ? 'webgl' : 'static',
      reason,
      outcome: webgl ? 'recovered' : 'degraded'
    })
  }, [])

  const handleRendererFailed = useCallback((): void => {
    reportMode(false, 'renderer_init_failed')
    setRenderFailed(true) // arm the heal loop
    // The static mark IS the finished surface in this mode. Callers gate a loading
    // placeholder on onReady (Memories crossfades on it), so without this the mark
    // would sit invisible behind a spinner until their bounded timeout.
    onReadyRef.current?.()
  }, [reportMode])

  const handleCreated = useCallback((): void => {
    // A context was really obtained — we are live. Clear the failed flag (stops the
    // heal loop) and, if we had degraded, report the recovery.
    setRenderFailed(false)
    reportMode(true, 'renderer_init_failed')
    onReadyRef.current?.()
  }, [reportMode])

  return (
    <div ref={hostRef} className="absolute inset-0">
      {showCanvas && (
        // Keyed with BOTH recoveryKey (post-crash canvas remount) and retryTick (the
        // heal loop's retry). A caught throw latches this boundary's own `failed`
        // state; the only way to clear it is a fresh boundary instance, so every heal
        // attempt must bump the key. Without retryTick a boundary that caught once
        // would pin the fallback for the life of the mount even on a recovered GPU.
        <ErrorBoundary
          key={`${recoveryKey}:${retryTick}`}
          label="BrainGraph"
          fallback={<BrainGraphFallback />}
          onError={handleRendererFailed}
        >
          <Canvas
            // Narrow FOV: a wide FOV projects off-center spheres into ellipses
            // ("deformed" nodes); this keeps them as round circles. CameraRig derives
            // its distance from the FOV, so the framing/zoom is unchanged.
            camera={{ position: [0, 0, 700], fov: 28, near: 1, far: 20000 }}
            dpr={[1, 2]}
            frameloop={frameLoop}
            gl={{ antialias: true, alpha: true }}
            onCreated={handleCreated}
          >
            <GraphScene
              graph={graph}
              centerNodeId={centerNodeId}
              interactive={interactive}
              shuffleKey={shuffleKey}
              frameLoop={frameLoop}
              labelMode={labelMode}
            />
          </Canvas>
        </ErrorBoundary>
      )}
    </div>
  )
}

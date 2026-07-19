import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Billboard, Text, Line } from '@react-three/drei'
import * as THREE from 'three'
import type { KnowledgeGraph } from '../../../../shared/types'
import {
  useGraphSimulation,
  fullGraphRadius,
  labelFontSize,
  type GraphSimulation,
  type NodePosition
} from '../../lib/useGraphSimulation'
import { nodeColor } from './nodeColor'
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

function GraphNodeMesh({
  sim,
  node,
  centerNodeId,
  reduced,
  posMap,
  frameLoop,
  labelFade
}: {
  sim: GraphSimulation
  node: NodePosition
  centerNodeId?: string
  reduced: boolean
  // Shared map (owned by GraphScene, recreated on mount) where each node writes
  // its eased on-screen position so the edges can connect to it.
  posMap: Map<string, THREE.Vector3>
  frameLoop: 'always' | 'demand'
  // 3D only: fade a label by how far its node sits BEHIND the cloud center
  // relative to the camera, so back-of-cloud titles recede instead of stacking
  // on the front ones. Off (labels full-opacity) on the flat 2D surfaces.
  labelFade: boolean
}): React.JSX.Element {
  const groupRef = useRef<THREE.Group>(null)
  const coreMat = useRef<THREE.MeshStandardMaterial>(null)
  const glowMat = useRef<THREE.MeshBasicMaterial>(null)
  const glowMesh = useRef<THREE.Mesh>(null)
  // troika Text instance (drei <Text> forwards its ref here); has fillOpacity + sync().
  const textRef = useRef<{ fillOpacity: number; sync: () => void } | null>(null)
  const lastFade = useRef(1)
  const target = useRef(new THREE.Vector3(node.x, node.y, node.z))
  const isFixed = node.id === centerNodeId
  const color = nodeColor(node.nodeType, isFixed)
  const radius = radiusFor(node, isFixed)
  // The center ("you") label gets a bit bigger than the proportional size.
  const labelSize = labelFontSize(node.sizeScale) * (isFixed ? 1.35 : 1)
  const phase = useMemo(() => hashPhase(node.id), [node.id])
  // Depth scale for the fade: the same analytic radius the camera frames to, so
  // a node a full cloud-radius behind center fades to the floor opacity.
  const fadeSpan = useMemo(() => fullGraphRadius(), [])
  const invalidate = useThree((state) => state.invalidate)

  // Read the live simulation position each frame (no React state in the loop)
  // and ease toward it so motion stays smooth. New nodes fly out from the
  // center and grow 0 → full size, then settle into a gentle continuous shine.
  useFrame((state) => {
    const g = groupRef.current
    if (!g) return
    const live = sim.liveNode(node.id)
    if (live) target.current.set(live.x ?? 0, live.y ?? 0, live.z ?? 0)

    let shouldContinue = false
    if (reduced) {
      g.position.copy(target.current)
      g.scale.setScalar(1)
    } else {
      // Low lerp factor = slow, smooth glide toward the target (used both for
      // the initial reveal and for the gentle reshuffle drift between screens).
      g.position.lerp(target.current, 0.045)
      if (g.position.distanceToSquared(target.current) < 0.01) g.position.copy(target.current)
      if (g.scale.x < 1) g.scale.setScalar(Math.min(1, g.scale.x + 0.05))
      shouldContinue = g.position.distanceToSquared(target.current) > 0.01 || g.scale.x < 1
    }
    // Record the eased on-screen position so the connecting lines follow the
    // sphere exactly (instead of snapping to the raw sim position). The map is
    // plain React-owned state, so this can never throw / blank the canvas.
    let v = posMap.get(node.id)
    if (!v) {
      v = new THREE.Vector3()
      posMap.set(node.id, v)
    }
    v.copy(g.position)

    // Shine: pulse the emissive core + halo so the modules glow and feel alive.
    // While a node is still growing in it flares brighter, giving the reveal a
    // satisfying "pop" before it settles to its idle twinkle.
    const entering = !reduced && g.scale.x < 1
    const t = state.clock.elapsedTime
    const pulse = reduced ? 0.6 : 0.5 + 0.5 * Math.sin(t * 2 + phase)
    const flare = entering ? 1.8 : 1
    if (coreMat.current) coreMat.current.emissiveIntensity = (0.85 + 0.45 * pulse) * flare
    if (glowMat.current) glowMat.current.opacity = (0.12 + 0.14 * pulse) * flare
    if (glowMesh.current) glowMesh.current.scale.setScalar(1 + 0.18 * pulse)

    // Depth fade (3D only): dim a label by how far its node sits BEHIND the cloud
    // center as seen from the camera (origin is the pinned "you" node / cloud
    // center). Quantized to 1/8 so troika only re-syncs a handful of times across
    // an orbit, not every frame. This is what keeps the front titles crisp while
    // the far side recedes — the readability win over a raw 3D cloud.
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
    if (frameLoop === 'demand' && shouldContinue) invalidate()
  })

  return (
    <group
      ref={groupRef}
      position={[node.x, node.y, node.z]}
      scale={reduced ? [1, 1, 1] : [0, 0, 0]}
    >
      <mesh>
        {/* 16×16 (down from 32×32): at the on-screen size these spheres actually
            render — small, glowing, and softened by the halo/bloom layers below
            — the extra polys were invisible but every one of them still had to
            be transformed and rasterized every animated frame across all nodes.
            This is the single biggest per-frame triangle-count cut here. */}
        <sphereGeometry args={[radius, 16, 16]} />
        <meshStandardMaterial
          ref={coreMat}
          color={color}
          emissive={color}
          emissiveIntensity={0.85}
          roughness={0.3}
          metalness={0.1}
        />
      </mesh>
      {/* pulsing glow halo (scales with the shine) */}
      <mesh ref={glowMesh}>
        <sphereGeometry args={[radius * 1.9, 12, 12]} />
        <meshBasicMaterial
          ref={glowMat}
          color={color}
          transparent
          opacity={0.12}
          depthWrite={false}
        />
      </mesh>
      {/* faint outer bloom for extra shine */}
      <mesh>
        <sphereGeometry args={[radius * 3, 8, 8]} />
        <meshBasicMaterial color={color} transparent opacity={0.04} depthWrite={false} />
      </mesh>
      <Billboard position={[0, radius + labelSize * 0.9, 0]}>
        <Text
          ref={textRef as never}
          // Font varies only ±20% with node size (matches collision/framing);
          // the center label is bumped a bit larger.
          fontSize={labelSize}
          color="#ffffff"
          anchorX="center"
          anchorY="middle"
          // Always on top of the lines/nodes so titles stay readable.
          renderOrder={4}
          depthOffset={-1}
        >
          {node.label}
        </Text>
      </Billboard>
    </group>
  )
}

// A single connecting line, drawn as a fat (real pixel-width) line so it is
// actually visible — plain THREE lines render at 1px and disappear against the
// glowing nodes. Its two endpoints are rewritten every frame from the eased
// on-screen positions, so the line stays glued to both spheres as they move.
// Colored by its target (module) node, so each line matches its node.
function GraphEdge({
  sim,
  edge,
  color,
  posMap
}: {
  sim: GraphSimulation
  edge: KnowledgeGraph['edges'][number]
  color: string
  posMap: Map<string, THREE.Vector3>
}): React.JSX.Element {
  const ref = useRef<{ geometry: { setPositions(p: number[]): void } } | null>(null)
  // Reused every frame instead of a fresh array literal each time — setPositions
  // only reads these six values (it copies them into its own GPU buffer), so
  // there's nothing gained by allocating a new array per edge per frame, only
  // GC pressure from it.
  const positions = useRef<number[]>([0, 0, 0, 0, 0, 0]).current
  useFrame(() => {
    const a = posMap.get(edge.sourceId) ?? sim.liveNode(edge.sourceId)
    const b = posMap.get(edge.targetId) ?? sim.liveNode(edge.targetId)
    if (!a || !b || !ref.current) return
    positions[0] = a.x ?? 0
    positions[1] = a.y ?? 0
    positions[2] = a.z ?? 0
    positions[3] = b.x ?? 0
    positions[4] = b.y ?? 0
    positions[5] = b.z ?? 0
    ref.current.geometry.setPositions(positions)
  })
  return (
    <Line
      ref={ref as never}
      points={[
        [0, 0, 0],
        [1, 0, 0]
      ]}
      color={color}
      lineWidth={0.8}
      transparent
      opacity={0.5}
      // Extra thin and underneath everything: depthTest on so the opaque node
      // balls occlude the lines, negative renderOrder + depthWrite off so the
      // glow and labels also sit on top.
      renderOrder={-1}
      depthTest={true}
      depthWrite={false}
    />
  )
}

function GraphEdges({
  sim,
  edges,
  posMap
}: {
  sim: GraphSimulation
  edges: KnowledgeGraph['edges']
  posMap: Map<string, THREE.Vector3>
}): React.JSX.Element {
  // Only draw edges whose endpoints both exist in the sim yet.
  const drawn = edges.filter((e) => sim.liveNode(e.sourceId) && sim.liveNode(e.targetId))
  return (
    <>
      {drawn.map((e) => (
        <GraphEdge
          key={e.id}
          sim={sim}
          edge={e}
          color={nodeColor(sim.liveNode(e.targetId)?.nodeType ?? 'concept', false)}
          posMap={posMap}
        />
      ))}
    </>
  )
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
  frameLoop = 'always'
}: BrainGraphProps): React.JSX.Element {
  // The interactive full-screen brain map runs the layout in 3D (OrbitControls lets
  // the user rotate to read depth, mirroring macOS's SceneKit MemoryGraphPage); the
  // fixed-camera surfaces (onboarding, inline Memories card) stay 2D so their labels
  // never overlap with no way to rotate them apart.
  const { sim, nodes, reduced } = useGraphSimulation(graph, centerNodeId, interactive ? 3 : 2)
  const invalidate = useThree((state) => state.invalidate)

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

  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight position={[200, 300, 400]} intensity={0.6} />
      {/* Depth fog in 3D so far spheres/edges recede — a depth cue for the mesh
          layer. Billboard labels use troika's own shader and ignore scene fog, so
          the far-label declutter is handled separately by the per-node distance
          fade in GraphNodeMesh. */}
      {interactive && <AdaptiveFog />}
      <GraphEdges sim={sim} edges={graph.edges} posMap={posMap} />
      {/* eslint-disable-next-line react-hooks/refs -- posMap is a lazy-init ref read here to glue edges/nodes to eased positions; intentional */}
      {nodes.map((n) => (
        <GraphNodeMesh
          key={n.id}
          sim={sim}
          node={n}
          centerNodeId={centerNodeId}
          reduced={reduced}
          posMap={posMap}
          frameLoop={frameLoop}
          labelFade={interactive === true}
        />
      ))}
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
  onVisibleChange
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
            />
          </Canvas>
        </ErrorBoundary>
      )}
    </div>
  )
}

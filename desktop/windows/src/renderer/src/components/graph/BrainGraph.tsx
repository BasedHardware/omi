import { useEffect, useMemo, useRef, useState } from 'react'
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
  posMap
}: {
  sim: GraphSimulation
  node: NodePosition
  centerNodeId?: string
  reduced: boolean
  // Shared map (owned by GraphScene, recreated on mount) where each node writes
  // its eased on-screen position so the edges can connect to it.
  posMap: Map<string, THREE.Vector3>
}): React.JSX.Element {
  const groupRef = useRef<THREE.Group>(null)
  const coreMat = useRef<THREE.MeshStandardMaterial>(null)
  const glowMat = useRef<THREE.MeshBasicMaterial>(null)
  const glowMesh = useRef<THREE.Mesh>(null)
  const target = useRef(new THREE.Vector3(node.x, node.y, node.z))
  const isFixed = node.id === centerNodeId
  const color = nodeColor(node.nodeType, isFixed)
  const radius = radiusFor(node, isFixed)
  // The center ("you") label gets a bit bigger than the proportional size.
  const labelSize = labelFontSize(node.sizeScale) * (isFixed ? 1.35 : 1)
  const phase = useMemo(() => hashPhase(node.id), [node.id])

  // Read the live simulation position each frame (no React state in the loop)
  // and ease toward it so motion stays smooth. New nodes fly out from the
  // center and grow 0 → full size, then settle into a gentle continuous shine.
  useFrame((state) => {
    const g = groupRef.current
    if (!g) return
    const live = sim.liveNode(node.id)
    if (live) target.current.set(live.x ?? 0, live.y ?? 0, live.z ?? 0)

    if (reduced) {
      g.position.copy(target.current)
      g.scale.setScalar(1)
    } else {
      // Low lerp factor = slow, smooth glide toward the target (used both for
      // the initial reveal and for the gentle reshuffle drift between screens).
      g.position.lerp(target.current, 0.045)
      if (g.scale.x < 1) g.scale.setScalar(Math.min(1, g.scale.x + 0.05))
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
  })

  return (
    <group ref={groupRef} position={[node.x, node.y, node.z]} scale={reduced ? [1, 1, 1] : [0, 0, 0]}>
      <mesh>
        <sphereGeometry args={[radius, 32, 32]} />
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
        <sphereGeometry args={[radius * 1.9, 24, 24]} />
        <meshBasicMaterial ref={glowMat} color={color} transparent opacity={0.12} depthWrite={false} />
      </mesh>
      {/* faint outer bloom for extra shine */}
      <mesh>
        <sphereGeometry args={[radius * 3, 16, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.04} depthWrite={false} />
      </mesh>
      <Billboard position={[0, radius + labelSize * 0.9, 0]}>
        <Text
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
  useFrame(() => {
    const a = posMap.get(edge.sourceId) ?? sim.liveNode(edge.sourceId)
    const b = posMap.get(edge.targetId) ?? sim.liveNode(edge.targetId)
    if (!a || !b || !ref.current) return
    ref.current.geometry.setPositions([
      a.x ?? 0,
      a.y ?? 0,
      a.z ?? 0,
      b.x ?? 0,
      b.y ?? 0,
      b.z ?? 0
    ])
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
    cam.position.z = Math.max(fitForHeight, fitForWidth) * FRAME_MARGIN
    cam.lookAt(0, 0, 0)
  })
  return null
}

function GraphScene({
  graph,
  centerNodeId,
  interactive,
  shuffleKey
}: BrainGraphProps): React.JSX.Element {
  const { sim, nodes, reduced } = useGraphSimulation(graph, centerNodeId)

  // Eased on-screen position of each node, written by the meshes and read by the
  // edges so the lines stay glued to the spheres. Owned here (not on the sim) and
  // recreated on mount, so it can never go stale across hot-reloads.
  const posMapRef = useRef<Map<string, THREE.Vector3>>(undefined)
  if (!posMapRef.current) posMapRef.current = new Map<string, THREE.Vector3>()
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
    if (!reduced) sim.reshuffle?.()
  }, [shuffleKey, sim, reduced])

  // Advance the physics in the render loop (only while warm). Nothing here
  // touches React state, so the scene never re-renders frame to frame.
  useFrame(() => {
    if (!reduced) sim.settleFrame()
  })

  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight position={[200, 300, 400]} intensity={0.6} />
      <GraphEdges sim={sim} edges={graph.edges} posMap={posMap} />
      {nodes.map((n) => (
        <GraphNodeMesh
          key={n.id}
          sim={sim}
          node={n}
          centerNodeId={centerNodeId}
          reduced={reduced}
          posMap={posMap}
        />
      ))}
      {interactive ? (
        <OrbitControls enablePan enableZoom enableRotate />
      ) : (
        <CameraRig />
      )}
    </>
  )
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
  pauseWhenHidden = false
}: BrainGraphProps): React.JSX.Element {
  const hostRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)

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
    const update = (): void => setVisible(el.clientWidth > 0 && el.clientHeight > 0)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [pauseWhenHidden])

  const showCanvas = !pauseWhenHidden || visible

  return (
    <div ref={hostRef} className="absolute inset-0">
      {showCanvas && (
      <Canvas
        // Narrow FOV: a wide FOV projects off-center spheres into ellipses
        // ("deformed" nodes); this keeps them as round circles. CameraRig derives
        // its distance from the FOV, so the framing/zoom is unchanged.
        camera={{ position: [0, 0, 700], fov: 28, near: 1, far: 20000 }}
        dpr={[1, 2]}
        frameloop="always"
        gl={{ antialias: true, alpha: true }}
      >
        <GraphScene
          graph={graph}
          centerNodeId={centerNodeId}
          interactive={interactive}
          shuffleKey={shuffleKey}
        />
      </Canvas>
      )}
    </div>
  )
}

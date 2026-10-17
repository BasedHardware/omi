// The memory atlas: the knowledge graph drawn as a map.
//
// The existing brain map keeps a large graph legible by HIDING nodes - a default
// cap on the most connected, with a "show all" escape hatch. Its own header
// records why: a real account measures ~188 nodes and ~474 edges with one
// 226-degree hub, and drawn whole it is an unreadable hairball.
//
// This takes the opposite approach to the same problem. Nothing is hidden;
// instead the entities are grouped into named regions, so the shape of the map
// carries the structure and the labels say what each part is about. Detail
// arrives as you zoom in rather than being thrown away up front.
//
// Canvas 2D rather than WebGL: this draws filled polygons and text, which canvas
// does natively, and it means the map renders in a plain jsdom test.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { KnowledgeGraph } from '../../../../shared/types'
import { buildAtlas, type Atlas } from '../../lib/atlas/buildAtlas'
import { territoryAt, type Territory } from '../../lib/atlas/territories'
import {
  MINIMUM_ZOOM,
  detailBudget,
  maximumZoom,
  panPreservingCenter,
  zoomToEnter
} from '../../lib/atlas/zoomPolicy'
import type { AtlasPoint } from '../../lib/atlas/islands'

/** Inset so a region touching the edge of the field still has margin on screen. */
const PADDING = 24

interface Camera {
  zoom: number
  panX: number
  panY: number
}

const IDENTITY: Camera = { zoom: 1, panX: 0, panY: 0 }

/** Atlas space (0..1) to canvas pixels. */
function project(
  point: AtlasPoint,
  camera: Camera,
  width: number,
  height: number
): { x: number; y: number } {
  const span = Math.min(width, height) - PADDING * 2
  return {
    x: width / 2 + (point.x - 0.5) * span * camera.zoom + camera.panX,
    // Atlas y runs up; canvas y runs down.
    y: height / 2 - (point.y - 0.5) * span * camera.zoom - camera.panY
  }
}

/** Canvas pixels back to atlas space, for hit testing. */
function unproject(
  x: number,
  y: number,
  camera: Camera,
  width: number,
  height: number
): AtlasPoint {
  const span = Math.min(width, height) - PADDING * 2
  return {
    x: (x - width / 2 - camera.panX) / (span * camera.zoom) + 0.5,
    y: -(y - height / 2 + camera.panY) / (span * camera.zoom) + 0.5
  }
}

function drawTerritory(
  ctx: CanvasRenderingContext2D,
  territory: Territory,
  camera: Camera,
  width: number,
  height: number,
  highlighted: boolean
): void {
  ctx.beginPath()
  for (const ring of territory.rings) {
    if (ring.length < 3) continue
    ring.forEach((point, i) => {
      const p = project(point, camera, width, height)
      if (i === 0) ctx.moveTo(p.x, p.y)
      else ctx.lineTo(p.x, p.y)
    })
    ctx.closePath()
  }
  // Even-odd so a ring enclosed by another reads as a hole, matching the
  // containment test the rest of the atlas uses.
  ctx.fillStyle = highlighted ? 'rgba(255,255,255,0.10)' : 'rgba(255,255,255,0.045)'
  ctx.fill('evenodd')
  ctx.strokeStyle = highlighted ? 'rgba(255,255,255,0.34)' : 'rgba(255,255,255,0.16)'
  ctx.lineWidth = 1
  ctx.stroke()
}

export interface MemoryAtlasProps {
  graph: KnowledgeGraph
  centerNodeId?: string
  /** Reports what the user is looking at, so a host can show it as chrome. */
  onFocusTerritory?: (territory: Territory | null) => void
}

export function MemoryAtlas(props: MemoryAtlasProps): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [camera, setCamera] = useState<Camera>(IDENTITY)
  const [hovered, setHovered] = useState<Territory | null>(null)
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null)

  const atlas: Atlas = useMemo(
    () => buildAtlas(props.graph, props.centerNodeId),
    [props.graph, props.centerNodeId]
  )

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (canvas === null) return
    const ctx = canvas.getContext('2d')
    if (ctx === null) return

    const ratio = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    const height = canvas.clientHeight
    if (width === 0 || height === 0) return
    canvas.width = Math.floor(width * ratio)
    canvas.height = Math.floor(height * ratio)
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    ctx.clearRect(0, 0, width, height)

    const budget = detailBudget(camera.zoom, atlas.nodes.length)

    for (const territory of atlas.territories) {
      drawTerritory(ctx, territory, camera, width, height, territory === hovered)
    }

    // Entities: most connected first, so a cap keeps the structural hubs.
    const ranked = [...atlas.nodes].sort((a, b) => b.degree - a.degree)
    const shown = ranked.slice(0, budget.maxNodes)
    for (const node of shown) {
      const p = project(node.position, camera, width, height)
      ctx.beginPath()
      ctx.arc(p.x, p.y, node.community === -1 ? 4 : 2.5, 0, Math.PI * 2)
      ctx.fillStyle = node.community === -1 ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.45)'
      ctx.fill()
    }

    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (const node of shown.slice(0, budget.maxLabels)) {
      const p = project(node.position, camera, width, height)
      ctx.font = '11px system-ui, sans-serif'
      ctx.fillStyle = 'rgba(255,255,255,0.62)'
      ctx.fillText(node.label, p.x, p.y - 9)
    }

    // Region captions last, so they sit above everything they name.
    for (const territory of atlas.territories) {
      const p = project(territory.center, camera, width, height)
      ctx.font = '600 10px system-ui, sans-serif'
      ctx.fillStyle = 'rgba(255,255,255,0.78)'
      // Uppercased at draw time only; the stored caption keeps its own casing.
      ctx.fillText(territory.caption.toUpperCase(), p.x, p.y)
    }
  }, [atlas, camera, hovered])

  useEffect(() => {
    draw()
  }, [draw])

  useEffect(() => {
    const onResize = (): void => draw()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [draw])

  const pointFor = (e: React.MouseEvent<HTMLCanvasElement>): AtlasPoint | null => {
    const canvas = canvasRef.current
    if (canvas === null) return null
    const rect = canvas.getBoundingClientRect()
    return unproject(
      e.clientX - rect.left,
      e.clientY - rect.top,
      camera,
      canvas.clientWidth,
      canvas.clientHeight
    )
  }

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label={`Memory atlas with ${atlas.territories.length} regions`}
      className="h-full w-full cursor-grab active:cursor-grabbing"
      onWheel={(e) => {
        const next = Math.min(
          Math.max(camera.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1), MINIMUM_ZOOM),
          maximumZoom(atlas.nodes.length, false)
        )
        setCamera((c) => ({
          zoom: next,
          panX: panPreservingCenter(c.panX, c.zoom, next),
          panY: panPreservingCenter(c.panY, c.zoom, next)
        }))
      }}
      onMouseDown={(e) => {
        drag.current = { x: e.clientX, y: e.clientY, panX: camera.panX, panY: camera.panY }
      }}
      onMouseUp={() => {
        drag.current = null
      }}
      onMouseLeave={() => {
        drag.current = null
        setHovered(null)
        props.onFocusTerritory?.(null)
      }}
      onMouseMove={(e) => {
        const dragging = drag.current
        if (dragging !== null) {
          setCamera((c) => ({
            ...c,
            panX: dragging.panX + (e.clientX - dragging.x),
            panY: dragging.panY - (e.clientY - dragging.y)
          }))
          return
        }
        const point = pointFor(e)
        const found = point === null ? null : territoryAt(atlas.territories, point)
        if (found !== hovered) {
          setHovered(found)
          props.onFocusTerritory?.(found)
        }
      }}
      onDoubleClick={(e) => {
        const point = pointFor(e)
        const found = point === null ? null : territoryAt(atlas.territories, point)
        if (found === null) {
          setCamera(IDENTITY)
          return
        }
        // Frame the region rather than jumping to a fixed magnification, so a
        // small region fills the same share of the viewport as a large one.
        setCamera({ zoom: zoomToEnter(found.radius, atlas.nodes.length), panX: 0, panY: 0 })
      }}
    />
  )
}

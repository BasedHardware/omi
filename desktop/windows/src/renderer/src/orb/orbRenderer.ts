// Raw WebGL2 rasterizer for the orb (no three.js). Renders an OrbFrame — the
// pose computed by choreography.ts — onto a small transparent canvas. Holds no
// clock and schedules nothing: callers (the deterministic harness, or the app's
// OrbAnimator) decide when and with what time to render.
import { ORB_VERT, ORB_FRAG } from './shader'
import { DOT_COUNT, type OrbFrame } from './choreography'

/** Rounded-rect target for the disc→rect morph, in disc-radius units. */
export type OrbRect = { halfW: number; halfH: number; corner: number }

export const DEFAULT_MORPH_RECT: OrbRect = { halfW: 0.94, halfH: 0.62, corner: 0.28 }

export class OrbRenderer {
  private gl: WebGL2RenderingContext
  private program: WebGLProgram
  private vao: WebGLVertexArrayObject
  private u: Record<string, WebGLUniformLocation | null> = {}
  private dotData = new Float32Array(DOT_COUNT * 4)
  private disposed = false

  constructor(
    private canvas: HTMLCanvasElement | OffscreenCanvas,
    opts: { powerPreference?: WebGLPowerPreference } = {}
  ) {
    const gl = canvas.getContext('webgl2', {
      alpha: true,
      premultipliedAlpha: true,
      antialias: false, // the shader does its own smoothstep AA
      depth: false,
      stencil: false,
      powerPreference: opts.powerPreference ?? 'low-power',
      preserveDrawingBuffer: true // harness readPixels after render
    }) as WebGL2RenderingContext | null
    if (!gl) throw new Error('WebGL2 unavailable')
    this.gl = gl

    const compile = (type: number, src: string): WebGLShader => {
      const sh = gl.createShader(type)
      if (!sh) throw new Error('createShader failed')
      gl.shaderSource(sh, src)
      gl.compileShader(sh)
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        throw new Error(`orb shader compile: ${gl.getShaderInfoLog(sh)}`)
      }
      return sh
    }
    const program = gl.createProgram()
    if (!program) throw new Error('createProgram failed')
    gl.attachShader(program, compile(gl.VERTEX_SHADER, ORB_VERT))
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, ORB_FRAG))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`orb shader link: ${gl.getProgramInfoLog(program)}`)
    }
    this.program = program

    // Full-screen triangle.
    const vao = gl.createVertexArray()
    if (!vao) throw new Error('createVertexArray failed')
    gl.bindVertexArray(vao)
    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(0)
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)
    this.vao = vao

    gl.useProgram(program)
    for (const name of [
      'u_resolution',
      'u_dots',
      'u_disc',
      'u_merge',
      'u_morph',
      'u_rectHalf',
      'u_rectCorner',
      'u_genesis',
      'u_noiseTime',
      'u_noiseAmp',
      'u_noiseFreq',
      'u_sminK'
    ]) {
      this.u[name] = gl.getUniformLocation(program, name)
    }
  }

  /** Rasterize one frame. `rect` shapes the morph target (expanded surface). */
  render(frame: OrbFrame, rect: OrbRect = DEFAULT_MORPH_RECT): void {
    if (this.disposed) return
    const gl = this.gl
    const w = this.canvas.width
    const h = this.canvas.height
    gl.viewport(0, 0, w, h)
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.useProgram(this.program)
    gl.bindVertexArray(this.vao)

    for (let i = 0; i < DOT_COUNT; i++) {
      const d = frame.dots[i]
      this.dotData[i * 4] = d.x
      this.dotData[i * 4 + 1] = d.y
      this.dotData[i * 4 + 2] = d.r
      this.dotData[i * 4 + 3] = d.halfLen
    }
    gl.uniform2f(this.u.u_resolution, w, h)
    gl.uniform4fv(this.u.u_dots, this.dotData)
    gl.uniform1f(this.u.u_disc, frame.params.discRadius)
    gl.uniform1f(this.u.u_merge, frame.merge)
    gl.uniform1f(this.u.u_morph, frame.morph)
    gl.uniform2f(this.u.u_rectHalf, rect.halfW, rect.halfH)
    gl.uniform1f(this.u.u_rectCorner, rect.corner)
    gl.uniform1f(this.u.u_genesis, frame.genesis)
    gl.uniform1f(this.u.u_noiseTime, frame.noiseTime)
    gl.uniform1f(this.u.u_noiseAmp, frame.params.noiseAmp)
    gl.uniform1f(this.u.u_noiseFreq, frame.params.noiseFreq)
    gl.uniform1f(this.u.u_sminK, frame.params.sminK)

    gl.drawArrays(gl.TRIANGLES, 0, 3)
  }

  /** RGBA readback of the current framebuffer (harness invariants). */
  readPixels(): Uint8Array {
    const gl = this.gl
    const w = this.canvas.width
    const h = this.canvas.height
    const out = new Uint8Array(w * h * 4)
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, out)
    return out
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    const ext = this.gl.getExtension('WEBGL_lose_context')
    ext?.loseContext()
  }
}

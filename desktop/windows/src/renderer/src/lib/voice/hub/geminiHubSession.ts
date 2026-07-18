// Gemini Live hub lane over WebSocket (Track 2 / A5 PR-4).
//
// A 1:1 port of the Gemini paths in macOS `RealtimeHubSession.swift`. Gemini uses
// MANUAL activity detection (`automaticActivityDetection.disabled: true`): each PTT
// turn is bracketed `activityStart` … `activityEnd`, and this MUST be sent every
// turn on a warm socket (sending it once at connect makes turns 2+ arrive with no
// speech window). Gemini has no reliable in-session cancel of a streaming reply,
// so barge-in is a fresh session at the controller boundary (not this lane);
// `geminiResponsePending` gates BOTH audio playback and turn completion to the
// current turn so an interrupted/abandoned turn's trailing audio can't leak.
//
// Windows deviation (D3): WebSocket + capture-window PCM + the existing
// `pcmPlayer`, and no mic is held open across the warm session (mic PCM arrives
// via `appendAudio`). This matches the shipped `geminiSession.ts` audio wiring;
// this lane just drives the manual-VAD frames over a raw WS instead of the SDK so
// the exact wire frames are assertable.

import {
  BaseHubSession,
  type HubBargeInStrategy,
  type HubProvider,
  type HubSessionOptions
} from './hubSession'
import { GEMINI_LIVE_MODEL } from '../tokenMint'
import type { VoiceToolDeclaration } from '../../../../../shared/types'

// JSON-Schema keywords that Gemini Live's function-declaration `parameters` (an
// OpenAPI-3.0 `Schema`, NOT full JSON Schema) does not accept. Sending any of them —
// most notably `additionalProperties`, which the host tool catalog stamps on every
// tool — makes Gemini REJECT the whole BidiGenerateContent setup and close the socket
// within seconds of connect (no `setupComplete`), so every warm silently cascades and
// the reconnect budget bleeds out. Full JSON Schema is only allowed in Gemini's
// separate `parameters_json_schema` field, which the raw Bidi setup frame does not use.
// OpenAI's realtime lane REQUIRES `additionalProperties:false` for strict tools, so this
// stripping is Gemini-only (see openaiHubSession, which passes the schema through).
const GEMINI_UNSUPPORTED_SCHEMA_KEYS = new Set([
  'additionalProperties',
  'unevaluatedProperties',
  '$schema',
  '$id',
  '$ref',
  '$defs',
  '$comment',
  'definitions',
  'oneOf',
  'allOf',
  'not',
  'const',
  'patternProperties',
  'propertyNames',
  'dependentSchemas',
  'dependencies',
  'if',
  'then',
  'else'
])

/** Recursively strip JSON-Schema-only keywords Gemini's `Schema` rejects, returning a
 *  clean OpenAPI-3.0-subset schema. Pure; leaves supported keys (type, properties,
 *  required, items, enum, anyOf, format, description, …) untouched. Exported for the
 *  regression test. */
export function sanitizeGeminiToolSchema(schema: unknown): unknown {
  if (Array.isArray(schema)) return schema.map(sanitizeGeminiToolSchema)
  if (schema && typeof schema === 'object') {
    const out: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(schema as Record<string, unknown>)) {
      if (GEMINI_UNSUPPORTED_SCHEMA_KEYS.has(key)) continue
      out[key] = sanitizeGeminiToolSchema(value)
    }
    return out
  }
  return schema
}

export class GeminiHubSession extends BaseHubSession {
  readonly provider: HubProvider = 'gemini'
  readonly requiredInputSampleRate = 16000
  readonly bargeInStrategy: HubBargeInStrategy = 'freshSession'

  // Manual-VAD: a turn's speech window is open between activityStart and activityEnd.
  private activityOpen = false
  private pendingActivityStart = false
  // A committed turn is awaiting its spoken reply. Gates audio + turnComplete to
  // the CURRENT turn (set on activityEnd/commit; cleared on this turn's
  // turnComplete, a server `interrupted`, or a barge-in beginTurn).
  private responsePending = false
  private pendingToolCallIds = new Set<string>()
  private syntheticToolCallCounter = 0

  constructor(opts: HubSessionOptions) {
    super(opts)
  }

  protected connectSpec(): { url: string; protocols?: string[] } {
    // Managed (ephemeral) path: the Constrained endpoint on v1alpha with
    // ?access_token= (Swift `makeRequest` .ephemeral). BYOK (?key=, v1beta) is a
    // host concern not needed for the Windows managed flow — deferred.
    const base =
      'wss://generativelanguage.googleapis.com/ws/' +
      'google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained'
    return { url: `${base}?access_token=${encodeURIComponent(this.token)}` }
  }

  protected sessionSetupFrame(): object {
    // Swift `sendSessionSetup` (gemini): AUDIO modality, manual activity detection,
    // Charon voice, sliding-window context compression, tool declarations.
    return {
      setup: {
        model: GEMINI_LIVE_MODEL,
        generationConfig: {
          responseModalities: ['AUDIO'],
          temperature: 0.3,
          mediaResolution: 'MEDIA_RESOLUTION_HIGH',
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: 'Charon' } } }
        },
        systemInstruction: { parts: [{ text: this.instructions }] },
        // Gemini's `parameters` is an OpenAPI-3.0 Schema — sanitize each tool's schema
        // to that subset or Gemini rejects the setup and fast-closes the socket.
        tools: [
          {
            functionDeclarations: this.tools.map((t: VoiceToolDeclaration) => ({
              name: t.name,
              description: t.description,
              parameters: sanitizeGeminiToolSchema(t.parameters)
            }))
          }
        ],
        inputAudioTranscription: {},
        outputAudioTranscription: {},
        realtimeInputConfig: {
          automaticActivityDetection: { disabled: true },
          turnCoverage: 'TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO'
        },
        contextWindowCompression: { slidingWindow: {} }
      }
    }
  }

  protected canAcceptInput(): boolean {
    return this.isOpen && this.activityOpen
  }

  protected appendAudioFrame(b64: string): void {
    this.send({ realtimeInput: { audio: { data: b64, mimeType: 'audio/pcm;rate=16000' } } })
  }

  protected onBeginTurn(interrupting: boolean): void {
    if (interrupting) {
      // Local gate for abandoned/stale events before the fresh-session replacement.
      this.responsePending = false
      this.pendingToolCallIds.clear()
    }
    if (this.activityOpen) return
    this.activityOpen = true
    if (this.isOpen) {
      this.send({ realtimeInput: { activityStart: {} } })
      this.flushPendingAudio()
      if (this.pendingCommit) {
        this.pendingCommit = false
        this.commitTurnNow()
      }
    } else {
      this.pendingActivityStart = true
    }
  }

  protected commitTurnNow(): void {
    this.send({ realtimeInput: { activityEnd: {} } })
    this.activityOpen = false
    this.responsePending = true
    // Gemini auto-responds at activityEnd; no explicit response request.
  }

  protected onCancelTurn(): void {
    // Abandon (silent tap / cancel), keeping the warm socket (Swift abandonInputTurn).
    this.responsePending = false
    this.pendingToolCallIds.clear()
    this.pendingActivityStart = false
    if (this.activityOpen && this.isOpen) {
      this.send({ realtimeInput: { activityEnd: {} } })
    }
    this.activityOpen = false
  }

  protected onSendToolResult(callId: string, name: string, output: string): void {
    this.pendingToolCallIds.delete(callId)
    this.send({
      toolResponse: {
        functionResponses: [{ id: callId, name, response: { result: output } }]
      }
    })
  }

  protected onProviderReady(): void {
    // Open the speech window if a turn started before we connected.
    if (this.pendingActivityStart) {
      this.pendingActivityStart = false
      this.send({ realtimeInput: { activityStart: {} } })
    }
  }

  protected resetProviderState(): void {
    this.activityOpen = false
    this.pendingActivityStart = false
    this.responsePending = false
    this.pendingToolCallIds.clear()
  }

  // MARK: Receive

  protected handleProviderMessage(e: Record<string, unknown>): void {
    if (e.setupComplete !== undefined) {
      this.markReady()
      return
    }
    // usageMetadata (client-reported billing) is a host concern — deferred to PR-5/6.
    const toolCall = e.toolCall as Record<string, unknown> | undefined
    if (toolCall) {
      const calls = (toolCall.functionCalls as Record<string, unknown>[] | undefined) ?? []
      // An abandoned/discarded turn still reaches Gemini (we send activityEnd to
      // close the window); without this guard it acts on half-heard audio.
      if (!this.responsePending) return
      for (const call of calls) {
        const name = typeof call.name === 'string' ? call.name : ''
        const callId = typeof call.id === 'string' ? call.id : this.nextSyntheticToolCallId(name)
        this.pendingToolCallIds.add(callId)
        const args = (call.args as Record<string, unknown> | undefined) ?? {}
        const argsJSON = JSON.stringify(args)
        if (name.length > 0) this.emitToolRequest({ name, callId, argumentsJSON: argsJSON })
      }
      return
    }
    const sc = e.serverContent as Record<string, unknown> | undefined
    if (!sc) return
    if (sc.interrupted === true) {
      // Barge-in: drop the pending reply so its trailing audio + bookkeeping
      // turnComplete are ignored, and flush queued playback immediately.
      this.responsePending = false
      this.pendingToolCallIds.clear()
      this.clearPlayback()
    }
    const it = sc.inputTranscription as Record<string, unknown> | undefined
    if (typeof it?.text === 'string') this.emitInputTranscript(it.text, false)
    const ot = sc.outputTranscription as Record<string, unknown> | undefined
    if (typeof ot?.text === 'string') this.emitAssistantText(ot.text, false)
    const modelTurn = sc.modelTurn as Record<string, unknown> | undefined
    const parts = (modelTurn?.parts as Record<string, unknown>[] | undefined) ?? []
    for (const p of parts) {
      if (typeof p.text === 'string') this.emitAssistantText(p.text, false)
      const inline = p.inlineData as Record<string, unknown> | undefined
      const mime = typeof inline?.mimeType === 'string' ? inline.mimeType : ''
      const data = typeof inline?.data === 'string' ? inline.data : ''
      if (mime.includes('audio/pcm') && data.length > 0 && this.responsePending) {
        this.playAudio(data) // gated: only the live turn's reply
      }
    }
    if (sc.turnComplete === true) {
      if (this.pendingToolCallIds.size > 0) return // defer until tool results are in
      // Only finish the turn we're actually awaiting a reply for. A turnComplete
      // that closes an interrupted/abandoned generation (pending=false) is ignored.
      if (this.responsePending) {
        this.responsePending = false
        this.flushPlayback()
        this.emitAssistantText('', true)
        this.emitTurnDone()
      }
    }
  }

  private nextSyntheticToolCallId(name: string): string {
    this.syntheticToolCallCounter += 1
    return `${name}:${this.syntheticToolCallCounter}`
  }
}

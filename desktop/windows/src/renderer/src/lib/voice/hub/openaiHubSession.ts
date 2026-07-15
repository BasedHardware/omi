// OpenAI Realtime hub lane over WebSocket (Track 2 / A5 PR-4).
//
// A 1:1 port of the OpenAI paths in macOS `RealtimeHubSession.swift`. PTT controls
// turns (`turn_detection: null` — NO server VAD): per turn we append mic PCM while
// held, `input_audio_buffer.commit` on release, then `response.create`. Barge-in
// cancels the in-flight reply in-session (`response.cancel` + `input_audio_buffer.clear`).
//
// Windows deviation (D3): this is WebSocket + capture-window PCM + the existing
// `pcmPlayer`, NOT the shipped `OpenAIRealtimeWebRTC` lane (which holds the mic
// open for its whole lifetime — a privacy regression on a warm hub). Auth over a
// browser/Electron WS uses subprotocols, since a WS cannot set an Authorization
// header from the renderer (§C.5): `["realtime", "openai-insecure-api-key.<secret>"]`.
//
// FRAME NOTE — §C.5 / the port plan summary say the OpenAI barge-in is
// `response.cancel` + `conversation.item.truncate`. The ACTUAL macOS session
// (`RealtimeHubSession.cancelActiveResponse`) sends `response.cancel` +
// `input_audio_buffer.clear`, and `conversation.item.truncate` appears NOWHERE in
// the macOS source. Per the brief's rule "the Swift wins", this lane ports the
// real Swift frames and does NOT emit a truncate (which would also require
// fabricating item_id/content_index/audio_end_ms the reducer never supplies).

import {
  BaseHubSession,
  type HubBargeInStrategy,
  type HubEventIdentity,
  type HubProvider,
  type HubSessionOptions
} from './hubSession'
import { OPENAI_REALTIME_MODEL } from '../tokenMint'

export class OpenAiHubSession extends BaseHubSession {
  readonly provider: HubProvider = 'openai'
  readonly requiredInputSampleRate = 24000
  readonly bargeInStrategy: HubBargeInStrategy = 'inSessionCancel'

  // A response is mid-flight — don't create a second (the API rejects
  // "Conversation already has an active response in progress").
  private responseActive = false
  private responseCreatePending = false
  private activeResponseID: string | null = null
  // If barge-in cancels while a response.create is still pending, the resulting
  // response.created must be consumed and ignored (Swift's canceled-pending flag).
  private pendingResponseCanceled = false
  // call_id → function name, captured from response.output_item.added.
  private functionNames = new Map<string, string>()
  // Assistant items already dispatched as tool calls (dedup on response.done).
  private dispatchedToolItems = new Set<string>()
  private pendingToolCallIds = new Set<string>()

  constructor(opts: HubSessionOptions) {
    super(opts)
  }

  protected connectSpec(): { url: string; protocols?: string[] } {
    return {
      url: `wss://api.openai.com/v1/realtime?model=${OPENAI_REALTIME_MODEL}`,
      protocols: ['realtime', `openai-insecure-api-key.${this.token}`]
    }
  }

  protected sessionSetupFrame(): object {
    // Idempotent full session.update (Swift openAISessionPayload). PCM 24k both
    // ways, `turn_detection: null` so PTT owns turns, whisper-1 input transcription.
    return {
      type: 'session.update',
      session: {
        type: 'realtime',
        instructions: this.instructions,
        output_modalities: ['audio'],
        audio: {
          input: {
            format: { type: 'audio/pcm', rate: 24000 },
            turn_detection: null,
            transcription: { model: 'whisper-1' }
          },
          output: { format: { type: 'audio/pcm', rate: 24000 }, voice: 'marin' }
        },
        tools: this.tools,
        tool_choice: 'auto'
      }
    }
  }

  protected canAcceptInput(): boolean {
    return this.isOpen
  }

  protected appendAudioFrame(b64: string): void {
    this.send({ type: 'input_audio_buffer.append', audio: b64 })
  }

  protected onBeginTurn(interrupting: boolean): void {
    // OpenAI is input_audio_buffer based, so a plain begin is a no-op. A barge-in
    // begin cancels the in-flight reply so the new turn starts clean.
    if (interrupting) this.cancelActiveResponse()
  }

  protected commitTurnNow(): void {
    this.send({ type: 'input_audio_buffer.commit' })
    this.requestResponse()
  }

  private requestResponse(): void {
    if (this.responseActive) return // never a second concurrent response
    this.responseActive = true
    this.responseCreatePending = true
    this.activeResponseID = null
    this.pendingResponseCanceled = false
    this.send({ type: 'response.create', response: { output_modalities: ['audio'] } })
  }

  /** Barge-in cancel of an in-flight reply (Swift `cancelActiveResponse`). */
  private cancelActiveResponse(): void {
    if (this.responseActive) {
      if (this.responseCreatePending) this.pendingResponseCanceled = true
      this.send({ type: 'response.cancel' })
      this.responseActive = false
      this.responseCreatePending = false
      this.activeResponseID = null
      this.pendingToolCallIds.clear()
    }
    // Drop any uncommitted mic input so it can't leak into the next turn.
    this.send({ type: 'input_audio_buffer.clear' })
    this.clearPlayback()
  }

  protected onCancelTurn(): void {
    // Abandon (silent tap / cancel), keeping the warm socket (Swift abandonInputTurn).
    this.functionNames.clear()
    this.dispatchedToolItems.clear()
    if (this.responseActive) this.send({ type: 'response.cancel' })
    this.responseActive = false
    this.responseCreatePending = false
    this.activeResponseID = null
    this.pendingResponseCanceled = false
    this.pendingToolCallIds.clear()
    this.send({ type: 'input_audio_buffer.clear' })
    this.clearPlayback()
  }

  protected onSendToolResult(callId: string, _name: string, output: string): void {
    this.pendingToolCallIds.delete(callId)
    this.send({
      type: 'conversation.item.create',
      item: { type: 'function_call_output', call_id: callId, output }
    })
    if (this.pendingToolCallIds.size === 0) this.requestResponse()
  }

  protected onProviderReady(): void {
    /* OpenAI has no per-turn activity window to open at ready. */
  }

  protected resetProviderState(): void {
    this.responseActive = false
    this.responseCreatePending = false
    this.activeResponseID = null
    this.pendingResponseCanceled = false
    this.functionNames.clear()
    this.dispatchedToolItems.clear()
    this.pendingToolCallIds.clear()
  }

  // MARK: Receive

  protected handleProviderMessage(e: Record<string, unknown>): void {
    const type = e.type
    if (typeof type !== 'string') return
    switch (type) {
      case 'session.created':
      case 'session.updated':
        this.markReady()
        return
      case 'response.created': {
        const response = e.response as Record<string, unknown> | undefined
        const id = typeof response?.id === 'string' ? response.id : undefined
        if (!id) return
        if (this.pendingResponseCanceled) {
          this.pendingResponseCanceled = false
          return // consumed a canceled response.created
        }
        if (!this.responseActive) return
        this.activeResponseID = id
        this.responseCreatePending = false
        return
      }
      case 'response.output_audio.delta': {
        if (!this.isCurrentResponseEvent(e)) return
        const b64 = e.delta
        if (typeof b64 === 'string') this.playAudio(b64)
        return
      }
      case 'response.output_audio_transcript.delta': {
        if (!this.isCurrentResponseEvent(e)) return
        const t = e.delta
        if (typeof t === 'string') this.emitAssistantText(t, false)
        return
      }
      case 'conversation.item.input_audio_transcription.delta': {
        const t = e.delta
        if (typeof t === 'string') this.emitInputTranscript(t, false)
        return
      }
      case 'conversation.item.input_audio_transcription.completed': {
        const t = e.transcript
        if (typeof t === 'string') this.emitInputTranscript(t, true)
        return
      }
      case 'response.output_item.added': {
        if (!this.isCurrentResponseEvent(e)) return
        const item = e.item as Record<string, unknown> | undefined
        if (item?.type === 'function_call') {
          const callId = item.call_id
          const name = item.name
          if (typeof callId === 'string' && typeof name === 'string') {
            this.functionNames.set(callId, name)
          }
        }
        return
      }
      case 'response.done':
        this.handleResponseDone(e)
        return
      case 'error': {
        this.responseActive = false
        this.responseCreatePending = false
        this.activeResponseID = null
        const err = e.error as Record<string, unknown> | undefined
        const msg = typeof err?.message === 'string' ? err.message : 'OpenAI realtime error'
        this.handleError(msg, true)
        return
      }
      default:
        return
    }
  }

  private eventResponseID(e: Record<string, unknown>): string | undefined {
    if (typeof e.response_id === 'string') return e.response_id
    const response = e.response as Record<string, unknown> | undefined
    return typeof response?.id === 'string' ? response.id : undefined
  }

  private isCurrentResponseEvent(e: Record<string, unknown>): boolean {
    if (!this.responseActive || this.responseCreatePending || !this.activeResponseID) return false
    return this.eventResponseID(e) === this.activeResponseID
  }

  private handleResponseDone(e: Record<string, unknown>): void {
    if (!this.isCurrentResponseEvent(e)) return // ignore a stale response.done
    const identity: HubEventIdentity | null = this.activeIdentity
    this.responseActive = false
    this.responseCreatePending = false
    this.activeResponseID = null
    const response = e.response as Record<string, unknown> | undefined
    const output = (response?.output as Record<string, unknown>[] | undefined) ?? []
    let firedTool = false
    for (const item of output) {
      if (item?.type !== 'function_call') continue
      const callId = item.call_id
      if (typeof callId !== 'string' || this.dispatchedToolItems.has(callId)) continue
      this.dispatchedToolItems.add(callId)
      this.pendingToolCallIds.add(callId)
      const name =
        (typeof item.name === 'string' ? item.name : this.functionNames.get(callId)) ?? ''
      const argsStr = typeof item.arguments === 'string' ? item.arguments : '{}'
      if (name.length > 0) {
        firedTool = true
        this.emitToolRequest({ name, callId, argumentsJSON: argsStr }, identity)
      }
    }
    // A tool-only response isn't the end of the turn — the model speaks after the
    // tool result. Otherwise the turn is done.
    if (!firedTool) {
      this.emitAssistantText('', true, identity)
      this.emitTurnDone(identity)
    }
  }
}

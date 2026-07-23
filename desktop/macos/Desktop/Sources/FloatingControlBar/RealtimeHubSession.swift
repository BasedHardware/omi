import Foundation
import VoiceTurnDomain

// MARK: - Realtime Hub Session
//
// One persistent WebSocket to a realtime provider, opened either with the user's
// own BYOK key (client-direct, gated by RealtimeHubSettings.canConnect) or with a
// server-minted ephemeral token (managed users). The model is the hub: it does
// in-session STT + reasoning + routing (via tool calls) and speaks the answer.
//
// Two providers, normalized to ONE internal stream surface
// (RealtimeHubSessionDelegate):
//
//   • OpenAI  — wss://api.openai.com/v1/realtime?model=gpt-realtime-2
//               Bearer = BYOK OpenAI key, NO `OpenAI-Beta` header (GA).
//               Native spoken audio out (24 kHz PCM) + function calling.
//               Transport: URLSession WebSocket (HTTP/1.1-friendly endpoint).
//
//   • Gemini  — wss://generativelanguage.googleapis.com/ws/…BidiGenerateContent?key=…
//               Live model, response modality AUDIO + function calling.
//               Native spoken audio out (PCM) + output transcription.
//               Transport: Network.framework WebSocket with ALPN pinned to
//               http/1.1 — Gemini's endpoint upgrades URLSession's WS to HTTP/2
//               and resets it (the documented reason the legacy path needed a
//               relay); pinning ALPN avoids the upgrade.
//
// Normalized events: transcript_in (input STT) / audio_out (OpenAI) |
// text_out (Gemini) / tool_call / turn.done.

private struct PendingOpenAIResponseIdentity {
  let identity: RealtimeHubEventIdentity
  var canceled: Bool
}

/// How the client authenticates to the realtime provider:
///   • byokKey   — the user's own provider key (Phase 1, client-direct, no backend)
///   • ephemeral — a short-lived token minted by the omi backend (Phase 2, managed)
/// OpenAI takes either as the `Authorization: Bearer` value. Gemini differs: a BYOK
/// key uses `?key=` on the normal BidiGenerateContent endpoint; an ephemeral token
/// uses `?access_token=` on the BidiGenerateContentConstrained endpoint (v1alpha).
enum HubAuth {
  case byokKey(String)
  case ephemeral(String)
  var value: String {
    switch self {
    case .byokKey(let k): return k
    case .ephemeral(let t): return t
    }
  }
  var isEphemeral: Bool { if case .ephemeral = self { return true } else { return false } }
}

enum RealtimeHubBargeInStrategy: Equatable {
  case inSessionCancel
  case freshSession
}

#if DEBUG
  struct RealtimeHubInputLifecycleSnapshot: Equatable {
    let isOpen: Bool
    let activityOpen: Bool
    let pendingAudioChunkCount: Int
    let pendingVideoFrameCount: Int
    let pendingCommit: Bool
    let responseIdentityCount: Int
    let inputIdentityCount: Int
    let testingResponseCreateCount: Int
    let testingLastResponseToolChoice: String?
    let testingLastResponseInstruction: String?
  }
#endif

final class RealtimeHubSession: NSObject, @unchecked Sendable {
  private let provider: RealtimeHubProvider
  private let auth: HubAuth
  private let instructions: String
  private let availableDirectedProviders: [String]
  /// Opaque cache-plan fields only; never raw conversation material.
  private let contextPlanID: String
  private let stableCacheIdentity: String
  private let dynamicContextIdentity: String
  private let contextCacheReplaced: Bool
  private weak var delegate: RealtimeHubSessionDelegate?

  /// Mic PCM input rate per provider (Gemini 16k native, OpenAI GA needs 24k).
  var requiredInputSampleRate: Int { provider == .openai ? 24000 : 16000 }
  /// Provider-specific interruption contract for a new PTT turn while a reply is still streaming.
  var bargeInStrategy: RealtimeHubBargeInStrategy {
    provider == .gemini ? .freshSession : .inSessionCancel
  }

  // All socket + state access is serialized here (audio arrives on the capture
  // thread; receives on the URLSession/NW queue). Delegate calls hop to main.
  let q = DispatchQueue(label: "omi.realtime-hub.session")

  var task: URLSessionWebSocketTask?
  var completedURLTaskIDs = Set<Int>()
  var urlTaskTerminalWaiters: [Int: [CheckedContinuation<Void, Never>]] = [:]
  private lazy var session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
  // Gemini's Live endpoint rejects both of Apple's WebSocket stacks, so it uses a
  // hand-rolled RFC 6455 client (RawWebSocket). OpenAI uses URLSession.
  var rawWS: RealtimeRawWebSocketTransport?
  private let rawWebSocketFactory: (URL, DispatchQueue) -> RealtimeRawWebSocketTransport
  private var usesRawWS: Bool { provider == .gemini }

  private var isOpen = false
  private var terminated = false
  #if DEBUG
    // The hermetic local-profile harness intentionally has no network socket. Its
    // explicit readiness seam is a successful local transport boundary, not a
    // disconnected production session.
    private var acceptsTestingTransport = false
    private var testingResponseCreateCount = 0
    private var testingLastResponseToolChoice: String?
    private var testingLastResponseInstruction: String?
  #endif
  private var activeEventIdentity: RealtimeHubEventIdentity?
  private var completedGeminiEventIdentity: RealtimeHubEventIdentity?
  private var pendingAudio: [Data] = []
  /// Screen frames awaiting an open socket (base64, mime) — flushed into the turn in
  /// markReady. A cold first turn would otherwise drop the frame before connect.
  private var pendingVideo: [(b64: String, mime: String)] = []
  /// Headless-test text awaiting a provider-acceptable input window.
  private var pendingTextInputs: [(text: String, logLabel: String)] = []
  private var pendingCommit = false
  /// OpenAI: call_id → function name, captured from response.output_item.added.
  private var openAIFunctionNames: [String: String] = [:]
  /// OpenAI: assistant items already dispatched as tool calls (dedup on response.done).
  private var dispatchedToolItems = Set<String>()
  /// Gemini manual-VAD: each PTT turn must be bracketed activityStart…activityEnd.
  /// On a WARM session that brackets per turn — sending it once at connect made
  /// turns 2+ arrive with no speech window (Gemini then greets generically).
  private var activityOpen = false
  private var pendingActivityStart = false
  /// OpenAI: a response is mid-flight — don't create a second one (the realtime
  /// API rejects "Conversation already has an active response in progress").
  private var openAIResponseActive = false
  private var openAIResponseCreatePending = false
  private var openAIActiveResponseID: String?
  private var openAIPendingResponseIdentities: [PendingOpenAIResponseIdentity] = []
  private var openAIResponseIdentities: [String: RealtimeHubEventIdentity] = [:]
  private var openAIPendingInputIdentities: [RealtimeHubEventIdentity] = []
  private var openAIInputItemIdentities: [String: RealtimeHubEventIdentity] = [:]
  /// Gemini: a committed turn is awaiting its spoken reply. Gates BOTH audio
  /// playback and turn completion to the CURRENT turn, so an interrupted/abandoned
  /// turn's trailing audio + bookkeeping `turnComplete` can't leak into the next
  /// one. Set on activityEnd (commit); cleared on this turn's `turnComplete`, on a
  /// server `interrupted`, or when a new turn interrupts (beginInputTurn interrupting).
  private var geminiResponsePending = false
  private var pendingOpenAIToolCallIds = Set<String>()
  private var pendingGeminiToolCallIds = Set<String>()
  /// A provider may close the function-call cycle without producing a user-facing
  /// response. One explicit internal continuation is permitted for that exact voice
  /// turn; further retries would create an unbounded tool/turn loop.
  private var postToolContinuationAttempted = false
  private var geminiSyntheticToolCallCounter = 0

  // Per-turn token usage for managed (ephemeral) billing — client-reported. Reset at
  // commit, reported at finishTurn (only for ephemeral sessions; BYOK pays the provider
  // directly). OpenAI sends a final usage per response.done (summed across a turn's
  // responses); Gemini sends cumulative usageMetadata (we keep the latest).
  private var usageInText = 0
  private var usageInAudio = 0
  private var usageInImage = 0
  private var usageInCached = 0
  private var usageOutText = 0
  private var usageOutAudio = 0
  /// Evidence is local-only. This opaque descriptor lets the local log correlate the
  /// attachment with Gemini's later per-modality usage without logging pixels or app text.
  private var activeScreenEvidence: RealtimeScreenEvidenceDescriptor?

  /// Log prefix that names the provider + model on every line, so it's always
  /// clear which model produced which event.
  private var tag: String { "RealtimeHub[\(provider == .openai ? "openai" : "gemini"):\(provider.modelID)]" }

  init(
    provider: RealtimeHubProvider,
    auth: HubAuth,
    instructions: String,
    availableDirectedProviders: [String] = [],
    contextPlanID: String = "",
    stableCacheIdentity: String = "",
    dynamicContextIdentity: String = "",
    contextCacheReplaced: Bool = false,
    rawWebSocketFactory: @escaping (URL, DispatchQueue) -> RealtimeRawWebSocketTransport = {
      RawWebSocket(url: $0, queue: $1)
    },
    delegate: RealtimeHubSessionDelegate
  ) {
    self.provider = provider
    self.auth = auth
    self.instructions = instructions
    self.availableDirectedProviders = availableDirectedProviders
    self.contextPlanID = contextPlanID
    self.stableCacheIdentity = stableCacheIdentity
    self.dynamicContextIdentity = dynamicContextIdentity
    self.contextCacheReplaced = contextCacheReplaced
    self.rawWebSocketFactory = rawWebSocketFactory
    self.delegate = delegate
    super.init()
  }

  // MARK: Lifecycle

  func start() {
    q.async { [weak self] in self?._start() }
  }

  private func _start() {
    guard !terminated else { return }
    guard let request = makeRequest(), let url = request.url else {
      notifyError(
        RealtimeHubTransportFailure(
          kind: .configuration,
          message: "Could not build \(provider.displayName) request URL",
          systemDomain: nil,
          systemCode: nil))
      return
    }
    log("RealtimeHub: connecting \(provider.displayName) → \(url.host ?? "?") (client-direct)")
    if usesRawWS {
      let ws = rawWebSocketFactory(url, q)
      rawWS = ws
      ws.onOpen = { [weak self] in
        guard let self else { return }
        guard !self.terminated else { return }
        log("RealtimeHub: raw WS open (\(self.provider.displayName))")
        self.sendSessionSetup()
      }
      ws.onMessage = { [weak self] data in self?.handleMessage(data) }
      ws.onClose = { [weak self] code, reason in
        self?.notifyError(.providerClose(code: code, reason: reason))
      }
      ws.onError = { [weak self] failure in
        self?.notifyError(.rawWebSocket(failure))
      }
      ws.connect()
      return
    }
    let t = session.webSocketTask(with: request)
    task = t
    t.resume()
    // Receive + setup begin in didOpenWithProtocol.
  }

  /// Stop delivering events to the delegate. Used when the controller intentionally
  /// drops this socket (barge-in / cancel reconnect) so its teardown close/error
  /// can't reach the controller and tear down the replacement session.
  func detach() {
    q.async { [weak self] in self?.delegate = nil }
  }

  func stop() {
    q.async { [weak self] in
      self?.beginStopOnQueue()
    }
  }

  func beginStopOnQueue() {
    beginTransportTerminationOnQueue()
    isOpen = false
    pendingAudio.removeAll()
    pendingVideo.removeAll()
    pendingTextInputs.removeAll()
    pendingCommit = false
    openAIFunctionNames.removeAll()
    dispatchedToolItems.removeAll()
    activityOpen = false
    pendingActivityStart = false
    openAIResponseActive = false
    openAIResponseCreatePending = false
    openAIActiveResponseID = nil
    openAIPendingResponseIdentities.removeAll()
    openAIResponseIdentities.removeAll()
    openAIPendingInputIdentities.removeAll()
    openAIInputItemIdentities.removeAll()
    geminiResponsePending = false
    postToolContinuationAttempted = false
    activeEventIdentity = nil
    completedGeminiEventIdentity = nil
  }

  private func beginTransportTerminationOnQueue() {
    task?.cancel(with: .goingAway, reason: nil)
    rawWS?.close()
    isOpen = false
  }

  private func notifyError(_ failure: RealtimeHubTransportFailure) {
    guard !terminated else { return }
    terminated = true
    // The session owns the physical transport. Retire it before publishing the
    // terminal callback so controller recovery can never overlap a replacement
    // with a still-live socket.
    // Preserve buffered logical input until the controller has captured any
    // reconnect obligation. Only the physical transport terminates here.
    beginTransportTerminationOnQueue()
    let d = delegate
    Task { @MainActor in d?.hubDidError(failure, source: self) }
  }

  // MARK: Public stream API

  /// Barge-in: cancel any in-flight reply so a new turn starts clean. Prevents the
  /// OpenAI "Conversation already has an active response in progress" error and a
  /// dangling Gemini activity window (which the server aborts with close 1008).
  func cancelActiveResponse() {
    q.async { [weak self] in
      guard let self, self.isOpen else { return }
      switch self.provider {
      case .openai:
        if self.openAIResponseActive {
          if self.openAIResponseCreatePending,
            let pendingIndex = self.openAIPendingResponseIdentities.firstIndex(where: { !$0.canceled })
          {
            self.openAIPendingResponseIdentities[pendingIndex].canceled = true
          }
          self.send(json: ["type": "response.cancel"])
          if let activeResponseID = self.openAIActiveResponseID {
            self.openAIResponseIdentities.removeValue(forKey: activeResponseID)
          }
          self.openAIResponseActive = false
          self.openAIResponseCreatePending = false
          self.openAIActiveResponseID = nil
          self.pendingOpenAIToolCallIds.removeAll()
        }
        // Drop any uncommitted mic input so it can't leak into the next turn.
        self.send(json: ["type": "input_audio_buffer.clear"])
      case .gemini:
        // Gemini can't cleanly cancel a streaming reply (it keeps speaking), so the
        // controller interrupts Gemini by reconnecting a fresh socket instead.
        break
      }
    }
  }

  /// Feed mic PCM16 mono at `requiredInputSampleRate` (caller resamples).
  func sendAudio(_ pcm: Data) {
    q.async { [weak self] in
      guard let self else { return }
      guard self.isOpen, self.provider == .openai || self.activityOpen else {
        self.pendingAudio.append(pcm)
        return
      }
      self.appendAudioFrame(pcm)
    }
  }

  #if DEBUG
    func inputLifecycleSnapshot() async -> RealtimeHubInputLifecycleSnapshot {
      await withCheckedContinuation { continuation in
        q.async {
          continuation.resume(
            returning: RealtimeHubInputLifecycleSnapshot(
              isOpen: self.isOpen,
              activityOpen: self.activityOpen,
              pendingAudioChunkCount: self.pendingAudio.count,
              pendingVideoFrameCount: self.pendingVideo.count,
              pendingCommit: self.pendingCommit,
              responseIdentityCount: self.openAIResponseIdentities.count,
              inputIdentityCount: self.openAIInputItemIdentities.count,
              testingResponseCreateCount: self.testingResponseCreateCount,
              testingLastResponseToolChoice: self.testingLastResponseToolChoice,
              testingLastResponseInstruction: self.testingLastResponseInstruction))
        }
      }
    }

    func markReadyForTesting() {
      q.async { [weak self] in
        self?.acceptsTestingTransport = true
        self?.markReady()
      }
    }

    func seedOpenAIIdentityMapsForTesting(
      identity: RealtimeHubEventIdentity,
      responseID: String,
      inputItemID: String
    ) async {
      await withCheckedContinuation { continuation in
        q.async {
          self.openAIResponseActive = true
          self.openAIActiveResponseID = responseID
          self.openAIResponseIdentities[responseID] = identity
          self.openAIInputItemIdentities[inputItemID] = identity
          continuation.resume()
        }
      }
    }

    func receiveOpenAIEventForTesting(_ event: [String: Any]) async {
      await withCheckedContinuation { continuation in
        // `[String: Any]` is not Sendable (`Any` isn't); box it so the session
        // queue closure can carry it across the concurrency boundary.
        let eventBox = SessionCallbackBox(event)
        q.async {
          self.handleOpenAI(eventBox.value)
          continuation.resume()
        }
      }
    }
  #endif

  /// Send one image as a video frame INSIDE the current open activity window (Gemini).
  /// Manual-VAD requires media to ride a user turn bracketed by activityStart…activityEnd;
  /// a frame sent here becomes part of the user's speech turn, so the model has the screen
  /// when it answers. This is the ONLY image delivery this model accepts — a separate
  /// image-only turn (after the speech turn closed) is rejected with close 1007.
  func sendVideoFrame(_ image: Data, mime: String, allowClosedActivityWindow: Bool = false) {
    guard provider == .gemini else { return }
    let b64 = image.base64EncodedString()
    q.async { [weak self] in
      guard let self else { return }
      // Buffer until the socket is open AND a turn is active, then flush in markReady.
      // A cold first turn dumps audio + this frame before connect (~300ms); without
      // buffering the frame is dropped and the model answers blind.
      guard self.isOpen, self.activityOpen || allowClosedActivityWindow else {
        self.pendingVideo.append((b64, mime))
        log("\(self.tag): screen frame buffered until open (\(image.count) bytes)")
        return
      }
      let phase = self.activityOpen ? "in-turn" : "after-activity-end"
      log("\(self.tag): screen frame sent \(phase) (\(image.count) bytes)")
      self.send(json: ["realtimeInput": ["video": ["data": b64, "mimeType": mime]]])
    }
  }

  /// TEST SEAM (ptt_test_turn only, bridge is non-prod-only): inject the probe text as
  /// realtime user input so the model answers the forced transcript instead of the
  /// fixture audio — the harness feeds a sine tone, and without this the model replies
  /// to a beep in whatever language it hallucinates. Gemini: text rides the open
  /// activity window (same rule as video frames). OpenAI: a user message item is
  /// appended before the audio commit.
  /// TEST SEAM (ptt_test_turn only): queue-synced snapshot of whether this session can
  /// accept in-turn input right now. Gemini needs the speech-activity window open;
  /// OpenAI only needs the socket. The headless turn waits on this before injecting
  /// text/committing — beginTurn may defer activityStart during a seed-stale reconnect,
  /// and an activityEnd without a window is a Gemini policy-close (1008).
  func activityWindowOpen() async -> Bool {
    await withCheckedContinuation { continuation in
      q.async {
        continuation.resume(
          returning: self.isOpen && (self.provider == .openai || self.activityOpen))
      }
    }
  }

  func sendTestTextInput(_ text: String) async -> Bool {
    await sendTextInput(text, logLabel: "test text input")
  }

  /// A provider can complete a tool-only response after accepting the final tool
  /// result without emitting a user-facing reply. Continue the same physical turn
  /// once, never as a synthetic user request. The continuation is bounded here so
  /// every caller shares the same no-loop contract.
  func resumeAfterToolOnlyCycle(
    identity: RealtimeHubEventIdentity,
    completion: @escaping (RealtimePostToolContinuationStartResult) -> Void
  ) {
    // The caller's completion is non-Sendable; box it so the session queue can
    // carry it across without forcing the caller's closure to be @Sendable.
    let completionBox = SessionCallbackBox(completion)
    q.async { [weak self] in
      guard let self else {
        completionBox.value(.transportUnavailable)
        return
      }

      guard self.activeEventIdentity == identity else {
        completionBox.value(.stale)
        return
      }
      guard self.isOpen else {
        completionBox.value(.transportUnavailable)
        return
      }

      let providerHasResponseInFlight: Bool
      switch self.provider {
      case .openai:
        providerHasResponseInFlight = self.openAIResponseActive || !self.pendingOpenAIToolCallIds.isEmpty
      case .gemini:
        providerHasResponseInFlight =
          self.activityOpen || self.geminiResponsePending || !self.pendingGeminiToolCallIds.isEmpty
      }
      if self.postToolContinuationAttempted {
        completionBox.value(providerHasResponseInFlight ? .alreadyInFlight : .exhausted)
        return
      }
      guard !providerHasResponseInFlight else {
        completionBox.value(.alreadyInFlight)
        return
      }

      switch self.provider {
      case .openai:
        self.postToolContinuationAttempted = true
        self.requestResponse(
          audio: true,
          toolChoice: "none",
          instructions: Self.openAIPostToolContinuationInstruction,
          reason: "post_tool_continuation")
        log("\(self.tag): requested explicit OpenAI post-tool continuation")
      case .gemini:
        self.postToolContinuationAttempted = true
        self.completedGeminiEventIdentity = nil
        self.activityOpen = true
        for wire in Self.geminiPostToolContinuationWires() {
          self.send(json: wire)
        }
        self.activityOpen = false
        self.geminiResponsePending = true
        log("\(self.tag): requested explicit Gemini post-tool continuation")
      }
      completionBox.value(.started)
    }
  }

  static let geminiPostToolContinuationInstruction =
    "The tool work for the user's most recent request is complete. Do not call any more tools. "
    + "Now give the concise, natural spoken answer to that same request using the tool result already provided."

  static let openAIPostToolContinuationInstruction =
    "The tool work for the user's most recent request is complete. Give the concise, natural spoken "
    + "answer to that same request now, using the tool result already provided. Do not call any tools."

  static func geminiPostToolContinuationWires() -> [[String: Any]] {
    [
      ["realtimeInput": ["activityStart": [:]]],
      ["realtimeInput": ["text": geminiPostToolContinuationInstruction]],
      ["realtimeInput": ["activityEnd": [:]]],
    ]
  }

  private func sendTextInput(_ text: String, logLabel: String) async -> Bool {
    await withCheckedContinuation { continuation in
      q.async { [weak self] in
        guard let self else {
          continuation.resume(returning: false)
          return
        }
        guard self.isOpen else {
          self.bufferTextInput(text, logLabel: logLabel, reason: "socket not open")
          continuation.resume(returning: true)
          return
        }
        if self.provider == .gemini, !self.activityOpen {
          self.bufferTextInput(text, logLabel: logLabel, reason: "no open activity window")
          continuation.resume(returning: true)
          return
        }
        self.sendTextInputNow(text, logLabel: logLabel)
        continuation.resume(returning: true)
      }
    }
  }

  private func bufferTextInput(_ text: String, logLabel: String, reason: String) {
    pendingTextInputs.append((text: text, logLabel: logLabel))
    log("\(tag): \(logLabel) buffered — \(reason) (\(text.count) chars)")
  }

  private func flushPendingTextInputs() {
    guard isOpen else { return }
    guard provider == .openai || activityOpen else { return }
    let inputs = pendingTextInputs
    pendingTextInputs.removeAll()
    for input in inputs {
      sendTextInputNow(input.text, logLabel: input.logLabel)
    }
  }

  private func sendTextInputNow(_ text: String, logLabel: String) {
    switch provider {
    case .gemini:
      send(json: ["realtimeInput": ["text": text]])
    case .openai:
      send(json: [
        "type": "conversation.item.create",
        "item": [
          "type": "message",
          "role": "user",
          "content": [["type": "input_text", "text": text]],
        ],
      ])
    }
    log("\(tag): \(logLabel) sent (\(text.count) chars)")
  }

  /// End the user's PTT turn and ask the model to respond.
  /// Start a new PTT turn. Gemini: open a fresh speech-activity window (must be
  /// done EVERY turn on a warm session). OpenAI: no-op (input_audio_buffer based).
  func beginInputTurn(
    turnID: VoiceTurnID? = nil,
    responseID: VoiceResponseID? = nil,
    interrupting: Bool = false
  ) {
    q.async { [weak self] in
      guard let self else { return }
      if let turnID, let responseID {
        self.activeEventIdentity = RealtimeHubEventIdentity(
          turnID: turnID,
          responseID: responseID)
      } else {
        self.activeEventIdentity = nil
      }
      self.postToolContinuationAttempted = false
      guard self.provider == .gemini else { return }
      // Barge-in on a live Gemini generation uses a fresh session at the controller
      // boundary. This same-session flag is only a local gate for abandoned/stale
      // Gemini events that arrive before replacement or on non-provider interruptions.
      if interrupting {
        self.geminiResponsePending = false
        self.pendingGeminiToolCallIds.removeAll()
      }
      guard !self.activityOpen else { return }
      self.activityOpen = true
      if self.isOpen {
        self.send(json: ["realtimeInput": ["activityStart": [:]]])
        self.flushPendingAudioIfReady()
        self.flushPendingTextInputs()
        log("\(self.tag): turn begin (activityStart\(interrupting ? ", interrupting in-flight reply" : ""))")
        if self.pendingCommit {
          self.pendingCommit = false
          self.commitInputTurnNow()
        }
      } else {
        self.pendingActivityStart = true
      }
    }
  }

  func commitInputTurn() {
    q.async { [weak self] in
      guard let self else { return }
      self.resetTurnUsage()  // fresh per-turn usage before the model responds
      guard self.isOpen, self.provider == .openai || self.activityOpen else {
        self.pendingCommit = true
        return
      }
      self.commitInputTurnNow()
    }
  }

  private func commitInputTurnNow() {
    flushPendingAudioIfReady()
    flushPendingTextInputs()
    log("\(tag): turn committed")
    switch provider {
    case .openai:
      pendingOpenAIToolCallIds.removeAll()
      if let identity = activeEventIdentity {
        openAIPendingInputIdentities.append(identity)
      }
      send(json: ["type": "input_audio_buffer.commit"])
      requestResponse(audio: true)
    case .gemini:
      pendingGeminiToolCallIds.removeAll()
      send(json: ["realtimeInput": ["activityEnd": [:]]])
      activityOpen = false
      geminiResponsePending = true
    // Gemini auto-responds at activityEnd; no explicit response request.
    }
  }

  /// Abandon the current turn without expecting a reply (silent tap / cancel). No
  /// teardown — closes the activity window and leaves the reply gated off, so the
  /// model never answers the silence and the warm socket (with context) is kept.
  func abandonInputTurn() {
    q.async { [weak self] in
      guard let self else { return }
      self.geminiResponsePending = false
      self.pendingAudio.removeAll()
      self.pendingVideo.removeAll()
      self.pendingTextInputs.removeAll()
      self.pendingCommit = false
      self.pendingActivityStart = false
      self.activeEventIdentity = nil
      self.completedGeminiEventIdentity = nil
      switch self.provider {
      case .openai:
        self.pendingOpenAIToolCallIds.removeAll()
        self.openAIFunctionNames.removeAll()
        self.dispatchedToolItems.removeAll()
        if self.openAIResponseActive {
          self.send(json: ["type": "response.cancel"])
        }
        self.openAIResponseActive = false
        self.openAIResponseCreatePending = false
        self.openAIActiveResponseID = nil
        self.openAIPendingResponseIdentities.removeAll()
        self.openAIResponseIdentities.removeAll()
        self.openAIPendingInputIdentities.removeAll()
        self.openAIInputItemIdentities.removeAll()
        // A pre-connect cancellation has no provider buffer to clear. Sending on
        // the absent transport would terminalize a session that may still connect.
        if self.isOpen {
          self.send(json: ["type": "input_audio_buffer.clear"])
        }
      case .gemini:
        self.pendingGeminiToolCallIds.removeAll()
        if self.activityOpen, self.isOpen {
          self.send(json: ["realtimeInput": ["activityEnd": [:]]])
        }
        self.activityOpen = false
      }
    }
  }

  /// Return a tool's result to the model and let it continue (speak).
  ///
  /// Gemini handles realtime video and tool responses as concurrent streams, so sending a
  /// screenshot as `realtimeInput.video` and then unblocking the function can race: the model
  /// may answer from older context before it processes the frame. Gemini 3 supports inline
  /// FunctionResponse parts; attach the fresh pixels there so the paused screenshot call resumes
  /// only with the exact image it captured.
  func sendToolResult(
    callId: String,
    name: String,
    output: String,
    screenEvidence: RealtimeScreenEvidenceAttachment? = nil,
    onWireEnqueued: ((Bool) -> Void)? = nil
  ) {
    // `onWireEnqueued` is caller-owned and non-Sendable; box it so the session
    // queue can carry it across without forcing the caller's closure @Sendable.
    let onWireEnqueuedBox = SessionCallbackBox(onWireEnqueued)
    q.async { [weak self] in
      guard let self else { return }
      switch self.provider {
      case .openai:
        if let screenEvidence {
          self.activeScreenEvidence = screenEvidence.descriptor
          let b64 = screenEvidence.jpeg.base64EncodedString()
          log(
            "\(self.tag): ptt_screen_evidence stage=tool_wire_prepared evidence=\(screenEvidence.descriptor.opaqueID) "
              + "image_bytes=\(screenEvidence.jpeg.count) serialized_bytes=\(b64.utf8.count)")
          self.send(json: [
            "type": "conversation.item.create",
            "item": [
              "type": "message", "role": "user",
              "content": [["type": "input_image", "image_url": "data:image/jpeg;base64,\(b64)"]],
            ],
          ]) { [weak self] imageError in
            guard let self, imageError == nil else {
              onWireEnqueuedBox.value?(false)
              return
            }
            self.enqueueOpenAIToolResult(
              callId: callId,
              output: output,
              onWireEnqueued: onWireEnqueuedBox.value)
          }
        } else {
          self.enqueueOpenAIToolResult(
            callId: callId,
            output: output,
            onWireEnqueued: onWireEnqueuedBox.value)
        }
      case .gemini:
        self.pendingGeminiToolCallIds.remove(callId)
        if let screenEvidence {
          self.activeScreenEvidence = screenEvidence.descriptor
        }
        let wire = Self.geminiToolResponse(
          callId: callId,
          name: name,
          output: output,
          screenEvidence: screenEvidence)
        if let screenEvidence {
          let serializedBytes = (try? JSONSerialization.data(withJSONObject: wire))?.count ?? 0
          log(
            "\(self.tag): ptt_screen_evidence stage=tool_wire_prepared evidence=\(screenEvidence.descriptor.opaqueID) "
              + "image_bytes=\(screenEvidence.jpeg.count) serialized_bytes=\(serializedBytes)")
        }
        self.send(json: wire) { error in
          onWireEnqueuedBox.value?(error == nil)
        }
      }
    }
  }

  /// Runs on the session queue after an optional image write has completed. The completion is a
  /// local transport fact only: the websocket accepted both exact function-response writes; it
  /// is not a provider acknowledgement or proof that Gemini/OpenAI has processed the image.
  private func enqueueOpenAIToolResult(
    callId: String,
    output: String,
    onWireEnqueued: ((Bool) -> Void)?
  ) {
    pendingOpenAIToolCallIds.remove(callId)
    send(json: [
      "type": "conversation.item.create",
      "item": ["type": "function_call_output", "call_id": callId, "output": output],
    ]) { [weak self] error in
      guard let self, error == nil else {
        onWireEnqueued?(false)
        return
      }
      onWireEnqueued?(true)
      if self.pendingOpenAIToolCallIds.isEmpty {
        self.requestResponse(audio: true)
      } else {
        log(
          "\(self.tag): waiting for \(self.pendingOpenAIToolCallIds.count) OpenAI tool result(s) before response.create"
        )
      }
    }
  }

  static func geminiToolResponse(
    callId: String,
    name: String,
    output: String,
    screenEvidence: RealtimeScreenEvidenceAttachment?
  ) -> [String: Any] {
    var functionResponse: [String: Any] = [
      "id": callId,
      "name": name,
      "response": ["result": output],
    ]
    if let screenEvidence {
      let displayName = "live-screenshot.jpg"
      functionResponse["response"] = [
        "result": output,
        "image": ["$ref": displayName],
        "evidence_id": screenEvidence.descriptor.evidenceID,
      ]
      functionResponse["parts"] = [
        [
          "inlineData": [
            "mimeType": "image/jpeg",
            "data": screenEvidence.jpeg.base64EncodedString(),
            "displayName": displayName,
          ]
        ]
      ]
    }
    return ["toolResponse": ["functionResponses": [functionResponse]]]
  }

  // OpenAI: ask for a response with the given modality (audio for spoken turns).
  private func requestResponse(
    audio: Bool,
    toolChoice: String? = nil,
    instructions: String? = nil,
    reason: String = "turn"
  ) {
    guard provider == .openai else { return }
    guard !openAIResponseActive else {
      log("\(tag): skip response.create — a response is already in progress")
      return
    }
    openAIResponseActive = true
    openAIResponseCreatePending = true
    openAIActiveResponseID = nil
    if let identity = activeEventIdentity {
      openAIPendingResponseIdentities.append(
        PendingOpenAIResponseIdentity(identity: identity, canceled: false))
    }
    var response: [String: Any] = ["output_modalities": [audio ? "audio" : "text"]]
    if let toolChoice {
      response["tool_choice"] = toolChoice
    }
    if let instructions {
      response["instructions"] = instructions
    }
    log("\(tag): response.create reason=\(reason) tool_choice=\(toolChoice ?? "session_default")")
    send(json: ["type": "response.create", "response": response])
  }

  // MARK: - Request / setup

  private func makeRequest() -> URLRequest? {
    switch provider {
    case .openai:
      // BYOK key and ephemeral token both ride the Bearer header (verified). GA: no
      // OpenAI-Beta header. Same endpoint either way.
      guard let url = URL(string: "wss://api.openai.com/v1/realtime?model=\(provider.modelID)")
      else { return nil }
      var r = URLRequest(url: url)
      r.setValue("Bearer \(auth.value)", forHTTPHeaderField: "Authorization")
      return r
    case .gemini:
      // Ephemeral tokens require the *Constrained* endpoint on v1alpha with
      // ?access_token= (verified); a BYOK key uses the plain endpoint on v1beta
      // with ?key=. (Apple's WS stacks can't reach either — RawWebSocket handles it.)
      let prefix = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage"
      let base: String
      let param: String
      switch auth {
      case .ephemeral:
        base = "\(prefix).v1alpha.GenerativeService.BidiGenerateContentConstrained"
        param = "access_token"
      case .byokKey:
        base = "\(prefix).v1beta.GenerativeService.BidiGenerateContent"
        param = "key"
      }
      guard var comps = URLComponents(string: base) else { return nil }
      comps.queryItems = [URLQueryItem(name: param, value: auth.value)]
      guard let url = comps.url else { return nil }
      return URLRequest(url: url)
    }
  }

  /// Whether the provider's input transcription accepts an explicit language hint.
  /// OpenAI's whisper transcription does; Gemini Live's inputAudioTranscription has no
  /// language field at all (native-audio models pick per utterance — the misdetect bug).
  var supportsInputTranscriptionLanguage: Bool { provider == .openai }

  /// ISO 639-1 hint applied to committed input transcription (OpenAI only).
  private var inputTranscriptionLanguage: String?

  /// Set (or clear, with nil) the input transcription language for this turn. Sends a
  /// full idempotent session.update — partial nested updates have murkier merge
  /// semantics, and the payload is deterministic anyway. Call BEFORE commitInputTurn();
  /// both hop to `q`, so FIFO ordering guarantees the update lands first. All state
  /// mutation happens on `q` (same discipline as every other send-path member).
  func setInputTranscriptionLanguage(_ code: String?) {
    guard provider == .openai else { return }
    q.async { [weak self] in
      guard let self else { return }
      guard code != self.inputTranscriptionLanguage else { return }
      self.inputTranscriptionLanguage = code
      log("\(self.tag): input transcription language → \(code ?? "auto")")
      guard self.isOpen else { return }  // pre-open: sendSessionSetup includes it
      self.send(json: self.openAISessionPayload())
    }
  }

  private func openAISessionPayload() -> [String: Any] {
    var transcription: [String: Any] = ["model": "whisper-1"]
    if let inputTranscriptionLanguage {
      transcription["language"] = inputTranscriptionLanguage
    }
    return [
      "type": "session.update",
      "session": [
        "type": "realtime",
        "instructions": instructions,
        "output_modalities": ["audio"],
        "audio": [
          "input": [
            "format": ["type": "audio/pcm", "rate": 24000],
            "turn_detection": NSNull(),  // PTT controls turns
            "transcription": transcription,
          ],
          "output": ["format": ["type": "audio/pcm", "rate": 24000], "voice": "marin"],
        ],
        "tools": RealtimeHubTools.openAITools(availableDirectedProviders: availableDirectedProviders),
        "tool_choice": "auto",
      ],
    ]
  }

  private func sendSessionSetup() {
    switch provider {
    case .openai:
      send(json: openAISessionPayload())
    case .gemini:
      // AUDIO modality: the only currently-available Live models are native-audio
      // (TEXT is rejected with close 1007). The spoken reply (24k PCM) is played by
      // StreamingPCMPlayer. outputAudioTranscription gives us the text for logging /
      // an optional bubble; inputAudioTranscription gives the user's STT.
      send(json: [
        "setup": [
          "model": "models/\(provider.modelID)",
          // Low temperature → tool-choice routing is consistent for identical inputs
          // (default ~1.0 made the same request flip between answering and escalating).
          // mediaResolution HIGH so a screenshot frame isn't downsampled to a generic blur.
          "generationConfig": [
            "responseModalities": ["AUDIO"], "temperature": 0.3,
            "mediaResolution": "MEDIA_RESOLUTION_HIGH",
            // Pin the spoken voice — with no speechConfig Gemini picks its own default,
            // which differs from the OpenAI hub voice (marin) and can change across
            // model revisions. Charon: deep, calm, "informative" — closest match to marin.
            "speechConfig": [
              "voiceConfig": ["prebuiltVoiceConfig": ["voiceName": "Charon"]]
            ],
          ],
          "systemInstruction": ["parts": [["text": instructions]]],
          "tools": [
            [
              "functionDeclarations": RealtimeHubTools.geminiFunctionDeclarations(
                availableDirectedProviders: availableDirectedProviders)
            ]
          ],
          "inputAudioTranscription": [:],
          "outputAudioTranscription": [:],
          // turnCoverage = ALL_VIDEO so an injected screenshot frame is part of the turn
          // even though we send it after activityEnd (default coverage would drop it).
          "realtimeInputConfig": [
            "automaticActivityDetection": ["disabled": true],
            "turnCoverage": "TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO",
          ],
          // Keep the session from degrading as turns accumulate: a sliding context
          // window stops unbounded growth (which was making replies slow to ~30–48s
          // and eventually stop). Without this, long sessions slowly die.
          "contextWindowCompression": ["slidingWindow": [:]],
        ]
      ])
    }
  }

  private func markReady() {
    guard !terminated, !isOpen else { return }
    isOpen = true
    log("\(tag): ready")
    // Open the speech window if a turn started before we connected (Gemini).
    if provider == .gemini, pendingActivityStart {
      pendingActivityStart = false
      send(json: ["realtimeInput": ["activityStart": [:]]])
    }
    flushPendingTextInputs()
    flushPendingAudioIfReady()
    // Flush any screen frame INTO the turn (after activityStart + audio, before commit).
    for v in pendingVideo {
      send(json: ["realtimeInput": ["video": ["data": v.b64, "mimeType": v.mime]]])
      log("\(tag): screen frame flushed into turn")
    }
    pendingVideo.removeAll()
    flushPendingTextInputs()
    if pendingCommit, provider == .openai || activityOpen {
      pendingCommit = false
      commitInputTurnNow()
    }
    let d = delegate
    Task { @MainActor in d?.hubDidConnect(source: self) }
  }

  // Send buffered audio after open (already on q).
  /// Send one mic PCM frame to the provider. Must be called on `q` with `isOpen`.
  /// Shared by sendAudio (live) and the markReady flush of buffered pre-connect audio.
  private func appendAudioFrame(_ pcm: Data) {
    let b64 = pcm.base64EncodedString()
    switch provider {
    case .openai:
      send(json: ["type": "input_audio_buffer.append", "audio": b64])
    case .gemini:
      send(json: ["realtimeInput": ["audio": ["data": b64, "mimeType": "audio/pcm;rate=16000"]]])
    }
  }

  private func flushPendingAudioIfReady() {
    guard isOpen, provider == .openai || activityOpen else { return }
    for chunk in pendingAudio { appendAudioFrame(chunk) }
    pendingAudio.removeAll()
  }

  // MARK: - Receive + parse

  private func receiveLoop() {
    task?.receive { [weak self] result in
      guard let self else { return }
      switch result {
      case .failure(let error):
        self.q.async { self.notifyError(.system(error, phase: .receive)) }
      case .success(let message):
        let data: Data?
        switch message {
        case .string(let text): data = Data(text.utf8)
        case .data(let d): data = d
        @unknown default: data = nil
        }
        if let data { self.q.async { self.handleMessage(data) } }
        self.receiveLoop()
      }
    }
  }

  private func handleMessage(_ data: Data) {
    guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
    switch provider {
    case .openai: handleOpenAI(obj)
    case .gemini: handleGemini(obj)
    }
  }

  private func deliverToDelegate(
    _ body: @escaping @MainActor (RealtimeHubSessionDelegate) -> Void
  ) {
    guard let delegate else { return }
    // `body` (@MainActor closure) and `delegate` are non-Sendable; box both for
    // the main hop. They are only ever used on the main actor.
    let delegateBox = SessionCallbackBox(delegate)
    let bodyBox = SessionCallbackBox(body)
    DispatchQueue.main.async {
      MainActor.assumeIsolated {
        bodyBox.value(delegateBox.value)
      }
    }
  }

  private func emitText(
    _ text: String,
    isFinal: Bool,
    identity explicitIdentity: RealtimeHubEventIdentity? = nil
  ) {
    guard !text.isEmpty || isFinal else { return }
    let identity = explicitIdentity ?? activeEventIdentity
    deliverToDelegate { delegate in
      delegate.hubDidEmitText(text, isFinal: isFinal, identity: identity, source: self)
    }
  }

  private func emitTranscript(
    _ text: String,
    isFinal: Bool,
    identity explicitIdentity: RealtimeHubEventIdentity? = nil
  ) {
    let identity = explicitIdentity ?? activeEventIdentity
    deliverToDelegate { delegate in
      delegate.hubDidReceiveInputTranscript(
        text, isFinal: isFinal, identity: identity, source: self)
    }
  }

  private func emitAudio(
    _ pcm: Data,
    identity explicitIdentity: RealtimeHubEventIdentity? = nil
  ) {
    let identity = explicitIdentity ?? activeEventIdentity
    deliverToDelegate { delegate in
      delegate.hubDidReceiveAudio(pcm, identity: identity, source: self)
    }
  }

  private func emitTool(
    name: String,
    callId: String,
    argumentsJSON: String,
    identity explicitIdentity: RealtimeHubEventIdentity? = nil
  ) {
    log("\(tag): tool_call \(name)(\(argumentsJSON.prefix(160)))")
    let identity = explicitIdentity ?? activeEventIdentity
    deliverToDelegate { delegate in
      delegate.hubDidRequestTool(
        name: name, callId: callId, argumentsJSON: argumentsJSON,
        identity: identity, source: self)
    }
  }

  private func finishTurn(identity explicitIdentity: RealtimeHubEventIdentity? = nil) {
    reportUsageIfNeeded()
    let identity = explicitIdentity ?? activeEventIdentity
    deliverToDelegate { delegate in
      delegate.hubDidFinishTurn(identity: identity, source: self)
    }
  }

  // MARK: - Usage (client-reported billing, managed sessions only)

  private func resetTurnUsage() {
    usageInText = 0
    usageInAudio = 0
    usageInImage = 0
    usageInCached = 0
    usageOutText = 0
    usageOutAudio = 0
  }

  /// OpenAI: response.done.usage is final per response → sum across the turn's responses.
  private func accumulateOpenAIUsage(_ usage: [String: Any]) {
    func n(_ d: [String: Any]?, _ k: String) -> Int {
      (d?[k] as? Int) ?? (d?[k] as? NSNumber)?.intValue ?? 0
    }
    let inD = usage["input_token_details"] as? [String: Any]
    let outD = usage["output_token_details"] as? [String: Any]
    usageInText += n(inD, "text_tokens")
    usageInAudio += n(inD, "audio_tokens")
    usageInImage += n(inD, "image_tokens")
    usageInCached += n(inD, "cached_tokens")
    usageOutText += n(outD, "text_tokens")
    usageOutAudio += n(outD, "audio_tokens")
  }

  /// Gemini: usageMetadata is cumulative for the turn → keep the latest (replace, not sum).
  private func accumulateGeminiUsage(_ um: [String: Any]) {
    func split(_ arr: Any?) -> (text: Int, audio: Int, image: Int) {
      var t = 0
      var a = 0
      var i = 0
      for d in (arr as? [[String: Any]]) ?? [] {
        let c = (d["tokenCount"] as? Int) ?? (d["tokenCount"] as? NSNumber)?.intValue ?? 0
        switch (d["modality"] as? String)?.uppercased() {
        case "AUDIO": a += c
        case "IMAGE": i += c
        default: t += c
        }
      }
      return (t, a, i)
    }
    let pin = split(um["promptTokensDetails"])
    let pout = split(um["responseTokensDetails"])
    if pin.text == 0 && pin.audio == 0 && pin.image == 0 {
      usageInText = (um["promptTokenCount"] as? Int) ?? 0
      usageInAudio = 0
      usageInImage = 0
    } else {
      usageInText = pin.text
      usageInAudio = pin.audio
      usageInImage = pin.image
    }
    if pout.text == 0 && pout.audio == 0 {
      usageOutText = (um["candidatesTokenCount"] as? Int) ?? (um["responseTokenCount"] as? Int) ?? 0
      usageOutAudio = 0
    } else {
      usageOutText = pout.text
      usageOutAudio = pout.audio
    }
    usageInCached = (um["cachedContentTokenCount"] as? Int) ?? 0
  }

  /// Report the turn's usage to the backend (managed sessions only — BYOK pays direct).
  /// Resets first so a second finishTurn (barge-in edge) can't double-report.
  private func reportUsageIfNeeded() {
    let it = usageInText
    let ia = usageInAudio
    let ic = usageInCached
    let ot = usageOutText
    let oa = usageOutAudio
    if let evidence = activeScreenEvidence {
      log(
        "\(tag): ptt_screen_evidence stage=provider_turn_done evidence=\(evidence.opaqueID) "
          + "image_tokens=\(usageInImage)")
      activeScreenEvidence = nil
    }
    resetTurnUsage()
    guard auth.isEphemeral, it + ia + ic + ot + oa > 0 else { return }
    let providerName = provider == .gemini ? "gemini" : "openai"
    let model = provider.modelID
    Task {
      await APIClient.shared.reportRealtimeUsage(
        provider: providerName, model: model,
        inputText: it, inputAudio: ia, inputCached: ic, outputText: ot, outputAudio: oa,
        contextPlanID: self.contextPlanID,
        stableCacheIdentity: self.stableCacheIdentity,
        dynamicContextIdentity: self.dynamicContextIdentity,
        contextCacheReplaced: self.contextCacheReplaced)
    }
  }

  // MARK: OpenAI events

  private func handleOpenAI(_ e: [String: Any]) {
    guard let type = e["type"] as? String else { return }
    switch type {
    case "session.created", "session.updated":
      markReady()
    case "response.created":
      guard let response = e["response"] as? [String: Any],
        let id = response["id"] as? String,
        !openAIPendingResponseIdentities.isEmpty
      else { return }
      let pending = openAIPendingResponseIdentities.removeFirst()
      guard !pending.canceled else {
        log("\(tag): consumed canceled response.created \(id)")
        return
      }
      guard openAIResponseActive else { return }
      openAIActiveResponseID = id
      openAIResponseIdentities[id] = pending.identity
      openAIResponseCreatePending = false
    case "response.output_audio.delta":
      guard isCurrentOpenAIResponseEvent(e), let identity = openAIResponseIdentity(for: e) else { return }
      if let b64 = e["delta"] as? String, let d = Data(base64Encoded: b64) {
        emitAudio(d, identity: identity)
      }
    case "response.output_audio_transcript.delta":
      guard isCurrentOpenAIResponseEvent(e), let identity = openAIResponseIdentity(for: e) else { return }
      if let t = e["delta"] as? String { emitText(t, isFinal: false, identity: identity) }
    case "input_audio_buffer.committed":
      if let itemID = e["item_id"] as? String, !openAIPendingInputIdentities.isEmpty {
        let identity = openAIPendingInputIdentities.removeFirst()
        openAIInputItemIdentities[itemID] = identity
      }
    case "conversation.item.input_audio_transcription.delta":
      guard let identity = openAIInputIdentity(for: e) else { return }
      if let t = e["delta"] as? String {
        emitTranscript(t, isFinal: false, identity: identity)
      }
    case "conversation.item.input_audio_transcription.completed":
      guard let itemID = e["item_id"] as? String,
        let identity = openAIInputItemIdentities.removeValue(forKey: itemID)
      else { return }
      if let t = e["transcript"] as? String {
        log("\(tag): heard \"\(t.prefix(120))\"")
        emitTranscript(t, isFinal: true, identity: identity)
      }
    case "response.output_item.added":
      guard isCurrentOpenAIResponseEvent(e) else { return }
      // Record function-call name keyed by call_id for the done parse below.
      if let item = e["item"] as? [String: Any], (item["type"] as? String) == "function_call",
        let callId = item["call_id"] as? String, let name = item["name"] as? String
      {
        openAIFunctionNames[callId] = name
      }
    case "response.done":
      handleOpenAIResponseDone(e)
    case "error":
      openAIResponseActive = false
      openAIResponseCreatePending = false
      openAIActiveResponseID = nil
      let msg = (e["error"] as? [String: Any])?["message"] as? String ?? "OpenAI realtime error"
      notifyError(.providerError(msg))
    default:
      break
    }
  }

  private func isCurrentOpenAIResponseEvent(_ e: [String: Any]) -> Bool {
    guard openAIResponseActive else { return false }
    guard !openAIResponseCreatePending, let expected = openAIActiveResponseID else { return false }
    let eventResponseID =
      (e["response_id"] as? String)
      ?? ((e["response"] as? [String: Any])?["id"] as? String)
    return eventResponseID == expected
  }

  private func openAIResponseIdentity(for event: [String: Any]) -> RealtimeHubEventIdentity? {
    let responseID =
      (event["response_id"] as? String)
      ?? ((event["response"] as? [String: Any])?["id"] as? String)
    return responseID.flatMap { openAIResponseIdentities[$0] }
  }

  private func openAIInputIdentity(for event: [String: Any]) -> RealtimeHubEventIdentity? {
    guard let itemID = event["item_id"] as? String else { return nil }
    return openAIInputItemIdentities[itemID]
  }

  private func handleOpenAIResponseDone(_ e: [String: Any]) {
    guard isCurrentOpenAIResponseEvent(e) else {
      log("\(tag): ignoring stale response.done")
      return
    }
    guard let responseIdentity = openAIResponseIdentity(for: e) else { return }
    let completedResponseID = openAIActiveResponseID
    openAIResponseActive = false  // this response finished — a new one may be created
    openAIResponseCreatePending = false
    openAIActiveResponseID = nil
    if let usage = (e["response"] as? [String: Any])?["usage"] as? [String: Any] {
      accumulateOpenAIUsage(usage)
    }
    let response = e["response"] as? [String: Any]
    let output = response?["output"] as? [[String: Any]] ?? []
    let status = response?["status"] as? String ?? "unknown"
    let outputKinds = output.compactMap { $0["type"] as? String }.joined(separator: ",")
    let statusDetail = ((response?["status_details"] as? [String: Any])?["type"] as? String) ?? "none"
    let outputSummary = outputKinds.isEmpty ? "none" : outputKinds
    log("\(tag): response.done status=\(status) detail=\(statusDetail) output=\(outputSummary)")
    var firedTool = false
    for item in output where (item["type"] as? String) == "function_call" {
      guard let callId = item["call_id"] as? String, !dispatchedToolItems.contains(callId) else {
        continue
      }
      dispatchedToolItems.insert(callId)
      pendingOpenAIToolCallIds.insert(callId)
      let name = (item["name"] as? String) ?? openAIFunctionNames[callId] ?? ""
      let argsStr = (item["arguments"] as? String) ?? "{}"
      if !name.isEmpty {
        firedTool = true
        emitTool(
          name: name,
          callId: callId,
          argumentsJSON: argsStr,
          identity: responseIdentity)
      }
    }
    // A response that only made tool calls isn't the end of the user's turn —
    // the model speaks after we return the tool result. Otherwise finish.
    if !firedTool {
      emitText("", isFinal: true, identity: responseIdentity)
      finishTurn(identity: responseIdentity)
    }
    if let completedResponseID {
      openAIResponseIdentities.removeValue(forKey: completedResponseID)
    }
  }

  // MARK: Gemini events

  private func handleGemini(_ e: [String: Any]) {
    if e["setupComplete"] != nil {
      markReady()
      return
    }
    if let um = e["usageMetadata"] as? [String: Any] { accumulateGeminiUsage(um) }
    if let toolCall = e["toolCall"] as? [String: Any],
      let calls = toolCall["functionCalls"] as? [[String: Any]]
    {
      // Ignore tool calls when no committed turn is awaiting a reply — an abandoned/
      // discarded turn still reaches Gemini (we send activityEnd to close the window),
      // and without this guard it acts on half-heard audio (e.g. fires get_tasks).
      // OpenAI is immune because an abandoned turn just clears its input buffer.
      guard geminiResponsePending else {
        log("\(tag): ignoring tool call — no live committed turn (abandoned/discarded)")
        return
      }
      for call in calls {
        let name = call["name"] as? String ?? ""
        // Gemini may omit ids; synthesize unique ones so same-name calls in one turn
        // do not collapse controller/session pending-tool bookkeeping.
        let callId = call["id"] as? String ?? nextGeminiSyntheticToolCallId(name: name)
        pendingGeminiToolCallIds.insert(callId)
        let args = call["args"] as? [String: Any] ?? [:]
        let argsJSON =
          (try? JSONSerialization.data(withJSONObject: args)).flatMap {
            String(data: $0, encoding: .utf8)
          } ?? "{}"
        if !name.isEmpty { emitTool(name: name, callId: callId, argumentsJSON: argsJSON) }
      }
      return
    }
    guard let sc = e["serverContent"] as? [String: Any] else { return }
    if (sc["interrupted"] as? Bool) == true {
      // Barge-in: drop the pending reply so its trailing audio + bookkeeping turnComplete
      // are ignored; the new turn (already started via activityStart) re-arms on commit.
      geminiResponsePending = false
      pendingGeminiToolCallIds.removeAll()
      log("\(tag): server confirmed interrupt")
    }
    // NOTE: do NOT finish on generationComplete — Gemini sends it while the spoken audio
    // is still streaming, so finishing there truncates the reply and makes the next turn
    // interrupt the server's still-open turn. We finish on turnComplete (below), which
    // arrives when the audio actually completes.
    if let it = sc["inputTranscription"] as? [String: Any], let t = it["text"] as? String {
      if let identity = GeminiRealtimeEventOwnership.inputIdentity(
        active: activeEventIdentity,
        completed: completedGeminiEventIdentity)
      {
        emitTranscript(t, isFinal: false, identity: identity)
      } else {
        log("\(tag): dropping ambiguous Gemini input transcription across turn boundary")
      }
    }
    if let ot = sc["outputTranscription"] as? [String: Any], let t = ot["text"] as? String {
      emitText(t, isFinal: false)  // the spoken reply's text, for logging / the bubble
    }
    if let parts = (sc["modelTurn"] as? [String: Any])?["parts"] as? [[String: Any]] {
      for p in parts {
        if let t = p["text"] as? String { emitText(t, isFinal: false) }
        if let inline = p["inlineData"] as? [String: Any],
          let mime = inline["mimeType"] as? String, mime.contains("audio/pcm"),
          let b64 = inline["data"] as? String, let d = Data(base64Encoded: b64)
        {
          if geminiResponsePending { emitAudio(d) }  // gated: only the live turn's reply
        }
      }
    }
    if (sc["turnComplete"] as? Bool) == true {
      guard pendingGeminiToolCallIds.isEmpty else {
        log("\(tag): deferring Gemini turnComplete with \(pendingGeminiToolCallIds.count) tool result(s) pending")
        return
      }
      // Only finish the turn we're actually awaiting a reply for. A turnComplete that
      // closes an interrupted/abandoned generation (pending=false) is ignored, so it
      // can't prematurely end the live turn.
      if geminiResponsePending {
        geminiResponsePending = false
        completedGeminiEventIdentity = activeEventIdentity
        emitText("", isFinal: true)
        finishTurn(identity: completedGeminiEventIdentity)
      }
    }
  }

  private func nextGeminiSyntheticToolCallId(name: String) -> String {
    geminiSyntheticToolCallCounter += 1
    return "\(name):\(geminiSyntheticToolCallCounter)"
  }

  // MARK: - Send (on q)

  private func send(json: [String: Any], completion: ((Error?) -> Void)? = nil) {
    // `completion` is non-Sendable; box it so the raw-WS / URLSession completion
    // closures can carry it across the session queue.
    let completionBox = SessionCallbackBox(completion)
    guard let data = try? JSONSerialization.data(withJSONObject: json),
      let text = String(data: data, encoding: .utf8)
    else {
      failSend(RealtimeHubSessionSendError.encodingFailed, completion: completion)
      return
    }
    #if DEBUG
      if acceptsTestingTransport {
        if (json["type"] as? String) == "response.create" {
          testingResponseCreateCount += 1
          testingLastResponseToolChoice = (json["response"] as? [String: Any])?["tool_choice"] as? String
          testingLastResponseInstruction = (json["response"] as? [String: Any])?["instructions"] as? String
        }
        completion?(nil)
        return
      }
    #endif
    if usesRawWS {
      guard let rawWS else {
        failSend(RealtimeHubSessionSendError.notConnected, completion: completion)
        return
      }
      rawWS.sendText(text) { [weak self] error in
        guard let self else { return }
        self.q.async {
          if let error { self.notifyError(.system(error, phase: .send)) }
          completionBox.value?(error)
        }
      }
      return
    }
    guard let task else {
      failSend(RealtimeHubSessionSendError.notConnected, completion: completion)
      return
    }
    task.send(.string(text)) { [weak self] error in
      guard let self else { return }
      self.q.async {
        if let error { self.notifyError(.system(error, phase: .send)) }
        completionBox.value?(error)
      }
    }
  }

  /// Every local send failure is a terminal session failure, including synchronous no-transport
  /// and encoding paths. A screen-evidence receipt must never wait for a provider deadline after
  /// the session has already proved it cannot enqueue the exact wire.
  private func failSend(_ error: Error, completion: ((Error?) -> Void)?) {
    notifyError(.system(error, phase: .send))
    completion?(error)
  }
}

private enum RealtimeHubSessionSendError: LocalizedError {
  case encodingFailed
  case notConnected

  var errorDescription: String? {
    switch self {
    case .encodingFailed: "Could not encode realtime transport data."
    case .notConnected: "Realtime transport is not connected."
    }
  }
}

// MARK: - URLSessionWebSocketDelegate (OpenAI)

extension RealtimeHubSession: URLSessionWebSocketDelegate {
  func urlSession(
    _ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol proto: String?
  ) {
    log("RealtimeHub: WS didOpen (OpenAI)")
    q.async {
      guard !self.terminated else { return }
      self.receiveLoop()
      self.sendSessionSetup()
    }
  }

  func urlSession(
    _ session: URLSession, webSocketTask: URLSessionWebSocketTask,
    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?
  ) {
    let r = reason.flatMap { String(data: $0, encoding: .utf8) } ?? ""
    q.async {
      self.notifyError(
        .providerClose(
          code: closeCode.rawValue,
          reason: r))
    }
  }

  func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    q.async {
      let taskID = task.taskIdentifier
      self.completedURLTaskIDs.insert(taskID)
      let waiters = self.urlTaskTerminalWaiters.removeValue(forKey: taskID) ?? []
      for waiter in waiters {
        waiter.resume()
      }
      if let error {
        self.notifyError(.system(error, phase: .connect))
      }
    }
  }
}

import Foundation
import Network

// MARK: - Realtime Hub Session (Phase 1, CLIENT-DIRECT)
//
// One persistent WebSocket to a realtime provider, opened with the user's own
// BYOK key (dev/test only — gated by RealtimeHubSettings.canConnect). The model
// is the hub: it does in-session STT + reasoning + routing (via tool calls) and
// speaks the answer.
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
//               half-cascade Live model, response modality TEXT + function calling.
//               Text out is spoken by the caller via AVSpeechSynthesizer.
//               Transport: Network.framework WebSocket with ALPN pinned to
//               http/1.1 — Gemini's endpoint upgrades URLSession's WS to HTTP/2
//               and resets it (the documented reason the legacy path needed a
//               relay); pinning ALPN avoids the upgrade.
//
// Normalized events: transcript_in (input STT) / audio_out (OpenAI) |
// text_out (Gemini) / tool_call / turn.done.

@MainActor
protocol RealtimeHubSessionDelegate: AnyObject {
  func hubDidConnect()
  func hubDidReceiveInputTranscript(_ text: String, isFinal: Bool)
  /// OpenAI native spoken audio (PCM16 mono 24 kHz).
  func hubDidReceiveAudio(_ pcm24k: Data)
  /// Assistant text to display / speak. Gemini emits its whole reply here;
  /// OpenAI emits its spoken transcript here (for the on-screen bubble).
  func hubDidEmitText(_ text: String, isFinal: Bool)
  func hubDidRequestTool(name: String, callId: String, argumentsJSON: String)
  func hubDidFinishTurn()
  func hubDidError(_ message: String)
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

final class RealtimeHubSession: NSObject {
  private let provider: RealtimeHubProvider
  private let auth: HubAuth
  private weak var delegate: RealtimeHubSessionDelegate?

  /// Mic PCM input rate per provider (Gemini 16k native, OpenAI GA needs 24k).
  var requiredInputSampleRate: Int { provider == .openai ? 24000 : 16000 }

  // All socket + state access is serialized here (audio arrives on the capture
  // thread; receives on the URLSession/NW queue). Delegate calls hop to main.
  private let q = DispatchQueue(label: "omi.realtime-hub.session")

  private var task: URLSessionWebSocketTask?
  private lazy var session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
  // Gemini's Live endpoint rejects both of Apple's WebSocket stacks, so it uses a
  // hand-rolled RFC 6455 client (RawWebSocket). OpenAI uses URLSession.
  private var rawWS: RawWebSocket?
  private var usesRawWS: Bool { provider == .gemini }

  private var isOpen = false
  private var terminated = false
  private var pendingAudio: [Data] = []
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
  /// Gemini: a committed turn is awaiting its spoken reply. Gates BOTH audio
  /// playback and turn completion to the CURRENT turn, so an interrupted/abandoned
  /// turn's trailing audio + bookkeeping `turnComplete` can't leak into the next
  /// one. Set on activityEnd (commit); cleared on this turn's `turnComplete`, on a
  /// server `interrupted`, or when a new turn interrupts (beginInputTurn interrupting).
  private var geminiResponsePending = false

  // Per-turn token usage for managed (ephemeral) billing — client-reported. Reset at
  // commit, reported at finishTurn (only for ephemeral sessions; BYOK pays the provider
  // directly). OpenAI sends a final usage per response.done (summed across a turn's
  // responses); Gemini sends cumulative usageMetadata (we keep the latest).
  private var usageInText = 0
  private var usageInAudio = 0
  private var usageInCached = 0
  private var usageOutText = 0
  private var usageOutAudio = 0
  /// Screenshot tool: injecting an image looks like new user input to Gemini, so it
  /// interrupts its own pending reply. These tell that self-induced interrupt apart
  /// from a real barge-in (which must drop the turn; this must NOT).
  private var geminiImageInjected = false
  private var geminiInterruptAfterInject = false

  /// Log prefix that names the provider + model on every line, so it's always
  /// clear which model produced which event.
  private var tag: String { "RealtimeHub[\(provider == .openai ? "openai" : "gemini"):\(provider.modelID)]" }

  init(provider: RealtimeHubProvider, auth: HubAuth, delegate: RealtimeHubSessionDelegate) {
    self.provider = provider
    self.auth = auth
    self.delegate = delegate
    super.init()
  }

  // MARK: Lifecycle

  func start() {
    q.async { [weak self] in self?._start() }
  }

  private func _start() {
    guard let request = makeRequest(), let url = request.url else {
      notifyError("Could not build \(provider.displayName) request URL")
      return
    }
    log("RealtimeHub: connecting \(provider.displayName) → \(url.host ?? "?") (client-direct)")
    if usesRawWS {
      let ws = RawWebSocket(url: url, queue: q)
      rawWS = ws
      ws.onOpen = { [weak self] in
        guard let self else { return }
        log("RealtimeHub: raw WS open (\(self.provider.displayName))")
        self.sendSessionSetup()
      }
      ws.onMessage = { [weak self] data in self?.handleMessage(data) }
      ws.onClose = { [weak self] code, reason in self?.notifyError("WebSocket closed (\(code)) \(reason)") }
      ws.onError = { [weak self] msg in self?.notifyError(msg) }
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
      guard let self else { return }
      self.task?.cancel(with: .goingAway, reason: nil)
      self.task = nil
      self.rawWS?.close()
      self.rawWS = nil
      self.isOpen = false
      self.pendingAudio.removeAll()
      self.pendingCommit = false
      self.openAIFunctionNames.removeAll()
      self.dispatchedToolItems.removeAll()
      self.activityOpen = false
      self.pendingActivityStart = false
      self.openAIResponseActive = false
      self.geminiResponsePending = false
      self.geminiImageInjected = false
      self.geminiInterruptAfterInject = false
    }
  }

  private func notifyError(_ message: String) {
    guard !terminated else { return }
    terminated = true
    let d = delegate
    Task { @MainActor in d?.hubDidError(message) }
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
          self.send(json: ["type": "response.cancel"])
          self.openAIResponseActive = false
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
      guard self.isOpen else { self.pendingAudio.append(pcm); return }
      self.appendAudioFrame(pcm)
    }
  }

  /// End the user's PTT turn and ask the model to respond.
  /// Start a new PTT turn. Gemini: open a fresh speech-activity window (must be
  /// done EVERY turn on a warm session). OpenAI: no-op (input_audio_buffer based).
  func beginInputTurn(interrupting: Bool = false) {
    guard provider == .gemini else { return }
    q.async { [weak self] in
      guard let self else { return }
      // Barge-in: abandon the previous turn's still-pending reply so its trailing
      // audio + bookkeeping turnComplete are ignored. A fresh activityStart on the
      // SAME socket cancels the in-flight generation server-side (it replies with
      // serverContent.interrupted) — no teardown, so conversation context survives.
      if interrupting {
        self.geminiResponsePending = false
        self.geminiImageInjected = false
        self.geminiInterruptAfterInject = false
      }
      guard !self.activityOpen else { return }
      self.activityOpen = true
      if self.isOpen {
        self.send(json: ["realtimeInput": ["activityStart": [:]]])
        log("\(self.tag): turn begin (activityStart\(interrupting ? ", interrupting in-flight reply" : ""))")
      } else {
        self.pendingActivityStart = true
      }
    }
  }

  func commitInputTurn() {
    q.async { [weak self] in
      guard let self else { return }
      self.resetTurnUsage()  // fresh per-turn usage before the model responds
      guard self.isOpen else { self.pendingCommit = true; return }
      log("\(self.tag): turn committed")
      switch self.provider {
      case .openai:
        self.send(json: ["type": "input_audio_buffer.commit"])
        self.requestResponse(audio: true)
      case .gemini:
        self.send(json: ["realtimeInput": ["activityEnd": [:]]])
        self.activityOpen = false
        self.geminiResponsePending = true  // expect a spoken reply for THIS turn
      // Gemini auto-responds at activityEnd; no explicit response request.
      }
    }
  }

  /// Abandon the current turn without expecting a reply (silent tap / cancel). No
  /// teardown — closes the activity window and leaves the reply gated off, so the
  /// model never answers the silence and the warm socket (with context) is kept.
  func abandonInputTurn() {
    q.async { [weak self] in
      guard let self else { return }
      self.geminiResponsePending = false
      switch self.provider {
      case .openai:
        self.send(json: ["type": "input_audio_buffer.clear"])
      case .gemini:
        if self.activityOpen, self.isOpen {
          self.send(json: ["realtimeInput": ["activityEnd": [:]]])
        }
        self.activityOpen = false
        self.pendingActivityStart = false
        self.pendingCommit = false
      }
    }
  }

  /// Return a tool's result to the model and let it continue (speak).
  func sendToolResult(callId: String, name: String, output: String) {
    q.async { [weak self] in
      guard let self else { return }
      switch self.provider {
      case .openai:
        self.send(json: [
          "type": "conversation.item.create",
          "item": ["type": "function_call_output", "call_id": callId, "output": output],
        ])
        self.requestResponse(audio: true)
      case .gemini:
        self.send(json: [
          "toolResponse": [
            "functionResponses": [["id": callId, "name": name, "response": ["result": output]]]
          ]
        ])
      }
    }
  }

  /// Inject a screenshot the model can reference on its next response.
  func injectImage(_ pngData: Data) {
    let b64 = pngData.base64EncodedString()
    q.async { [weak self] in
      guard let self else { return }
      switch self.provider {
      case .openai:
        self.send(json: [
          "type": "conversation.item.create",
          "item": [
            "type": "message", "role": "user",
            "content": [["type": "input_image", "image_url": "data:image/png;base64,\(b64)"]],
          ],
        ])
      case .gemini:
        // gemini-3.1-flash-live-preview rejects clientContent mid-session (close 1007 —
        // it's only for seeding initial history). Send the screenshot as a realtimeInput
        // video frame instead — the documented mid-session image path.
        self.send(json: [
          "realtimeInput": ["video": ["data": b64, "mimeType": "image/png"]]
        ])
        self.geminiImageInjected = true  // may self-interrupt; don't drop the turn if so
      }
    }
  }

  // OpenAI: ask for a response with the given modality (audio for spoken turns).
  private func requestResponse(audio: Bool) {
    guard provider == .openai else { return }
    guard !openAIResponseActive else {
      log("\(tag): skip response.create — a response is already in progress")
      return
    }
    openAIResponseActive = true
    send(json: ["type": "response.create", "response": ["output_modalities": [audio ? "audio" : "text"]]])
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

  private func sendSessionSetup() {
    switch provider {
    case .openai:
      send(json: [
        "type": "session.update",
        "session": [
          "type": "realtime",
          "instructions": RealtimeHubTools.systemInstruction,
          "output_modalities": ["audio"],
          "audio": [
            "input": [
              "format": ["type": "audio/pcm", "rate": 24000],
              "turn_detection": NSNull(),  // PTT controls turns
              "transcription": ["model": "whisper-1"],
            ],
            "output": ["format": ["type": "audio/pcm", "rate": 24000], "voice": "marin"],
          ],
          "tools": RealtimeHubTools.openAITools,
          "tool_choice": "auto",
        ],
      ])
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
          ],
          "systemInstruction": ["parts": [["text": RealtimeHubTools.systemInstruction]]],
          "tools": [["functionDeclarations": RealtimeHubTools.geminiFunctionDeclarations]],
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
    guard !isOpen else { return }
    isOpen = true
    log("\(tag): ready")
    // Open the speech window if a turn started before we connected (Gemini).
    if provider == .gemini, pendingActivityStart {
      pendingActivityStart = false
      send(json: ["realtimeInput": ["activityStart": [:]]])
    }
    for chunk in pendingAudio { appendAudioFrame(chunk) }
    pendingAudio.removeAll()
    if pendingCommit {
      pendingCommit = false
      // Re-run commit now that we're open.
      switch provider {
      case .openai:
        send(json: ["type": "input_audio_buffer.commit"])
        requestResponse(audio: true)
      case .gemini:
        send(json: ["realtimeInput": ["activityEnd": [:]]])
        activityOpen = false
        geminiResponsePending = true
      }
    }
    let d = delegate
    Task { @MainActor in d?.hubDidConnect() }
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

  // MARK: - Receive + parse

  private func receiveLoop() {
    task?.receive { [weak self] result in
      guard let self else { return }
      switch result {
      case .failure(let error):
        self.q.async { self.notifyError(error.localizedDescription) }
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

  private func emitText(_ text: String, isFinal: Bool) {
    guard !text.isEmpty || isFinal else { return }
    let d = delegate
    Task { @MainActor in d?.hubDidEmitText(text, isFinal: isFinal) }
  }

  private func emitTranscript(_ text: String, isFinal: Bool) {
    let d = delegate
    Task { @MainActor in d?.hubDidReceiveInputTranscript(text, isFinal: isFinal) }
  }

  private func emitAudio(_ pcm: Data) {
    let d = delegate
    Task { @MainActor in d?.hubDidReceiveAudio(pcm) }
  }

  private func emitTool(name: String, callId: String, argumentsJSON: String) {
    log("\(tag): tool_call \(name)(\(argumentsJSON.prefix(160)))")
    let d = delegate
    Task { @MainActor in
      d?.hubDidRequestTool(name: name, callId: callId, argumentsJSON: argumentsJSON)
    }
  }

  private func finishTurn() {
    reportUsageIfNeeded()
    let d = delegate
    Task { @MainActor in d?.hubDidFinishTurn() }
  }

  // MARK: - Usage (client-reported billing, managed sessions only)

  private func resetTurnUsage() {
    usageInText = 0
    usageInAudio = 0
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
    usageInCached += n(inD, "cached_tokens")
    usageOutText += n(outD, "text_tokens")
    usageOutAudio += n(outD, "audio_tokens")
  }

  /// Gemini: usageMetadata is cumulative for the turn → keep the latest (replace, not sum).
  private func accumulateGeminiUsage(_ um: [String: Any]) {
    func split(_ arr: Any?) -> (text: Int, audio: Int) {
      var t = 0, a = 0
      for d in (arr as? [[String: Any]]) ?? [] {
        let c = (d["tokenCount"] as? Int) ?? (d["tokenCount"] as? NSNumber)?.intValue ?? 0
        if (d["modality"] as? String)?.uppercased() == "AUDIO" { a += c } else { t += c }
      }
      return (t, a)
    }
    let pin = split(um["promptTokensDetails"])
    let pout = split(um["responseTokensDetails"])
    if pin.text == 0 && pin.audio == 0 {
      usageInText = (um["promptTokenCount"] as? Int) ?? 0
      usageInAudio = 0
    } else {
      usageInText = pin.text
      usageInAudio = pin.audio
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
    let it = usageInText, ia = usageInAudio, ic = usageInCached, ot = usageOutText, oa = usageOutAudio
    resetTurnUsage()
    guard auth.isEphemeral, it + ia + ic + ot + oa > 0 else { return }
    let providerName = provider == .gemini ? "gemini" : "openai"
    let model = provider.modelID
    Task {
      await APIClient.shared.reportRealtimeUsage(
        provider: providerName, model: model,
        inputText: it, inputAudio: ia, inputCached: ic, outputText: ot, outputAudio: oa)
    }
  }

  // MARK: OpenAI events

  private func handleOpenAI(_ e: [String: Any]) {
    guard let type = e["type"] as? String else { return }
    switch type {
    case "session.created", "session.updated":
      markReady()
    case "response.output_audio.delta":
      if let b64 = e["delta"] as? String, let d = Data(base64Encoded: b64) { emitAudio(d) }
    case "response.output_audio_transcript.delta":
      if let t = e["delta"] as? String { emitText(t, isFinal: false) }
    case "conversation.item.input_audio_transcription.delta":
      if let t = e["delta"] as? String { emitTranscript(t, isFinal: false) }
    case "conversation.item.input_audio_transcription.completed":
      if let t = e["transcript"] as? String {
        log("\(tag): heard \"\(t.prefix(120))\"")
        emitTranscript(t, isFinal: true)
      }
    case "response.output_item.added":
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
      let msg = (e["error"] as? [String: Any])?["message"] as? String ?? "OpenAI realtime error"
      notifyError(msg)
    default:
      break
    }
  }

  private func handleOpenAIResponseDone(_ e: [String: Any]) {
    openAIResponseActive = false  // this response finished — a new one may be created
    if let usage = (e["response"] as? [String: Any])?["usage"] as? [String: Any] {
      accumulateOpenAIUsage(usage)
    }
    let output = (e["response"] as? [String: Any])?["output"] as? [[String: Any]] ?? []
    var firedTool = false
    for item in output where (item["type"] as? String) == "function_call" {
      guard let callId = item["call_id"] as? String, !dispatchedToolItems.contains(callId) else {
        continue
      }
      dispatchedToolItems.insert(callId)
      let name = (item["name"] as? String) ?? openAIFunctionNames[callId] ?? ""
      let argsStr = (item["arguments"] as? String) ?? "{}"
      if !name.isEmpty {
        firedTool = true
        emitTool(name: name, callId: callId, argumentsJSON: argsStr)
      }
    }
    // A response that only made tool calls isn't the end of the user's turn —
    // the model speaks after we return the tool result. Otherwise finish.
    if !firedTool {
      emitText("", isFinal: true)
      finishTurn()
    }
  }

  // MARK: Gemini events

  private func handleGemini(_ e: [String: Any]) {
    if e["setupComplete"] != nil { markReady(); return }
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
        // Gemini may omit id for single calls; synthesize one for our bookkeeping.
        let callId = call["id"] as? String ?? name
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
      if geminiImageInjected {
        // Self-induced: injecting a screenshot looks like new user input to Gemini, so it
        // interrupts its own pending reply. Keep the turn alive — the real answer (using
        // the image) arrives as a fresh generation right after.
        geminiInterruptAfterInject = true
        log("\(tag): self-induced interrupt (screenshot) — keeping turn alive")
      } else {
        // Real barge-in: drop the pending reply so its trailing audio + bookkeeping
        // turnComplete are ignored; the new turn (already started via activityStart)
        // re-arms on commit.
        geminiResponsePending = false
        log("\(tag): server confirmed interrupt")
      }
    }
    // NOTE: do NOT finish on generationComplete — Gemini sends it while the spoken audio
    // is still streaming, so finishing there truncates the reply and makes the next turn
    // interrupt the server's still-open turn. We finish on turnComplete (below), which
    // arrives when the audio actually completes.
    if let it = sc["inputTranscription"] as? [String: Any], let t = it["text"] as? String {
      emitTranscript(t, isFinal: false)
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
      // Only finish the turn we're actually awaiting a reply for. A turnComplete that
      // closes an interrupted/abandoned generation (pending=false) is ignored, so it
      // can't prematurely end the live turn — the failure both the reconnect approach
      // and the earlier same-session attempt hit.
      geminiImageInjected = false  // the screenshot-injection turn is over either way
      if geminiInterruptAfterInject {
        // This turnComplete just closes the screenshot-injection interrupt; the model's
        // real answer follows as a fresh generation. Swallow it, keep the turn pending.
        geminiInterruptAfterInject = false
      } else if geminiResponsePending {
        geminiResponsePending = false
        emitText("", isFinal: true)
        finishTurn()
      }
    }
  }

  // MARK: - Send (on q)

  private func send(json: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: json),
      let text = String(data: data, encoding: .utf8)
    else { return }
    if usesRawWS {
      rawWS?.sendText(text)
      return
    }
    task?.send(.string(text)) { [weak self] error in
      if let error { self?.q.async { self?.notifyError(error.localizedDescription) } }
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
      self.receiveLoop()
      self.sendSessionSetup()
    }
  }

  func urlSession(
    _ session: URLSession, webSocketTask: URLSessionWebSocketTask,
    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?
  ) {
    let r = reason.flatMap { String(data: $0, encoding: .utf8) } ?? ""
    q.async { self.notifyError("WebSocket closed (\(closeCode.rawValue)) \(r)") }
  }

  func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    if let error {
      q.async { self.notifyError("WebSocket failed: \(error.localizedDescription)") }
    }
  }
}

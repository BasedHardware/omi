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

final class RealtimeHubSession: NSObject {
  private let provider: RealtimeHubProvider
  private let apiKey: String
  private weak var delegate: RealtimeHubSessionDelegate?

  /// Mic PCM input rate per provider (Gemini 16k native, OpenAI GA needs 24k).
  var requiredInputSampleRate: Int { provider == .openai ? 24000 : 16000 }

  // All socket + state access is serialized here (audio arrives on the capture
  // thread; receives on the URLSession/NW queue). Delegate calls hop to main.
  private let q = DispatchQueue(label: "omi.realtime-hub.session")

  private var task: URLSessionWebSocketTask?
  private lazy var session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
  private var nw: NWConnection?
  private var usesNW: Bool { provider == .gemini }

  private var isOpen = false
  private var terminated = false
  private var pendingAudio: [Data] = []
  private var pendingCommit = false
  /// OpenAI: call_id → function name, captured from response.output_item.added.
  private var openAIFunctionNames: [String: String] = [:]
  /// OpenAI: assistant items already dispatched as tool calls (dedup on response.done).
  private var dispatchedToolItems = Set<String>()

  init(provider: RealtimeHubProvider, apiKey: String, delegate: RealtimeHubSessionDelegate) {
    self.provider = provider
    self.apiKey = apiKey
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
    if usesNW {
      startNW(url: url)
      return
    }
    let t = session.webSocketTask(with: request)
    task = t
    t.resume()
    // Receive + setup begin in didOpenWithProtocol.
  }

  func stop() {
    q.async { [weak self] in
      guard let self else { return }
      self.task?.cancel(with: .goingAway, reason: nil)
      self.task = nil
      self.nw?.cancel()
      self.nw = nil
      self.isOpen = false
      self.pendingAudio.removeAll()
      self.pendingCommit = false
      self.openAIFunctionNames.removeAll()
      self.dispatchedToolItems.removeAll()
    }
  }

  private func notifyError(_ message: String) {
    guard !terminated else { return }
    terminated = true
    let d = delegate
    Task { @MainActor in d?.hubDidError(message) }
  }

  // MARK: Public stream API

  /// Feed mic PCM16 mono at `requiredInputSampleRate` (caller resamples).
  func sendAudio(_ pcm: Data) {
    q.async { [weak self] in
      guard let self else { return }
      guard self.isOpen else { self.pendingAudio.append(pcm); return }
      let b64 = pcm.base64EncodedString()
      switch self.provider {
      case .openai:
        self.send(json: ["type": "input_audio_buffer.append", "audio": b64])
      case .gemini:
        self.send(json: [
          "realtimeInput": ["audio": ["data": b64, "mimeType": "audio/pcm;rate=16000"]]
        ])
      }
    }
  }

  /// End the user's PTT turn and ask the model to respond.
  func commitInputTurn() {
    q.async { [weak self] in
      guard let self else { return }
      guard self.isOpen else { self.pendingCommit = true; return }
      switch self.provider {
      case .openai:
        self.send(json: ["type": "input_audio_buffer.commit"])
        self.requestResponse(audio: true)
      case .gemini:
        self.send(json: ["realtimeInput": ["activityEnd": [:]]])
      // Gemini auto-responds at activityEnd; no explicit response request.
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
        self.send(json: [
          "clientContent": [
            "turns": [["role": "user", "parts": [["inlineData": ["mimeType": "image/png", "data": b64]]]]],
            "turnComplete": false,
          ]
        ])
      }
    }
  }

  // OpenAI: ask for a response with the given modality (audio for spoken turns).
  private func requestResponse(audio: Bool) {
    guard provider == .openai else { return }
    send(json: ["type": "response.create", "response": ["output_modalities": [audio ? "audio" : "text"]]])
  }

  // MARK: - Request / setup

  private func makeRequest() -> URLRequest? {
    switch provider {
    case .openai:
      guard let url = URL(string: "wss://api.openai.com/v1/realtime?model=\(provider.modelID)")
      else { return nil }
      var r = URLRequest(url: url)
      // GA: Bearer only, no OpenAI-Beta header.
      r.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
      return r
    case .gemini:
      // Key travels in the query string for the BidiGenerateContent endpoint.
      let base =
        "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
      guard var comps = URLComponents(string: base) else { return nil }
      comps.queryItems = [URLQueryItem(name: "key", value: apiKey)]
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
      send(json: [
        "setup": [
          "model": "models/\(provider.modelID)",
          "generationConfig": ["responseModalities": ["TEXT"]],
          "systemInstruction": ["parts": [["text": RealtimeHubTools.systemInstruction]]],
          "tools": [["functionDeclarations": RealtimeHubTools.geminiFunctionDeclarations]],
          "inputAudioTranscription": [:],
          "realtimeInputConfig": ["automaticActivityDetection": ["disabled": true]],
        ]
      ])
    }
  }

  private func markReady() {
    guard !isOpen else { return }
    isOpen = true
    log("RealtimeHub: \(provider.displayName) ready")
    if provider == .gemini {
      send(json: ["realtimeInput": ["activityStart": [:]]])
    }
    for chunk in pendingAudio { rawSendAudio(chunk) }
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
      }
    }
    let d = delegate
    Task { @MainActor in d?.hubDidConnect() }
  }

  // Send buffered audio after open (already on q).
  private func rawSendAudio(_ pcm: Data) {
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
    let d = delegate
    Task { @MainActor in
      d?.hubDidRequestTool(name: name, callId: callId, argumentsJSON: argumentsJSON)
    }
  }

  private func finishTurn() {
    let d = delegate
    Task { @MainActor in d?.hubDidFinishTurn() }
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
      if let t = e["transcript"] as? String { emitTranscript(t, isFinal: true) }
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
      let msg = (e["error"] as? [String: Any])?["message"] as? String ?? "OpenAI realtime error"
      notifyError(msg)
    default:
      break
    }
  }

  private func handleOpenAIResponseDone(_ e: [String: Any]) {
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
    if let toolCall = e["toolCall"] as? [String: Any],
      let calls = toolCall["functionCalls"] as? [[String: Any]]
    {
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
    if let it = sc["inputTranscription"] as? [String: Any], let t = it["text"] as? String {
      emitTranscript(t, isFinal: false)
    }
    if let parts = (sc["modelTurn"] as? [String: Any])?["parts"] as? [[String: Any]] {
      for p in parts {
        if let t = p["text"] as? String { emitText(t, isFinal: false) }
      }
    }
    if (sc["turnComplete"] as? Bool) == true {
      emitText("", isFinal: true)
      finishTurn()
    }
  }

  // MARK: - Network.framework transport (Gemini, ALPN pinned to http/1.1)

  private func startNW(url: URL) {
    let wsOpts = NWProtocolWebSocket.Options()
    wsOpts.autoReplyPing = true
    let tls = NWProtocolTLS.Options()
    // Pin ALPN to http/1.1 so the server does not upgrade the WebSocket to HTTP/2
    // (which silently resets Apple's WS stacks — the reason the legacy path used a relay).
    sec_protocol_options_add_tls_application_protocol(tls.securityProtocolOptions, "http/1.1")
    let params = NWParameters(tls: tls)
    params.defaultProtocolStack.applicationProtocols.insert(wsOpts, at: 0)
    let conn = NWConnection(to: .url(url), using: params)
    nw = conn
    conn.stateUpdateHandler = { [weak self] state in
      guard let self else { return }
      switch state {
      case .ready:
        log("RealtimeHub: NW WS ready (Gemini)")
        self.q.async {
          self.receiveNW()
          self.sendSessionSetup()
        }
      case .failed(let err):
        self.q.async { self.notifyError("NW failed: \(err)") }
      case .waiting(let err):
        log("RealtimeHub: NW waiting: \(err)")
      default:
        break
      }
    }
    conn.start(queue: q)
  }

  private func receiveNW() {
    nw?.receiveMessage { [weak self] data, _, _, error in
      guard let self else { return }
      if let error {
        self.q.async { self.notifyError("NW receive: \(error)") }
        return
      }
      if let data { self.q.async { self.handleMessage(data) } }
      if self.nw?.state == .ready { self.receiveNW() }
    }
  }

  private func sendNW(_ text: String) {
    guard let conn = nw else { return }
    let meta = NWProtocolWebSocket.Metadata(opcode: .text)
    let ctx = NWConnection.ContentContext(identifier: "send", metadata: [meta])
    conn.send(
      content: Data(text.utf8), contentContext: ctx, isComplete: true,
      completion: .contentProcessed { [weak self] error in
        if let error { self?.q.async { self?.notifyError("NW send: \(error)") } }
      })
  }

  // MARK: - Send (on q)

  private func send(json: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: json),
      let text = String(data: data, encoding: .utf8)
    else { return }
    if usesNW {
      sendNW(text)
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

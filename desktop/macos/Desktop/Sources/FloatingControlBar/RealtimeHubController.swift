import AVFoundation
import CoreGraphics
import Foundation

// MARK: - Realtime Hub Controller (Phase 1)
//
// Owns one persistent, warm RealtimeHubSession and makes the realtime model the
// single tool-dispatching hub for the voice path. It:
//   • keeps the WS warm between PTT turns (no reopen per press),
//   • feeds mic PCM in and plays the model's spoken reply out
//     (OpenAI native audio → StreamingPCMPlayer; Gemini text → AVSpeechSynthesizer),
//   • executes the model's tool calls against EXISTING app code / endpoints:
//       ask_higher_model → POST /v2/chat/completions (Claude, prompt-cached)
//       spawn_agent      → AgentPillsManager.spawnFromUserQuery (AgentBridge, non-blocking)
//       screenshot       → ScreenCaptureManager (+ inject into the session)
//       point_click      → local CGEvent click
//
// This BYPASSES the Haiku classify() router — routing is the model's tool choice.

@MainActor
final class RealtimeHubController: NSObject, RealtimeHubSessionDelegate {
  static let shared = RealtimeHubController()

  private weak var barState: FloatingControlBarState?
  private var session: RealtimeHubSession?
  private var sessionProvider: RealtimeHubProvider?
  private var pcmPlayer: StreamingPCMPlayer?
  private let speech = AVSpeechSynthesizer()

  // Per-turn state.
  private var turnTranscript = ""
  private var assistantText = ""
  private var speculativeWarmDone = false
  private var speculativeScreenshot: Data?

  /// Held warm so spawn_agent's pi-mono bridge boot is off the hot path. The pill
  /// spawn creates its own provider; warming this one primes node/auth caches.
  private var warmProvider: ChatProvider?

  private override init() { super.init() }

  /// True when the hub should drive PTT (enabled + a usable BYOK key for the
  /// selected provider). Read by PushToTalkManager at PTT start.
  var isActive: Bool { RealtimeHubSettings.shared.isActive }

  func setup(barState: FloatingControlBarState) {
    self.barState = barState
    NotificationCenter.default.addObserver(
      self, selector: #selector(settingsChanged),
      name: .realtimeHubSettingsDidChange, object: nil)
  }

  @objc private func settingsChanged() {
    // Provider/enabled changed — drop the old socket so the next turn reconnects
    // with the new provider/key (the hub reads provider at connect, per spec).
    teardownSession()
    if isActive { ensureWarm() }
  }

  // MARK: - Warm session lifecycle (kept open between turns)

  /// Open the WS now if it isn't already (no-op if not active or already warm).
  func ensureWarm() {
    guard isActive else { return }
    let provider = RealtimeHubSettings.shared.provider
    if session != nil, sessionProvider == provider { return }
    if session != nil { teardownSession() }

    guard let key = APIKeyService.byokKey(provider.byokProvider) else {
      log(
        "⚠️ RealtimeHub: no BYOK \(provider.byokProvider.displayName) key set — realtime hub "
          + "cannot connect client-direct (Phase 1 is dev/BYOK only). Falling back to the cascade.")
      return
    }
    let s = RealtimeHubSession(provider: provider, apiKey: key, delegate: self)
    session = s
    sessionProvider = provider
    if provider == .openai, pcmPlayer == nil { pcmPlayer = StreamingPCMPlayer(sampleRate: 24000) }
    s.start()
    log("RealtimeHub: warming \(provider.displayName) session (client-direct, BYOK)")
  }

  private func teardownSession() {
    session?.stop()
    session = nil
    sessionProvider = nil
  }

  // MARK: - PTT integration

  /// PTT-down: make sure the socket is warm and reset per-turn state. Captures a
  /// speculative screenshot in the background (non-blocking) for the screenshot tool.
  func beginTurn() {
    ensureWarm()
    turnTranscript = ""
    assistantText = ""
    speculativeWarmDone = false
    speculativeScreenshot = nil
    pcmPlayer?.stop()  // interrupt any prior reply
    if speech.isSpeaking { speech.stopSpeaking(at: .immediate) }
    // Speculative, parallel, non-blocking screen grab (item 6a).
    Task.detached(priority: .utility) {
      let shot = ScreenCaptureManager.captureScreenData()
      await MainActor.run { self.speculativeScreenshot = shot }
    }
  }

  /// Mic chunk (16 kHz PCM16 mono) → resample to the provider's rate → session.
  func feedAudio(_ pcm16k: Data) {
    guard let s = session else { return }
    let rate = s.requiredInputSampleRate
    let pcm = rate == 16000 ? pcm16k : PushToTalkManager.resamplePCM16(pcm16k, from: 16000, to: rate)
    s.sendAudio(pcm)
  }

  /// PTT-up: end the turn; the model now responds (and may call tools).
  func commitTurn() {
    session?.commitInputTurn()
  }

  /// Abandon the turn without committing (cancel / silent). Keep the socket warm.
  func cancelTurn() {
    // Nothing to commit; warm session stays open for the next turn.
    turnTranscript = ""
    assistantText = ""
  }

  // MARK: - RealtimeHubSessionDelegate

  func hubDidConnect() {
    log("RealtimeHub: connected (\(sessionProvider?.displayName ?? "?"))")
  }

  func hubDidReceiveInputTranscript(_ text: String, isFinal: Bool) {
    if isFinal {
      if !text.isEmpty { turnTranscript = text }
    } else {
      turnTranscript += text
    }
    barState?.voiceTranscript = turnTranscript
    // Speculatively warm the agent bridge while the user is still talking, if the
    // request looks action-y (inverse of the chat fast-path heuristic). Keeps the
    // existing conditional-attach heuristic intact.
    if !speculativeWarmDone, !turnTranscript.isEmpty,
      !FloatingControlBarManager.routerCanSkipToChat(turnTranscript)
    {
      speculativeWarmDone = true
      speculativelyWarmAgent()
    }
  }

  func hubDidReceiveAudio(_ pcm24k: Data) {
    pcmPlayer?.enqueue(pcm24k)  // OpenAI native spoken audio
  }

  func hubDidEmitText(_ text: String, isFinal: Bool) {
    if !text.isEmpty { assistantText += text }
    if isFinal {
      let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      // Gemini is TEXT-only — speak its reply locally via macOS AVSpeechSynthesizer.
      // OpenAI already spoke via native audio (this text is just the transcript).
      if sessionProvider == .gemini, !reply.isEmpty { speak(reply) }
      if !reply.isEmpty { log("RealtimeHub: reply — \(reply.prefix(160))") }
    }
  }

  func hubDidRequestTool(name: String, callId: String, argumentsJSON: String) {
    log("RealtimeHub: tool_call \(name) \(argumentsJSON)")
    let arguments =
      (try? JSONSerialization.jsonObject(with: Data(argumentsJSON.utf8)) as? [String: Any]) ?? [:]
    guard let tool = HubTool(rawValue: name) else {
      session?.sendToolResult(callId: callId, name: name, output: "Unknown tool.")
      return
    }
    switch tool {
    case .askHigherModel:
      let query = (arguments["query"] as? String) ?? turnTranscript
      Task { [weak self] in
        guard let self else { return }
        let answer = await self.escalateToHigherModel(query)
        self.session?.sendToolResult(callId: callId, name: name, output: answer)
      }
    case .spawnAgent:
      let brief = (arguments["brief"] as? String) ?? turnTranscript
      let model = ShortcutSettings.shared.selectedModel.isEmpty
        ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
      // Non-blocking: spawn renders its own pill ("text bubble") and runs on its
      // own ChatProvider/AgentBridge. We don't await it on the voice loop.
      let pill = AgentPillsManager.shared.spawnFromUserQuery(brief, model: model, fromVoice: true)
      session?.sendToolResult(
        callId: callId, name: name,
        output: "Started a background agent: \"\(pill.title)\". It's working on it now.")
    case .screenshot:
      let shot = speculativeScreenshot ?? ScreenCaptureManager.captureScreenData()
      if let shot { session?.injectImage(shot) }
      session?.sendToolResult(
        callId: callId, name: name,
        output: shot == nil ? "Could not capture the screen." : "Screen captured.")
    case .pointClick:
      let x = (arguments["x"] as? Double) ?? (arguments["x"] as? NSNumber)?.doubleValue ?? 0
      let y = (arguments["y"] as? Double) ?? (arguments["y"] as? NSNumber)?.doubleValue ?? 0
      let ok = Self.click(at: CGPoint(x: x, y: y))
      session?.sendToolResult(
        callId: callId, name: name,
        output: ok ? "Clicked at \(Int(x)), \(Int(y))." : "Could not click.")
    }
  }

  func hubDidFinishTurn() {
    exitVoiceUI()
  }

  func hubDidError(_ message: String) {
    logError("RealtimeHub: session error — \(message)")
    exitVoiceUI()
    // Drop the socket so the next PTT reconnects cleanly; legacy cascade still
    // works as the broader fallback (hub is gated/optional).
    teardownSession()
  }

  /// Return the floating bar from its PTT voice state to compact after a hub turn.
  private func exitVoiceUI() {
    guard let barState else { return }
    barState.voiceTranscript = ""
    barState.isVoiceListening = false
    barState.isVoiceLocked = false
    barState.isVoiceFollowUp = false
    FloatingControlBarManager.shared.resizeForPTT(expanded: false)
  }

  // MARK: - Tools

  /// ask_higher_model — reuse the EXISTING prompt-cached /v2/chat/completions
  /// (no new backend route). Returns the assistant text for the model to speak.
  private func escalateToHigherModel(_ query: String) async -> String {
    let baseURL = await APIClient.shared.rustBackendURL
    guard !baseURL.isEmpty else { return "I couldn't reach the model right now." }
    let normalized = baseURL.hasSuffix("/") ? baseURL : baseURL + "/"
    guard let url = URL(string: normalized + "v2/chat/completions") else {
      return "I couldn't reach the model right now."
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = 30
    do {
      let headers = try await APIClient.shared.buildHeaders(requireAuth: true)
      for (k, v) in headers { request.setValue(v, forHTTPHeaderField: k) }
    } catch {
      return "I couldn't authenticate to the model."
    }
    let body: [String: Any] = [
      "model": "claude-sonnet-4-6",
      "max_tokens": 1024,
      "messages": [
        [
          "role": "user",
          "content":
            "Answer concisely for a spoken reply (a few sentences max):\n\n\(query)",
        ]
      ],
      "stream": false,
    ]
    do {
      request.httpBody = try JSONSerialization.data(withJSONObject: body)
      let (data, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
        let code = (response as? HTTPURLResponse)?.statusCode ?? -1
        log("RealtimeHub: ask_higher_model HTTP \(code)")
        return "The model is unavailable right now."
      }
      guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
        let choices = json["choices"] as? [[String: Any]],
        let message = choices.first?["message"] as? [String: Any],
        let text = message["content"] as? String
      else {
        return "I didn't get a usable answer."
      }
      return text.trimmingCharacters(in: .whitespacesAndNewlines)
    } catch {
      log("RealtimeHub: ask_higher_model failed — \(error.localizedDescription)")
      return "I ran into an error reaching the model."
    }
  }

  private func speculativelyWarmAgent() {
    if warmProvider == nil { warmProvider = ChatProvider() }
    let provider = warmProvider
    Task { await provider?.warmupBridge() }
    log("RealtimeHub: speculatively warming agent bridge (action-y intent)")
  }

  private func speak(_ text: String) {
    let utterance = AVSpeechUtterance(string: text)
    utterance.voice =
      AVSpeechSynthesisVoice(language: AVSpeechSynthesisVoice.currentLanguageCode())
      ?? AVSpeechSynthesisVoice(language: "en-US")
    speech.speak(utterance)
  }

  /// Local synthetic mouse click (point_click tool).
  @discardableResult
  static func click(at point: CGPoint) -> Bool {
    guard let down = CGEvent(
      mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point,
      mouseButton: .left),
      let up = CGEvent(
        mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point,
        mouseButton: .left)
    else { return false }
    down.post(tap: .cghidEventTap)
    up.post(tap: .cghidEventTap)
    return true
  }
}

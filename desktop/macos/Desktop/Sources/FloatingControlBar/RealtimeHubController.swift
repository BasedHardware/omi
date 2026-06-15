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
  private var audioReceivedThisTurn = false
  /// When the last PTT turn started — used to keep the socket warm via auto-reconnect
  /// only while the user is actively using it (Gemini idle-closes the WS ~2.5 min).
  private var lastTurnAt: Date?
  private var reconnectPending = false
  /// True between commit and turn-done — used to detect barge-in (a new PTT while
  /// the previous reply is still in flight).
  private var responding = false
  /// After an INTENTIONAL teardown+reconnect (barge-in/cancel), swallow the old
  /// socket's death-rattle error briefly so it doesn't tear down the fresh session.
  private var ignoreErrorsUntil: Date?

  /// Held warm so spawn_agent's pi-mono bridge boot is off the hot path. The pill
  /// spawn creates its own provider; warming this one primes node/auth caches.
  private var warmProvider: ChatProvider?

  private override init() { super.init() }

  /// True when the hub should drive PTT (enabled + a usable BYOK key for the
  /// selected provider). Read by PushToTalkManager at PTT start.
  var isActive: Bool { RealtimeHubSettings.shared.isActive }

  func setup(barState: FloatingControlBarState) {
    self.barState = barState
    // Register the observer exactly once — duplicate registrations (re-entrant
    // setup) fired settingsChanged N times, each tearing down + recreating the
    // socket, which orphaned a connecting session (Gemini 1001/1008 closes).
    NotificationCenter.default.removeObserver(
      self, name: .realtimeHubSettingsDidChange, object: nil)
    NotificationCenter.default.addObserver(
      self, selector: #selector(settingsChanged),
      name: .realtimeHubSettingsDidChange, object: nil)
    // Expose the headless E2E action (omi-ctl action hub_test_turn pcm=… provider=…).
    RealtimeHubTestHarness.registerAutomationAction()
  }

  @objc private func settingsChanged() {
    // Only reconnect if the effective provider actually changed (or we're now
    // off) — avoids redundant teardown/recreate races on unrelated notifications.
    if !isActive { teardownSession(); return }
    if session != nil, sessionProvider == RealtimeHubSettings.shared.provider { return }
    teardownSession()
    ensureWarm()
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
    // Both providers now stream native spoken audio (24k PCM): OpenAI gpt-realtime,
    // Gemini native-audio Live. The half-cascade TEXT→AVSpeech plan is infeasible
    // (those models were deprecated), so AVSpeech is only a no-audio fallback.
    if pcmPlayer == nil { pcmPlayer = StreamingPCMPlayer(sampleRate: 24000) }
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
    // Barge-in: was a reply from the previous turn still in flight when the user
    // started talking again?
    let bargeIn = responding
    responding = false
    turnTranscript = ""
    assistantText = ""
    speculativeWarmDone = false
    speculativeScreenshot = nil
    audioReceivedThisTurn = false
    lastTurnAt = Date()
    pcmPlayer?.stop()  // stop any prior reply locally
    if speech.isSpeaking { speech.stopSpeaking(at: .immediate) }
    if bargeIn, sessionProvider == .gemini {
      // Gemini keeps streaming its reply even after activityEnd, so the only clean
      // interrupt is to drop the socket — that stops the in-flight audio. The new
      // turn proceeds on a fresh socket (audio buffers until it reconnects).
      log("RealtimeHub[gemini]: barge-in — reconnecting to stop in-flight reply")
      ignoreErrorsUntil = Date().addingTimeInterval(0.6)
      teardownSession()
    } else if bargeIn {
      session?.cancelActiveResponse()  // OpenAI: response.cancel + clear input
    }
    ensureWarm()  // (re)connect if needed
    // Open a fresh speech window for this turn (Gemini manual-VAD needs it EVERY
    // turn on a warm session; OpenAI no-op).
    session?.beginInputTurn()
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
    responding = true
    session?.commitInputTurn()
  }

  /// Abandon the turn without committing (silent tap / cancel). Must leave NO open
  /// turn behind, or the model answers the non-speech later.
  func cancelTurn() {
    responding = false
    turnTranscript = ""
    assistantText = ""
    if sessionProvider == .gemini {
      // The speech window was already opened (activityStart on beginTurn); the only
      // way to drop it without the model answering the silence is a fresh socket.
      ignoreErrorsUntil = Date().addingTimeInterval(0.6)
      teardownSession()
      ensureWarm()
    } else {
      session?.cancelActiveResponse()  // OpenAI: clear the uncommitted input buffer
    }
    exitVoiceUI()
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
    audioReceivedThisTurn = true
    pcmPlayer?.enqueue(pcm24k)  // native spoken audio (OpenAI + Gemini)
  }

  func hubDidEmitText(_ text: String, isFinal: Bool) {
    if !text.isEmpty { assistantText += text }
    if isFinal {
      let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      // Fallback only: if the model produced text but no native audio this turn,
      // speak it locally via macOS AVSpeechSynthesizer. Normally both providers
      // stream spoken audio (played by StreamingPCMPlayer) so this stays unused.
      if !audioReceivedThisTurn, !reply.isEmpty { speak(reply) }
      if !reply.isEmpty { log("RealtimeHub: reply — \(reply.prefix(160))") }
    }
  }

  func hubDidRequestTool(name: String, callId: String, argumentsJSON: String) {
    let providerTag = sessionProvider == .gemini ? "gemini" : "openai"
    let arguments =
      (try? JSONSerialization.jsonObject(with: Data(argumentsJSON.utf8)) as? [String: Any]) ?? [:]
    guard let tool = HubTool(rawValue: name) else {
      log("RealtimeHub[\(providerTag)]: tool_call UNKNOWN \(name) — rejecting")
      session?.sendToolResult(callId: callId, name: name, output: "Unknown tool.")
      return
    }
    switch tool {
    case .askHigherModel:
      let query = (arguments["query"] as? String) ?? turnTranscript
      log("RealtimeHub[\(providerTag)]: tool ask_higher_model → POST /v2/chat/completions (claude-sonnet-4-6) query=\"\(query.prefix(80))\"")
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
      log("RealtimeHub[\(providerTag)]: tool spawn_agent → AgentBridge pill=\"\(pill.title)\" model=\(model)")
      session?.sendToolResult(
        callId: callId, name: name,
        output: "Started a background agent: \"\(pill.title)\". It's working on it now.")
    case .screenshot:
      let shot = speculativeScreenshot ?? ScreenCaptureManager.captureScreenData()
      if let shot { session?.injectImage(shot) }
      log("RealtimeHub[\(providerTag)]: tool screenshot → local capture (\(shot?.count ?? 0) bytes)")
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
    responding = false
    let providerTag = sessionProvider == .gemini ? "gemini" : "openai"
    let heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    log("RealtimeHub[\(providerTag)]: turn done — heard=\"\(heard.prefix(80))\" audio=\(audioReceivedThisTurn)")
    exitVoiceUI()
  }

  func hubDidError(_ message: String) {
    // Swallow the death-rattle from a socket we just intentionally dropped
    // (barge-in/cancel reconnect) so it can't tear down the fresh session.
    if let until = ignoreErrorsUntil, Date() < until {
      log("RealtimeHub: ignoring expected post-reconnect error — \(message)")
      return
    }
    responding = false
    logError("RealtimeHub: session error — \(message)")
    exitVoiceUI()
    // Drop the socket; the next PTT reconnects lazily anyway.
    teardownSession()
    // If the user has been active recently, the provider likely idle-closed the
    // warm socket (Gemini does this ~2.5 min idle) — re-warm a fresh one so the
    // next turn is instant. Bounded to recent activity so an idle, walked-away
    // session doesn't reconnect-churn forever.
    let recentlyActive = lastTurnAt.map { Date().timeIntervalSince($0) < 180 } ?? false
    if isActive, recentlyActive, !reconnectPending {
      reconnectPending = true
      DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
        guard let self else { return }
        self.reconnectPending = false
        if self.isActive, self.session == nil { self.ensureWarm() }
      }
    }
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
    let t0 = Date()
    do {
      request.httpBody = try JSONSerialization.data(withJSONObject: body)
      let (data, response) = try await URLSession.shared.data(for: request)
      let ms = Int(Date().timeIntervalSince(t0) * 1000)
      guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
        let code = (response as? HTTPURLResponse)?.statusCode ?? -1
        log("RealtimeHub: ask_higher_model ← claude-sonnet-4-6 HTTP \(code) in \(ms)ms (FAILED)")
        return "The model is unavailable right now."
      }
      guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
        let choices = json["choices"] as? [[String: Any]],
        let message = choices.first?["message"] as? [String: Any],
        let text = message["content"] as? String
      else {
        log("RealtimeHub: ask_higher_model ← unexpected response shape in \(ms)ms")
        return "I didn't get a usable answer."
      }
      let answer = text.trimmingCharacters(in: .whitespacesAndNewlines)
      log("RealtimeHub: ask_higher_model ← claude-sonnet-4-6 OK in \(ms)ms (\(answer.count) chars)")
      return answer
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

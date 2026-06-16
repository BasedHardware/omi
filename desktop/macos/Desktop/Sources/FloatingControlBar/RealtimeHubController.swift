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
  /// When the current warm socket last connected — used to tell a normal idle-close
  /// (survived a while → keep re-warming) from a fast config/auth failure (don't loop).
  private var lastWarmAt: Date?
  /// Consecutive failed (re)connects with no surviving session — caps churn on a hard
  /// failure. Reset when a socket survives past the idle window or a turn completes.
  private var hubReconnectStrikes = 0
  /// True between commit and turn-done — used to detect barge-in (a new PTT while
  /// the previous reply is still in flight).
  private var responding = false

  /// Log tag for the currently-connected provider.
  private var providerTag: String { sessionProvider == .gemini ? "gemini" : "openai" }

  /// Held warm so spawn_agent's pi-mono bridge boot is off the hot path. The pill
  /// spawn creates its own provider; warming this one primes node/auth caches.
  private var warmProvider: ChatProvider?

  private override init() { super.init() }

  /// In-flight ephemeral mint guard (managed users).
  private var minting = false

  /// True when the hub should drive this PTT turn. Read by PushToTalkManager at PTT
  /// start. BYOK users are ready immediately (own key); managed users are ready only
  /// once a warm session exists (token minted + connecting) — otherwise PTT falls
  /// back to the legacy cascade for that turn.
  var isActive: Bool {
    guard RealtimeHubSettings.shared.isEnabled else { return false }
    let provider = RealtimeHubSettings.shared.provider
    if APIKeyService.byokKey(provider.byokProvider) != nil { return true }
    return session != nil && sessionProvider == provider
  }

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
    // Only reconnect if enabled and the provider actually changed — avoids
    // redundant teardown/recreate races on unrelated notifications.
    if !RealtimeHubSettings.shared.isEnabled { teardownSession(); return }
    if session != nil, sessionProvider == RealtimeHubSettings.shared.provider { return }
    teardownSession()
    ensureWarm()
  }

  // MARK: - Warm session lifecycle (kept open between turns)

  /// Open the WS now if it isn't already (no-op if disabled or already warm).
  /// BYOK → connect client-direct with the user's key (Phase 1). Otherwise, if
  /// signed in → mint a server-side ephemeral token (Phase 2) and connect with it.
  func ensureWarm() {
    guard RealtimeHubSettings.shared.isEnabled else { return }
    let provider = RealtimeHubSettings.shared.provider
    if session != nil, sessionProvider == provider { return }
    if session != nil { teardownSession() }

    if let key = APIKeyService.byokKey(provider.byokProvider) {
      startSession(provider: provider, auth: .byokKey(key))
    } else if AuthService.shared.isSignedIn {
      mintAndConnect(provider: provider)
    } else {
      log("RealtimeHub: enabled but no BYOK key and not signed in — hub unavailable (cascade).")
    }
  }

  /// Managed users: fetch a short-lived ephemeral token from the backend (gated by
  /// auth + paywall there), then connect. On any failure (incl. 402 not-entitled),
  /// leave the session nil so PTT falls back to the cascade.
  private func mintAndConnect(provider: RealtimeHubProvider) {
    guard !minting else { return }
    minting = true
    let providerParam = provider == .openai ? "openai" : "gemini"
    log("RealtimeHub: minting ephemeral \(provider.displayName) token (managed)")
    Task { [weak self] in
      let token = await APIClient.shared.mintRealtimeToken(provider: providerParam)
      guard let self else { return }
      self.minting = false
      guard let token else {
        log("⚠️ RealtimeHub: ephemeral mint failed / not entitled — staying on cascade")
        return
      }
      // Provider/enable may have changed while minting; only connect if still wanted.
      guard RealtimeHubSettings.shared.isEnabled,
        RealtimeHubSettings.shared.provider == provider, self.session == nil
      else { return }
      self.startSession(provider: provider, auth: .ephemeral(token))
    }
  }

  private func startSession(provider: RealtimeHubProvider, auth: HubAuth) {
    let s = RealtimeHubSession(provider: provider, auth: auth, delegate: self)
    session = s
    sessionProvider = provider
    // Both providers stream native spoken audio (24k PCM) → StreamingPCMPlayer;
    // AVSpeech is only a no-audio fallback.
    if pcmPlayer == nil { pcmPlayer = StreamingPCMPlayer(sampleRate: 24000) }
    s.start()
    log(
      "RealtimeHub: warming \(provider.displayName) session "
        + "(\(auth.isEphemeral ? "ephemeral/managed" : "client-direct/BYOK"))")
  }

  private func teardownSession() {
    // Detach first so a socket we're dropping can't deliver a late error/close to us
    // and tear down the fresh session we're about to create.
    session?.detach()
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
    if bargeIn {
      // Interrupt the in-flight reply IN-SESSION (no teardown — the warm socket and
      // its conversation context survive). OpenAI: response.cancel + clear input.
      // Gemini: the fresh activityStart sent by beginInputTurn(interrupting:) cancels
      // the current generation server-side; the pending-reply gate drops its tail.
      log("RealtimeHub[\(providerTag)]: barge-in — interrupting in-flight reply (same session)")
      session?.cancelActiveResponse()
    }
    ensureWarm()  // (re)connect only if the socket idle-closed
    // Open a fresh speech window for this turn (Gemini manual-VAD needs it EVERY
    // turn on a warm session; OpenAI no-op).
    session?.beginInputTurn(interrupting: bargeIn)
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
    // Abandon the open turn WITHOUT tearing down the socket: close the speech window
    // and leave the reply gated off so the model never answers the silence. Keeps the
    // warm session (and its context) so the next real turn is instant and in-context.
    session?.abandonInputTurn()
    exitVoiceUI()
  }

  // MARK: - RealtimeHubSessionDelegate

  func hubDidConnect() {
    lastWarmAt = Date()
    log("RealtimeHub: connected (\(sessionProvider?.displayName ?? "?"))")
  }

  func hubDidReceiveInputTranscript(_ text: String, isFinal: Bool) {
    if isFinal {
      if !text.isEmpty { turnTranscript = text }
    } else {
      turnTranscript += text
    }
    // Don't surface Gemini's LIVE partial transcript on the bar: on a quiet/near-silent
    // hold it transcribes background noise into random words (the bar shows "…" on commit
    // instead). turnTranscript is still kept for the agent-warm heuristic and the final.
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
    case .getTasks:
      // Fast LOCAL read — no agent. Fetch today's + overdue tasks and hand them back
      // as text for the model to speak (this is the read path, vs spawn_agent actions).
      Task { @MainActor [weak self] in
        guard let self else { return }
        await TasksStore.shared.loadDashboardTasks()
        let overdue = TasksStore.shared.overdueTasks
        let today = TasksStore.shared.todaysTasks
        func list(_ items: [TaskActionItem]) -> String {
          items.prefix(15).map { "- \($0.description)" }.joined(separator: "\n")
        }
        var out = ""
        if !overdue.isEmpty { out += "Overdue (\(overdue.count)):\n\(list(overdue))\n" }
        if !today.isEmpty { out += "Due today (\(today.count)):\n\(list(today))\n" }
        if out.isEmpty { out = "No tasks overdue or due today." }
        log("RealtimeHub[\(self.providerTag)]: tool get_tasks → \(overdue.count) overdue, \(today.count) today")
        self.session?.sendToolResult(callId: callId, name: name, output: out)
      }
    case .spawnAgent:
      let brief = (arguments["brief"] as? String) ?? turnTranscript
      let model = ShortcutSettings.shared.selectedModel.isEmpty
        ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
      // Non-blocking: spawn renders its own pill ("text bubble") and runs on its
      // own ChatProvider/AgentBridge. We don't await it on the voice loop.
      // fromVoice:false — the hub model speaks its own natural acknowledgment, so the pill
      // must NOT also speak its canned randomAck ("on it") or we double up.
      let pill = AgentPillsManager.shared.spawnFromUserQuery(brief, model: model, fromVoice: false)
      log("RealtimeHub[\(providerTag)]: tool spawn_agent → AgentBridge pill=\"\(pill.title)\" model=\(model)")
      // Terse directive (not speakable content): the model already said its one-line ack
      // BEFORE calling, so it should NOT generate a slow second utterance after this.
      session?.sendToolResult(
        callId: callId, name: name,
        output: "Agent started. Acknowledged before the call — do not say anything else.")
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
    hubReconnectStrikes = 0  // a completed turn proves the hub works — reset the budget
    let heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    log("RealtimeHub[\(providerTag)]: turn done — heard=\"\(heard.prefix(80))\" audio=\(audioReceivedThisTurn)")
    exitVoiceUI()
  }

  func hubDidError(_ message: String) {
    // A socket we intentionally dropped is detached in teardownSession() before it's
    // released, so its death-rattle never reaches us — only the live session's errors
    // land here.
    responding = false
    logError("RealtimeHub: session error — \(message)")
    exitVoiceUI()
    let aliveFor = lastWarmAt.map { Date().timeIntervalSince($0) } ?? 0
    teardownSession()
    // Re-warm so the NEXT PTT uses the hub, not the STT cascade. Gemini idle-closes
    // the socket (~2.5 min, close 1008) even before the first turn; managed users have
    // no BYOK key, so once `session` is nil `isActive` is false and PTT silently falls
    // back to omni STT. So gate on isEnabled (NOT isActive, which needs a live session).
    // A socket that survived past the idle window was a normal idle-close → reset the
    // strike budget and keep re-warming forever; one that died fast is likely a config/
    // auth failure → let the strikes cap stop the churn.
    if aliveFor > 60 { hubReconnectStrikes = 0 }
    guard RealtimeHubSettings.shared.isEnabled, !reconnectPending, hubReconnectStrikes < 5 else { return }
    hubReconnectStrikes += 1
    reconnectPending = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
      guard let self else { return }
      self.reconnectPending = false
      if RealtimeHubSettings.shared.isEnabled, self.session == nil { self.ensureWarm() }
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

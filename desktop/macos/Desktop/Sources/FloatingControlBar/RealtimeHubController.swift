import AppKit
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


/// Safe, non-sensitive classification for realtime WebSocket teardown messages.
///
/// Gemini can idle-close warm sessions with WebSocket 1008 after the socket has
/// lived for a while. That path is expected and should re-warm quietly rather
/// than page Sentry as a production error. Fast 1008 closes are different: they
/// usually mean provider policy/auth/config rejection and should still be
/// reported, but with a stable category instead of raw provider text.
enum RealtimeHubCloseCategory: String {
  case expectedIdleTeardown = "expected_idle_teardown"
  case providerAuthFailed = "provider_auth_failed"
  case providerQuotaExceeded = "provider_quota_exceeded"
  case providerPolicyCloseFast = "provider_policy_close_fast"
  case providerTransient = "provider_transient"
}

enum RealtimeHubCloseClassifier {
  static let idleTeardownThreshold: TimeInterval = 60

  static func category(
    message: String,
    aliveFor: TimeInterval,
    hasActiveTurn: Bool = false
  ) -> RealtimeHubCloseCategory? {
    let lower = message.lowercased()
    guard lower.contains("websocket closed (1008)") else { return nil }
    if CredentialHealthManager.classifyProviderClose(
      message: message,
      provider: .openai) == .providerQuotaExceeded(provider: .openai)
    {
      return .providerQuotaExceeded
    }
    if CredentialHealthManager.classifyProviderClose(
      message: message,
      provider: .openai) == .providerAuthFailed(provider: .openai, mode: .byok)
    {
      return .providerAuthFailed
    }
    if !hasActiveTurn && aliveFor >= idleTeardownThreshold { return .expectedIdleTeardown }
    return .providerPolicyCloseFast
  }

  static func shouldReportToSentry(_ category: RealtimeHubCloseCategory?) -> Bool {
    category != .expectedIdleTeardown
  }
}

/// Keeps the response glow tied to perceived playback instead of raw PCM chunk
/// boundaries. Realtime providers can leave short gaps between streamed audio
/// buffers; clearing the glow on every empty queue makes the notch resize and
/// shimmer restart repeatedly.
final class RealtimeResponseGlowGate {
  private let idleClearDelay: TimeInterval
  private let setActive: (Bool) -> Void
  private var idleClearWorkItem: DispatchWorkItem?
  private(set) var isActive = false

  init(idleClearDelay: TimeInterval = 0.75, setActive: @escaping (Bool) -> Void) {
    self.idleClearDelay = idleClearDelay
    self.setActive = setActive
  }

  func markPlaybackActive() {
    idleClearWorkItem?.cancel()
    idleClearWorkItem = nil
    guard !isActive else { return }
    isActive = true
    setActive(true)
  }

  func scheduleIdleClear() {
    idleClearWorkItem?.cancel()
    let workItem = DispatchWorkItem { [weak self] in
      guard let self else { return }
      self.isActive = false
      self.setActive(false)
      self.idleClearWorkItem = nil
    }
    idleClearWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + idleClearDelay, execute: workItem)
  }

  func clearImmediately() {
    idleClearWorkItem?.cancel()
    idleClearWorkItem = nil
    guard isActive else {
      setActive(false)
      return
    }
    isActive = false
    setActive(false)
  }
}

@MainActor
final class RealtimeHubController: NSObject, RealtimeHubSessionDelegate, AVSpeechSynthesizerDelegate {
  static let shared = RealtimeHubController()

  private weak var barState: FloatingControlBarState?
  private var session: RealtimeHubSession?
  private var sessionProvider: RealtimeHubProvider?
  private var sessionAuth: HubAuth?
  private var pcmPlayer: StreamingPCMPlayer?
  private let speech = AVSpeechSynthesizer()
  private lazy var responseGlowGate = RealtimeResponseGlowGate { [weak self] active in
    self?.barState?.isVoiceResponseActive = active
  }
  private let agentControlService = AgentControlService()

  // Per-turn state.
  private var turnTranscript = ""
  private var assistantText = ""
  private var speculativeWarmDone = false
  private var speculativeScreenshot: Data?
  private var audioReceivedThisTurn = false
  /// Tracks whether local AVSpeechSynthesizer speech is queued or active this
  /// turn. Set synchronously in speak() to avoid the race where exitVoiceUI
  /// checks speech.isSpeaking before the synthesizer has started the queued
  /// utterance (which can clear the response glow mid-utterance). Cleared in
  /// both didFinish and didCancel delegate callbacks so cancellation paths
  /// (system interruption, stopSpeaking) always release the glow.
  private var localSpeechActive = false
  /// `spawn_agent` is a handoff, not a read tool. After the tool result returns,
  /// the realtime model sometimes continues with meta/control text; never speak it.
  private var suppressAssistantOutputForCurrentTurn = false
  /// Guards against recording the same turn to chat history twice (a delegate that
  /// fires turn-done more than once on reconnect/barge-in edges). Reset per turn.
  private var turnRecorded = false
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
  /// After this many consecutive fast failures (e.g. a stale/revoked key failing auth),
  /// the hub stops re-warming so it doesn't hammer a dead endpoint.
  private static let maxReconnectStrikes = 5
  /// True only while a session is connected + authenticated for `sessionProvider`. This is
  /// what gates `isActive`: a PTT turn enters hub mode only when the hub is genuinely
  /// connected right now; otherwise it transparently uses the legacy cascade. Set in
  /// hubDidConnect (fires post-auth, on "ready") and cleared on teardown/error, so a
  /// stale/revoked key — which never connects — never costs the user a turn.
  private var hubConnected = false
  /// True between commit and turn-done — used to detect barge-in (a new PTT while
  /// the previous reply is still in flight).
  private var responding = false
  /// True while native realtime PCM has been scheduled locally but has not drained yet.
  /// Provider turn completion means the server finished sending; the Mac may still be
  /// playing the queued tail, and a new PTT during that tail is still a barge-in.
  private var realtimePlaybackActive = false
  /// Monotonic owner for realtime playback-idle callbacks. The PCM player can
  /// complete older buffers after a stop, rebuild, or newer audio chunk; only the
  /// latest scheduled playback epoch may clear `realtimePlaybackActive`.
  private var realtimePlaybackEpoch = 0

  /// Log tag for the currently-connected provider.
  private var providerTag: String { sessionProvider == .gemini ? "gemini" : "openai" }

  /// Latest local identity card, injected into each new session's system instruction.
  /// Refreshed off the hot path; an empty string just means "no card yet" (graceful).
  private var aboutUserCard: String = ""

  private func refreshAboutUserCard() {
    Task { @MainActor [weak self] in
      self?.aboutUserCard = await AboutUserCard.build()
    }
  }

  /// Held warm so spawn_agent's pi-mono bridge boot is off the hot path. The pill
  /// spawn creates its own provider; warming this one primes node/auth caches.
  private var warmProvider: ChatProvider?

  /// In-flight ephemeral mint guard (managed users).
  private var minting = false
  /// A Gemini active-reply barge-in replaces the whole session. Managed sessions
  /// need a fresh one-use token first, so hold early mic chunks/commit until the
  /// replacement session exists and can use its normal socket-open buffering.
  private var bargeInReplacementInFlight = false
  private var bargeInReplacementPendingTurn = false
  private var bargeInReplacementPendingCommit = false
  private var bargeInReplacementAudioBuffer: [Data] = []

  /// Failover chain: when the Auto-selected (primary) provider can't connect, the hub
  /// tries the OTHER realtime provider before dropping to the legacy Claude cascade.
  /// nil = on the primary; non-nil = the provider we failed over TO.
  private var fallbackProvider: RealtimeHubProvider?

  private override init() {
    super.init()
    speech.delegate = self
  }

  /// The realtime provider to actually connect: the failover pick if we've switched to
  /// it, otherwise the user/Auto-selected one.
  private var effectiveProvider: RealtimeHubProvider {
    fallbackProvider ?? RealtimeHubSettings.shared.provider
  }

  /// Switch to the other realtime provider after the current one fails to connect.
  /// Returns true if a failover was started. Only fires once per chain (primary →
  /// alternate); if the alternate also fails we stop and let PTT use the Claude cascade.
  @discardableResult
  private func failoverToAlternateProvider() -> Bool {
    guard fallbackProvider == nil else { return false }  // already on the alternate → cascade
    let primary = RealtimeHubSettings.shared.provider
    fallbackProvider = primary.alternate
    log("RealtimeHub: \(primary.displayName) unavailable — failing over to \(primary.alternate.displayName)")
    teardownSession()
    ensureWarm()
    return true
  }

  /// True when the hub should drive this PTT turn. Read by PushToTalkManager at PTT
  /// start. The hub is the default voice path (no opt-in toggle).
  var isActive: Bool {
    // Drive a turn only when the hub is actually CONNECTED + authenticated for the
    // selected provider OR the failover provider we switched to. A turn never enters hub
    // mode on a key/token that can't connect (stale/revoked key, failed mint, mid-
    // reconnect, or a just-switched provider): PTT transparently uses the legacy cascade
    // instead, so a broken hub never costs the user a turn. The hub re-warms in the
    // background and flips this true once it connects.
    hubConnected && (sessionProvider == RealtimeHubSettings.shared.provider || sessionProvider == fallbackProvider)
  }

  /// PTT cold-start grace: give an already-warming/reconnecting hub a short chance to
  /// become ready before falling back to the slower transcript cascade.
  func waitUntilActive(timeout: TimeInterval) async -> Bool {
    ensureWarm()
    if isActive { return true }
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
      try? await Task.sleep(nanoseconds: 50_000_000)
      if Task.isCancelled { return false }
      if isActive { return true }
    }
    return isActive
  }

  func setup(barState: FloatingControlBarState) {
    self.barState = barState
    // The hub provider follows the "Voice Model" picker, so re-warm when it changes —
    // observe the live settings notification (posted by the picker, RealtimeOmniSettings
    // setters, and AutoModelSelector). Register exactly once — duplicate registrations
    // (re-entrant setup) fired settingsChanged N times, each tearing down + recreating
    // the socket, which orphaned a connecting session (Gemini 1001/1008 closes).
    NotificationCenter.default.removeObserver(
      self, name: .realtimeOmniSettingsDidChange, object: nil)
    NotificationCenter.default.addObserver(
      self, selector: #selector(settingsChanged),
      name: .realtimeOmniSettingsDidChange, object: nil)
    // After the Mac sleeps, a long-lived WS can come back a "zombie": still open at the
    // socket level (so PTT routes a turn to it), but the server is gone — the turn commits
    // and silently never replies, with no close event to trigger reconnect or fallback. The
    // only reliable recovery today is a manual app restart. Observe system wake and drop +
    // rebuild the session once, so the first PTT after sleep gets a fresh socket. Rare,
    // discrete event (not a timer) → no reconnect churn. Register exactly once.
    NSWorkspace.shared.notificationCenter.removeObserver(
      self, name: NSWorkspace.didWakeNotification, object: nil)
    NSWorkspace.shared.notificationCenter.addObserver(
      self, selector: #selector(systemDidWake),
      name: NSWorkspace.didWakeNotification, object: nil)
    // Expose the headless E2E action (omi-ctl action hub_test_turn pcm=… provider=…).
    RealtimeHubTestHarness.registerAutomationAction()
    refreshAboutUserCard()
  }

  /// System woke from sleep — proactively replace a possibly-stale socket so the first PTT
  /// after sleep doesn't hit a zombie session (commit → no reply → no fallback → hang).
  /// Only acts when idle: a live session exists and we're neither mid-reply nor mid-mint, so
  /// this never interrupts an active turn or races a connect already in flight. teardown
  /// forces session=nil so ensureWarm() rebuilds (it would otherwise treat the stale socket
  /// as already-warm and no-op).
  @objc private func systemDidWake() {
    guard session != nil, !responding, !minting else { return }
    log("RealtimeHub: system woke — re-warming session (dropping possibly-stale socket)")
    teardownSession()
    ensureWarm()
  }

  @objc private func settingsChanged() {
    // A new pick (user or Auto/AutoModelSelector) re-evaluates from the primary, dropping
    // any active failover so the freshly-selected provider is honored.
    fallbackProvider = nil
    // Only reconnect if the provider actually changed — avoids redundant
    // teardown/recreate races on unrelated notifications.
    if session != nil, sessionProvider == RealtimeHubSettings.shared.provider { return }
    teardownSession()
    refreshAboutUserCard()
    ensureWarm()
  }

  // MARK: - Warm session lifecycle (kept open between turns)

  /// Open the WS now if it isn't already (no-op if already warm). BYOK → connect
  /// client-direct with the user's key. Otherwise, if signed in → mint a server-side
  /// ephemeral token and connect with it.
  func ensureWarm() {
    let provider = effectiveProvider
    if session != nil, sessionProvider == provider { return }
    if session != nil { teardownSession() }

    if let key = APIKeyService.byokKey(provider.byokProvider) {
      let fingerprint = APIKeyService.byokFingerprint(key)
      guard CredentialHealthManager.shared.canUseBYOK(provider: provider.byokProvider, fingerprint: fingerprint) else {
        log("RealtimeHub: skipping known-bad \(provider.displayName) BYOK key fingerprint")
        if failoverToAlternateProvider() {
          return
        } else if AuthService.shared.isSignedIn {
          mintAndConnect(provider: provider)
        } else {
          CredentialHealthManager.shared.recordProviderFailure(
            .providerAuthFailed(provider: provider, mode: .byok),
            provider: provider,
            authMode: .byok,
            fingerprint: fingerprint,
            context: "realtime_byok_blocked")
        }
        return
      }
      startSession(provider: provider, auth: .byokKey(key))
    } else if AuthService.shared.isSignedIn {
      mintAndConnect(provider: provider)
    } else {
      log("RealtimeHub: no BYOK key and not signed in — hub unavailable (cascade).")
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
      guard let self else { return }
      let token: String
      do {
        token = try await APIClient.shared.mintRealtimeToken(provider: providerParam)
      } catch let error as CredentialHealthError {
        self.minting = false
        CredentialHealthManager.shared.record(error, context: "realtime_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: error.failureClass.logValue,
          phase: "warm")
        if error.failureClass.isAccountWide {
          log("RealtimeHub: account credential failure during mint — staying on cascade")
        } else if !self.failoverToAlternateProvider() {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      } catch {
        self.minting = false
        let typed = CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)
        CredentialHealthManager.shared.record(typed, context: "realtime_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: "backend_transient",
          phase: "warm")
        if !self.failoverToAlternateProvider() {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      }
      self.minting = false
      // Provider may have changed (picker/failover) while minting; only connect if still wanted.
      guard self.effectiveProvider == provider, self.session == nil
      else { return }
      self.startSession(provider: provider, auth: .ephemeral(token))
    }
  }

  private func startSession(provider: RealtimeHubProvider, auth: HubAuth) {
    let instructions = RealtimeHubTools.systemInstruction(aboutUser: aboutUserCard)
    let s = RealtimeHubSession(provider: provider, auth: auth, instructions: instructions, delegate: self)
    lastWarmAt = nil
    hubConnected = false
    session = s
    sessionProvider = provider
    sessionAuth = auth
    // Both providers stream native spoken audio (24k PCM) → StreamingPCMPlayer;
    // AVSpeech is only a no-audio fallback.
    if pcmPlayer == nil {
      pcmPlayer = makePCMPlayer()
    }
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
    sessionAuth = nil
    hubConnected = false  // no live session → PTT falls back to the cascade until re-warm
    clearBargeInReplacementState()
  }

  private func clearBargeInReplacementState() {
    bargeInReplacementInFlight = false
    bargeInReplacementPendingTurn = false
    bargeInReplacementPendingCommit = false
    bargeInReplacementAudioBuffer.removeAll()
  }

  @discardableResult
  private func restartSessionForBargeIn() -> Bool {
    guard let provider = sessionProvider, let auth = sessionAuth else { return false }
    session?.detach()
    session?.stop()
    session = nil
    sessionProvider = nil
    sessionAuth = nil
    hubConnected = false
    bargeInReplacementInFlight = true
    bargeInReplacementPendingTurn = true
    bargeInReplacementPendingCommit = false
    bargeInReplacementAudioBuffer.removeAll()
    switch auth {
    case .byokKey:
      startReplacementSessionForBargeIn(provider: provider, auth: auth)
    case .ephemeral:
      remintReplacementSessionForBargeIn(provider: provider)
    }
    return true
  }

  private func remintReplacementSessionForBargeIn(provider: RealtimeHubProvider) {
    guard !minting else {
      log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement skipped; token mint already in flight")
      clearBargeInReplacementState()
      return
    }
    minting = true
    let providerParam = provider == .openai ? "openai" : "gemini"
    log("RealtimeHub[\(provider.displayName)]: minting fresh token for barge-in replacement")
    Task { [weak self] in
      guard let self else { return }
      guard self.bargeInReplacementInFlight else {
        self.minting = false
        return
      }
      guard self.effectiveProvider == provider, self.session == nil else {
        self.minting = false
        self.clearBargeInReplacementState()
        self.ensureWarm()
        return
      }
      let token: String
      do {
        token = try await APIClient.shared.mintRealtimeToken(provider: providerParam)
      } catch let error as CredentialHealthError {
        self.minting = false
        CredentialHealthManager.shared.record(error, context: "realtime_barge_in_mint")
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if !error.failureClass.isAccountWide, !self.failoverToAlternateProvider() {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      } catch {
        self.minting = false
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if !self.failoverToAlternateProvider() {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      }
      self.minting = false
      self.startReplacementSessionForBargeIn(provider: provider, auth: .ephemeral(token))
    }
  }

  private func startReplacementSessionForBargeIn(provider: RealtimeHubProvider, auth: HubAuth) {
    startSession(provider: provider, auth: auth)
    bargeInReplacementInFlight = false
    if bargeInReplacementPendingTurn {
      bargeInReplacementPendingTurn = false
      session?.beginInputTurn(interrupting: false)
    }
    if provider == .gemini, let speculativeScreenshot {
      session?.sendVideoFrame(speculativeScreenshot, mime: "image/jpeg")
    }
    flushBargeInReplacementAudioBuffer()
    if bargeInReplacementPendingCommit {
      bargeInReplacementPendingCommit = false
      session?.commitInputTurn()
    }
  }

  private func failBargeInReplacement(provider: RealtimeHubProvider, reason: String) {
    let hadCommittedTurn = bargeInReplacementPendingCommit
    clearBargeInReplacementState()
    guard hadCommittedTurn else { return }
    log("RealtimeHub[\(provider.displayName)]: barge-in replacement failed after commit — \(reason)")
    responding = false
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
    exitVoiceUI(clearResponseGlow: true)
  }

  private func flushBargeInReplacementAudioBuffer() {
    guard let s = session, !bargeInReplacementAudioBuffer.isEmpty else { return }
    let bufferedChunks = bargeInReplacementAudioBuffer
    bargeInReplacementAudioBuffer.removeAll()
    for pcm16k in bufferedChunks {
      sendAudio(pcm16k, to: s)
    }
  }

  private func makePCMPlayer() -> StreamingPCMPlayer {
    let player = StreamingPCMPlayer(sampleRate: 24000)
    player.onPlaybackScheduled = { [weak self] playbackEpoch in
      Task { @MainActor in
        guard let self else { return }
        self.realtimePlaybackActive = true
        self.realtimePlaybackEpoch = playbackEpoch
      }
    }
    player.onPlaybackIdle = { [weak self] playbackEpoch in
      Task { @MainActor in
        guard let self, self.realtimePlaybackEpoch == playbackEpoch else { return }
        self.realtimePlaybackActive = false
        self.clearResponseGlowIfRealtimeAudioIdle()
      }
    }
    return player
  }

  // MARK: - PTT integration

  /// PTT-down: make sure the socket is warm and reset per-turn state. Captures a
  /// speculative screenshot in the background (non-blocking) for the screenshot tool.
  func beginTurn() {
    // Barge-in: was a reply from the previous turn still in flight when the user
    // started talking again?
    let providerResponseInFlight = responding
    let bargeIn = responding || realtimePlaybackActive || localSpeechActive || speech.isSpeaking
    responding = false
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    var replacementSessionOwnsInputTurn = false
    turnTranscript = ""
    assistantText = ""
    speculativeWarmDone = false
    speculativeScreenshot = nil
    audioReceivedThisTurn = false
    suppressAssistantOutputForCurrentTurn = false
    turnRecorded = false
    lastTurnAt = Date()
    if bargeIn {
      pcmPlayer?.stop()  // stop the prior reply locally only for a real barge-in.
    }
    // Stop any queued or active local speech BEFORE resetting the flag, so a
    // barge-in before the synthesizer started playback still cancels the prior
    // turn's reply. Using localSpeechActive (set synchronously in speak) instead
    // of speech.isSpeaking, which is false until playback actually starts.
    if localSpeechActive || speech.isSpeaking {
      speech.stopSpeaking(at: .immediate)
      localSpeechActive = false
    }
    responseGlowGate.clearImmediately()
    if providerResponseInFlight {
      switch session?.bargeInStrategy ?? .inSessionCancel {
      case .inSessionCancel:
        // OpenAI exposes an explicit response.cancel path, so the warm socket and
        // conversation context survive while the next input buffer starts clean.
        log("RealtimeHub[\(providerTag)]: barge-in — interrupting in-flight reply (same session)")
        session?.cancelActiveResponse()
      case .freshSession:
        // Gemini Live has no reliable in-session cancel for a streaming reply. Reusing
        // that socket can leave the next PTT turn queued behind the old generation, so
        // replace the connection and let the fresh session buffer this new turn while it opens.
        if restartSessionForBargeIn() {
          replacementSessionOwnsInputTurn = true
          log("RealtimeHub: barge-in — replacing session for clean next turn")
        } else {
          session?.cancelActiveResponse()
        }
      }
    } else if bargeIn {
      log("RealtimeHub[\(providerTag)]: barge-in — stopping local playback tail")
    }
    ensureWarm()  // (re)connect only if the socket idle-closed
    // Open a fresh speech window for this turn (Gemini manual-VAD needs it EVERY
    // turn on a warm session; OpenAI no-op).
    if !replacementSessionOwnsInputTurn {
      session?.beginInputTurn(interrupting: providerResponseInFlight)
    }
    // Capture the screen at turn START and, for Gemini, send it in-turn right away — early
    // enough that the ~450KB JPEG uploads/decodes during the seconds of speech, so the
    // model can see it when it answers. A frame attached at commit (PTT-up) lands too late:
    // the model starts generating before it decodes and answers blind on the first turn
    // (correct only on the next turn, once the frame is in context). Non-blocking.
    Task.detached(priority: .utility) {
      let jpeg = ScreenCaptureManager.captureScreenJPEG()
      await MainActor.run {
        self.speculativeScreenshot = jpeg
        if self.sessionProvider == .gemini, let jpeg {
          self.session?.sendVideoFrame(jpeg, mime: "image/jpeg")
        }
      }
    }
  }

  /// Mic chunk (16 kHz PCM16 mono) → resample to the provider's rate → session.
  func feedAudio(_ pcm16k: Data) {
    guard let s = session else {
      if bargeInReplacementInFlight {
        bargeInReplacementAudioBuffer.append(pcm16k)
      }
      return
    }
    sendAudio(pcm16k, to: s)
  }

  private func sendAudio(_ pcm16k: Data, to s: RealtimeHubSession) {
    let rate = s.requiredInputSampleRate
    let pcm = rate == 16000 ? pcm16k : PushToTalkManager.resamplePCM16(pcm16k, from: 16000, to: rate)
    s.sendAudio(pcm)
  }

  /// PTT-up: end the turn; the model now responds (and may call tools).
  func commitTurn() {
    responding = true
    // (The screen frame is sent at turn START — see beginTurn — so it has time to
    // upload/decode before the model answers. Nothing to attach here.)
    guard session != nil else {
      if bargeInReplacementInFlight {
        bargeInReplacementPendingCommit = true
      } else {
        responding = false
        exitVoiceUI(clearResponseGlow: true)
      }
      return
    }
    session?.commitInputTurn()
  }

  /// Abandon the turn without committing (silent tap / cancel). Must leave NO open
  /// turn behind, or the model answers the non-speech later.
  func cancelTurn() {
    responding = false
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    turnTranscript = ""
    assistantText = ""
    clearBargeInReplacementState()
    // Abandon the open turn WITHOUT tearing down the socket: close the speech window
    // and leave the reply gated off so the model never answers the silence. Keeps the
    // warm session (and its context) so the next real turn is instant and in-context.
    session?.abandonInputTurn()
    exitVoiceUI(clearResponseGlow: true)
  }

  // MARK: - RealtimeHubSessionDelegate

  private func isCurrentSession(_ source: RealtimeHubSession) -> Bool {
    source === session
  }

  private func sendToolResultIfCurrent(
    source: RealtimeHubSession,
    callId: String,
    name: String,
    output: String
  ) {
    guard isCurrentSession(source) else {
      log("RealtimeHub[\(providerTag)]: dropping stale tool result \(name)")
      return
    }
    source.sendToolResult(callId: callId, name: name, output: output)
  }

  func hubDidConnect(source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    lastWarmAt = Date()
    hubConnected = true  // authenticated + ready — PTT may now route turns to the hub
    log("RealtimeHub: connected (\(sessionProvider?.displayName ?? "?"))")
  }

  func hubDidReceiveInputTranscript(_ text: String, isFinal: Bool, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
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

  func hubDidReceiveAudio(_ pcm24k: Data, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    guard !suppressAssistantOutputForCurrentTurn else { return }
    // If PTT muted music/system output while listening, make sure the model's
    // reply is audible even if capture teardown restore is delayed by hardware.
    SystemAudioMuteController.shared.restore()
    guard let pcmPlayer, pcmPlayer.enqueue(pcm24k) else {
      log("RealtimeHub[\(providerTag)]: native audio chunk could not be scheduled; keeping text fallback armed")
      return
    }
    audioReceivedThisTurn = true
    realtimePlaybackActive = true
    realtimePlaybackEpoch = pcmPlayer.playbackEpoch
    responseGlowGate.markPlaybackActive()
  }

  func hubDidEmitText(_ text: String, isFinal: Bool, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    guard !suppressAssistantOutputForCurrentTurn else { return }
    if !text.isEmpty { assistantText += text }
    if isFinal {
      let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      // Fallback only: if the model produced text but no native audio this turn,
      // speak it locally via macOS AVSpeechSynthesizer. Normally both providers
      // stream spoken audio (played by StreamingPCMPlayer) so this stays unused.
      if !audioReceivedThisTurn, !reply.isEmpty {
        responseGlowGate.markPlaybackActive()
        speak(reply)
      }
      if !reply.isEmpty { log("RealtimeHub: reply — \(reply.prefix(160))") }
    }
  }

  /// Run an async tool `body`, then speak its result: on throw → `errorText`, on an
  /// empty/whitespace result → `emptyText`. Shared by the data read/write tool cases so the
  /// Task / do-catch / blank-check / log / sendToolResult tail lives in exactly one place.
  private func runToolAndSpeak(
    source: RealtimeHubSession,
    callId: String, name: String, detail: String = "",
    emptyText: String, errorText: String,
    _ body: @escaping () async throws -> String
  ) {
    Task { [weak self] in
      guard let self else { return }
      var out: String
      do { out = try await body() } catch { out = errorText }
      if out.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { out = emptyText }
      let suffix = detail.isEmpty ? "" : " \(detail)"
      log("RealtimeHub[\(self.providerTag)]: tool \(name)\(suffix) → \(out.prefix(60))")
      self.sendToolResultIfCurrent(source: source, callId: callId, name: name, output: out)
    }
  }

  func hubDidRequestTool(name: String, callId: String, argumentsJSON: String, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    let arguments =
      (try? JSONSerialization.jsonObject(with: Data(argumentsJSON.utf8)) as? [String: Any]) ?? [:]
    guard let tool = HubTool(rawValue: name) else {
      log("RealtimeHub[\(providerTag)]: tool_call UNKNOWN \(name) — rejecting")
      sendToolResultIfCurrent(source: source, callId: callId, name: name, output: "Unknown tool.")
      return
    }
    func arg(_ key: String) -> String { (arguments[key] as? String) ?? turnTranscript }
    func argInt(_ key: String) -> Int? { (arguments[key] as? Int) ?? (arguments[key] as? NSNumber)?.intValue }
    switch tool {
    case .askHigherModel:
      let query = arg("query")
      let context = (arguments["context"] as? String) ?? ""
      log(
        "RealtimeHub[\(providerTag)]: tool ask_higher_model → POST /v2/chat/completions (\(ModelQoS.Claude.defaultSelection)) query=\"\(query.prefix(80))\""
      )
      Task { [weak self] in
        guard let self else { return }
        let answer = await self.escalateToHigherModel(
          query, context: context, aboutUser: self.aboutUserCard)
        self.sendToolResultIfCurrent(source: source, callId: callId, name: name, output: answer)
      }
    case .getTasks:
      // Fast LOCAL read — no agent. Fetch today's + overdue tasks and hand them back
      // as text for the model to speak (this is the read path, vs spawn_agent actions).
      Task { @MainActor [weak self] in
        guard let self else { return }
        await TasksStore.shared.loadDashboardTasks()
        let overdue = TasksStore.shared.overdueTasks
        let today = TasksStore.shared.todaysTasks
        // Include the task id (for update_action_item) — the model is told never to speak ids.
        func list(_ items: [TaskActionItem]) -> String {
          items.prefix(15).map { "- \($0.description) [id:\($0.id)]" }.joined(separator: "\n")
        }
        var out = ""
        if !overdue.isEmpty { out += "Overdue (\(overdue.count)):\n\(list(overdue))\n" }
        if !today.isEmpty { out += "Due today (\(today.count)):\n\(list(today))\n" }
        if out.isEmpty { out = "No tasks overdue or due today." }
        log("RealtimeHub[\(self.providerTag)]: tool get_tasks → \(overdue.count) overdue, \(today.count) today")
        self.sendToolResultIfCurrent(source: source, callId: callId, name: name, output: out)
      }
    case .getMemories:
      // Fast READ — "who am I" / "what do you know about me". Backend memories+facts.
      runToolAndSpeak(
        source: source,
        callId: callId, name: name,
        emptyText: "I don't have any memories saved about you yet.",
        errorText: "Could not read your memories right now."
      ) { try await APIClient.shared.toolGetMemories(limit: 15).resultText }
    case .searchMemories:
      let query = arg("query")
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "q=\"\(query.prefix(60))\"",
        emptyText: "I couldn't find anything about that.",
        errorText: "Could not search your memories right now."
      ) { try await APIClient.shared.toolSearchMemories(query: query, limit: 5).resultText }
    case .searchConversations:
      // Capped for voice: top 5, summaries only (no full transcripts).
      let query = arg("query")
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "q=\"\(query.prefix(60))\"",
        emptyText: "I couldn't find a conversation about that.",
        errorText: "Could not search your conversations right now."
      ) {
        try await APIClient.shared.toolSearchConversations(
          query: query, limit: 5, includeTranscript: false
        ).resultText
      }
    case .getConversations:
      // Fast READ — most recent conversations, newest first (backend orders created_at DESC).
      // Capped for voice: top 3, summaries only. This is the recency path; search_conversations
      // is semantic and must NOT be used for "most recent".
      runToolAndSpeak(
        source: source,
        callId: callId, name: name,
        emptyText: "I don't see any recent conversations.",
        errorText: "Could not read your recent conversations right now."
      ) {
        try await APIClient.shared.toolGetConversations(
          limit: 3, includeTranscript: false
        ).resultText
      }
    case .getDailyRecap:
      // Fast LOCAL read of the on-device activity DB — apps/minutes, conversations, tasks,
      // focus, screen context. Reuses the SAME executor the desktop chat uses, so voice and
      // chat answer "what did I do yesterday" from one code path.
      let daysAgo = argInt("days_ago") ?? 1
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "days_ago=\(daysAgo)",
        emptyText: "I don't have any activity recorded for then.",
        errorText: "Could not pull up your activity right now."
      ) {
        await ChatToolExecutor.execute(
          ToolCall(name: "get_daily_recap", arguments: ["days_ago": daysAgo], thoughtSignature: nil))
      }
    case .getActionItems:
      // Backend READ of the full task list with filters (completed / due-date range) — the
      // capable sibling of the local get_tasks. Same APIClient path the chat agent uses.
      let completed = arguments["completed"] as? Bool
      let dueStart = arguments["due_start_date"] as? String
      let dueEnd = arguments["due_end_date"] as? String
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: completed.map { "completed=\($0)" } ?? "",
        emptyText: "I couldn't find any matching tasks.",
        errorText: "Could not read your tasks right now."
      ) {
        try await APIClient.shared.toolGetActionItems(
          limit: 25, completed: completed, dueStartDate: dueStart, dueEndDate: dueEnd
        ).resultText
      }
    case .getTaskAgentStatus:
      let result = TaskAgentStatusRegistry.shared.combinedSummary()
      log("RealtimeHub[\(providerTag)]: tool get_task_agent_status")
      sendToolResultIfCurrent(source: source, callId: callId, name: name, output: result)
    case .manageAgentPills:
      let action = ((arguments["action"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines))
        .flatMap { $0.isEmpty ? nil : $0 } ?? "list"
      let agentId = (arguments["agent_id"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
      let result = AgentPillsManager.shared.manage(action: action, agentId: agentId)
      log("RealtimeHub[\(providerTag)]: tool manage_agent_pills action=\(action)")
      sendToolResultIfCurrent(source: source, callId: callId, name: name, output: result)
    case .listAgentSessions, .getAgentRun, .cancelAgentRun, .inspectAgentArtifacts, .updateAgentArtifactLifecycle:
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: agentControlService.logDetail(name: name, arguments: arguments),
        emptyText: "No canonical agent data came back.",
        errorText: "Could not reach the agent control plane right now."
      ) {
        try await self.agentControlService.executeVoiceTool(name: name, arguments: arguments)
      }
    case .searchScreenHistory:
      // Fast LOCAL semantic search over screen history (same executor as chat).
      let query = arg("query")
      var toolArgs: [String: Any] = ["query": query]
      if let days = argInt("days") { toolArgs["days"] = days }
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "q=\"\(query.prefix(60))\"",
        emptyText: "I couldn't find anything on your screen about that.",
        errorText: "Could not search your screen history right now."
      ) {
        await ChatToolExecutor.execute(
          ToolCall(name: "search_screen_history", arguments: toolArgs, thoughtSignature: nil))
      }
    case .createActionItem:
      let description = (arguments["description"] as? String)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let dueAt = arguments["due_at"] as? String
      guard !description.isEmpty else {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name, output: "No task description was given.")
        return
      }
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "\"\(description.prefix(60))\"",
        emptyText: "Task created.",
        errorText: "Could not create the task right now."
      ) {
        try await APIClient.shared.toolCreateActionItem(
          description: description, dueAt: dueAt
        ).resultText
      }
    case .updateActionItem:
      guard let id = (arguments["id"] as? String), !id.isEmpty else {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "Missing the task id — call get_tasks first to find it.")
        return
      }
      let completed = arguments["completed"] as? Bool
      let newDescription = arguments["description"] as? String
      let dueAt = arguments["due_at"] as? String
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "id=\(id.prefix(8))",
        emptyText: "Task updated.",
        errorText: "Could not update the task right now."
      ) {
        try await APIClient.shared.toolUpdateActionItem(
          id: id, completed: completed, description: newDescription, dueAt: dueAt
        ).resultText
      }
    case .createCalendarEvent:
      let title = (arguments["title"] as? String)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      guard !title.isEmpty else {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name, output: "No calendar event title was given.")
        return
      }
      guard let startTime = arguments["start_time"] as? String, !startTime.isEmpty else {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name, output: "No calendar event start time was given.")
        return
      }
      guard let endTime = arguments["end_time"] as? String, !endTime.isEmpty else {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name, output: "No calendar event end time was given.")
        return
      }
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "\"\(title.prefix(60))\"",
        emptyText: "Calendar event created.",
        errorText: "Could not create the calendar event right now."
      ) {
        try await APIClient.shared.toolCreateCalendarEvent(
          title: title,
          startTime: startTime,
          endTime: endTime,
          description: arguments["description"] as? String,
          location: arguments["location"] as? String,
          attendees: arguments["attendees"] as? String
        ).resultText
      }
    case .spawnAgent:
      let brief = arg("brief")
      let title = (arguments["title"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
      let providerName = ((arguments["provider"] as? String) ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: " ", with: "")
      let directedProvider: AgentPillsManager.DirectedProvider?
      switch providerName {
      case "openclaw": directedProvider = .openclaw
      case "hermes": directedProvider = .hermes
      case "codex": directedProvider = .codex
      case "": directedProvider = nil
      default:
        session?.sendToolResult(
          callId: callId, name: name,
          output: "Unsupported agent provider '\(providerName)'. Use 'hermes', 'openclaw', or 'codex'.")
        return
      }
      if let directedProvider {
        let availability = LocalAgentProviderDetector.availability(for: directedProvider)
        guard availability.isAvailable else {
          let setupPrompt = availability.setupPrompt
          assistantText = setupPrompt
          barState?.isVoiceResponseActive = true
          if !audioReceivedThisTurn {
            speak(directedProvider.setupNeededStatus)
          }
          suppressAssistantOutputForCurrentTurn = true
          log("RealtimeHub[\(providerTag)]: tool spawn_agent provider=\(directedProvider.rawValue) unavailable")
          sendToolResultIfCurrent(
            source: source, callId: callId, name: name,
            output: availability.toolError)
          return
        }
      }
      let model = ShortcutSettings.shared.selectedModel.isEmpty
        ? ModelQoS.Claude.defaultSelection : ShortcutSettings.shared.selectedModel
      // Non-blocking: spawn renders its own pill ("text bubble") and runs on its
      // own ChatProvider/AgentBridge. We don't await it on the voice loop.
      // fromVoice:false — the hub model speaks its own natural acknowledgment, so the pill
      // must NOT also speak its canned randomAck ("on it") or we double up.
      let pill = AgentPillsManager.shared.spawnFromUserQuery(
        brief, model: model, fromVoice: false,
        preFetchedTitle: (title?.isEmpty == false) ? title : directedProvider?.displayName,
        bridgeHarnessOverride: directedProvider?.harnessMode)
      log("RealtimeHub[\(providerTag)]: tool spawn_agent → AgentBridge pill=\"\(pill.title)\" model=\(model) provider=\(directedProvider?.rawValue ?? "default") titled=\(title?.isEmpty == false)")
      if !audioReceivedThisTurn {
        let existingAck = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
        let ack = existingAck.isEmpty ? "Starting a background agent." : existingAck
        assistantText = ack
        barState?.isVoiceResponseActive = true
        speak(ack)
      }
      suppressAssistantOutputForCurrentTurn = true
      // Don't report "started" blind: startup-class failures (provider not
      // running / not signed in) surface within ~1.5s. Watch the pill briefly
      // so the model can announce a failure immediately instead of telling the
      // user a dead agent is "running in the background".
      Task { @MainActor [weak self] in
        try? await Task.sleep(nanoseconds: 1_800_000_000)
        let output: String
        if case .failed(let errorText) = pill.status {
          output =
            "Agent FAILED to start: \(errorText) — relay this to the user (including any command verbatim) and offer next steps: fix the provider as instructed, or run the task with the default agent instead."
        } else {
          output =
            "Agent started and is running in the background. If the user later asks about its status or results, call get_task_agent_status first — never answer from memory."
        }
        self?.sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: output)
      }
    case .screenshot:
      // Gemini: the screen is already attached to every turn (see commitTurn), so the
      // tool is just an ack — pushing another image here is the broken path (mid-tool-call
      // injection self-interrupts the turn / closes the socket 1007). OpenAI: add the image
      // as an ordered conversation item (that path works for OpenAI).
      let shot = speculativeScreenshot ?? ScreenCaptureManager.captureScreenData()
      if sessionProvider == .openai, let shot { session?.injectImage(shot) }
      log("RealtimeHub[\(providerTag)]: tool screenshot → ack (\(shot?.count ?? 0) bytes, screen on turn)")
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: shot == nil ? "Could not capture the screen." : "Screen captured.")
    case .pointClick:
      let x = (arguments["x"] as? Double) ?? (arguments["x"] as? NSNumber)?.doubleValue ?? 0
      let y = (arguments["y"] as? Double) ?? (arguments["y"] as? NSNumber)?.doubleValue ?? 0
      let ok = Self.click(at: CGPoint(x: x, y: y))
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: ok ? "Clicked at \(Int(x)), \(Int(y))." : "Could not click.")
    }
  }

  func hubDidFinishTurn(source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    responding = false
    hubReconnectStrikes = 0  // a completed turn proves the hub works — reset the budget
    let heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    log("RealtimeHub[\(providerTag)]: turn done — heard=\"\(heard.prefix(80))\" audio=\(audioReceivedThisTurn)")
    if realtimePlaybackActive {
      log("RealtimeHub[\(providerTag)]: server turn done; waiting for local playback to drain")
    }
    // Record the completed turn into chat history (+ backend sync) in the background.
    // The hub plays its reply itself and never routes through the query path, so this is
    // the only place voice turns get persisted. Idempotent per turn; recordVoiceTurn is
    // fire-and-forget so it never stalls the warm socket or the next PTT press.
    if !turnRecorded {
      turnRecorded = true
      FloatingControlBarManager.shared.recordVoiceTurn(userText: heard, assistantText: reply)
    }
    exitVoiceUI()
  }

  func hubDidError(_ message: String, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    // A socket we intentionally dropped is detached in teardownSession() before it's
    // released, so its death-rattle never reaches us — only the live session's errors
    // land here.
    let hasActiveTurn = responding
      || (barState?.isVoiceListening == true)
      || (barState?.isVoiceResponseActive == true)
    responding = false
    let aliveFor = (hubConnected ? lastWarmAt.map { Date().timeIntervalSince($0) } : nil) ?? 0
    // Most "session error" closes are expected lifecycle events, not bugs: a socket
    // that lived past the idle window is a normal provider idle-close (Gemini ~2.5min,
    // 1008), and a client "operation was aborted"/cancellation is a teardown. Reporting
    // these to Sentry as errors created the high-volume OMI-DESKTOP-27C cluster. Keep
    // them as local logs; only capture genuine fast-fail provider errors, without raw
    // provider close text for known fast policy/auth/config rejects.
    let closeCategory = RealtimeHubCloseClassifier.category(
      message: message,
      aliveFor: aliveFor,
      hasActiveTurn: hasActiveTurn)
    let provider = sessionProvider
    let authMode: CredentialAuthMode = sessionAuth?.isEphemeral == true ? .managed : .byok
    let fingerprint = provider.flatMap { APIKeyService.byokKey($0.byokProvider) }.map(APIKeyService.byokFingerprint)
    var credentialFailureClass: CredentialFailureClass?
    if let provider, closeCategory != .expectedIdleTeardown {
      var failureClass = CredentialHealthManager.classifyProviderClose(message: message, provider: provider)
      if authMode == .managed, case .providerAuthFailed = failureClass {
        failureClass = .providerAuthFailed(provider: provider, mode: .managed)
      }
      credentialFailureClass = failureClass
      CredentialHealthManager.shared.recordProviderFailure(
        failureClass,
        provider: provider,
        authMode: authMode,
        fingerprint: fingerprint,
        context: "realtime_socket")
    }
    let categoryText = closeCategory.map { " category=\($0.rawValue)" } ?? ""
    let shouldRedactProviderMessage: Bool = {
      if closeCategory == .providerPolicyCloseFast { return true }
      if case .providerAuthFailed = credentialFailureClass { return true }
      if case .providerQuotaExceeded = credentialFailureClass { return true }
      return false
    }()
    let safeMessage = shouldRedactProviderMessage ? "" : " \(message)"
    DesktopDiagnosticsManager.shared.recordRealtimeProviderClose(
      provider: providerTag,
      category: closeCategory?.rawValue,
      aliveFor: aliveFor,
      activeTurn: hasActiveTurn)
    if RealtimeHubCloseClassifier.shouldReportToSentry(closeCategory) {
      logError("RealtimeHub: session error —\(categoryText) provider=\(providerTag)\(safeMessage)")
    } else {
      log("RealtimeHub: session closed —\(categoryText) provider=\(providerTag) aliveFor=\(Int(aliveFor))s \(message)")
    }
    // The reply is dead — stop any buffered audio before collapsing.
    pcmPlayer?.stop()
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    if localSpeechActive || speech.isSpeaking {
      speech.stopSpeaking(at: .immediate)
      localSpeechActive = false
    }
    exitVoiceUI(clearResponseGlow: true)
    teardownSession()
    // A session that died fast (connected, then the provider rejected/aborted it — e.g.
    // Gemini close 1008 / 429) is a real provider failure: try the OTHER realtime provider
    // before the cascade. One that lived long was a normal idle-close → re-warm the same.
    if case .providerAuthFailed = credentialFailureClass {
      if aliveFor < 10, failoverToAlternateProvider() { return }
      return
    }
    if case .providerQuotaExceeded = credentialFailureClass {
      if failoverToAlternateProvider() { return }
      return
    }
    if aliveFor < 10, failoverToAlternateProvider() { return }
    // Re-warm so the NEXT PTT uses the hub, not the STT cascade. Gemini idle-closes
    // the socket (~2.5 min, close 1008) even before the first turn; managed users have
    // no BYOK key, so once `session` is nil `isActive` is false and PTT silently falls
    // back to omni STT. So always try to re-warm (the hub is the default voice path).
    // A socket that survived past the idle window was a normal idle-close → reset the
    // strike budget (and the failover, returning to the Auto pick) and keep re-warming.
    if aliveFor > 60 {
      hubReconnectStrikes = 0
      fallbackProvider = nil
    }
    guard !reconnectPending, hubReconnectStrikes < Self.maxReconnectStrikes else { return }
    hubReconnectStrikes += 1
    reconnectPending = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
      guard let self else { return }
      self.reconnectPending = false
      if self.session == nil { self.ensureWarm() }
    }
  }

  /// Return the floating bar from its PTT voice state to compact after a hub turn.
  private func exitVoiceUI(clearResponseGlow: Bool = false) {
    guard let barState else { return }
    // Capture before clearing: a mid-turn error or silent-tap cancel clears the
    // listening flag here, so PushToTalkManager.updateBarState() (which resizes only
    // on a wasListening→false transition) would see no change and leave the bar wide.
    let wasExpandedForVoice = barState.isVoiceListening
    barState.voiceTranscript = ""
    // When the turn fell back to local AVSpeechSynthesizer speech (no realtime audio)
    // or the spawn_agent path spoke a local ack, audioReceivedThisTurn is false but
    // the synthesizer has been asked to speak. Keep the glow active until the delegate
    // (didFinish/didCancel) clears it, so the spoken-response indicator doesn't
    // disappear mid-utterance. Using localSpeechActive (set synchronously in speak)
    // instead of speech.isSpeaking avoids the race where isSpeaking is still false
    // because the synthesizer hasn't started the queued utterance yet.
    if clearResponseGlow || (!audioReceivedThisTurn && !localSpeechActive) {
      responseGlowGate.clearImmediately()
    }
    barState.isVoiceListening = false
    barState.isVoiceLocked = false
    barState.isVoiceFollowUp = false
    // Collapse the bar ourselves in that case — guarded so we never shrink the bar out
    // from under an open conversation, response, notification, hover, or onboarding.
    guard wasExpandedForVoice,
      !barState.showingAIConversation, !barState.showingAIResponse,
      barState.currentNotification == nil, !barState.isHoveringBar,
      UserDefaults.standard.bool(forKey: "hasCompletedOnboarding")
    else { return }
    FloatingControlBarManager.shared.resizeForPTT(expanded: false)
  }

  private func clearResponseGlowIfRealtimeAudioIdle() {
    responseGlowGate.scheduleIdleClear()
  }

  // MARK: - Tools

  /// ask_higher_model — reuse the EXISTING prompt-cached /v2/chat/completions
  /// (no new backend route). Returns the assistant text for the model to speak.
  private func escalateToHigherModel(_ query: String, context: String, aboutUser: String)
    async -> String
  {
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
    let body = RealtimeHubTools.escalationBody(
      query: query, context: context, aboutUser: aboutUser)
    let t0 = Date()
    do {
      request.httpBody = try JSONSerialization.data(withJSONObject: body)
      let (data, response) = try await URLSession.shared.data(for: request)
      let ms = Int(Date().timeIntervalSince(t0) * 1000)
      guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
        let code = (response as? HTTPURLResponse)?.statusCode ?? -1
        log("RealtimeHub: ask_higher_model ← \(ModelQoS.Claude.defaultSelection) HTTP \(code) in \(ms)ms (FAILED)")
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
      log("RealtimeHub: ask_higher_model ← \(ModelQoS.Claude.defaultSelection) OK in \(ms)ms (\(answer.count) chars)")
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
    // Set synchronously so exitVoiceUI sees it even before the synthesizer
    // starts playback (isSpeaking is false until the queued utterance begins).
    localSpeechActive = true
    speech.speak(utterance)
  }

  nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      self.localSpeechActive = false
      self.responseGlowGate.clearImmediately()
    }
  }

  /// Handles non-explicit cancellation paths (system interruption, future code,
  /// or unexpected state) so the response glow doesn't stay stuck when speech
  /// is cancelled without didFinish firing.
  nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      self.localSpeechActive = false
      self.responseGlowGate.clearImmediately()
    }
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

import AppKit
import CoreGraphics
import Foundation

// MARK: - Realtime Hub Controller (Phase 1)
//
// Owns one persistent, warm RealtimeHubSession and makes the realtime model the
// single tool-dispatching hub for the voice path. It:
//   • keeps the WS warm between PTT turns (no reopen per press),
//   • feeds mic PCM in and plays the model's spoken reply out
//     (provider native audio → StreamingPCMPlayer; selected app voice fallback → FloatingBarVoicePlaybackService),
//   • executes the model's tool calls against EXISTING app code / endpoints:
//       ask_higher_model → POST /v2/chat/completions (Claude, prompt-cached)
//       spawn_agent      → canonical background agent + floating pill projection
//       screenshot       → ScreenCaptureManager (+ inject into the session when explicitly requested)
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
    hasActiveTurn: Bool = false,
    provider: RealtimeHubProvider = .openai
  ) -> RealtimeHubCloseCategory? {
    let lower = message.lowercased()
    guard lower.contains("websocket closed (1008)") else { return nil }
    if CredentialHealthManager.classifyProviderClose(
      message: message,
      provider: provider) == .providerQuotaExceeded(provider: provider)
    {
      return .providerQuotaExceeded
    }
    if CredentialHealthManager.classifyProviderClose(
      message: message,
      provider: provider) == .providerAuthFailed(provider: provider, mode: .byok)
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

enum RealtimeHubCommitResult: Equatable {
  case accepted
  case deferredForReplacement
  case rejectedNoSession
}

enum RealtimeHubToolFailureKind: String, Equatable {
  case backendUnauthorized = "backend_unauthorized"
  case backendRateLimited = "backend_rate_limited"
  case backendClientRejected = "backend_client_rejected"
  case backendServerError = "backend_server_error"
  case backendTransport = "backend_transport"
  case responseDecode = "response_decode"
  case providerCredential = "provider_credential"
  case toolExecution = "tool_execution"

  static func classify(_ error: Error) -> RealtimeHubToolFailureKind {
    if error is DecodingError { return .responseDecode }
    if let apiError = error as? APIError {
      switch apiError {
      case .unauthorized:
        return .backendUnauthorized
      case .syncRateLimited:
        return .backendRateLimited
      case .invalidResponse, .decodingError:
        return .responseDecode
      case .httpError(let statusCode, _):
        switch statusCode {
        case 401, 403:
          return .backendUnauthorized
        case 408, 425, 429:
          return .backendRateLimited
        case 400..<500:
          return .backendClientRejected
        case 500..<600:
          return .backendServerError
        default:
          return .backendTransport
        }
      case .unsupportedTierScopedBulkMutation, .syncUploadRejected:
        return .backendClientRejected
      }
    }
    if let credentialError = error as? CredentialHealthError {
      switch credentialError.failureClass {
      case .requiresLogin, .backendUnauthorized:
        return .backendUnauthorized
      case .paywalled, .byokEnrollmentMismatch, .providerAuthFailed, .providerQuotaExceeded:
        return .providerCredential
      case .backendTransient:
        return .backendServerError
      case .providerTransient, .providerPolicyClose, .unknown:
        return .backendTransport
      }
    }
    let nsError = error as NSError
    if nsError.domain == NSURLErrorDomain { return .backendTransport }
    return .toolExecution
  }

  var userFacingReason: String {
    switch self {
    case .backendUnauthorized:
      return "Sign-in or account access needs attention."
    case .backendRateLimited:
      return "The service is rate limited; try again shortly."
    case .backendClientRejected:
      return "The request was rejected."
    case .backendServerError:
      return "The backend is temporarily unavailable."
    case .backendTransport:
      return "The network request failed."
    case .responseDecode:
      return "The response could not be read."
    case .providerCredential:
      return "The provider credential needs attention."
    case .toolExecution:
      return "The tool failed while running."
    }
  }
}

struct RealtimeHubToolFailure: Equatable {
  let kind: RealtimeHubToolFailureKind

  static func classify(_ error: Error) -> RealtimeHubToolFailure {
    RealtimeHubToolFailure(kind: RealtimeHubToolFailureKind.classify(error))
  }

  func userFacingOutput(base: String) -> String {
    "\(base) \(kind.userFacingReason)"
  }
}

private struct PendingBargeInReplacementTurn {
  var pendingBegin = true
  var pendingCommit = false
  var audioBuffer: [Data] = []
}

struct InterruptedTurnPayload: Equatable {
  let userText: String
  let assistantText: String
  let idempotencyKey: String

  /// User-visible chat text for a PTT-barged reply: keep streamed partial text only.
  static func visibleAssistantText(partialAssistantText: String) -> String {
    partialAssistantText.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

enum RealtimeHubBargeInContinuity {
  static func prepareReplacementSession(
    interruptedTurn: InterruptedTurnPayload?,
    recordInterruptedTurn: (InterruptedTurnPayload) async -> Void,
    refreshVoiceSeed: () async -> Void,
    startReplacementSession: () -> Void
  ) async {
    if let interruptedTurn {
      await recordInterruptedTurn(interruptedTurn)
    }
    await refreshVoiceSeed()
    startReplacementSession()
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
final class RealtimeHubController: NSObject, RealtimeHubSessionDelegate {
  static let shared = RealtimeHubController()

  private weak var barState: FloatingControlBarState?
  private var session: RealtimeHubSession?
  private var sessionProvider: RealtimeHubProvider?
  private var sessionAuth: HubAuth?
  private var pcmPlayer: StreamingPCMPlayer?
  private lazy var responseGlowGate = RealtimeResponseGlowGate { [weak self] active in
    if active {
      self?.barState?.isVoiceResponseActive = true
    } else {
      self?.barState?.clearVoiceResponseState()
    }
  }
  private let agentControlService = AgentControlService()

  // Per-turn state.
  private var turnTranscript = ""
  private var assistantText = ""
  private var speculativeWarmDone = false
  private var speculativeScreenshot: Data?
  private var audioReceivedThisTurn = false
  /// `spawn_agent` is a handoff, not a read tool. After the tool result returns,
  /// the realtime model sometimes continues with meta/control text; never speak it.
  private var suppressAssistantOutputForCurrentTurn = false
  /// Guards against recording the same turn to the kernel twice (a delegate that
  /// fires turn-done more than once on reconnect/barge-in edges). Reset per turn.
  private var turnRecorded = false
  /// Stable per-turn key for kernel idempotent voice-turn persistence.
  private var turnIdempotencyKey = ""
  /// Kernel-projected transcript tail prefetched when PTT is armed (key-down).
  private var prefetchedVoiceSeedContext = ""
  private var prefetchedFloatingAgentStatus = ""
  private var voiceTurnScreenContextSentEpoch: Int?
  /// Seed baked into the current warm session's system instructions.
  private var sessionVoiceSeedContextSnapshot = ""
  private var voiceSeedPrefetchTask: Task<Void, Never>?
  private var bargeInContinuityTask: Task<Void, Never>?
  private var pendingBargeInProvider: RealtimeHubProvider?
  private var pendingBargeInAuth: HubAuth?

  // Per-turn language identification (multi-language PTT).
  /// Local copy of this turn's mic audio (16 kHz s16le mono) for on-device language ID.
  private var turnAudio16k = Data()
  /// Monotonic turn counter guarding async language-ID results against cross-turn races.
  private var turnEpoch = 0
  /// True from PTT-down (`beginTurn`) until commit/cancel — gates activityStart retry on reconnect.
  private var inputTurnInProgress = false
  /// `beginInputTurn` was deferred because the warm session was still opening after seed-stale reconnect.
  private var inputTurnActivityStartPending = false
  private var pendingInputTurnInterrupting = false
  /// Early (mid-hold) language verdict — kicked off ~1.5 s into the hold so it's already
  /// computed by PTT-up and the provider hint adds zero perceived latency.
  private var earlyLIDTask: Task<PTTLanguageIdentifier.Verdict, Never>?
  /// Language code from the early verdict for THIS turn (nil = none arrived in time).
  /// Written by the early task's continuation, consumed synchronously at commit — so
  /// commit never awaits anything and can never drop a turn on a guard.
  private var turnEarlyVerdictCode: String?
  /// Full-buffer decode kicked at commit; supplies the fallback transcript when the
  /// provider's transcript comes back in a language the user doesn't speak.
  private var fullLIDTask: Task<PTTLanguageIdentifier.Verdict, Never>?
  /// Diagnostics of the last completed turn, for the `ptt_test_turn` automation action.
  private var lastTurnDiagnostics: [String: String] = [:]
  /// TEST SEAM (ptt_test_turn only, bridge is non-prod-only): replaces the provider's
  /// transcript for the next turn-done, simulating a provider-side language misdetect
  /// (the "Russian speech transcribed as Italian" case) — the one input that can't be
  /// forced from outside. Everything downstream (mismatch check, local-transcript
  /// fallback, persistence) runs the real path. Cleared after one use.
  private var testProviderTranscriptOverride: String?
  private static let maxTurnAudioBytes = 3_840_000  // 120 s @ 16 kHz s16le
  private static let earlyLIDBytes = 48_000  // 1.5 s
  /// Pending voice→agent handoff recorded during a tool call but persisted only
  /// after the final transcript arrives in hubDidFinishTurn, so the user text is
  /// complete (not a partial interim ASR result).
  private var pendingVoiceAgentHandoff: (title: String, brief: String)?
  /// Provider turn-complete events can arrive after a tool-call-only response and
  /// before our async tool body has returned. Keep the voice turn open until every
  /// requested tool has been answered; otherwise the bar collapses after "I'll check"
  /// and the follow-up response is lost until the next PTT.
  private var pendingRealtimeToolCallIds = Set<String>()
  private var realtimeToolTurnEpoch = 0
  private var pendingCompletedAgentDeltaAckIds: [String] = []
  private var pendingCompletedAgentDeltaHighWaterMs: Int?
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
  private var turnGeneration: UInt64 = 0
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
  private var pendingBargeInReplacement: PendingBargeInReplacementTurn?

  /// Failover chain: when the Auto-selected (primary) provider can't connect, the hub
  /// tries the OTHER realtime provider before dropping to the legacy Claude cascade.
  /// nil = on the primary; non-nil = the provider we failed over TO.
  private var fallbackProvider: RealtimeHubProvider?

  private override init() {
    super.init()
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

  private func shouldFailoverToAlternate(for failureClass: CredentialFailureClass?) -> Bool {
    switch failureClass {
    case .providerAuthFailed, .providerQuotaExceeded:
      return true
    case .backendUnauthorized, .requiresLogin, .paywalled, .byokEnrollmentMismatch,
         .backendTransient, .providerTransient, .providerPolicyClose, .unknown, .none:
      return false
    }
  }

  private func recordRealtimeMintFailure(
    _ error: RealtimeTokenMintError,
    provider providerParam: String,
    phase: String,
    context: String
  ) {
    CredentialHealthManager.shared.record(error.healthError, context: context)
    DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
      provider: providerParam,
      reason: error.payload?.reason ?? error.healthError.failureClass.logValue,
      phase: phase,
      httpStatusCode: error.statusCode,
      backendRoute: error.payload?.backendRoute,
      upstreamStatusCode: error.payload?.upstreamStatusCode,
      providerCode: error.payload?.code,
      retryable: error.payload?.retryable)
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
    // Voice-language edits must reach a WARM session: settingsChanged() early-returns
    // when the provider is unchanged, so without this the system-instruction languages
    // line (and the LID prewarm) would only apply after the next idle re-mint.
    NotificationCenter.default.removeObserver(self, name: .voiceLanguagesDidChange, object: nil)
    NotificationCenter.default.addObserver(
      self, selector: #selector(voiceLanguagesChanged),
      name: .voiceLanguagesDidChange, object: nil)
    // Expose the headless E2E action (omi-ctl action hub_test_turn pcm=… provider=…).
    RealtimeHubTestHarness.registerAutomationAction()
    registerPTTLanguageTestAction()
    // Load the multilingual language-ID model off the hot path so the first PTT turn's
    // early verdict (and the bubble-fallback decode) doesn't pay model-load latency.
    // Only for users who explicitly configured voice languages — the gate that keeps
    // this whole feature inert for default-config users.
    if !AssistantSettings.shared.voiceBaseLanguages.isEmpty {
      Task.detached(priority: .utility) { await PTTLanguageIdentifier.shared.prewarm() }
    }
    refreshAboutUserCard()
  }

  /// Headless E2E for the PTT language path: drives the REAL controller turn flow
  /// (beginTurn → paced feedAudio → commitTurn → turn-done) with a PCM file, so the
  /// early language ID, the provider hint, and the bubble fallback run exactly as a
  /// real hold-to-talk. `omi-ctl action ptt_test_turn pcm=/tmp/q.pcm [timeout=30]`.
  private func registerPTTLanguageTestAction() {
    DesktopAutomationActionRegistry.shared.register(
      name: "ptt_test_turn",
      summary: "Drive a real PTT hub turn from a PCM16/16k mono file through the controller "
        + "(language ID + provider hint + bubble fallback); returns turn diagnostics.",
      params: ["pcm", "timeout", "force_transcript"]
    ) { [weak self] params in
      guard let path = params["pcm"],
        let data = try? Data(contentsOf: URL(fileURLWithPath: path)), !data.isEmpty
      else { return ["error": "missing or unreadable 'pcm' file (expected raw s16le 16k mono)"] }
      let timeout = Double(params["timeout"] ?? "") ?? 30
      let textOnly = params["text_only"] == "1"
      guard let self else { return ["error": "hub controller unavailable"] }
      return await self.runHeadlessPTTTurn(
        pcm16k: data, timeout: timeout, forceTranscript: params["force_transcript"],
        textOnly: textOnly)
    }
  }

  private func runHeadlessPTTTurn(
    pcm16k: Data, timeout: Double, forceTranscript: String? = nil, textOnly: Bool = false
  ) async -> [String: String] {
    // A voice-seed reconnect (triggered by the previous turn's kernel write) can replace
    // the warm session mid-turn; the fed audio/text/commit then land on the dead socket
    // and the turn never completes. Detect the swap and redrive the turn once.
    for attempt in 0..<2 {
      if attempt > 0 {
        // Attempt 0's turn died with its session. Clear stale reply-in-flight state so
        // the fresh beginTurn isn't misread as a barge-in — that would capture a bogus
        // interrupted turn, mark turnRecorded, and skip diagnostics on the real reply.
        responding = false
        realtimePlaybackActive = false
      }
      ensureWarm()
      guard await waitUntilActive(timeout: 15) else {
        return ["error": "hub session did not become active (check sign-in / provider keys)"]
      }
      prefetchVoiceSeedContextIfNeeded()
      try? await Task.sleep(nanoseconds: 500_000_000)
      ensureWarm()
      guard await waitUntilActive(timeout: 15) else {
        return ["error": "hub session did not become active after voice seed prefetch"]
      }
      lastTurnDiagnostics = [:]
      beginTurn()
      testProviderTranscriptOverride = forceTranscript
      let chunkBytes = 3_200  // 100 ms @ 16 kHz s16le
      if !textOnly {
        // Pace the audio like real speech (100 ms chunks) so the mid-hold early language ID
        // triggers on the same timeline as a real hold.
        var offset = 0
        while offset < pcm16k.count {
          let end = min(offset + chunkBytes, pcm16k.count)
          feedAudio(pcm16k.subdata(in: offset..<end))
          offset = end
          try? await Task.sleep(nanoseconds: 100_000_000)
        }
      }
      // beginTurn can defer activityStart while a seed-stale reconnect finishes; text or
      // commit sent before the window opens orphans the turn and Gemini closes 1008.
      let windowDeadline = Date().addingTimeInterval(10)
      while Date() < windowDeadline {
        if let live = session, await live.activityWindowOpen() { break }
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      if textOnly {
        // Gemini rejects pure-text activity windows (1007 precondition); a brief silence
        // frame keeps the window "real" without the sine hallucination flake.
        let silenceChunk = Data(count: chunkBytes)
        for _ in 0..<2 {
          feedAudio(silenceChunk)
          try? await Task.sleep(nanoseconds: 100_000_000)
        }
      }
      // beginTurn's seed refresh can reconnect the warm socket; capture the live session
      // only after the activity window (and any textOnly silence) is ready so we don't
      // false-positive redrive on the expected post-beginTurn reconnect.
      let turnSession = session
      // Without injecting the forced transcript as real model input, the provider answers
      // whatever it hallucinates from the fixture audio (unrelated-reply flake). Harness
      // probes pass text_only=1 so no competing audio is fed at all; the language-ID
      // harness keeps feeding real speech PCM alongside the forced transcript.
      if let forceTranscript, !forceTranscript.isEmpty {
        _ = await session?.sendTestTextInput(forceTranscript)
      }
      commitTurn()
      let deadline = Date().addingTimeInterval(timeout)
      var redrive = false
      while Date() < deadline {
        if !lastTurnDiagnostics.isEmpty { return lastTurnDiagnostics }
        if attempt == 0, session !== turnSession {
          redrive = true
          break
        }
        try? await Task.sleep(nanoseconds: 200_000_000)
      }
      guard redrive else { break }
      log("RealtimeHub: headless PTT turn lost to a mid-turn session swap — redriving once")
      try? await Task.sleep(nanoseconds: 1_000_000_000)
    }
    return ["error": "turn did not complete within \(Int(timeout))s"]
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

  /// Voice languages changed: prewarm the LID model (a 1→2 language change would
  /// otherwise cold-load on the first turn) and rebuild an idle warm session so the
  /// new languages line lands in the system instruction now, not at the next re-mint.
  @objc private func voiceLanguagesChanged() {
    if !AssistantSettings.shared.voiceBaseLanguages.isEmpty {
      Task.detached(priority: .utility) { await PTTLanguageIdentifier.shared.prewarm() }
    }
    guard session != nil, !responding, !minting else { return }
    log("RealtimeHub: voice languages changed — re-warming session with updated instructions")
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
      } catch let error as RealtimeTokenMintError {
        self.minting = false
        self.recordRealtimeMintFailure(error, provider: providerParam, phase: "warm", context: "realtime_mint")
        if error.healthError.failureClass.isAccountWide {
          log("RealtimeHub: account credential failure during mint — staying on cascade")
        } else if !self.failoverToAlternateProvider() {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      } catch let error as CredentialHealthError {
        self.minting = false
        CredentialHealthManager.shared.record(error, context: "realtime_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: error.failureClass.logValue,
          phase: "warm",
          httpStatusCode: error.failureClass.httpStatusCode)
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
      if self.pendingBargeInReplacement != nil {
        self.finishBargeInReplacementAfterSessionStart(provider: provider)
      }
    }
  }

  private func startSession(provider: RealtimeHubProvider, auth: HubAuth) {
    let topLevelContext = voiceSessionSeedContext()
    sessionVoiceSeedContextSnapshot = topLevelContext
    let instructions = RealtimeHubTools.systemInstruction(
      aboutUser: aboutUserCard,
      topLevelConversationContext: topLevelContext,
      userLanguages: AssistantSettings.shared.voiceBaseLanguages)
    let s = RealtimeHubSession(provider: provider, auth: auth, instructions: instructions, delegate: self)
    lastWarmAt = nil
    hubConnected = false
    session = s
    sessionProvider = provider
    sessionAuth = auth
    // Both providers stream native spoken audio (24k PCM) → StreamingPCMPlayer;
    // selected app voice playback handles any no-audio fallback.
    if pcmPlayer == nil {
      pcmPlayer = makePCMPlayer()
    }
    s.start()
    log(
      "RealtimeHub: warming \(provider.displayName) session "
        + "(\(auth.isEphemeral ? "ephemeral/managed" : "client-direct/BYOK"), "
        + "contextChars=\(topLevelContext.count))")
  }

  /// Conversation seed for a fresh realtime session — kernel projection plus floating agents.
  private func voiceSessionSeedContext() -> String {
    var sections: [String] = []
    let kernelSeed = prefetchedVoiceSeedContext.trimmingCharacters(in: .whitespacesAndNewlines)
    if !kernelSeed.isEmpty {
      sections.append(kernelSeed)
    }
    let floatingAgents = prefetchedFloatingAgentStatus
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if !floatingAgents.isEmpty {
      sections.append(floatingAgents)
    }
    return sections.joined(separator: "\n\n")
  }

  /// Prefetch kernel voice seed on PTT key-down so seed-stale reconnect can finish before `beginTurn`.
  func prefetchVoiceSeedContextIfNeeded() {
    voiceSeedPrefetchTask?.cancel()
    voiceSeedPrefetchTask = Task { [weak self] in
      async let seed = FloatingControlBarManager.shared.kernelVoiceSeedContext()
      async let floatingStatus = FloatingControlBarManager.shared.floatingAgentStatusContext()
      let resolvedSeed = await seed
      let resolvedFloatingStatus = await floatingStatus
      await MainActor.run {
        guard let self, !Task.isCancelled else { return }
        self.prefetchedVoiceSeedContext = resolvedSeed
        self.prefetchedFloatingAgentStatus = resolvedFloatingStatus
      }
    }
  }

  private func refreshVoiceSeedContext() async {
    voiceSeedPrefetchTask?.cancel()
    voiceSeedPrefetchTask = nil
    prefetchedVoiceSeedContext = await FloatingControlBarManager.shared.kernelVoiceSeedContext()
    prefetchedFloatingAgentStatus = await FloatingControlBarManager.shared.floatingAgentStatusContext()
  }

  /// Warm sessions bake instructions at connect time. Reconnect when newer typed turns
  /// change the kernel-projected seed so PTT sees the latest main-chat transcript.
  private func reconnectWarmSessionIfSeedStale() {
    guard session != nil else { return }
    let current = voiceSessionSeedContext()
    guard current != sessionVoiceSeedContextSnapshot else { return }
    log(
      "RealtimeHub: voice seed changed — reconnecting warm session "
        + "(was \(sessionVoiceSeedContextSnapshot.count) chars, now \(current.count))")
    teardownSession()
  }

  private func sendVoiceTurnScreenContextIfNeeded(epoch: Int) async {
    guard inputTurnInProgress, epoch == turnEpoch else { return }
    guard voiceTurnScreenContextSentEpoch != epoch else { return }
    guard let targetSession = session else { return }

    let rawPayload = await ScreenContextWorkContextBuilder.payload(arguments: [
      "minutes": 10,
      "max_age_seconds": ScreenContextWorkContextBuilder.voiceTurnStaleCaptureThresholdSeconds,
    ])
    guard inputTurnInProgress, epoch == turnEpoch else { return }
    guard voiceTurnScreenContextSentEpoch != epoch else { return }
    guard self.session === targetSession else { return }

    let envelope: [String: Any] = [
      "permission": [
        "screen_recording": CGPreflightScreenCaptureAccess() ? "granted" : "not_granted"
      ],
      "reason": "ambient_voice_turn_context",
      "context": rawPayload,
      "guidance":
        "Hidden current-work context for this push-to-talk turn. Use it silently if the user asks what is on screen, what they are looking at, or uses deictic phrases like this/that/here. For voice turns, finalized screen context older than 15 seconds is treated as stale. If screen_now.source is live_capture_stale_rewind or raw pixels are needed, call the screenshot tool before answering current screen contents. If permission is denied and the user asked about screen contents, say Omi cannot see the screen yet.",
    ]
    guard
      let data = try? JSONSerialization.data(withJSONObject: envelope, options: [.prettyPrinted, .sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return
    }
    let sent = await targetSession.sendTurnContextText("<auto_voice_screen_context>\n\(json)\n</auto_voice_screen_context>")
    guard inputTurnInProgress, epoch == turnEpoch else { return }
    guard self.session === targetSession else { return }
    guard voiceTurnScreenContextSentEpoch != epoch else { return }
    if sent {
      voiceTurnScreenContextSentEpoch = epoch
    }
  }

  private func recordTurnToKernel(
    userText: String,
    assistantText: String,
    interrupted: Bool
  ) {
    Task {
      await recordTurnToKernelAwaiting(
        userText: userText,
        assistantText: assistantText,
        interrupted: interrupted,
        idempotencyKey: turnIdempotencyKey
      )
    }
  }

  private func recordTurnToKernelAwaiting(
    userText: String,
    assistantText: String,
    interrupted: Bool,
    idempotencyKey: String
  ) async {
    let surface = FloatingControlBarManager.shared.mainChatSurfaceReference()
    await FloatingControlBarManager.shared.recordSurfaceTurn(
      surface: surface,
      userText: userText,
      assistantText: assistantText,
      origin: "realtime_voice",
      interrupted: interrupted,
      idempotencyKey: idempotencyKey
    )
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
    sessionVoiceSeedContextSnapshot = ""
    clearBargeInReplacementState()
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
  }

  private func clearBargeInReplacementState() {
    pendingBargeInReplacement = nil
    pendingBargeInProvider = nil
    pendingBargeInAuth = nil
    bargeInContinuityTask?.cancel()
    bargeInContinuityTask = nil
  }

  @discardableResult
  private func prepareBargeInReplacement() -> Bool {
    guard let provider = sessionProvider, let auth = sessionAuth else { return false }
    session?.detach()
    session?.stop()
    session = nil
    sessionProvider = nil
    sessionAuth = nil
    hubConnected = false
    pendingBargeInReplacement = PendingBargeInReplacementTurn()
    pendingBargeInProvider = provider
    pendingBargeInAuth = auth
    return true
  }

  private func completeBargeInReplacementAfterContinuity(
    interruptedTurn: InterruptedTurnPayload?
  ) {
    bargeInContinuityTask?.cancel()
    bargeInContinuityTask = Task { @MainActor [weak self] in
      guard let self else { return }
      await RealtimeHubBargeInContinuity.prepareReplacementSession(
        interruptedTurn: interruptedTurn,
        recordInterruptedTurn: { [weak self] turn in
          await self?.recordTurnToKernelAwaiting(
            userText: turn.userText,
            assistantText: turn.assistantText,
            interrupted: true,
            idempotencyKey: turn.idempotencyKey
          )
        },
        refreshVoiceSeed: { [weak self] in
          await self?.refreshVoiceSeedContext()
        },
        startReplacementSession: { [weak self] in
          guard let self,
                let provider = self.pendingBargeInProvider,
                let auth = self.pendingBargeInAuth
          else { return }
          self.pendingBargeInProvider = nil
          self.pendingBargeInAuth = nil
          switch auth {
          case .byokKey:
            self.startReplacementSessionForBargeIn(provider: provider, auth: auth)
          case .ephemeral:
            self.remintReplacementSessionForBargeIn(provider: provider)
          }
        }
      )
    }
  }

  @discardableResult
  private func restartSessionForBargeIn(interruptedTurn: InterruptedTurnPayload?) -> Bool {
    guard prepareBargeInReplacement() else { return false }
    completeBargeInReplacementAfterContinuity(interruptedTurn: interruptedTurn)
    return true
  }

  private func remintReplacementSessionForBargeIn(provider: RealtimeHubProvider) {
    guard !minting else {
      log("RealtimeHub[\(provider.displayName)]: barge-in replacement queued behind existing token mint")
      return
    }
    minting = true
    let providerParam = provider == .openai ? "openai" : "gemini"
    log("RealtimeHub[\(provider.displayName)]: minting fresh token for barge-in replacement")
    Task { [weak self] in
      guard let self else { return }
      guard self.pendingBargeInReplacement != nil else {
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
      } catch let error as RealtimeTokenMintError {
        self.minting = false
        self.recordRealtimeMintFailure(
          error,
          provider: providerParam,
          phase: "barge_in_replacement",
          context: "realtime_barge_in_mint")
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if self.shouldFailoverToAlternate(for: error.healthError.failureClass), self.failoverToAlternateProvider() {
          return
        } else if !error.healthError.failureClass.isAccountWide {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      } catch let error as CredentialHealthError {
        self.minting = false
        CredentialHealthManager.shared.record(error, context: "realtime_barge_in_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: error.failureClass.logValue,
          phase: "barge_in_replacement",
          httpStatusCode: error.failureClass.httpStatusCode)
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if self.shouldFailoverToAlternate(for: error.failureClass), self.failoverToAlternateProvider() {
          return
        } else if !error.failureClass.isAccountWide {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      } catch {
        self.minting = false
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: "backend_transient",
          phase: "barge_in_replacement")
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        return
      }
      self.minting = false
      self.startReplacementSessionForBargeIn(provider: provider, auth: .ephemeral(token))
    }
  }

  private func startReplacementSessionForBargeIn(provider: RealtimeHubProvider, auth: HubAuth) {
    startSession(provider: provider, auth: auth)
    finishBargeInReplacementAfterSessionStart(provider: provider)
  }

  private func finishBargeInReplacementAfterSessionStart(provider: RealtimeHubProvider) {
    guard var pending = pendingBargeInReplacement else { return }
    pendingBargeInReplacement = nil
    if pending.pendingBegin {
      pending.pendingBegin = false
      session?.beginInputTurn(interrupting: false)
    }
    flushBargeInReplacementAudioBuffer(pending.audioBuffer)
    if pending.pendingCommit {
      pending.pendingCommit = false
      session?.commitInputTurn()
    }
  }

  private func failBargeInReplacement(provider: RealtimeHubProvider, reason: String) {
    let hadCommittedTurn = pendingBargeInReplacement?.pendingCommit == true
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

  private func flushBargeInReplacementAudioBuffer(_ bufferedChunks: [Data]) {
    guard let s = session, !bufferedChunks.isEmpty else { return }
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
    let voicePlaybackActive = FloatingBarVoicePlaybackService.shared.isSpeaking
    let bargeIn = responding || realtimePlaybackActive || voicePlaybackActive
    let interruptedTurn = bargeIn ? captureInterruptedTurnPayloadIfNeeded() : nil
    responding = false
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    var replacementSessionOwnsInputTurn = false
    var deferredFreshSessionSeedPrefetch = false
    turnTranscript = ""
    assistantText = ""
    speculativeWarmDone = false
    speculativeScreenshot = nil
    audioReceivedThisTurn = false
    turnGeneration &+= 1
    let screenshotTurnGeneration = turnGeneration
    suppressAssistantOutputForCurrentTurn = false
    turnRecorded = false
    turnIdempotencyKey = UUID().uuidString
    if let interruptedTurn {
      turnRecorded = true
      if !providerResponseInFlight || session?.bargeInStrategy != .freshSession {
        Task {
          await recordTurnToKernelAwaiting(
            userText: interruptedTurn.userText,
            assistantText: interruptedTurn.assistantText,
            interrupted: true,
            idempotencyKey: interruptedTurn.idempotencyKey
          )
        }
      }
    }
    turnEpoch += 1
    turnAudio16k.removeAll(keepingCapacity: true)
    earlyLIDTask = nil
    turnEarlyVerdictCode = nil
    fullLIDTask = nil
    testProviderTranscriptOverride = nil  // never leak a test override into a real turn
    pendingVoiceAgentHandoff = nil
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
    voiceTurnScreenContextSentEpoch = nil
    lastTurnAt = Date()
    inputTurnInProgress = true
    inputTurnActivityStartPending = false
    pendingInputTurnInterrupting = providerResponseInFlight
    if bargeIn {
      pcmPlayer?.stop()  // stop the prior reply locally only for a real barge-in.
    }
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
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
        if restartSessionForBargeIn(interruptedTurn: interruptedTurn) {
          replacementSessionOwnsInputTurn = true
          deferredFreshSessionSeedPrefetch = true
          log("RealtimeHub: barge-in — replacing session for clean next turn")
        } else {
          session?.cancelActiveResponse()
        }
      }
    } else if bargeIn {
      log("RealtimeHub[\(providerTag)]: barge-in — stopping local playback tail")
    }
    if !deferredFreshSessionSeedPrefetch {
      let ownsInputTurn = !replacementSessionOwnsInputTurn
      let interrupting = providerResponseInFlight
      Task { @MainActor in
        await self.refreshVoiceSeedContext()
        self.reconnectWarmSessionIfSeedStale()
        self.ensureWarm()
        if ownsInputTurn {
          if await self.waitUntilActive(timeout: 15) {
            self.session?.beginInputTurn(interrupting: interrupting)
            await self.sendVoiceTurnScreenContextIfNeeded(epoch: self.turnEpoch)
          } else {
            self.inputTurnActivityStartPending = true
            self.pendingInputTurnInterrupting = interrupting
            log(
              "RealtimeHub: session not ready for activityStart — will retry on connect")
          }
        }
      }
    } else {
      ensureWarm()
      if !replacementSessionOwnsInputTurn {
        session?.beginInputTurn(interrupting: providerResponseInFlight)
        Task { @MainActor in
          await self.sendVoiceTurnScreenContextIfNeeded(epoch: self.turnEpoch)
        }
      }
    }
    // Capture locally at turn START so the explicit screenshot tool can respond without
    // blocking on screen capture. Do not upload raw pixels speculatively; provider-visible
    // screen access must happen through an explicit tool request.
    Task.detached(priority: .utility) {
      let jpeg = ScreenCaptureManager.captureScreenJPEG()
      await MainActor.run {
        guard self.turnGeneration == screenshotTurnGeneration else { return }
        self.speculativeScreenshot = jpeg
      }
    }
  }

  private func captureInterruptedTurnPayloadIfNeeded() -> InterruptedTurnPayload? {
    guard !turnRecorded else { return nil }
    let heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !heard.isEmpty else { return nil }
    return InterruptedTurnPayload(
      userText: heard,
      assistantText: InterruptedTurnPayload.visibleAssistantText(partialAssistantText: assistantText),
      idempotencyKey: turnIdempotencyKey
    )
  }

  /// Mic chunk (16 kHz PCM16 mono) → resample to the provider's rate → session.
  func feedAudio(_ pcm16k: Data) {
    // Mic chunks arrive on the CoreAudio IOProc thread — @MainActor is NOT enforced
    // here under minimal concurrency checking. Turn-buffer state is main-isolated, so
    // hop before touching it (the session send path below is thread-safe: it hops to
    // the session's own serial queue internally). The hop can land a tail chunk after
    // commitTurn's snapshot; that only trims the LOCAL fallback transcript, never the
    // audio sent to the provider.
    DispatchQueue.main.async { [weak self] in self?.bufferTurnAudio(pcm16k) }
    guard let s = session else {
      if pendingBargeInReplacement != nil {
        pendingBargeInReplacement?.audioBuffer.append(pcm16k)
      } else {
        log("RealtimeHub[\(providerTag)]: dropping mic audio because no realtime session owns this turn")
      }
      return
    }
    sendAudio(pcm16k, to: s)
  }

  /// Keep a local copy of the turn's audio and kick the early language-ID pass once
  /// ~1.5 s has accumulated — it runs WHILE the user is still holding the key, so the
  /// verdict is ready at PTT-up and hinting the provider costs zero perceived latency.
  /// Skipped for single-language users (no identification needed to pick the hint).
  private func bufferTurnAudio(_ pcm16k: Data) {
    guard turnAudio16k.count < Self.maxTurnAudioBytes else { return }
    turnAudio16k.append(pcm16k)
    guard earlyLIDTask == nil, turnAudio16k.count >= Self.earlyLIDBytes else { return }
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    guard candidates.count > 1 else { return }
    let audio = Data(turnAudio16k.prefix(Self.earlyLIDBytes * 2))
    let epoch = turnEpoch
    let task = Task.detached(priority: .userInitiated) {
      await PTTLanguageIdentifier.shared.identify(pcm16k: audio, candidates: candidates)
    }
    earlyLIDTask = task
    // Land the verdict back on the turn as soon as it's ready (normally well before
    // PTT-up). Commit reads it synchronously — no await window, no droppable turn.
    Task { @MainActor [weak self] in
      let verdict = await task.value
      guard let self, self.turnEpoch == epoch else { return }
      self.turnEarlyVerdictCode = verdict.languageCode
    }
  }

  private func sendAudio(_ pcm16k: Data, to s: RealtimeHubSession) {
    let rate = s.requiredInputSampleRate
    let pcm = rate == 16000 ? pcm16k : PushToTalkManager.resamplePCM16(pcm16k, from: 16000, to: rate)
    s.sendAudio(pcm)
  }

  /// PTT-up: end the turn; the model now responds (and may call tools).
  func commitTurn() -> RealtimeHubCommitResult {
    inputTurnInProgress = false
    inputTurnActivityStartPending = false
    responding = true
    // (The screen frame is sent at turn START — see beginTurn — so it has time to
    // upload/decode before the model answers. Nothing to attach here.)
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    // Full-buffer decode for the bubble-fallback transcript (both providers). Kicked
    // BEFORE the session guard; if the commit is rejected the result is simply unused.
    // Runs during the seconds the model spends answering; consumed at turn-done.
    if !turnAudio16k.isEmpty, !candidates.isEmpty {
      let audio = turnAudio16k
      fullLIDTask = Task.detached(priority: .userInitiated) {
        await PTTLanguageIdentifier.shared.identify(pcm16k: audio, candidates: candidates)
      }
    }
    guard let s = session else {
      if var pending = pendingBargeInReplacement {
        pending.pendingCommit = true
        pendingBargeInReplacement = pending
        log(
          "RealtimeHub[\(providerTag)]: barge-in replacement not ready at commit — "
            + "deferring commit (bufferedChunks=\(pending.audioBuffer.count))"
        )
        ensureWarm()
        return .deferredForReplacement
      }
      responding = false
      exitVoiceUI(clearResponseGlow: true)
      return .rejectedNoSession
    }
    // Hint the provider's transcription with the identified language, entirely
    // synchronously: one configured language → hint it directly; several → whatever the
    // mid-hold verdict produced by now (nil clears any stale hint from a prior turn and
    // leaves the provider on auto-detect — same as today's behavior).
    if s.supportsInputTranscriptionLanguage, !candidates.isEmpty {
      s.setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)
    }
    s.commitInputTurn()
    return .accepted
  }

  /// Await a task's value with a REAL deadline on return time. A plain withTaskGroup
  /// race is not enough: the group awaits its remaining children at scope exit and
  /// `Task<T, Never>.value` is not cancellation-interruptible, so the "timeout" would
  /// still block for the task's full duration (e.g. a cold model load). Unstructured
  /// racers + a resume-once gate make the deadline bound the return, not just the value.
  private static func value<T: Sendable>(of task: Task<T, Never>, timeoutMs: UInt64) async -> T? {
    let once = ResumeOnceGate()
    return await withCheckedContinuation { (cont: CheckedContinuation<T?, Never>) in
      Task {
        let v = await task.value
        if once.first() { cont.resume(returning: v) }
      }
      Task {
        try? await Task.sleep(nanoseconds: timeoutMs * 1_000_000)
        if once.first() { cont.resume(returning: nil) }
      }
    }
  }

  /// Abandon the turn without committing (silent tap / cancel). Must leave NO open
  /// turn behind, or the model answers the non-speech later.
  func cancelTurn() {
    inputTurnInProgress = false
    inputTurnActivityStartPending = false
    responding = false
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    turnGeneration &+= 1
    turnTranscript = ""
    assistantText = ""
    pendingVoiceAgentHandoff = nil
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
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
    output: String,
    expectedTurnEpoch: Int? = nil
  ) {
    guard isCurrentSession(source) else {
      log("RealtimeHub[\(providerTag)]: dropping stale tool result \(name)")
      return
    }
    let turnEpoch = expectedTurnEpoch ?? realtimeToolTurnEpoch
    let key = toolCallKey(callId: callId, name: name, turnEpoch: turnEpoch)
    guard turnEpoch == realtimeToolTurnEpoch, pendingRealtimeToolCallIds.contains(key) else {
      log("RealtimeHub[\(providerTag)]: dropping stale tool result \(name) epoch=\(turnEpoch)")
      return
    }
    pendingRealtimeToolCallIds.remove(key)
    source.sendToolResult(callId: callId, name: name, output: output)
  }

  func hubDidConnect(source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    lastWarmAt = Date()
    hubConnected = true  // authenticated + ready — PTT may now route turns to the hub
    log("RealtimeHub: connected (\(sessionProvider?.displayName ?? "?"))")
    if inputTurnInProgress,
      inputTurnActivityStartPending || sessionProvider == .gemini
    {
      session?.beginInputTurn(interrupting: pendingInputTurnInterrupting)
      inputTurnActivityStartPending = false
      Task { @MainActor in
        await self.sendVoiceTurnScreenContextIfNeeded(epoch: self.turnEpoch)
      }
    }
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
    if !text.isEmpty {
      assistantText += text
    }
    if isFinal {
      let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      // Fallback only: if the model produced text but no native audio this turn,
      // speak it through the selected app voice. Normally both providers stream
      // spoken audio (played by StreamingPCMPlayer) so this stays unused.
      if !audioReceivedThisTurn, !reply.isEmpty {
        responseGlowGate.markPlaybackActive()
        FloatingBarVoicePlaybackService.shared.speakOneShot(reply)
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
    expectedTurnEpoch: Int,
    _ body: @escaping () async throws -> String
  ) {
    Task { [weak self] in
      guard let self else { return }
      var out: String
      let suffix = detail.isEmpty ? "" : " \(detail)"
      do {
        out = try await body()
        if out.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { out = emptyText }
        log("RealtimeHub[\(self.providerTag)]: tool \(name)\(suffix) → \(out.prefix(60))")
      } catch {
        let failure = RealtimeHubToolFailure.classify(error)
        out = failure.userFacingOutput(base: errorText)
        log(
          "RealtimeHub[\(self.providerTag)]: tool \(name)\(suffix) FAILED "
            + "failure_type=\(failure.kind.rawValue)"
        )
      }
      self.sendToolResultIfCurrent(
        source: source, callId: callId, name: name, output: out, expectedTurnEpoch: expectedTurnEpoch)
    }
  }

  func hubDidRequestTool(name: String, callId: String, argumentsJSON: String, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    let toolTurnEpoch = realtimeToolTurnEpoch
    pendingRealtimeToolCallIds.insert(toolCallKey(callId: callId, name: name, turnEpoch: toolTurnEpoch))
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
        self.sendToolResultIfCurrent(
          source: source, callId: callId, name: name, output: answer, expectedTurnEpoch: toolTurnEpoch)
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
        self.sendToolResultIfCurrent(
          source: source, callId: callId, name: name, output: out, expectedTurnEpoch: toolTurnEpoch)
      }
    case .getMemories:
      // Fast READ — "who am I" / "what do you know about me". Backend memories+facts.
      runToolAndSpeak(
        source: source,
        callId: callId, name: name,
        emptyText: "I don't have any memories saved about you yet.",
        errorText: "Could not read your memories right now.",
        expectedTurnEpoch: toolTurnEpoch
      ) { try await APIClient.shared.toolGetMemories(limit: 15).resultText }
    case .searchMemories:
      let query = arg("query")
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "q=\"\(query.prefix(60))\"",
        emptyText: "I couldn't find anything about that.",
        errorText: "Could not search your memories right now.",
        expectedTurnEpoch: toolTurnEpoch
      ) { try await APIClient.shared.toolSearchMemories(query: query, limit: 5).resultText }
    case .searchConversations:
      // Capped for voice: top 5, summaries only (no full transcripts).
      let query = arg("query")
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "q=\"\(query.prefix(60))\"",
        emptyText: "I couldn't find a conversation about that.",
        errorText: "Could not search your conversations right now.",
        expectedTurnEpoch: toolTurnEpoch
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
        errorText: "Could not read your recent conversations right now.",
        expectedTurnEpoch: toolTurnEpoch
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
        errorText: "Could not pull up your activity right now.",
        expectedTurnEpoch: toolTurnEpoch
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
        errorText: "Could not read your tasks right now.",
        expectedTurnEpoch: toolTurnEpoch
      ) {
        try await APIClient.shared.toolGetActionItems(
          limit: 25, completed: completed, dueStartDate: dueStart, dueEndDate: dueEnd
        ).resultText
      }
    case .setDesktopAttentionOverride:
      let dismissed = (arguments["dismissed"] as? Bool) ?? true
      let action = dismissed ? "dismiss" : "list"
      if dismissed && !Self.userExplicitlyRequestedPillManagement(action: action, transcript: turnTranscript) {
        log("RealtimeHub[\(providerTag)]: blocked set_desktop_attention_override subject=\(arguments["subjectId"] as? String ?? "")")
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "Dismissal blocked: only dismiss or clear floating agent pills when the user explicitly asks.",
          expectedTurnEpoch: toolTurnEpoch)
        return
      }
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: agentControlService.logDetail(name: name, arguments: arguments),
        emptyText: "No canonical agent data came back.",
        errorText: "Could not reach the agent control plane right now.",
        expectedTurnEpoch: toolTurnEpoch
      ) {
        try await self.agentControlService.executeVoiceTool(name: name, arguments: arguments)
      }
    case .listAgentSessions, .getAgentRun, .cancelAgentRun, .inspectAgentArtifacts, .updateAgentArtifactLifecycle:
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: agentControlService.logDetail(name: name, arguments: arguments),
        emptyText: "No canonical agent data came back.",
        errorText: "Could not reach the agent control plane right now.",
        expectedTurnEpoch: toolTurnEpoch
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
        errorText: "Could not search your screen history right now.",
        expectedTurnEpoch: toolTurnEpoch
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
        errorText: "Could not create the task right now.",
        expectedTurnEpoch: toolTurnEpoch
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
        errorText: "Could not update the task right now.",
        expectedTurnEpoch: toolTurnEpoch
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
        errorText: "Could not create the calendar event right now.",
        expectedTurnEpoch: toolTurnEpoch
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
      let objective = {
        let primary = arg("objective")
        if !primary.isEmpty { return primary }
        return arg("brief")
      }()
      let providerName = ((arguments["provider"] as? String) ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: " ", with: "")
      if !providerName.isEmpty && providerName != "openclaw" && providerName != "hermes" {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "Unsupported agent provider '\(providerName)'. Use 'hermes' or 'openclaw'.",
          expectedTurnEpoch: toolTurnEpoch)
        return
      }
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "\"\(objective.prefix(60))\"",
        emptyText: "Started a background agent.",
        errorText: "Could not start the background agent right now.",
        expectedTurnEpoch: toolTurnEpoch
      ) {
        if !objective.isEmpty {
          FloatingBarVoicePlaybackService.shared.speakBackgroundAgentKickoff()
        }
        var toolArgs = arguments
        toolArgs["objective"] = objective
        let result = try await self.agentControlService.executeVoiceTool(name: "spawn_agent", arguments: toolArgs)
        await AgentPillsManager.shared.refreshProjectedPillsFromKernel()
        return result
      }
    case .screenshot:
      // Raw pixels enter provider context only after an explicit screenshot tool call.
      let shot: Data?
      switch sessionProvider {
      case .openai:
        shot = speculativeScreenshot ?? ScreenCaptureManager.captureScreenJPEG()
        if let shot { session?.injectImage(shot) }
      case .gemini:
        shot = speculativeScreenshot ?? ScreenCaptureManager.captureScreenJPEG()
        if let shot { session?.sendVideoFrame(shot, mime: "image/jpeg", allowClosedActivityWindow: true) }
      case .none:
        shot = nil
      }
      log("RealtimeHub[\(providerTag)]: tool screenshot → ack (\(shot?.count ?? 0) bytes, screen on turn)")
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: shot == nil ? "Could not capture the screen." : "Screen captured.")
    case .pointClick:
      guard
        let x = Self.finiteCoordinate(arguments["x"]),
        let y = Self.finiteCoordinate(arguments["y"])
      else {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "Could not click: point_click requires finite numeric x and y coordinates.")
        return
      }
      let ok = Self.click(at: CGPoint(x: x, y: y))
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: ok ? "Clicked at \(Int(x)), \(Int(y))." : "Could not click.")
    }
  }

  private func handleRealtimeDelegationRequest(
    brief: String,
    title: String?,
    providerName: String,
    source: RealtimeHubSession,
    callId: String,
    name: String,
    expectedTurnEpoch: Int
  ) async {
    let userText = turnTranscript
    var directedProvider: AgentPillsManager.DirectedProvider?
    switch providerName {
    case "openclaw": directedProvider = .openclaw
    case "hermes": directedProvider = .hermes
    case "": directedProvider = nil
    default:
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: "Unsupported agent provider '\(providerName)'. Use 'hermes' or 'openclaw'.",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    }

    let resolution = await AgentDelegationResolver.shared.resolve(
      .init(
        surface: .realtimeVoice,
        userText: userText,
        proposedBrief: brief,
        proposedTitle: title,
        proposedAck: nil,
        directedProvider: directedProvider,
        topLevelContext: voiceSessionSeedContext(),
        agentStatusSummary: AgentPillsManager.shared.snapshotJSON(limit: 8),
        explicitDelegationRequested: true))
    guard isCurrentToolTurn(source: source, callId: callId, name: name, expectedTurnEpoch: expectedTurnEpoch) else {
      log("RealtimeHub[\(providerTag)]: dropping stale spawn_agent resolution before side effects")
      return
    }
    guard resolution.action == .spawn,
          let resolvedBrief = resolution.brief?.trimmingCharacters(in: .whitespacesAndNewlines),
          !resolvedBrief.isEmpty
    else {
      assistantText = resolution.userFacingText
      barState?.isVoiceResponseActive = true
      suppressAssistantOutputForCurrentTurn = false
      log("RealtimeHub[\(providerTag)]: tool spawn_agent blocked by resolver action=\(resolution.action.rawValue)")
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: "No agent started. Ask the user: \(resolution.userFacingText)",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    }

    directedProvider = resolution.directedProvider ?? directedProvider
    if let directedProvider {
      let availability = LocalAgentProviderDetector.availability(for: directedProvider)
      guard availability.isAvailable else {
        let setupPrompt = availability.setupPrompt
        assistantText = setupPrompt
        barState?.isVoiceResponseActive = true
        if !audioReceivedThisTurn {
          FloatingBarVoicePlaybackService.shared.speakOneShot(directedProvider.setupNeededStatus)
        }
        suppressAssistantOutputForCurrentTurn = true
        log("RealtimeHub[\(providerTag)]: tool spawn_agent provider=\(directedProvider.rawValue) unavailable")
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: availability.toolError,
          expectedTurnEpoch: expectedTurnEpoch)
        return
      }
    }

    let model = ShortcutSettings.shared.selectedModel.isEmpty
      ? ModelQoS.Claude.defaultSelection : ShortcutSettings.shared.selectedModel
    guard let pill = AgentDelegationExecutor.shared.spawnResolvedDelegation(
      .init(
        originalUserText: userText,
        brief: resolvedBrief,
        title: resolution.title ?? ((title?.isEmpty == false) ? title : directedProvider?.displayName),
        spokenAck: resolution.ack,
        directedProvider: directedProvider),
      model: model,
      fromVoice: false)
    else {
      assistantText = "What should the background agent do?"
      barState?.isVoiceResponseActive = true
      suppressAssistantOutputForCurrentTurn = false
      log("RealtimeHub[\(providerTag)]: tool spawn_agent refused by delegation executor")
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: "No agent started. Ask the user what the background agent should do.",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    }

    log("RealtimeHub[\(providerTag)]: tool spawn_agent → canonical pill=\"\(pill.title)\" model=\(model) provider=\(directedProvider?.rawValue ?? "default") titled=\(title?.isEmpty == false)")
    let shouldAllowNativePostSpawnAck = !audioReceivedThisTurn
    if !audioReceivedThisTurn {
      let existingAck = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      let resolvedAck = resolution.ack?.trimmingCharacters(in: .whitespacesAndNewlines)
      let ack = existingAck.isEmpty
        ? (resolvedAck?.isEmpty == false ? resolvedAck! : "Starting a background agent.")
        : existingAck
      assistantText = ack
    }
    // Defer durable chat-history handoff recording to hubDidFinishTurn so the
    // final ASR transcript is used instead of a partial interim transcript.
    pendingVoiceAgentHandoff = (title: pill.title, brief: resolvedBrief)
    suppressAssistantOutputForCurrentTurn = !shouldAllowNativePostSpawnAck
    sendToolResultIfCurrent(
      source: source, callId: callId, name: name,
      output: "Agent started.",
      expectedTurnEpoch: expectedTurnEpoch)
  }

  func hubDidFinishTurn(source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    guard pendingRealtimeToolCallIds.isEmpty else {
      log("RealtimeHub[\(providerTag)]: deferring turn done with \(pendingRealtimeToolCallIds.count) tool result(s) pending")
      return
    }
    responding = false
    hubReconnectStrikes = 0  // a completed turn proves the hub works — reset the budget
    var heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    if let forced = testProviderTranscriptOverride {
      testProviderTranscriptOverride = nil
      heard = forced
      log("RealtimeHub: TEST override provider transcript → \"\(forced.prefix(60))\"")
    }
    let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    log("RealtimeHub[\(providerTag)]: turn done — heard=\"\(heard.prefix(80))\" audio=\(audioReceivedThisTurn)")
    if realtimePlaybackActive {
      log("RealtimeHub[\(providerTag)]: server turn done; waiting for local playback to drain")
    }
    // Record the completed turn to the kernel; chat UI updates from turn_recorded events.
    if !turnRecorded {
      turnRecorded = true
      if let handoff = pendingVoiceAgentHandoff {
        pendingVoiceAgentHandoff = nil
        let handoffReply = "Started background agent \"\(handoff.title)\" for: \(handoff.brief)"
        recordTurnToKernel(userText: heard, assistantText: handoffReply, interrupted: false)
      } else {
        let candidates = AssistantSettings.shared.voiceBaseLanguages
        let fullTask = fullLIDTask
        let provider = providerTag
        let capturedIdempotencyKey = turnIdempotencyKey
        Task { @MainActor [weak self] in
          var userText = heard
          var providerLang: String?
          var usedLocal = false
          var localTranscript: String?
          var localLang: String?
          if !candidates.isEmpty, let fullTask {
            providerLang =
              heard.isEmpty
              ? nil : PTTLanguageIdentifier.dominantLanguage(of: heard, hints: [])
            let mismatch = heard.isEmpty || (providerLang.map { !candidates.contains($0) } ?? false)
            if mismatch {
              let verdict = await Self.value(of: fullTask, timeoutMs: 1500)
              localTranscript = verdict?.transcript
              localLang = verdict?.languageCode
              if let local = localTranscript, !local.isEmpty, localLang != nil {
                log(
                  "RealtimeHub: provider transcript lang=\(providerLang ?? "none") outside user "
                    + "languages \(candidates) — using local \(localLang ?? "?") transcript for chat"
                )
                userText = local
                usedLocal = true
              }
            }
          }
          self?.turnIdempotencyKey = capturedIdempotencyKey
          self?.recordTurnToKernel(userText: userText, assistantText: reply, interrupted: false)
          self?.lastTurnDiagnostics = [
            "provider": provider,
            "provider_transcript": heard,
            "provider_transcript_language": providerLang ?? "",
            "saved_user_text": userText,
            "used_local_transcript": usedLocal ? "true" : "false",
            "local_transcript": localTranscript ?? "",
            "local_language": localLang ?? "",
            "assistant_reply": reply,
          ]
        }
      }
    }
    if !pendingCompletedAgentDeltaAckIds.isEmpty {
      DesktopCoordinatorService.shared.acknowledgeCompletedAgentDelta(
        surfaceKind: "ptt",
        ids: pendingCompletedAgentDeltaAckIds,
        completedAtHighWaterMs: pendingCompletedAgentDeltaHighWaterMs
      )
      pendingCompletedAgentDeltaAckIds.removeAll()
      pendingCompletedAgentDeltaHighWaterMs = nil
    }
    exitVoiceUI()
  }

  private nonisolated static func userExplicitlyRequestedPillManagement(
    action: String,
    transcript: String
  ) -> Bool {
    let normalizedAction = action.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard normalizedAction != "list", normalizedAction != "status" else { return true }

    let text = transcript.lowercased()
    let mentionsAgentSurface =
      text.contains("agent") || text.contains("subagent") || text.contains("sub-agent")
      || text.contains("background") || text.contains("pill")
    guard mentionsAgentSurface else { return false }

    switch normalizedAction {
    case "dismiss":
      return text.contains("dismiss") || text.contains("close") || text.contains("remove")
        || text.contains("hide") || text.contains("clear")
    case "clear_completed":
      let mentionsCompleted = text.contains("completed") || text.contains("finished") || text.contains("done")
      let asksToClear = text.contains("clear") || text.contains("dismiss") || text.contains("remove")
      return mentionsCompleted && asksToClear
    default:
      return false
    }
  }

  private func toolCallKey(callId: String, name: String, turnEpoch: Int) -> String {
    "\(turnEpoch):\(name):\(callId)"
  }

  private func isCurrentToolTurn(
    source: RealtimeHubSession,
    callId: String,
    name: String,
    expectedTurnEpoch: Int
  ) -> Bool {
    guard isCurrentSession(source) else { return false }
    let key = toolCallKey(callId: callId, name: name, turnEpoch: expectedTurnEpoch)
    return expectedTurnEpoch == realtimeToolTurnEpoch && pendingRealtimeToolCallIds.contains(key)
  }

  private func clearRealtimeToolTracking() {
    realtimeToolTurnEpoch += 1
    pendingRealtimeToolCallIds.removeAll()
  }

  private func coordinatorOpenLoopsIsEmpty(_ raw: String) -> Bool {
    guard let data = raw.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return false }
    if let openLoops = object["openLoops"] as? [Any] { return openLoops.isEmpty }
    if let items = object["items"] as? [Any] { return items.isEmpty }
    return false
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
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
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
      hasActiveTurn: hasActiveTurn,
      provider: sessionProvider ?? .openai)
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
      activeTurn: hasActiveTurn,
      authMode: authMode,
      failureClass: credentialFailureClass)
    if RealtimeHubCloseClassifier.shouldReportToSentry(closeCategory) {
      logError("RealtimeHub: session error —\(categoryText) provider=\(providerTag)\(safeMessage)")
    } else {
      log("RealtimeHub: session closed —\(categoryText) provider=\(providerTag) aliveFor=\(Int(aliveFor))s \(message)")
    }
    // The reply is dead — stop any buffered audio before collapsing.
    pcmPlayer?.stop()
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    exitVoiceUI(clearResponseGlow: true)
    teardownSession()
    // Provider switching changes the user's voice identity and can fragment model-local
    // context. Only switch for stable credential/quota classes; transient fast closes
    // re-warm the same provider and rely on the shared continuity packet.
    if case .providerAuthFailed = credentialFailureClass {
      if aliveFor < 10, failoverToAlternateProvider() { return }
      return
    }
    if case .providerQuotaExceeded = credentialFailureClass {
      if failoverToAlternateProvider() { return }
      return
    }
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
    // When selected app voice playback is handling a no-native-audio fallback
    // or spawn-agent kickoff sample, keep the glow active until the shared
    // playback service finishes and clears it.
    if clearResponseGlow || (!audioReceivedThisTurn && !FloatingBarVoicePlaybackService.shared.isSpeaking) {
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

  nonisolated static func finiteCoordinate(_ value: Any?) -> Double? {
    let coordinate: Double?
    switch value {
    case is Bool:
      coordinate = nil
    case let number as NSNumber:
      coordinate = number.doubleValue
    case let double as Double:
      coordinate = double
    case let int as Int:
      coordinate = Double(int)
    default:
      coordinate = nil
    }
    guard let coordinate, coordinate.isFinite else { return nil }
    return coordinate
  }
}

/// Resume-at-most-once gate for continuation races (see RealtimeHubController.value(of:)).
private final class ResumeOnceGate: @unchecked Sendable {
  private let lock = NSLock()
  private var done = false
  func first() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    if done { return false }
    done = true
    return true
  }
}

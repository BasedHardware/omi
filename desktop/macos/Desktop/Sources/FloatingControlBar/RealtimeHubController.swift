import AppKit
import CoreGraphics
import Foundation
import OmiSupport

// MARK: - Realtime Hub Controller (Phase 1)
//
// Owns one persistent, warm RealtimeHubSession as the physical voice provider
// driver. The kernel remains the single semantic router and tool authority. It:
//   • keeps the WS warm between PTT turns (no reopen per press),
//   • feeds mic PCM in and plays the model's spoken reply out
//     (provider native audio → StreamingPCMPlayer; selected app voice fallback → FloatingBarVoicePlaybackService),
//   • submits every model tool call to the kernel's durable external-run ledger;
//     Swift executes only the generated realtime-owned commands returned through
//     the validated authorized-tool envelope.
//
// Provider tool proposals are untrusted until the kernel resolves the canonical
// route and authorizes the active run/attempt capability.

#if DEBUG
/// Deterministic provider decisions for the hermetic desktop profile. This type
/// is absent from release builds and is reachable only through `ptt_test_turn`.
struct RealtimeLocalProfileTurnPlan: Equatable {
  struct Spawn: Equatable {
    let objective: String
    let title: String
  }

  static let exactMemoryAgentRequest =
    "Have an agent look through my memories today and surface one surprising insight."

  let assistantText: String
  let spawn: Spawn?

  static func make(
    transcript rawTranscript: String,
    voiceContext: String,
    localProfileEnabled: Bool
  ) -> Self? {
    guard localProfileEnabled else { return nil }
    let transcript = rawTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !transcript.isEmpty else { return nil }

    if transcript == exactMemoryAgentRequest {
      return Self(
        assistantText: "I started a background agent to review today's memories.",
        spawn: Spawn(objective: transcript, title: "Today's memory insight"))
    }

    if transcript.localizedCaseInsensitiveContains("what was the last thing i asked you for"),
      let reference = lastHarnessReference(in: voiceContext)
    {
      return Self(
        assistantText: "The last request was the background-agent task tagged \(reference).",
        spawn: nil)
    }

    if let marker = lastHarnessReference(in: transcript) {
      return Self(assistantText: "Stub saw marker: \(marker)", spawn: nil)
    }
    return Self(assistantText: "Hermetic realtime stub response.", spawn: nil)
  }

  private static func lastHarnessReference(in text: String) -> String? {
    guard
      let expression = try? NSRegularExpression(
        pattern: #"(?:GAUNTLET|RESILIENCE)[A-Z0-9-]*"#),
      let match = expression.matches(
        in: text, range: NSRange(text.startIndex..., in: text)).last,
      let range = Range(match.range, in: text)
    else { return nil }
    return String(text[range])
  }
}
#endif

/// A canonical spawn receipt proves that the child exists, but it does not
/// authorize the realtime provider to narrate the child's eventual outcome.
/// Provider continuations remain necessary for transport completion, but are
/// not presented to the user for that turn.
enum RealtimeAcceptedSpawnPresentationPolicy {
  static func suppressesProviderContinuation(hasCanonicalSpawnReceipt: Bool) -> Bool {
    hasCanonicalSpawnReceipt
  }

  static func requiresProviderContinuation(hasCanonicalSpawnReceipt: Bool) -> Bool {
    !hasCanonicalSpawnReceipt
  }
}

/// Keeps the response glow tied to perceived playback instead of raw PCM chunk
/// boundaries. Realtime providers can leave short gaps between streamed audio
/// buffers; clearing the glow on every empty queue makes the notch resize and
/// shimmer restart repeatedly.
@MainActor
final class RealtimeResponseGlowGate {
  private let idleClearDelay: TimeInterval
  private let scheduler: DelayedActionScheduling
  private let setActive: (Bool, VoiceOutputLease?) -> Void
  private var idleClearCancellation: DelayedActionCancellation?
  private var lease: VoiceOutputLease?
  private(set) var isActive = false

  init(
    idleClearDelay: TimeInterval = 0.75,
    scheduler: DelayedActionScheduling? = nil,
    setActive: @escaping (Bool, VoiceOutputLease?) -> Void
  ) {
    self.idleClearDelay = idleClearDelay
    self.scheduler = scheduler ?? TaskDelayedActionScheduler()
    self.setActive = setActive
  }

  func markPlaybackActive(lease: VoiceOutputLease) {
    idleClearCancellation?.cancel()
    idleClearCancellation = nil
    self.lease = lease
    guard !isActive else { return }
    isActive = true
    setActive(true, lease)
  }

  func scheduleIdleClear() {
    idleClearCancellation?.cancel()
    let expectedLease = lease
    idleClearCancellation = scheduler.schedule(after: idleClearDelay) { [weak self] in
      guard let self, self.lease == expectedLease else { return }
      self.idleClearCancellation = nil
      self.isActive = false
      self.lease = nil
      self.setActive(false, expectedLease)
    }
  }

  func clearImmediately() {
    idleClearCancellation?.cancel()
    idleClearCancellation = nil
    let expectedLease = lease
    lease = nil
    guard isActive else {
      setActive(false, expectedLease)
      return
    }
    isActive = false
    setActive(false, expectedLease)
  }
}

@MainActor
final class RealtimeHubController: NSObject, RealtimeHubSessionDelegate {
  static let shared = RealtimeHubController()

  var session: RealtimeHubSession?
  private var voiceSessionID: VoiceSessionID?
  /// Shared with the screen-evidence receipt extension to fence image dispatch to one response.
  var voiceResponseID: VoiceResponseID?
  private var sessionProvider: RealtimeHubProvider?
  private var sessionAuth: HubAuth?
  /// Sessions detach from logical ownership synchronously, then close on their
  /// transport queue. Retain them until that queue drains so an effective-owner
  /// transition can await every teardown already initiated by reducer effects.
  private var detachedSessionsAwaitingDrain: [ObjectIdentifier: RealtimeHubSession] = [:]
  private struct PhysicalSessionOwnerBinding {
    let sourceID: ObjectIdentifier
    let ownerScope: RealtimeHubOwnerScope
  }
  /// Replaced atomically with each physical session. The identity fields are
  /// immutable and the object identifier prevents a scope from drifting onto a
  /// different socket through an independent property assignment.
  private var sessionOwnerBinding: PhysicalSessionOwnerBinding?
#if DEBUG
  /// Installed only for the lifetime of one local-profile `ptt_test_turn`.
  /// Production builds have no provider-warm bypass surface.
  private var localProfileTransportAuthority: RealtimeLocalProfileTransportAuthority?
#endif
  private var sessionOwnerScope: RealtimeHubOwnerScope? {
    guard let session, let binding = sessionOwnerBinding,
      binding.sourceID == ObjectIdentifier(session)
    else { return nil }
    return binding.ownerScope
  }
  private var pcmPlayer: StreamingPCMPlayer?
  lazy var responseGlowGate = RealtimeResponseGlowGate { [weak self] active, lease in
    guard self != nil, let lease,
      VoiceTurnCoordinator.shared.activeTurnID == lease.turnID
    else { return }
    VoiceTurnCoordinator.shared.send(.responseActiveChanged(turnID: lease.turnID, active: active))
  }
  // Per-turn state.
  private var turnTranscript = ""
  private var providerTranscriptFinalized = false
  /// Last provider input-transcript mutation for the active PTT turn. Permission
  /// tools use this only to wait for a stable live transcript; it is reset with
  /// every turn and is never persisted.
  /// Screen-evidence telemetry records only whether this current turn saw a transcript event.
  var lastInputTranscriptUpdateAt: Date?
  var assistantText = ""
  private var audioReceivedThisTurn = false
  /// Stable per-turn key for kernel idempotent voice-turn persistence.
  private var turnIdempotencyKey = ""
  /// (a) Pure cache of the typed kernel voice-context snapshot. Rebuild via
  /// `refreshVoiceContextSnapshot` / `fetchVoiceContextSnapshot` on relaunch.
  private var prefetchedVoiceContext = ""
  private var prefetchedVoiceContextSessionID = ""
  private var prefetchedVoiceContextFreshnessIdentity = ""
  private var prefetchedVoiceContextPlanID = ""
  private var prefetchedVoiceStableCacheIdentity = ""
  private var prefetchedVoiceDynamicContextIdentity = ""
  private var pendingContextCacheReplacement = false
  private var prefetchedVoiceSemanticGuidance = ""
  /// Exact Node registry projection from the bridge init handshake. Empty is a
  /// fail-closed value until the runtime has declared available adapters.
  private var registeredDirectedProviderIDs: [String] = []
  private var prefetchedVoiceContextTurnIDs: Set<String> = []
  private var prefetchedVoiceContextOwnerScope: RealtimeHubOwnerScope?
  /// Typed snapshot identity baked into the current warm session's instructions.
  private var sessionVoiceContextFreshnessIdentity = ""
  /// A PTT current-screen answer is grounded in exactly one pre-overlay, turn-scoped image.
  /// It is never ambient context and is released on terminal/cancel paths.
  var screenEvidence: RealtimeScreenEvidence?
  var screenEvidenceReadiness: RealtimeScreenEvidenceReadiness?
  var screenGroundingState: RealtimeScreenGroundingState = .inactive
  /// Latest safe protocol disposition, surfaced only through the non-production automation
  /// bridge. This lets a PTT probe distinguish a provider wait from a local lifecycle failure.
  var lastScreenEvidenceProtocolCompletion: RealtimeScreenEvidenceProtocolCompletion = .notRun
  var authorizedRealtimeScreenshotImages: [String: RealtimeScreenEvidenceAttachment] = [:]
  var screenAnswerPresented = false
  private var voiceContextPrefetchTask: Task<Void, Never>?
  private var voiceContextRefreshGeneration: UInt64 = 0
  private var turnPreparationTask: Task<Void, Never>?
  /// (b) Genuinely local: in-flight write Tasks + optional completion receipts.
  /// Receipts shadow kernel acceptance only until consumed; on relaunch they are
  /// rebuilt via `RealtimeHubContinuityRestore.kernelOwnsExchange`, never disk.
  private let turnPersistenceLedger = RealtimeTurnPersistenceLedger()
  private struct AcceptedSpawnJournalReceipt {
    let ownerID: String
    let receipt: RealtimeSpawnJournalReceipt
  }
  /// (c) Shadow truth: mirrors a kernel-accepted spawn exchange for this process.
  /// Authoritative owner is the kernel journal / voice-context turn IDs; restore
  /// through `RealtimeHubContinuityRestore` + `RealtimeTurnJournalAuthority`.
  private var acceptedSpawnJournalReceiptByContinuityKey: [
    String: AcceptedSpawnJournalReceipt
  ] = [:]
  private let legacyVoiceJournalImportStore = LegacyVoiceJournalImportStore.shared
  private var legacyVoiceJournalImportTask: Task<Void, Never>?
  private var legacyVoiceJournalImportedOwners = Set<String>()
  private var deferredSessionRefreshTask: Task<Void, Never>?
  private var canceledTurnRewarmTask: Task<Void, Never>?
  /// (b) Genuinely local race fence — never observed by the kernel.
  private var cancelContinuityFenceActive = false
  private var cancelContinuityFenceTurnID: VoiceTurnID?
  private var bargeInContinuityTask: Task<Void, Never>?
  private var bargeInReplacementGeneration: UInt64 = 0
  private var pendingBargeInProvider: RealtimeHubProvider?
  private var pendingBargeInAuth: HubAuth?
  private var pendingBargeInOwnerScope: RealtimeHubOwnerScope?
  /// Gemini input-transcription events do not carry a stable per-item ID. Once a
  /// turn completes, require a fresh provider session before accepting another PTT
  /// turn so a late event from A can never be attributed to B.
  private var geminiSessionNeedsTurnBoundary = false

  // Per-turn language identification (multi-language PTT).
  /// Local copy of this turn's mic audio (16 kHz s16le mono) for on-device language ID.
  private var turnAudio16k = Data()
  /// Monotonic turn counter guarding async language-ID results against cross-turn races.
  private var turnEpoch = 0
  /// `beginInputTurn` was deferred because the warm session was still opening after a context reconnect.
  private var inputTurnActivityStartPending = false
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
  /// Harness-visible outcome of the most recent externally authorized tool.
  /// An empty error means the kernel accepted and executed the proposal.
  private var lastExternalToolName = ""
  private var lastExternalToolErrorCode = ""
  private static let maxTurnAudioBytes = 3_840_000  // 120 s @ 16 kHz s16le
  private static let earlyLIDBytes = 48_000  // 1.5 s
  /// Transport correlation only. Logical pending-tool ownership and completion
  /// live in `VoiceTurn`; each correlation returns the reducer-issued identity.
  private var toolEffectIdentityByTransportKey: [String: VoiceEffectIdentity] = [:]
  /// (b) Genuinely local: in-flight begin-external-run Task handle. Kernel owns
  /// the resulting binding; this Task dies with the process and is not rebuilt.
  private struct ExternalRunAuthorityState {
    let ownerID: String
    let turnID: VoiceTurnID
    let task: Task<ExternalSurfaceRunBinding, Error>
  }
  private struct ExternalRunTerminalizationResult: Sendable {
    let binding: ExternalSurfaceRunBinding?
    let cleanupCapability: RuntimeOwnerTransitionCleanupCapability?
    let closed: Bool
    let failureCode: String?
  }
  private enum ExternalRunBindingResolution: Sendable {
    case bound(ExternalSurfaceRunBinding)
    case failed(String)
  }
  private struct TrackedExternalRunTerminalization {
    let ownerID: String
    let terminalStatus: ExternalSurfaceRunTerminalStatus
    let errorCode: String?
    let task: Task<ExternalRunTerminalizationResult, Never>
  }
  private static let externalRunClientID = "omi-realtime-voice"
  private static let externalRunHarnessMode = "piMono"
  private var externalRunAuthorityState: ExternalRunAuthorityState?
  private var externalRunTerminalizations: [UUID: TrackedExternalRunTerminalization] = [:]
  /// The begin RPC itself is bounded to 10 seconds. Two seconds of scheduling
  /// margin keeps owner replacement bounded without abandoning a request that
  /// can still create a physical kernel run. A task still in process startup is
  /// cancelled; AgentRuntimeProcess revalidates A immediately before its wire
  /// mutation, so it cannot create a late run after B becomes visible.
  private static let ownerTransitionExternalRunBindingTimeout: Duration = .seconds(12)
#if DEBUG
  private var ownerBoundaryExternalRunCompletion:
    (@Sendable (
      ExternalSurfaceRunBinding,
      ExternalSurfaceRunTerminalStatus,
      String?,
      RuntimeOwnerTransitionCleanupCapability?
    ) async throws -> Void)?
#endif
  /// (b) Genuinely local: in-flight authorized tool envelopes for this process.
  var authorizedRealtimeInvocations: [String: RealtimeAuthorizedToolInvocation] = [:]
  /// (b) Genuinely local delivery dedupe for this process. Kernel authorizes
  /// each run; this set only suppresses duplicate command delivery in-session.
  private var completedAuthorizedRealtimeInvocationIDs: Set<String> = []
  var realtimeToolTurnEpoch = 0
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
  private var pendingSessionRefreshReason: String?
  /// Invalidates delayed reconnect callbacks admitted by a previous owner.
  private var ownerBoundaryGeneration: UInt64 = 0
  /// After this many consecutive fast failures (e.g. a stale/revoked key failing auth),
  /// the hub stops re-warming so it doesn't hammer a dead endpoint.
  private static let maxReconnectStrikes = 5
  /// True only while a session is connected + authenticated for `sessionProvider`. This is
  /// what gates `isActive`: a PTT turn enters hub mode only when the hub is genuinely
  /// connected right now; otherwise it transparently uses the legacy cascade. Set in
  /// hubDidConnect (fires post-auth, on "ready") and cleared on teardown/error, so a
  /// stale/revoked key — which never connects — never costs the user a turn.
  private var hubConnected = false
  /// Monotonic owner for realtime playback-idle callbacks. The PCM player can
  /// complete older buffers after a stop, rebuild, or newer audio chunk; only the
  /// latest scheduled playback epoch may publish a drain for the current lease.
  private var realtimePlaybackEpoch = 0

  /// Log tag for the currently-connected provider.
  var providerTag: String { sessionProvider == .gemini ? "gemini" : "openai" }

  private var reducerCapturingInput: Bool {
    VoiceTurnCoordinator.shared.activeTurn?.phase.isRecording == true
  }

  private var reducerProviderActive: Bool {
    guard let phase = VoiceTurnCoordinator.shared.activeTurn?.phase else { return false }
    switch phase {
    case .awaitingResponse, .awaitingTools, .playing:
      return true
    case .idle, .pendingLockDecision, .recording, .lockedRecording, .finalizing,
      .awaitingJournal, .terminal:
      return false
    }
  }

  private var reducerNativePlaybackActive: Bool {
    VoiceTurnCoordinator.shared.outputSnapshot.activeLease?.lane == .nativeRealtime
  }

  private var reducerInterruptsPreviousTurn: Bool {
    VoiceTurnCoordinator.shared.activeTurn?.supersededTurnID != nil
  }

  private var hasActiveVoiceTurn: Bool {
    VoiceTurnCoordinator.shared.activeTurnID != nil
  }

  private var lifecycleSnapshot: RealtimeHubLifecycleSnapshot {
    RealtimeHubLifecycleSnapshot(
      capturingInput: reducerCapturingInput,
      providerActive: reducerProviderActive,
      playbackActive: reducerNativePlaybackActive,
      pendingToolCount: VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs.count ?? 0,
      coordinatorTurnActive: VoiceTurnCoordinator.shared.activeTurnID != nil,
      minting: minting)
  }

  /// In-flight ephemeral mint guard (managed users).
  private var minting = false
  private var mintGeneration: UInt64 = 0
  private var mintOwnerScope: RealtimeHubOwnerScope?
  /// A Gemini active-reply barge-in replaces the whole session. Managed sessions
  /// need a fresh one-use token first, so hold early mic chunks/commit until the
  /// replacement session exists and can use its normal socket-open buffering.
  private var replacementAudioBuffer: RealtimeReplacementAudioBuffer?
  /// A session can be replaced between PTT-down and its first microphone chunk.
  /// Preserve that one turn until the replacement session is authenticated, then
  /// replay it in order before committing.
  private var reconnectAudioBuffer: RealtimeReconnectAudioBuffer?

  /// Failover chain: when the Auto-selected (primary) provider can't connect, the hub
  /// tries the OTHER realtime provider before dropping to the legacy Claude cascade.
  /// nil = on the primary; non-nil = the provider we failed over TO.
  private var fallbackProvider: RealtimeHubProvider?
  /// Reason passed to ``failoverToAlternateProvider``; cleared after a successful connect on the alternate.
  private var pendingFailoverReason: String?

  private override init() {
    super.init()
    Task { [weak self] in
      await AgentRuntimeProcess.shared.setAuthorizedRealtimeToolHandler { [weak self] command in
        guard let self else {
          return .failed(
            Self.authorizedRealtimeToolError(code: "realtime_handler_unavailable"))
        }
        return await self.executeAuthorizedRealtimeTool(command)
      }
    }
  }

  /// The realtime provider to actually connect: the failover pick if we've switched to
  /// it, otherwise the user/Auto-selected one.
  private var effectiveProvider: RealtimeHubProvider {
    fallbackProvider ?? RealtimeHubSettings.shared.provider
  }

  private var currentOwnerScope: RealtimeHubOwnerScope {
    RealtimeHubOwnerScope.capture(currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
  }

  private func isOwnerScopeCurrent(_ scope: RealtimeHubOwnerScope) -> Bool {
    scope.isCurrent(currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
  }

#if DEBUG
  private func isAuthorizedLocalProfileTransport(_ source: RealtimeHubSession? = nil) -> Bool {
    guard let authority = localProfileTransportAuthority else { return false }
    let candidate = source ?? session
    return authority.accepts(
      sourceID: candidate.map(ObjectIdentifier.init),
      currentOwnerID: RuntimeOwnerIdentity.currentOwnerId(),
      localProfileEnabled: DesktopLocalProfile.isEnabled,
      authorizationIsCurrent: RuntimeOwnerIdentity.isAuthorizationCurrent(
        authority.authorizationSnapshot))
  }
#endif

  /// Account replacement is a hard physical boundary: detach the old socket,
  /// cancel any reducer turn still owned by it, and discard its rendered context
  /// before the replacement account can warm a session.
  private func discardSessionAfterOwnerChange() {
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID {
      _ = VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID)
    }
    teardownSession()
    prefetchedVoiceContext = ""
    prefetchedVoiceContextSessionID = ""
    prefetchedVoiceContextFreshnessIdentity = ""
    prefetchedVoiceContextPlanID = ""
    prefetchedVoiceStableCacheIdentity = ""
    prefetchedVoiceDynamicContextIdentity = ""
    prefetchedVoiceSemanticGuidance = ""
    prefetchedVoiceContextTurnIDs.removeAll()
    prefetchedVoiceContextOwnerScope = nil
  }

  /// Hard physical owner boundary. Persisted defaults still name the previous
  /// owner, but authorization is already revoked; transport queues drain before
  /// defaults mutate to the replacement owner.
  func quiesceForEffectiveOwnerTransition(
    previousOwnerID: String?,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability
  ) async {
    guard RuntimeOwnerIdentity.authorizesTransitionCleanup(
      cleanupCapability,
      previousOwnerID: previousOwnerID)
    else {
      assertionFailure("Realtime owner cleanup capability mismatched")
      return
    }
    if let externalRunAuthorityState {
      if externalRunAuthorityState.ownerID == previousOwnerID {
        completeExternalRunAuthority(
          turnID: externalRunAuthorityState.turnID,
          reason: .ownerChanged)
      } else {
        assertionFailure("Realtime external run owner did not match transition cleanup owner")
        externalRunAuthorityState.task.cancel()
        self.externalRunAuthorityState = nil
      }
    }
    ownerBoundaryGeneration &+= 1
    voiceContextRefreshGeneration &+= 1
    turnPersistenceLedger.cancelAll()
    turnEpoch &+= 1
    realtimePlaybackEpoch &+= 1
    mintGeneration &+= 1
    minting = false
    mintOwnerScope = nil

    voiceContextPrefetchTask?.cancel()
    voiceContextPrefetchTask = nil
    turnPreparationTask?.cancel()
    turnPreparationTask = nil
    legacyVoiceJournalImportTask?.cancel()
    legacyVoiceJournalImportTask = nil
    deferredSessionRefreshTask?.cancel()
    deferredSessionRefreshTask = nil
    canceledTurnRewarmTask?.cancel()
    canceledTurnRewarmTask = nil
    earlyLIDTask?.cancel()
    earlyLIDTask = nil
    fullLIDTask?.cancel()
    fullLIDTask = nil

    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
    pendingSessionRefreshReason = nil
    reconnectPending = false
    hubReconnectStrikes = 0
    fallbackProvider = nil
    pendingFailoverReason = nil
    cancelContinuityFenceActive = false
    cancelContinuityFenceTurnID = nil
    inputTurnActivityStartPending = false
    turnTranscript = ""
    providerTranscriptFinalized = false
    lastInputTranscriptUpdateAt = nil
    assistantText = ""
    audioReceivedThisTurn = false
    lastExternalToolName = ""
    lastExternalToolErrorCode = ""
    turnIdempotencyKey = ""
    turnAudio16k.removeAll()
    turnEarlyVerdictCode = nil
    lastTurnDiagnostics.removeAll()
    testProviderTranscriptOverride = nil
    acceptedSpawnJournalReceiptByContinuityKey.removeAll()
    prefetchedVoiceContext = ""
    prefetchedVoiceContextSessionID = ""
    prefetchedVoiceContextFreshnessIdentity = ""
    prefetchedVoiceContextPlanID = ""
    prefetchedVoiceStableCacheIdentity = ""
    prefetchedVoiceDynamicContextIdentity = ""
    prefetchedVoiceSemanticGuidance = ""
    prefetchedVoiceContextTurnIDs.removeAll()
    prefetchedVoiceContextOwnerScope = nil

    if let detachedSession = detachPhysicalSessionForTeardown() {
      schedulePhysicalSessionTeardown(detachedSession)
    }
    let sessionsToDrain = Array(detachedSessionsAwaitingDrain.values)
    for detachedSession in sessionsToDrain {
      await detachedSession.stopAndWait()
      detachedSessionsAwaitingDrain.removeValue(forKey: ObjectIdentifier(detachedSession))
    }
    await drainExternalRunTerminalizations(
      previousOwnerID: previousOwnerID,
      cleanupCapability: cleanupCapability)
    log(
      "RealtimeHub: drained physical session before replacing owner "
        + (previousOwnerID == nil ? "signed_out" : "authenticated"))
  }

  private func drainExternalRunTerminalizations(
    previousOwnerID: String?,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability
  ) async {
    guard RuntimeOwnerIdentity.authorizesTransitionCleanup(
      cleanupCapability,
      previousOwnerID: previousOwnerID)
    else {
      assertionFailure("Realtime cleanup capability expired before external-run drain")
      return
    }
    guard let previousOwnerID else {
      if !externalRunTerminalizations.isEmpty {
        assertionFailure("Signed-out cleanup found an owner-bound external run")
      }
      return
    }

    let matching = externalRunTerminalizations.filter { $0.value.ownerID == previousOwnerID }
    for (id, tracked) in matching {
      var result = await tracked.task.value
      if !result.closed, let binding = result.binding {
        result = await terminalizeExternalRun(
          binding: binding,
          terminalStatus: tracked.terminalStatus,
          errorCode: tracked.errorCode,
          cleanupCapability: cleanupCapability)
      }
      if let usedCapability = result.cleanupCapability,
        usedCapability != cleanupCapability
      {
        assertionFailure("External-run cleanup used the wrong transition generation")
      }
      if !result.closed, result.binding != nil {
        assertionFailure(
          "External voice run remained active at owner boundary: "
            + (result.failureCode ?? "unknown"))
      }
      removeTrackedExternalRunTerminalization(id)
    }
#if DEBUG
    ownerBoundaryExternalRunCompletion = nil
#endif
  }

#if DEBUG
  /// Installs a detached, never-started physical session so owner-boundary
  /// tests exercise the production controller without network or wall clocks.
  func installOwnerBoundaryFixture(ownerID: String) {
    teardownSession()
    let ownerScope = RealtimeHubOwnerScope.authenticated(ownerID)
    let fixtureSession = RealtimeHubSession(
      provider: .openai,
      auth: .byokKey("owner-boundary-fixture"),
      instructions: "owner-boundary-fixture",
      delegate: self)
    session = fixtureSession
    voiceSessionID = VoiceSessionID()
    sessionProvider = .openai
    sessionAuth = .byokKey("owner-boundary-fixture")
    sessionOwnerBinding = PhysicalSessionOwnerBinding(
      sourceID: ObjectIdentifier(fixtureSession),
      ownerScope: ownerScope)
    hubConnected = true
    prefetchedVoiceContext = "owner-private-context"
    prefetchedVoiceContextSessionID = "owner-session"
    prefetchedVoiceContextFreshnessIdentity = "owner-freshness"
    prefetchedVoiceContextPlanID = "owner-plan"
    prefetchedVoiceStableCacheIdentity = "owner-stable-cache"
    prefetchedVoiceDynamicContextIdentity = "owner-dynamic-context"
    prefetchedVoiceSemanticGuidance = "owner semantic guidance"
    prefetchedVoiceContextTurnIDs = ["owner-turn"]
    prefetchedVoiceContextOwnerScope = ownerScope
    pendingSessionRefreshReason = "owner-fixture-refresh"
    turnAudio16k = Data(repeating: 1, count: 16)
  }

  /// Hermetic kernel-side external-run seam. The supplied closure is the
  /// physical daemon completion boundary; owner-transition tests suspend it to
  /// prove persisted owner mutation waits for a terminal receipt.
  func installOwnerBoundaryExternalRunFixture(
    ownerID: String,
    turnID: VoiceTurnID,
    onComplete: @escaping @Sendable (
      ExternalSurfaceRunBinding,
      ExternalSurfaceRunTerminalStatus,
      String?,
      RuntimeOwnerTransitionCleanupCapability?
    ) async throws -> Void
  ) {
    let binding = ExternalSurfaceRunBinding(
      ownerID: ownerID,
      sessionID: "owner-boundary-session",
      turnID: turnID.rawValue.uuidString.lowercased(),
      runID: "owner-boundary-run",
      attemptID: "owner-boundary-attempt",
      duplicate: false)
    externalRunAuthorityState?.task.cancel()
    externalRunAuthorityState = ExternalRunAuthorityState(
      ownerID: ownerID,
      turnID: turnID,
      task: Task { binding })
    ownerBoundaryExternalRunCompletion = onComplete
  }

  /// Installs a begin task that completed without a binding. This models the
  /// conservative side of a lost/failed begin receipt: Swift cannot prove that
  /// Node did not create a run, so transition tracking must retain the entry
  /// until the owner-wide runtime revocation barrier completes.
  func installOwnerBoundaryUnresolvedExternalRunFixture(
    ownerID: String,
    turnID: VoiceTurnID
  ) {
    externalRunAuthorityState?.task.cancel()
    externalRunAuthorityState = ExternalRunAuthorityState(
      ownerID: ownerID,
      turnID: turnID,
      task: Task<ExternalSurfaceRunBinding, Error> {
        throw ExternalSurfaceAuthorityError(code: "owner_boundary_begin_receipt_lost")
      })
    ownerBoundaryExternalRunCompletion = nil
  }

  /// Deterministically awaits and reconciles every tracked terminalization so
  /// tests inspect the same pruning policy as the production completion task.
  func settleOwnerBoundaryExternalRunTerminalizations() async {
    let tracked = externalRunTerminalizations
    for (id, terminalization) in tracked {
      let result = await terminalization.task.value
      reconcileTrackedExternalRunTerminalization(id: id, result: result)
    }
  }

  var ownerBoundarySnapshot: RealtimeHubOwnerBoundarySnapshot {
    RealtimeHubOwnerBoundarySnapshot(
      hasPhysicalSession: session != nil,
      physicalOwnerID: sessionOwnerScope?.authenticatedOwnerID,
      prefetchedOwnerID: prefetchedVoiceContextOwnerScope?.authenticatedOwnerID,
      prefetchedContextIsEmpty: prefetchedVoiceContext.isEmpty,
      hasPendingOwnerWork: pendingSessionRefreshReason != nil
        || !turnPersistenceLedger.pendingContinuityKeys.isEmpty
        || voiceContextPrefetchTask != nil
        || turnPreparationTask != nil
        || !detachedSessionsAwaitingDrain.isEmpty
        || externalRunAuthorityState != nil
        || !externalRunTerminalizations.isEmpty,
      hubConnected: hubConnected,
      turnAudioByteCount: turnAudio16k.count)
  }
#endif

  @discardableResult
  private func discardMismatchedSessionIfNeeded() -> Bool {
    guard session != nil else { return false }
    guard
      !RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: sessionOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    else { return false }
    log("RealtimeHub: detaching physical session after authenticated owner changed")
    discardSessionAfterOwnerChange()
    return true
  }

  private func beginMint(ownerScope: RealtimeHubOwnerScope) -> UInt64? {
    guard !minting else { return nil }
    mintGeneration &+= 1
    minting = true
    mintOwnerScope = ownerScope
    return mintGeneration
  }

  @discardableResult
  private func releaseMint(generation: UInt64, ownerScope: RealtimeHubOwnerScope) -> Bool {
    guard minting, mintGeneration == generation, mintOwnerScope == ownerScope else {
      return false
    }
    minting = false
    mintOwnerScope = nil
    return true
  }

  private func acceptMintCompletionOrRewarm(
    generation: UInt64,
    ownerScope: RealtimeHubOwnerScope
  ) -> Bool {
    guard mintGeneration == generation, mintOwnerScope == ownerScope else { return false }
    guard
      RealtimeHubOwnerFence.acceptsMintCompletion(
        mintOwner: ownerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    else {
      _ = releaseMint(generation: generation, ownerScope: ownerScope)
      log("RealtimeHub: discarding token mint completed after authenticated owner changed")
      clearBargeInReplacementState()
      ensureWarm()
      return false
    }
    return true
  }

  /// Switch to the other realtime provider after the current one fails to connect.
  /// Returns true if a failover was started. Only fires once per chain (primary →
  /// alternate); if the alternate also fails we stop and let PTT use the Claude cascade.
  @discardableResult
  private func failoverToAlternateProvider(reason: String = "other") -> Bool {
    guard fallbackProvider == nil else {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: effectiveProvider.rawValue,
        to: "cascade",
        reason: reason,
        outcome: .exhausted,
        extra: ["user_visible": false])
      return false  // already on the alternate → cascade
    }
    let primary = RealtimeHubSettings.shared.provider
    fallbackProvider = primary.alternate
    pendingFailoverReason = reason
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "realtime_hub",
      from: primary.rawValue,
      to: primary.alternate.rawValue,
      reason: reason,
      outcome: .degraded,
      extra: ["user_visible": false])
    log(
      "RealtimeHub: \(primary.displayName) unavailable — failing over to \(primary.alternate.displayName)"
    )
    teardownSession()
    ensureWarm()
    return true
  }

  private func failoverReason(for failureClass: CredentialFailureClass?) -> String {
    switch failureClass {
    case .providerAuthFailed:
      return "auth"
    case .providerQuotaExceeded:
      return "quota"
    case .backendUnauthorized, .requiresLogin, .paywalled, .byokEnrollmentMismatch,
      .backendTransient, .providerTransient, .providerPolicyClose, .unknown, .none:
      return "other"
    }
  }

  @discardableResult
  private func failoverBargeInReplacement(
    from provider: RealtimeHubProvider,
    reason: String
  ) -> Bool {
    guard fallbackProvider == nil,
      let pendingTurn = replacementAudioBuffer,
      let replacementOwnerScope = pendingBargeInOwnerScope,
      isOwnerScopeCurrent(replacementOwnerScope),
      let responseID = voiceResponseID
    else { return false }

    let alternate = provider.alternate
    fallbackProvider = alternate
    pendingFailoverReason = reason
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "realtime_hub",
      from: provider.rawValue,
      to: alternate.rawValue,
      reason: reason,
      outcome: .degraded,
      extra: ["user_visible": false])
    log(
      "RealtimeHub: preserving barge-in turn while failing over "
        + "\(provider.displayName) → \(alternate.displayName)")

    teardownSession()
    replacementAudioBuffer = pendingTurn
    voiceResponseID = responseID
    pendingBargeInOwnerScope = replacementOwnerScope

    if let key = APIKeyService.byokKey(alternate.byokProvider) {
      pendingBargeInProvider = alternate
      pendingBargeInAuth = .byokKey(key)
      startReplacementSessionForBargeIn(
        provider: alternate,
        auth: .byokKey(key),
        ownerScope: replacementOwnerScope)
      return true
    }
    guard AuthService.shared.isSignedIn else { return false }
    pendingBargeInProvider = alternate
    // Marker only: a newer PTT can rotate continuity while the real alternate
    // one-use token is still minting. The start path always remints this case.
    pendingBargeInAuth = .ephemeral("")
    remintReplacementSessionForBargeIn(provider: alternate)
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

  /// True only when a physical provider socket is authenticated. This is a
  /// latency hint, never authority to open input; every turn still obtains a
  /// context-bound admission before audio leaves its buffer.
  var isTransportReady: Bool {
    // Drive a turn only when the hub is actually CONNECTED + authenticated for the
    // selected provider OR the failover provider we switched to. A turn never enters hub
    // mode on a key/token that can't connect (stale/revoked key, failed mint, mid-
    // reconnect, or a just-switched provider): PTT transparently uses the legacy cascade
    // instead, so a broken hub never costs the user a turn. The hub re-warms in the
    // background and flips this true once it connects.
    guard
      RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: sessionOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    else {
      if session != nil {
        log("RealtimeHub: refusing warm socket owned by a previous authenticated user")
        discardSessionAfterOwnerChange()
        ensureWarm()
      }
      return false
    }
    return hubConnected
      && (sessionProvider == RealtimeHubSettings.shared.provider
        || sessionProvider == fallbackProvider)
  }

  /// PTT cold-start grace: give an already-warming/reconnecting hub a short chance to
  /// become ready before falling back to the slower transcript cascade.
  func waitUntilActive(timeout: TimeInterval) async -> Bool {
    ensureWarm()
    if isTransportReady { return true }
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
      try? await Task.sleep(nanoseconds: 50_000_000)
      if Task.isCancelled { return false }
      if isTransportReady { return true }
    }
    return isTransportReady
  }

  func setup() {
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
    registerRapidPTTBurstTestAction()
    // Load the multilingual language-ID model off the hot path so the first PTT turn's
    // early verdict (and the bubble-fallback decode) doesn't pay model-load latency.
    // Only for users who explicitly configured voice languages — the gate that keeps
    // this whole feature inert for default-config users.
    if !AssistantSettings.shared.voiceBaseLanguages.isEmpty {
      Task.detached(priority: .utility) { await PTTLanguageIdentifier.shared.prewarm() }
    }
  }

  /// Headless E2E for the PTT language path: drives the REAL controller turn flow
  /// (beginTurn → paced feedAudio → commitTurn → turn-done) with a PCM file, so the
  /// early language ID, the provider hint, and the bubble fallback run exactly as a
  /// real hold-to-talk. `omi-ctl action ptt_test_turn pcm=/tmp/q.pcm [timeout=30]`.
  private func registerPTTLanguageTestAction() {
    DesktopAutomationActionRegistry.shared.register(
      name: "ptt_test_turn",
      summary: "Drive a real PTT hub turn from a PCM16/16k mono file through the controller "
        + "with the production pre-overlay screen capture; returns safe lifecycle and screen-protocol diagnostics.",
      params: ["pcm", "timeout", "force_transcript", "text_only"]
    ) { [weak self] params in
      guard let path = params["pcm"],
        let data = try? Data(contentsOf: URL(fileURLWithPath: path)), !data.isEmpty
      else { return ["error": "missing or unreadable 'pcm' file (expected raw s16le 16k mono)"] }
      let timeout = Double(params["timeout"] ?? "") ?? 30
      let textOnly = params["text_only"] == "1"
      guard let self else { return ["error": "hub controller unavailable"] }
      var result = await self.runHeadlessPTTTurn(
        pcm16k: data, timeout: timeout, forceTranscript: params["force_transcript"],
        textOnly: textOnly)
      for (key, value) in self.automationPTTDiagnostics() {
        result[key] = value
      }
      return result
    }
  }

  private func runHeadlessPTTTurn(
    pcm16k: Data, timeout: Double, forceTranscript: String? = nil, textOnly: Bool = false
  ) async -> [String: String] {
#if DEBUG
    if DesktopLocalProfile.isEnabled {
      return await runLocalProfileHeadlessPTTTurn(
        pcm16k: pcm16k,
        timeout: timeout,
        forceTranscript: forceTranscript,
        textOnly: textOnly)
    }
#endif
    // A voice-context reconnect (triggered by the previous turn's kernel write) can replace
    // the warm session mid-turn; the fed audio/text/commit then land on the dead socket
    // and the turn never completes. Detect the swap and redrive the turn once.
    for attempt in 0..<2 {
      if attempt > 0 {
        // Attempt 0's turn died with its session. Clear stale reply-in-flight state so
        // the fresh beginTurn isn't misread as a barge-in — that would capture a bogus
        // interrupted turn and skip diagnostics on the real reply.
        if let staleTurnID = VoiceTurnCoordinator.shared.activeTurnID {
          _ = cancelTurn(turnID: staleTurnID)
          VoiceTurnCoordinator.shared.send(.finish(turnID: staleTurnID, reason: .providerFailed))
        }
      }
      ensureWarm()
      guard await waitUntilActive(timeout: 15) else {
        return ["error": "hub session did not become active (check sign-in / provider keys)"]
      }
      prefetchVoiceContextSnapshotIfNeeded()
      try? await Task.sleep(nanoseconds: 500_000_000)
      ensureWarm()
      guard await waitUntilActive(timeout: 15) else {
        return ["error": "hub session did not become active after voice context prefetch"]
      }
      lastTurnDiagnostics = [:]
      let turnID = RealtimeAutomationTurnHarness.begin(on: VoiceTurnCoordinator.shared)
      VoiceTurnCoordinator.shared.send(
        .selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
      let screenEvidenceCaptured = PushToTalkManager.shared.captureScreenEvidenceForAutomation(turnID: turnID)
      log(
        "RealtimeHub: headless PTT screen evidence capture="
          + (screenEvidenceCaptured ? "available" : "unavailable"))
      beginTurn(turnID: turnID)
      testProviderTranscriptOverride = forceTranscript
      let forcedSelection = RealtimeAutomationTranscriptOverridePolicy.select(
        providerText: "",
        providerIsFinal: false,
        forcedText: forceTranscript)
      if forcedSelection.usedOverride {
        turnTranscript = forcedSelection.text
        providerTranscriptFinalized = forcedSelection.isFinal
        lastInputTranscriptUpdateAt = Date()
      }
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
      // beginTurn can defer activityStart while a context reconnect finishes; text or
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
      // beginTurn's context refresh can reconnect the warm socket; capture the live session
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
      VoiceTurnCoordinator.shared.send(.finalize(turnID: turnID))
      _ = commitTurn()
      let deadline = Date().addingTimeInterval(timeout)
      let canonicalContinuityKey = "voice:\(turnID.rawValue.uuidString.lowercased())"
      var redrive = false
      while Date() < deadline {
        let hasCanonicalSpawnReceipt =
          acceptedSpawnJournalReceiptByContinuityKey[canonicalContinuityKey] != nil
        if let terminal = VoiceTurnCoordinator.shared.model.lastTerminal,
          terminal.turnID == turnID
        {
          if terminal.reason == .success {
            var result = lastTurnDiagnostics
            result["terminal_reason"] = terminal.reason.rawValue
            return result
          }
          return ["error": "voice turn terminated with \(terminal.reason.rawValue)"]
        }
        if !hasCanonicalSpawnReceipt, !lastTurnDiagnostics.isEmpty {
          return lastTurnDiagnostics
        }
        if attempt == 0,
          RealtimeHeadlessPTTSessionSwapPolicy.shouldRedrive(
            sessionChanged: session !== turnSession,
            hasCanonicalSpawnReceipt: hasCanonicalSpawnReceipt)
        {
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

#if DEBUG
  /// Hermetic `ptt_test_turn` transport for `OMI_DESKTOP_LOCAL_PROFILE=1`.
  /// Provider events are synthesized, but every logical boundary remains the
  /// production boundary: voice reducer, external-run capability, tool ledger,
  /// spawn journal receipt, and kernel turn finalization.
  private func runLocalProfileHeadlessPTTTurn(
    pcm16k: Data,
    timeout: Double,
    forceTranscript: String?,
    textOnly: Bool
  ) async -> [String: String] {
    guard !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress else {
      return ["error": "local-profile realtime transport unavailable during owner transition"]
    }
    guard let forceTranscript, !forceTranscript.trimmingCharacters(
      in: .whitespacesAndNewlines).isEmpty
    else {
      return ["error": "local-profile ptt_test_turn requires a non-empty force_transcript"]
    }

    guard await refreshVoiceContextSnapshot(),
      !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress,
      !prefetchedVoiceContextSessionID.isEmpty
    else {
      return ["error": "local-profile realtime voice context session is unavailable"]
    }
    guard
      let plan = RealtimeLocalProfileTurnPlan.make(
        transcript: forceTranscript,
        voiceContext: prefetchedVoiceContext,
        localProfileEnabled: DesktopLocalProfile.isEnabled)
    else {
      return ["error": "local-profile realtime provider could not plan the test turn"]
    }

    let localOwnerScope = currentOwnerScope
    guard let localOwnerID = localOwnerScope.authenticatedOwnerID,
      let localAuthorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: localOwnerID)
    else {
      return ["error": "local-profile realtime transport requires an authenticated owner"]
    }
    teardownSession()
    let context = voiceSessionContext(for: localOwnerScope)
    sessionVoiceContextFreshnessIdentity = context.snapshotFreshnessIdentity
    let localSession = RealtimeHubSession(
      provider: .openai,
      auth: .byokKey("omi-local-profile-stub"),
      instructions: "Hermetic local-profile realtime transport.",
      delegate: self)
    lastWarmAt = nil
    hubConnected = false
    session = localSession
    voiceSessionID = VoiceSessionID()
    sessionProvider = .openai
    sessionAuth = .byokKey("omi-local-profile-stub")
    sessionOwnerBinding = PhysicalSessionOwnerBinding(
      sourceID: ObjectIdentifier(localSession),
      ownerScope: localOwnerScope)
    localProfileTransportAuthority = RealtimeLocalProfileTransportAuthority(
      sourceID: ObjectIdentifier(localSession),
      ownerScope: localOwnerScope,
      authorizationSnapshot: localAuthorization)
    defer {
      if session === localSession {
        teardownSession()
      }
    }
    localSession.markReadyForTesting()
    guard
      await waitUntilLocalProfileTransportReady(
        localSession,
        ownerScope: localOwnerScope,
        timeout: min(3, max(1, timeout)))
    else {
      return ["error": "local-profile realtime transport did not become active"]
    }

    lastTurnDiagnostics = [:]
    let turnID = RealtimeAutomationTurnHarness.begin(on: VoiceTurnCoordinator.shared)
    VoiceTurnCoordinator.shared.send(
      .selectRoute(turnID: turnID, route: .hub(sessionID: voiceSessionID)))
    beginTurn(turnID: turnID)
    if !textOnly {
      feedAudio(Data(pcm16k.prefix(3_200)), turnID: turnID)
    }
    VoiceTurnCoordinator.shared.send(.finalize(turnID: turnID))
    let commitResult = commitTurn()
    guard commitResult == .accepted, let responseID = voiceResponseID else {
      let failedTurn = VoiceTurnCoordinator.shared.activeTurn
      let recentTimeline = VoiceTurnCoordinator.shared.timelineSnapshot().suffix(6).map {
        "\($0.sequence):\($0.event):"
          + "\($0.phaseBefore.map(VoiceTurnCoordinator.phaseLabel) ?? "idle")->"
          + "\($0.phaseAfter.map(VoiceTurnCoordinator.phaseLabel) ?? "idle")"
      }.joined(separator: ",")
      let phase = failedTurn.map { VoiceTurnCoordinator.phaseLabel($0.phase) } ?? "idle"
      let route = failedTurn.map { VoiceTurnCoordinator.routeLabel($0.route) } ?? "none"
      let owner = failedTurn?.ownerID ?? "none"
      log(
        "RealtimeHub: local-profile synthetic commit rejected result=\(commitResult) "
          + "phase=\(phase) route=\(route) owner=\(owner) timeline=[\(recentTimeline)]")
      VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .providerFailed))
      return [
        "error": "local-profile realtime reducer rejected the synthetic commit",
        "commit_result": "\(commitResult)",
        "phase": phase,
        "route": route,
        "owner": owner,
        "recent_timeline": recentTimeline,
      ]
    }

    let eventIdentity = RealtimeHubEventIdentity(turnID: turnID, responseID: responseID)
    hubDidReceiveInputTranscript(
      forceTranscript,
      isFinal: true,
      identity: eventIdentity,
      source: localSession)

    var reply = plan.assistantText
    if let spawn = plan.spawn {
      let callID = "local-profile-spawn-\(turnID.rawValue.uuidString.lowercased())"
      hubDidRequestTool(
        name: "spawn_agent",
        callId: callID,
        argumentsJSON: Self.localProfileSpawnArgumentsJSON(spawn),
        identity: eventIdentity,
        source: localSession)

      let toolDeadline = Date().addingTimeInterval(max(1, timeout))
      while Date() < toolDeadline {
        let pending = VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs
          .contains(VoiceToolCallID(callID)) == true
        if !pending {
          if let receipt = acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] {
            reply = receipt.receipt.assistantText
            break
          }
          VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .providerFailed))
          return ["error": "local-profile spawn_agent completed without a canonical journal receipt"]
        }
        try? await Task.sleep(nanoseconds: 50_000_000)
      }
      guard acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] != nil else {
        VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .toolTimeout))
        return ["error": "local-profile spawn_agent did not finish within \(Int(timeout))s"]
      }
    }

    // A post-tool provider continuation clears the reducer's continuation fence.
    // `isFinal=false` avoids physical speech in a cursor-free hermetic run; the
    // following turn-finished event remains the authoritative provider boundary.
    assistantText = ""
    hubDidEmitText(
      reply,
      isFinal: false,
      identity: eventIdentity,
      source: localSession)
    hubDidFinishTurn(identity: eventIdentity, source: localSession)

    let completionDeadline = Date().addingTimeInterval(max(1, timeout))
    while Date() < completionDeadline {
      if let terminal = VoiceTurnCoordinator.shared.model.lastTerminal,
        terminal.turnID == turnID
      {
        guard terminal.reason == .success else {
          return ["error": "local-profile voice turn terminated with \(terminal.reason.rawValue)"]
        }
        if !lastTurnDiagnostics.isEmpty { return lastTurnDiagnostics }
      }
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    return ["error": "local-profile voice turn did not finalize within \(Int(timeout))s"]
  }

  /// Waits on the exact hermetic socket without entering `ensureWarm()` or
  /// comparing it with the user's provider preference. Both operations are
  /// correct for production warm sessions and wrong for an offline transport.
  private func waitUntilLocalProfileTransportReady(
    _ source: RealtimeHubSession,
    ownerScope: RealtimeHubOwnerScope,
    timeout: TimeInterval
  ) async -> Bool {
    let deadline = Date().addingTimeInterval(timeout)
    repeat {
      guard localProfileTransportAuthority?.ownerScope == ownerScope,
        isAuthorizedLocalProfileTransport(source),
        source === session
      else { return false }
      if hubConnected, await source.activityWindowOpen() { return true }
      try? await Task.sleep(nanoseconds: 50_000_000)
      if Task.isCancelled { return false }
    } while Date() < deadline
    guard isAuthorizedLocalProfileTransport(source), source === session, hubConnected else {
      return false
    }
    return await source.activityWindowOpen()
  }

  private nonisolated static func localProfileSpawnArgumentsJSON(
    _ spawn: RealtimeLocalProfileTurnPlan.Spawn
  ) -> String {
    let payload: [String: Any] = [
      "objective": spawn.objective,
      "title": spawn.title,
      "visible": true,
    ]
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else { return "{}" }
    return json
  }
#endif

  /// Non-production regression harness for the exact user report: commit several
  /// PTT clips back-to-back without waiting for provider replies, then wait only
  /// for the final reply. Earlier turns must be persisted and included in its context.
  private func registerRapidPTTBurstTestAction() {
    DesktopAutomationActionRegistry.shared.register(
      name: "ptt_test_burst",
      summary: "Drive three back-to-back PCM PTT turns and return final diagnostics.",
      params: ["pcm1", "pcm2", "pcm3", "timeout"]
    ) { [weak self] params in
      let paths = [params["pcm1"], params["pcm2"], params["pcm3"]]
      let clips = paths.compactMap { path in
        path.flatMap { try? Data(contentsOf: URL(fileURLWithPath: $0)) }
      }
      guard clips.count == 3, clips.allSatisfy({ !$0.isEmpty }) else {
        return ["error": "pcm1, pcm2, and pcm3 must be readable PCM16/16k mono files"]
      }
      guard let self else { return ["error": "hub controller unavailable"] }
      return await self.runHeadlessRapidPTTBurst(
        clips: clips,
        timeout: Double(params["timeout"] ?? "") ?? 60)
    }
  }

  private func runHeadlessRapidPTTBurst(
    clips: [Data],
    timeout: Double
  ) async -> [String: String] {
    ensureWarm()
    guard await waitUntilActive(timeout: 15) else {
      return ["error": "hub session did not become active"]
    }
    lastTurnDiagnostics = [:]
    for clip in clips {
      let turnID = RealtimeAutomationTurnHarness.begin(on: VoiceTurnCoordinator.shared)
      VoiceTurnCoordinator.shared.send(
        .selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
      beginTurn(turnID: turnID)
      var offset = 0
      while offset < clip.count {
        let end = min(offset + 3_200, clip.count)
        feedAudio(clip.subdata(in: offset..<end), turnID: turnID)
        offset = end
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      VoiceTurnCoordinator.shared.send(.finalize(turnID: turnID))
      _ = commitTurn()
    }

    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
      if !lastTurnDiagnostics.isEmpty { return lastTurnDiagnostics }
      try? await Task.sleep(nanoseconds: 200_000_000)
    }
    return ["error": "rapid PTT burst did not complete within \(Int(timeout))s"]
  }

  /// System woke from sleep — proactively replace a possibly-stale socket so the first PTT
  /// after sleep doesn't hit a zombie session (commit → no reply → no fallback → hang).
  /// Only acts when idle: a live session exists and we're neither mid-reply nor mid-mint, so
  /// this never interrupts an active turn or races a connect already in flight. teardown
  /// forces session=nil so ensureWarm() rebuilds (it would otherwise treat the stale socket
  /// as already-warm and no-op).
  @objc private func systemDidWake() {
    requestSessionRefresh(reason: "system_wake")
  }

  /// Voice languages changed: prewarm the LID model (a 1→2 language change would
  /// otherwise cold-load on the first turn) and rebuild an idle warm session so the
  /// new languages line lands in the system instruction now, not at the next re-mint.
  @objc private func voiceLanguagesChanged() {
    if !AssistantSettings.shared.voiceBaseLanguages.isEmpty {
      Task.detached(priority: .utility) { await PTTLanguageIdentifier.shared.prewarm() }
    }
    requestSessionRefresh(reason: "voice_languages_changed")
  }

  @objc private func settingsChanged() {
    guard RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot) else {
      pendingSessionRefreshReason = "provider_settings_changed"
      log("RealtimeHub: deferring provider settings change until active voice turn terminates")
      return
    }
    resetFailoverForProviderSettingsChange()
    // Only reconnect if the provider actually changed — avoids redundant
    // teardown/recreate races on unrelated notifications.
    if session != nil, sessionProvider == RealtimeHubSettings.shared.provider,
      RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: sessionOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    {
      return
    }
    teardownSession()
    ensureWarm()
  }

  private func requestSessionRefresh(reason: String) {
    guard session != nil else { return }
    guard RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot) else {
      pendingSessionRefreshReason = reason
      log("RealtimeHub: deferring \(reason) session refresh until active voice turn terminates")
      return
    }
    log("RealtimeHub: \(reason) — re-warming idle session")
    teardownSession()
    ensureWarm()
  }

  private func applyPendingSessionRefreshIfIdle() {
    guard let reason = pendingSessionRefreshReason,
      RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot)
    else { return }
    pendingSessionRefreshReason = nil
    if reason == "voice_context_changed" {
      deferredSessionRefreshTask?.cancel()
      deferredSessionRefreshTask = Task { @MainActor [weak self] in
        guard let self else { return }
        if await self.refreshVoiceContextAfterPersistenceFence(reason: reason) {
          self.cancelContinuityFenceActive = false
          self.cancelContinuityFenceTurnID = nil
          self.canceledTurnRewarmTask = nil
          log("RealtimeHub: applying deferred voice context refresh after turn persistence")
          self.teardownSession()
          self.ensureWarm()
        }
        self.deferredSessionRefreshTask = nil
      }
      return
    }
    log("RealtimeHub: applying deferred \(reason) session refresh")
    if reason == "provider_settings_changed" {
      resetFailoverForProviderSettingsChange()
    }
    teardownSession()
    ensureWarm()
  }

  /// Waits for every persistence write visible at the fence, refreshes context,
  /// and retries if either a new turn or a new write appears across an await.
  /// Callers decide when it is safe to release any stronger reconnect gate.
  private func refreshVoiceContextAfterPersistenceFence(reason: String) async -> Bool {
    while !Task.isCancelled {
      let observedTurnEpoch = turnEpoch
      let observedPersistenceGeneration = turnPersistenceLedger.generation
      await turnPersistenceLedger.awaitPendingObligations()
      guard RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot) else {
        pendingSessionRefreshReason = reason
        return false
      }
      guard observedTurnEpoch == turnEpoch,
        observedPersistenceGeneration == turnPersistenceLedger.generation
      else { continue }

      guard await refreshVoiceContextSnapshot() else {
        if Task.isCancelled { return false }
        continue
      }
      guard !Task.isCancelled,
        RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot)
      else {
        pendingSessionRefreshReason = reason
        return false
      }
      guard observedTurnEpoch == turnEpoch,
        observedPersistenceGeneration == turnPersistenceLedger.generation
      else { continue }

      return true
    }
    return false
  }

  private func resetFailoverForProviderSettingsChange() {
    // A new pick (user or Auto/AutoModelSelector) re-evaluates from the primary.
    // This reset moves with session replacement so an active fallback turn keeps
    // a coherent provider identity until it terminates.
    fallbackProvider = nil
    pendingFailoverReason = nil
  }

  // MARK: - Warm session lifecycle (kept open between turns)

  /// Open the WS now if it isn't already (no-op if already warm). BYOK → connect
  /// client-direct with the user's key. Otherwise, if signed in → mint a server-side
  /// ephemeral token and connect with it.
  func ensureWarm() {
#if DEBUG
    // The local-profile action owns an already-installed hermetic transport.
    // Re-entering normal warm-up here would replace it and mint a real provider
    // token while the offline gauntlet is exercising the production reducer.
    if isAuthorizedLocalProfileTransport() { return }
#endif
    guard !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress else {
      log("RealtimeHub: warm start denied during effective-owner transition")
      return
    }
    guard !cancelContinuityFenceActive else {
      log("RealtimeHub: general warm deferred behind canceled-turn continuity fence")
      return
    }
    guard
      RealtimeHubLifecyclePolicy.canStartGeneralWarmSession(
        replacementPending: replacementAudioBuffer != nil)
    else {
      log("RealtimeHub: general warm skipped while barge-in replacement owns session startup")
      return
    }
    let provider = effectiveProvider
    let ownerScope = currentOwnerScope
    if session != nil, sessionProvider == provider,
      RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: sessionOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    {
      return
    }
    if session != nil, sessionOwnerScope != ownerScope {
      log("RealtimeHub: rebuilding warm session after authenticated owner changed")
      discardSessionAfterOwnerChange()
    }
    if session != nil { teardownSession() }

    if let key = APIKeyService.byokKey(provider.byokProvider) {
      let fingerprint = APIKeyService.byokFingerprint(key)
      guard
        CredentialHealthManager.shared.canUseBYOK(
          provider: provider.byokProvider, fingerprint: fingerprint)
      else {
        log("RealtimeHub: skipping known-bad \(provider.displayName) BYOK key fingerprint")
        if failoverToAlternateProvider(reason: "auth") {
          return
        } else if AuthService.shared.isSignedIn {
          guard case .authenticated = ownerScope else { return }
          mintAndConnect(provider: provider, ownerScope: ownerScope)
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
      startSession(provider: provider, auth: .byokKey(key), ownerScope: ownerScope)
    } else if AuthService.shared.isSignedIn {
      guard case .authenticated = ownerScope else {
        log("RealtimeHub: signed-in state has no stable owner identity — hub unavailable")
        return
      }
      mintAndConnect(provider: provider, ownerScope: ownerScope)
    } else {
      log("RealtimeHub: no BYOK key and not signed in — hub unavailable (cascade).")
    }
  }

  private func completeExternalRunAuthority(
    turnID: VoiceTurnID,
    reason: VoiceTurnTerminalReason
  ) {
    guard let state = externalRunAuthorityState, state.turnID == turnID else { return }
    externalRunAuthorityState = nil
    authorizedRealtimeInvocations = authorizedRealtimeInvocations.filter {
      $0.value.turnID != turnID
    }
    completedAuthorizedRealtimeInvocationIDs.removeAll()
    let terminalStatus = RealtimeExternalRunTerminalPolicy.status(for: reason)
    let errorCode = terminalStatus == .failed ? reason.rawValue : nil
    let terminalizationID = UUID()
    let task = Task { @MainActor [weak self] in
      let resolution = await awaitWithTimeout(
        Self.ownerTransitionExternalRunBindingTimeout
      ) { () -> ExternalRunBindingResolution in
        do {
          return .bound(try await state.task.value)
        } catch {
          let code = (error as? ExternalSurfaceAuthorityError)?.code
            ?? "external_surface_begin_failed"
          return .failed(code)
        }
      }
      switch resolution {
      case .some(.bound(let binding)):
        guard let self else {
          return ExternalRunTerminalizationResult(
            binding: binding,
            cleanupCapability: nil,
            closed: false,
            failureCode: "realtime_controller_released")
        }
        return await self.terminalizeExternalRun(
          binding: binding,
          terminalStatus: terminalStatus,
          errorCode: errorCode)
      case .some(.failed(let code)):
        log("RealtimeHub: external run completion failed code=\(code)")
        return ExternalRunTerminalizationResult(
          binding: nil,
          cleanupCapability: nil,
          closed: false,
          failureCode: code)
      case .none:
        state.task.cancel()
        log("RealtimeHub: external run begin drain timed out at owner boundary")
        return ExternalRunTerminalizationResult(
          binding: nil,
          cleanupCapability: nil,
          closed: false,
          failureCode: "external_surface_begin_drain_timeout")
      }
    }
    trackExternalRunTerminalization(
      id: terminalizationID,
      ownerID: state.ownerID,
      terminalStatus: terminalStatus,
      errorCode: errorCode,
      task: task)
  }

  private func terminalizeExternalRun(
    binding: ExternalSurfaceRunBinding,
    terminalStatus: ExternalSurfaceRunTerminalStatus,
    errorCode: String?,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability? = nil
  ) async -> ExternalRunTerminalizationResult {
    let effectiveCleanupCapability = cleanupCapability
      ?? RuntimeOwnerIdentity.transitionCleanupCapability(
        forPreviousOwnerID: binding.ownerID)
    do {
#if DEBUG
      if let ownerBoundaryExternalRunCompletion {
        try await ownerBoundaryExternalRunCompletion(
          binding,
          terminalStatus,
          errorCode,
          effectiveCleanupCapability)
      } else {
        _ = try await AgentRuntimeProcess.shared.completeExternalSurfaceRun(
          clientId: Self.externalRunClientID,
          harnessMode: Self.externalRunHarnessMode,
          binding: binding,
          terminalStatus: terminalStatus,
          errorCode: errorCode,
          transitionCleanupCapability: effectiveCleanupCapability)
      }
#else
      _ = try await AgentRuntimeProcess.shared.completeExternalSurfaceRun(
        clientId: Self.externalRunClientID,
        harnessMode: Self.externalRunHarnessMode,
        binding: binding,
        terminalStatus: terminalStatus,
        errorCode: errorCode,
        transitionCleanupCapability: effectiveCleanupCapability)
#endif
      return ExternalRunTerminalizationResult(
        binding: binding,
        cleanupCapability: effectiveCleanupCapability,
        closed: true,
        failureCode: nil)
    } catch {
      let code = (error as? ExternalSurfaceAuthorityError)?.code
        ?? "external_surface_complete_failed"
      log("RealtimeHub: external run completion failed code=\(code)")
      return ExternalRunTerminalizationResult(
        binding: binding,
        cleanupCapability: effectiveCleanupCapability,
        closed: false,
        failureCode: code)
    }
  }

  private func trackExternalRunTerminalization(
    id: UUID,
    ownerID: String,
    terminalStatus: ExternalSurfaceRunTerminalStatus,
    errorCode: String?,
    task: Task<ExternalRunTerminalizationResult, Never>
  ) {
    externalRunTerminalizations[id] = TrackedExternalRunTerminalization(
      ownerID: ownerID,
      terminalStatus: terminalStatus,
      errorCode: errorCode,
      task: task)

    Task { @MainActor [weak self] in
      let result = await task.value
      guard let self else { return }
      self.reconcileTrackedExternalRunTerminalization(id: id, result: result)
    }
  }

  private func reconcileTrackedExternalRunTerminalization(
    id: UUID,
    result: ExternalRunTerminalizationResult
  ) {
    // Only a confirmed ordinary close is safe to forget. A failed begin with
    // no binding is unresolved, not proof that Node created no run; retain it
    // until owner quiescence's correlated owner-wide revocation barrier.
    if result.cleanupCapability == nil, result.closed {
      removeTrackedExternalRunTerminalization(id)
    }
  }

  private func removeTrackedExternalRunTerminalization(_ id: UUID) {
    externalRunTerminalizations.removeValue(forKey: id)
  }

  func voiceTurnDidTerminate(turnID: VoiceTurnID) {
    if let terminal = VoiceTurnCoordinator.shared.model.lastTerminal,
      terminal.turnID == turnID
    {
      completeExternalRunAuthority(turnID: turnID, reason: terminal.reason)
      if screenEvidence?.descriptor.turnID == turnID {
        clearScreenGrounding(stage: terminal.reason == .success ? "released" : "cancelled")
      }
    } else if screenEvidence?.descriptor.turnID == turnID {
      clearScreenGrounding(stage: "cancelled")
    }
    guard pendingSessionRefreshReason != nil else { return }
    guard
      RealtimeHubLifecyclePolicy.shouldResumeCanceledTurnRefresh(
        fenceTurnID: cancelContinuityFenceTurnID,
        terminalTurnID: turnID)
    else { return }

    if cancelContinuityFenceActive {
      canceledTurnRewarmTask?.cancel()
      canceledTurnRewarmTask = nil
    }
    applyPendingSessionRefreshIfIdle()
  }

  /// Managed users: fetch a short-lived ephemeral token from the backend (gated by
  /// auth + paywall there), then connect. On any failure (incl. 402 not-entitled),
  /// leave the session nil so PTT falls back to the cascade.
  private func mintAndConnect(
    provider: RealtimeHubProvider,
    ownerScope: RealtimeHubOwnerScope
  ) {
    guard case .authenticated(let ownerID) = ownerScope,
      isOwnerScopeCurrent(ownerScope),
      let mintGeneration = beginMint(ownerScope: ownerScope)
    else { return }
    let providerParam = provider == .openai ? "openai" : "gemini"
    log("RealtimeHub: minting ephemeral \(provider.displayName) token (managed)")
    Task { [weak self] in
      guard let self else { return }
      let token: String
      do {
        token = try await APIClient.shared.mintRealtimeToken(
          provider: providerParam,
          expectedOwnerID: ownerID)
      } catch let error as RealtimeTokenMintError {
        guard self.acceptMintCompletionOrRewarm(
          generation: mintGeneration,
          ownerScope: ownerScope)
        else { return }
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        self.recordRealtimeMintFailure(
          error, provider: providerParam, phase: "warm", context: "realtime_mint")
        if error.healthError.failureClass.isAccountWide {
          log("RealtimeHub: account credential failure during mint — staying on cascade")
        } else if !self.failoverToAlternateProvider(
          reason: self.failoverReason(for: error.healthError.failureClass))
        {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      } catch let error as CredentialHealthError {
        guard self.acceptMintCompletionOrRewarm(
          generation: mintGeneration,
          ownerScope: ownerScope)
        else { return }
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        CredentialHealthManager.shared.record(error, context: "realtime_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: error.failureClass.logValue,
          phase: "warm",
          httpStatusCode: error.failureClass.httpStatusCode)
        if error.failureClass.isAccountWide {
          log("RealtimeHub: account credential failure during mint — staying on cascade")
        } else if !self.failoverToAlternateProvider(
          reason: self.failoverReason(for: error.failureClass))
        {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      } catch {
        guard self.acceptMintCompletionOrRewarm(
          generation: mintGeneration,
          ownerScope: ownerScope)
        else { return }
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        let typed = CredentialHealthError.backendTransient(
          statusCode: nil, message: error.localizedDescription)
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
      guard self.acceptMintCompletionOrRewarm(
        generation: mintGeneration,
        ownerScope: ownerScope)
      else { return }
      _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
      // Provider may have changed (picker/failover) while minting; only connect if still wanted.
      guard self.effectiveProvider == provider, self.session == nil else {
        self.ensureWarm()
        return
      }
      self.startSession(
        provider: provider,
        auth: .ephemeral(token),
        ownerScope: ownerScope)
    }
  }

  private func startSession(
    provider: RealtimeHubProvider,
    auth: HubAuth,
    ownerScope: RealtimeHubOwnerScope
  ) {
    guard !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress else {
      log("RealtimeHub: physical session start denied during effective-owner transition")
      return
    }
    guard !cancelContinuityFenceActive else {
      log("RealtimeHub: session start rejected behind canceled-turn continuity fence")
      return
    }
    guard isOwnerScopeCurrent(ownerScope) else {
      log("RealtimeHub: session start rejected after authenticated owner changed")
      ensureWarm()
      return
    }
    let topLevelContext = voiceSessionContext(for: ownerScope)
    sessionVoiceContextFreshnessIdentity = topLevelContext.snapshotFreshnessIdentity
    let instructions = RealtimeHubTools.systemInstruction(
      kernelContext: topLevelContext.rendered,
      kernelSemanticGuidance: topLevelContext.semanticGuidance,
      userLanguages: AssistantSettings.shared.voiceBaseLanguages)
    let s = RealtimeHubSession(
      provider: provider,
      auth: auth,
      instructions: instructions,
      availableDirectedProviders: registeredDirectedProviderIDs,
      contextPlanID: topLevelContext.planID,
      stableCacheIdentity: topLevelContext.stableCacheIdentity,
      dynamicContextIdentity: topLevelContext.dynamicContextIdentity,
      contextCacheReplaced: pendingContextCacheReplacement,
      delegate: self)
    pendingContextCacheReplacement = false
    lastWarmAt = nil
    hubConnected = false
    session = s
    voiceSessionID = VoiceSessionID()
    sessionProvider = provider
    sessionAuth = auth
    sessionOwnerBinding = PhysicalSessionOwnerBinding(
      sourceID: ObjectIdentifier(s),
      ownerScope: ownerScope)
    // Both providers stream native spoken audio (24k PCM) → StreamingPCMPlayer;
    // selected app voice playback handles any no-audio fallback.
    if pcmPlayer == nil {
      pcmPlayer = makePCMPlayer()
    }
    s.start()
    log(
      "RealtimeHub: warming \(provider.displayName) session "
        + "(\(auth.isEphemeral ? "ephemeral/managed" : "client-direct/BYOK"), "
        + "contextChars=\(topLevelContext.rendered.count) plan=\(topLevelContext.planID.prefix(24)))")
  }

  struct VoiceSessionContext {
    let sessionID: String
    let rendered: String
    let snapshotFreshnessIdentity: String
    let planID: String
    let stableCacheIdentity: String
    let dynamicContextIdentity: String
    let semanticGuidance: String

    /// Availability contract, mirroring `KernelVoiceContextSnapshot.isResolved`:
    /// a kernel session bound to this owner scope plus a deterministic freshness
    /// identity. Rendered context, plan identities, and semantic guidance are
    /// context *material* — a valid new conversation renders none of it, and
    /// `RealtimeHubTools.escalationBody` omits each empty section on its own.
    /// Requiring them here would fail-closed on the first turn of every session.
    var isResolved: Bool {
      !sessionID.isEmpty && !snapshotFreshnessIdentity.isEmpty
    }
  }

  /// Exact context material selected and rendered by the kernel for realtime.
  private func voiceSessionContext(for ownerScope: RealtimeHubOwnerScope) -> VoiceSessionContext {
    guard prefetchedVoiceContextOwnerScope == ownerScope else {
      return VoiceSessionContext(
        sessionID: "", rendered: "", snapshotFreshnessIdentity: "", planID: "",
        stableCacheIdentity: "", dynamicContextIdentity: "", semanticGuidance: "")
    }
    return VoiceSessionContext(
      sessionID: prefetchedVoiceContextSessionID,
      rendered: prefetchedVoiceContext,
      snapshotFreshnessIdentity: prefetchedVoiceContextFreshnessIdentity,
      planID: prefetchedVoiceContextPlanID,
      stableCacheIdentity: prefetchedVoiceStableCacheIdentity,
      dynamicContextIdentity: prefetchedVoiceDynamicContextIdentity,
      semanticGuidance: prefetchedVoiceSemanticGuidance
    )
  }

  /// Prefetch the typed kernel snapshot on PTT key-down before `beginTurn`.
  func prefetchVoiceContextSnapshotIfNeeded() {
    voiceContextPrefetchTask?.cancel()
    voiceContextRefreshGeneration &+= 1
    let refreshGeneration = voiceContextRefreshGeneration
    let ownerScope = currentOwnerScope
    voiceContextPrefetchTask = Task { [weak self] in
      await self?.importLegacyVoiceJournalIfNeeded()
      guard let self, self.isOwnerScopeCurrent(ownerScope) else { return }
      let resolvedSnapshot: KernelVoiceContextSnapshot
      do {
        resolvedSnapshot = try await FloatingControlBarManager.shared.kernelVoiceContextSnapshot()
      } catch is CancellationError {
        // Expected only for a speculative key-down prefetch superseded by the
        // hard refresh. This task owns the suppression.
        return
      } catch {
        return
      }
      let registeredProviders = await AgentRuntimeProcess.shared.registeredDirectedProviderIDs()
      await MainActor.run {
        guard !Task.isCancelled,
          self.voiceContextRefreshGeneration == refreshGeneration,
          self.isOwnerScopeCurrent(ownerScope),
          resolvedSnapshot.isResolved
        else { return }
        self.prefetchedVoiceContext = resolvedSnapshot.context
        self.prefetchedVoiceContextSessionID = resolvedSnapshot.sessionId
        self.prefetchedVoiceContextFreshnessIdentity = resolvedSnapshot.freshnessIdentity
        self.prefetchedVoiceContextPlanID = resolvedSnapshot.contextPlanID
        self.prefetchedVoiceStableCacheIdentity = resolvedSnapshot.stableCacheIdentity
        self.prefetchedVoiceDynamicContextIdentity = resolvedSnapshot.dynamicContextIdentity
        self.prefetchedVoiceSemanticGuidance = resolvedSnapshot.semanticGuidance
        self.updateRegisteredDirectedProviders(registeredProviders)
        self.prefetchedVoiceContextTurnIDs = resolvedSnapshot.turnIDs
        self.prefetchedVoiceContextOwnerScope = ownerScope
      }
    }
  }

  @discardableResult
  private func refreshVoiceContextSnapshot() async -> Bool {
    guard !Task.isCancelled else { return false }
    let ownerScope = currentOwnerScope
    await importLegacyVoiceJournalIfNeeded()
    guard !Task.isCancelled, isOwnerScopeCurrent(ownerScope) else { return false }
    voiceContextPrefetchTask?.cancel()
    voiceContextPrefetchTask = nil
    voiceContextRefreshGeneration &+= 1
    let refreshGeneration = voiceContextRefreshGeneration
    let resolvedSnapshot: KernelVoiceContextSnapshot
    do {
      resolvedSnapshot = try await FloatingControlBarManager.shared.kernelVoiceContextSnapshot()
    } catch {
      return false
    }
    let registeredProviders = await AgentRuntimeProcess.shared.registeredDirectedProviderIDs()
    guard resolvedSnapshot.isResolved else {
      log("RealtimeHub: retaining the last voice context after an unresolved kernel snapshot")
      return false
    }
    guard !Task.isCancelled, voiceContextRefreshGeneration == refreshGeneration,
      isOwnerScopeCurrent(ownerScope)
    else {
      return false
    }
    prefetchedVoiceContext = resolvedSnapshot.context
    prefetchedVoiceContextSessionID = resolvedSnapshot.sessionId
    prefetchedVoiceContextFreshnessIdentity = resolvedSnapshot.freshnessIdentity
    prefetchedVoiceContextPlanID = resolvedSnapshot.contextPlanID
    prefetchedVoiceStableCacheIdentity = resolvedSnapshot.stableCacheIdentity
    prefetchedVoiceDynamicContextIdentity = resolvedSnapshot.dynamicContextIdentity
    prefetchedVoiceSemanticGuidance = resolvedSnapshot.semanticGuidance
    updateRegisteredDirectedProviders(registeredProviders)
    prefetchedVoiceContextTurnIDs = resolvedSnapshot.turnIDs
    prefetchedVoiceContextOwnerScope = ownerScope
    return true
  }

  private func updateRegisteredDirectedProviders(_ providers: [String]) {
    let normalized = providers.filter { ["hermes", "openclaw"].contains($0) }.sorted()
    guard registeredDirectedProviderIDs != normalized else { return }
    registeredDirectedProviderIDs = normalized
    // A realtime provider's tool schema is immutable for the physical session.
    // Replace a warm session so it cannot advertise a stale local adapter.
    if session != nil {
      teardownSession()
      ensureWarm()
    }
  }

  /// Establish a reducer-owned input boundary before a PTT turn can touch the
  /// provider. The buffer is drained only after the canonical kernel snapshot
  /// has been refreshed and the physical session carries that snapshot.
  @discardableResult
  private func beginContextFreshInputPreparation(
    turnID: VoiceTurnID,
    responseID: VoiceResponseID,
    interrupting: Bool
  ) -> Bool {
    guard reconnectAudioBuffer == nil,
      let identity = VoiceTurnCoordinator.shared.reserveEffectIdentity()
    else {
      return false
    }
    reconnectAudioBuffer = RealtimeReconnectAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: identity,
      interrupting: interrupting)
    VoiceTurnCoordinator.shared.send(
      .providerReconnectStarted(
        turnID: turnID,
        identity: identity,
        previousSessionID: voiceSessionID))
    return true
  }

  /// Drains a PTT input held while the canonical context snapshot was refreshed
  /// onto the already-warm provider. This shares the same reducer fences and
  /// ordered replay path as a physical reconnect without needlessly replacing a
  /// fresh socket.
  private func finishContextFreshInputOnCurrentSession() {
    guard let pending = reconnectAudioBuffer, let live = session else { return }
    guard let voiceSessionID else { return }
    let admission = RealtimeInputAdmissionPolicy.decide(
      pending: pending,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      sessionContextFreshnessIdentity: sessionVoiceContextFreshnessIdentity)
    guard admission == .admit else {
      reconnectAudioBuffer = nil
      live.abandonInputTurn()
      VoiceTurnCoordinator.shared.send(
        .providerReconnectFailed(
          turnID: pending.turnID,
          identity: pending.identity,
          message: "realtime context admission rejected: \(admission)"))
      log("RealtimeHub: rejected context-preparation audio before provider admission: \(admission)")
      return
    }
    VoiceTurnCoordinator.shared.send(
      .providerReconnected(
        turnID: pending.turnID,
        identity: pending.identity,
        sessionID: voiceSessionID))
    guard VoiceTurnCoordinator.shared.isProviderConnectionReady(
      turnID: pending.turnID,
      sessionID: voiceSessionID)
    else {
      reconnectAudioBuffer = nil
      live.abandonInputTurn()
      log("RealtimeHub: reducer rejected context-prepared input before audio replay")
      return
    }
    reconnectAudioBuffer = nil
    inputTurnActivityStartPending = false
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    if live.supportsInputTranscriptionLanguage, !candidates.isEmpty {
      live.setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)
    }
    live.beginInputTurn(
      turnID: pending.turnID,
      responseID: pending.responseID,
      interrupting: pending.interrupting)
    for pcm16k in pending.audioBuffer {
      sendAudio(pcm16k, to: live)
    }
    if VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true {
      live.commitInputTurn()
      VoiceTurnCoordinator.shared.send(
        .hubCommitAccepted(
          turnID: pending.turnID,
          sessionID: voiceSessionID,
          responseID: pending.responseID))
    }
  }

  /// A released PTT turn remains eligible for context preparation while its
  /// reducer-owned commit is deferred. This lets a short press finish the
  /// snapshot/reconnect/replay sequence instead of abandoning its captured
  /// audio when the key is released before the snapshot arrives.
  private func contextFreshInputPreparationIsCurrent(
    turnID: VoiceTurnID,
    preparationEpoch: Int
  ) -> Bool {
    guard VoiceTurnCoordinator.shared.activeTurnID == turnID,
      turnEpoch == preparationEpoch,
      let activeTurn = VoiceTurnCoordinator.shared.activeTurn,
      activeTurn.id == turnID
    else {
      return false
    }
    return activeTurn.phase.isRecording || activeTurn.hubCommitPending
  }

  /// A failed kernel snapshot must release the buffered PTT boundary. Leaving
  /// it pending would prevent the next press from reserving a new input turn.
  private func failContextFreshInputPreparation(
    turnID: VoiceTurnID,
    message: String
  ) {
    guard let pending = reconnectAudioBuffer, pending.turnID == turnID else { return }
    reconnectAudioBuffer = nil
    inputTurnActivityStartPending = false
    guard VoiceTurnCoordinator.shared.activeTurnID == turnID else { return }
    session?.abandonInputTurn()
    VoiceTurnCoordinator.shared.send(
      .providerReconnectFailed(
        turnID: turnID,
        identity: pending.identity,
        message: message))
  }

  @discardableResult
  private func enqueueTurnPersistence(
    idempotencyKey: String,
    retainingReceipt: Bool = false,
    _ operation: @escaping @MainActor () async -> Bool
  ) -> Task<Bool, Never> {
    turnPersistenceLedger.enqueue(
      continuityKey: idempotencyKey,
      retainingReceipt: retainingReceipt,
      operation)
  }

  /// A native screen answer becomes visible before the provider can narrate it.
  /// Register its canonical journal obligation through the same retained receipt
  /// path as other authoritative local results before the reducer closes the turn.
  @discardableResult
  func enqueueAuthoritativeScreenEvidencePersistence(
    ownerID: String,
    assistantText: String
  ) -> Task<Bool, Never> {
    let idempotencyKey = turnIdempotencyKey
    let userText = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    return enqueueTurnPersistence(idempotencyKey: idempotencyKey, retainingReceipt: true) { [weak self] in
      await self?.persistTurnDirectlyToKernel(
        ownerID: ownerID,
        userText: userText,
        assistantText: assistantText,
        interrupted: false,
        idempotencyKey: idempotencyKey,
        acceptedSpawnOwnerID: nil) ?? false
    }
  }

  /// The kernel journal and its SQLite outbox are the only durable transcript
  /// authority. Swift may retry this idempotent RPC in-process, but never stores
  /// a second durable queue.
  private func persistTurnDirectlyToKernel(
    ownerID: String,
    userText: String,
    assistantText: String,
    interrupted: Bool,
    idempotencyKey: String,
    acceptedSpawnOwnerID: String?
  ) async -> Bool {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      log("RealtimeHub: refusing voice journal write after authenticated owner changed")
      return false
    }
    let surface = FloatingControlBarManager.shared.mainChatSurfaceReference()
    let kernelOwnsExchange = RealtimeHubContinuityRestore.kernelOwnsExchange(
      continuityKey: idempotencyKey,
      kernelTurnIDs: prefetchedVoiceContextTurnIDs)
    return await RealtimeTurnJournalAuthority.persist(
      turnOwnerID: ownerID,
      acceptedSpawnOwnerID: acceptedSpawnOwnerID,
      kernelOwnsExchange: kernelOwnsExchange,
      refreshAcceptedSpawn: {
        guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
        await FloatingControlBarManager.shared.refreshKernelJournal(surface: surface)
        return AuthorizedToolExecution.isOwnerCurrent(ownerID)
      },
      recordProviderExchange: {
        guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
        for attempt in 0..<2 {
          guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
          let accepted = await FloatingControlBarManager.shared.recordExchange(
            surface: surface,
            ownerID: ownerID,
            userText: userText,
            assistantText: assistantText,
            origin: "realtime_voice",
            continuityKey: idempotencyKey)
          guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
          if accepted { return true }
          if attempt == 0 { try? await Task.sleep(nanoseconds: 250_000_000) }
        }
        log("RealtimeHub: kernel journal rejected voice turn (code=journal_record_failed)")
        return false
      })
  }

  /// Imports at most 200 entries per pass from the retired Swift queue. This is
  /// an upgrade-only reader: successful entries move into the kernel journal and
  /// are deleted from UserDefaults; no new entry is ever written here.
  private func importLegacyVoiceJournalIfNeeded() async {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      !legacyVoiceJournalImportedOwners.contains(ownerID)
    else { return }
    if let existing = legacyVoiceJournalImportTask {
      await existing.value
      return
    }
    let task = Task { @MainActor [weak self] in
      guard let self else { return }
      guard let candidates = self.legacyVoiceJournalImportStore.nextBatch(ownerID: ownerID) else {
        log("RealtimeHub: legacy voice journal import skipped unreadable data")
        self.legacyVoiceJournalImportedOwners.insert(ownerID)
        return
      }
      if candidates.isEmpty {
        self.legacyVoiceJournalImportedOwners.insert(ownerID)
        return
      }

      var importedKeys = Set<String>()
      for entry in candidates {
        guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { break }
        let surface = AgentSurfaceReference(
          surfaceKind: entry.surfaceKind,
          externalRefKind: entry.externalRefKind,
          externalRefId: entry.externalRefID)
        let accepted = await FloatingControlBarManager.shared.recordExchange(
          surface: surface,
          ownerID: ownerID,
          userText: entry.userText,
          assistantText: entry.assistantText,
          origin: "realtime_voice",
          continuityKey: entry.idempotencyKey)
        guard accepted else { break }
        importedKeys.insert(entry.idempotencyKey)
      }

      self.legacyVoiceJournalImportStore.acknowledge(
        ownerID: ownerID, idempotencyKeys: importedKeys)
      if self.legacyVoiceJournalImportStore.nextBatch(ownerID: ownerID)?.isEmpty == true {
        self.legacyVoiceJournalImportedOwners.insert(ownerID)
      }
    }
    legacyVoiceJournalImportTask = task
    await task.value
    legacyVoiceJournalImportTask = nil
  }

  private func awaitTurnPersistenceFence() async {
    while !Task.isCancelled {
      let observedGeneration = turnPersistenceLedger.generation
      await turnPersistenceLedger.awaitPendingObligations()
      guard observedGeneration == turnPersistenceLedger.generation else { continue }
      return
    }
  }

  /// Completes the reducer-owned journal fence only after the canonical kernel
  /// has acknowledged this turn's stable idempotency key. Merely enqueueing the
  /// durable outbox entry is not logical success.
  func finalizeJournal(turnID: VoiceTurnID, identity: VoiceEffectIdentity) {
    let idempotencyKey = turnIdempotencyKey
    Task { @MainActor [weak self] in
      guard let self else { return }
      let receipt = await self.turnPersistenceLedger.consumeReceipt(for: idempotencyKey)
      guard VoiceTurnCoordinator.shared.activeTurnID == turnID else { return }
      let accepted = receipt?.accepted == true
      guard VoiceTurnCoordinator.shared.activeTurnID == turnID else { return }
      if accepted {
        VoiceTurnCoordinator.shared.send(
          .journalAccepted(turnID: turnID, identity: identity))
        // The provider only receives kernel context when its socket starts.
        // Re-warm after the durable journal acknowledgement so the usual next
        // PTT press is already fresh; beginTurn still enforces the hard gate
        // for a press that races this asynchronous refresh.
        self.requestSessionRefresh(reason: "voice_context_changed")
      } else {
        VoiceTurnCoordinator.shared.send(
          .journalFailed(
            turnID: turnID,
            identity: identity,
            message: "kernel journal did not acknowledge the turn"))
      }
    }
  }

  private func detachPhysicalSessionForTeardown(
    preservingReconnectAudio: Bool = false
  ) -> RealtimeHubSession? {
    let detachedSession = session
    // Detach first so a socket we're dropping can't deliver a late error/close to us
    // and tear down the fresh session we're about to create.
    detachedSession?.detach()
    session = nil
    voiceSessionID = nil
    // The buffered reconnect input is the logical owner of its response ID.
    // Rebind it here so callbacks from the fresh physical socket pass the same
    // identity fence that guarded the original PTT turn.
    voiceResponseID = RealtimeHubReconnectIdentityPolicy.responseIDAfterSessionDetach(
      preservingReconnectAudio: preservingReconnectAudio,
      pendingReconnect: reconnectAudioBuffer)
    sessionProvider = nil
    sessionAuth = nil
    sessionOwnerBinding = nil
#if DEBUG
    localProfileTransportAuthority = nil
#endif
    hubConnected = false  // no live session → PTT falls back to the cascade until re-warm
    sessionVoiceContextFreshnessIdentity = ""
    geminiSessionNeedsTurnBoundary = false
    if !preservingReconnectAudio {
      reconnectAudioBuffer = nil
    }
    clearBargeInReplacementState()
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
    return detachedSession
  }

  private func teardownSession(preservingReconnectAudio: Bool = false) {
    guard let detachedSession = detachPhysicalSessionForTeardown(
      preservingReconnectAudio: preservingReconnectAudio
    ) else { return }
    schedulePhysicalSessionTeardown(detachedSession)
  }

  private func schedulePhysicalSessionTeardown(_ detachedSession: RealtimeHubSession) {
    let sessionID = ObjectIdentifier(detachedSession)
    guard detachedSessionsAwaitingDrain[sessionID] == nil else { return }
    detachedSessionsAwaitingDrain[sessionID] = detachedSession
    Task { @MainActor [weak self, weak detachedSession] in
      guard let detachedSession else { return }
      await detachedSession.stopAndWait()
      self?.detachedSessionsAwaitingDrain.removeValue(forKey: sessionID)
    }
  }

  private func clearBargeInReplacementState() {
    bargeInReplacementGeneration &+= 1
    replacementAudioBuffer = nil
    pendingBargeInProvider = nil
    pendingBargeInAuth = nil
    pendingBargeInOwnerScope = nil
    bargeInContinuityTask?.cancel()
    bargeInContinuityTask = nil
  }

  @discardableResult
  private func prepareBargeInReplacement() -> Bool {
    guard let provider = sessionProvider ?? pendingBargeInProvider,
      let auth = sessionAuth ?? pendingBargeInAuth,
      let ownerScope = sessionOwnerScope ?? pendingBargeInOwnerScope,
      RealtimeHubOwnerFence.acceptsBargeInReplacement(
        sessionOwner: ownerScope,
        replacementOwner: ownerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId()),
      let turnID = VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.activeTurn?.ownerID == ownerScope.authenticatedOwnerID,
      let responseID = voiceResponseID,
      let identity = VoiceTurnCoordinator.shared.reserveEffectIdentity()
    else { return false }
    let interruptedSession = session
    interruptedSession?.detach()
    session = nil
    sessionProvider = nil
    sessionAuth = nil
    sessionOwnerBinding = nil
    hubConnected = false
    if let interruptedSession {
      schedulePhysicalSessionTeardown(interruptedSession)
    }
    replacementAudioBuffer = RealtimeReplacementAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: identity)
    VoiceTurnCoordinator.shared.send(
      .providerReplacementStarted(
        turnID: turnID,
        identity: identity,
        previousResponseID: nil,
        nextResponseID: responseID))
    pendingBargeInProvider = provider
    pendingBargeInAuth = auth
    pendingBargeInOwnerScope = ownerScope
    return true
  }

  private func completeBargeInReplacementAfterContinuity(
    interruptedTurnTask: Task<InterruptedTurnPayload?, Never>?
  ) {
    guard let replacementOwnerScope = pendingBargeInOwnerScope,
      isOwnerScopeCurrent(replacementOwnerScope)
    else {
      clearBargeInReplacementState()
      ensureWarm()
      return
    }
    bargeInContinuityTask?.cancel()
    bargeInReplacementGeneration &+= 1
    let generation = bargeInReplacementGeneration
    bargeInContinuityTask = Task { @MainActor [weak self] in
      guard let self else { return }
      let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
        resolveInterruptedTurn: {
          guard generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope)
          else { return nil }
          guard let interruptedTurnTask else { return nil }
          return await interruptedTurnTask.value
        },
        recordInterruptedTurn: { [weak self] turn in
          guard let self, generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope),
            turn.ownerID == replacementOwnerScope.authenticatedOwnerID
          else { return false }
          let task = self.enqueueTurnPersistence(idempotencyKey: turn.idempotencyKey) {
            [weak self] in
            await self?.persistTurnDirectlyToKernel(
              ownerID: turn.ownerID,
              userText: turn.userText,
              assistantText: turn.assistantText,
              interrupted: true,
              idempotencyKey: turn.idempotencyKey,
              acceptedSpawnOwnerID: turn.acceptedSpawnOwnerID) ?? false
          }
          return await task.value
        },
        refreshVoiceContext: { [weak self] in
          guard let self, generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope)
          else { return nil }
          await self.awaitTurnPersistenceFence()
          guard generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope)
          else { return nil }
          guard await self.refreshVoiceContextSnapshot() else { return nil }
          return self.prefetchedVoiceContextTurnIDs
        },
        startReplacementSession: { [weak self] in
          guard let self,
            generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope),
            self.pendingBargeInOwnerScope == replacementOwnerScope,
            let provider = self.pendingBargeInProvider,
            let auth = self.pendingBargeInAuth
          else { return }
          switch auth {
          case .byokKey:
            self.startReplacementSessionForBargeIn(
              provider: provider,
              auth: auth,
              ownerScope: replacementOwnerScope)
          case .ephemeral:
            self.remintReplacementSessionForBargeIn(provider: provider)
          }
        }
      )
      guard outcome != .started, outcome != .cancelled,
        generation == self.bargeInReplacementGeneration,
        self.isOwnerScopeCurrent(replacementOwnerScope),
        let provider = self.pendingBargeInProvider
      else { return }
      let reason: String
      switch outcome {
      case .interruptedTurnPersistenceFailed:
        reason = "interrupted turn could not be persisted"
      case .contextUnavailable:
        reason = "interrupted turn context did not become visible"
      case .started, .cancelled:
        return
      }
      self.failBargeInReplacement(provider: provider, reason: reason)
    }
  }

  @discardableResult
  private func restartSessionForBargeIn(
    interruptedTurnTask: Task<InterruptedTurnPayload?, Never>?
  ) -> Bool {
    guard prepareBargeInReplacement() else { return false }
    completeBargeInReplacementAfterContinuity(interruptedTurnTask: interruptedTurnTask)
    return true
  }

  private func remintReplacementSessionForBargeIn(provider: RealtimeHubProvider) {
    guard let ownerScope = pendingBargeInOwnerScope,
      case .authenticated(let ownerID) = ownerScope,
      isOwnerScopeCurrent(ownerScope)
    else {
      clearBargeInReplacementState()
      ensureWarm()
      return
    }
    guard let mintGeneration = beginMint(ownerScope: ownerScope) else {
      log(
        "RealtimeHub[\(provider.displayName)]: barge-in replacement queued behind existing token mint"
      )
      return
    }
    let replacementGeneration = bargeInReplacementGeneration
    let providerParam = provider == .openai ? "openai" : "gemini"
    log("RealtimeHub[\(provider.displayName)]: minting fresh token for barge-in replacement")
    Task { [weak self] in
      guard let self else { return }
      if self.redriveReplacementMintIfStale(
        replacementGeneration: replacementGeneration,
        mintGeneration: mintGeneration,
        ownerScope: ownerScope)
      { return }
      guard self.replacementAudioBuffer != nil else {
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        return
      }
      guard self.effectiveProvider == provider, self.session == nil else {
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        self.clearBargeInReplacementState()
        self.ensureWarm()
        return
      }
      let token: String
      do {
        token = try await APIClient.shared.mintRealtimeToken(
          provider: providerParam,
          expectedOwnerID: ownerID)
      } catch let error as RealtimeTokenMintError {
        if self.redriveReplacementMintIfStale(
          replacementGeneration: replacementGeneration,
          mintGeneration: mintGeneration,
          ownerScope: ownerScope)
        { return }
        guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
        self.recordRealtimeMintFailure(
          error,
          provider: providerParam,
          phase: "barge_in_replacement",
          context: "realtime_barge_in_mint")
        if self.shouldFailoverToAlternate(for: error.healthError.failureClass),
          self.failoverBargeInReplacement(
            from: provider,
            reason: self.failoverReason(for: error.healthError.failureClass))
        {
          return
        }
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if !error.healthError.failureClass.isAccountWide {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      } catch let error as CredentialHealthError {
        if self.redriveReplacementMintIfStale(
          replacementGeneration: replacementGeneration,
          mintGeneration: mintGeneration,
          ownerScope: ownerScope)
        { return }
        guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
        CredentialHealthManager.shared.record(error, context: "realtime_barge_in_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: error.failureClass.logValue,
          phase: "barge_in_replacement",
          httpStatusCode: error.failureClass.httpStatusCode)
        if self.shouldFailoverToAlternate(for: error.failureClass),
          self.failoverBargeInReplacement(
            from: provider,
            reason: self.failoverReason(for: error.failureClass))
        {
          return
        }
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if !error.failureClass.isAccountWide {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      } catch {
        if self.redriveReplacementMintIfStale(
          replacementGeneration: replacementGeneration,
          mintGeneration: mintGeneration,
          ownerScope: ownerScope)
        { return }
        guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: "backend_transient",
          phase: "barge_in_replacement")
        if self.failoverBargeInReplacement(from: provider, reason: "other") {
          return
        }
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        return
      }
      if self.redriveReplacementMintIfStale(
        replacementGeneration: replacementGeneration,
        mintGeneration: mintGeneration,
        ownerScope: ownerScope)
      { return }
      guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
      self.startReplacementSessionForBargeIn(
        provider: provider,
        auth: .ephemeral(token),
        ownerScope: ownerScope)
    }
  }

  /// A completed mint belongs to the replacement generation that started it.
  /// Stale success and failure callbacks may only release the mint slot and
  /// redrive the newest generation; they must not mutate that generation's state.
  @discardableResult
  private func redriveReplacementMintIfStale(
    replacementGeneration: UInt64,
    mintGeneration: UInt64,
    ownerScope: RealtimeHubOwnerScope
  ) -> Bool {
    guard self.mintGeneration == mintGeneration, mintOwnerScope == ownerScope else { return true }
    let generationChanged = replacementGeneration != bargeInReplacementGeneration
    let ownerChanged = !isOwnerScopeCurrent(ownerScope)
      || pendingBargeInOwnerScope != ownerScope
    guard generationChanged || ownerChanged else { return false }
    _ = releaseMint(generation: mintGeneration, ownerScope: ownerScope)
    if ownerChanged {
      log("RealtimeHub: discarding barge-in remint after authenticated owner changed")
      clearBargeInReplacementState()
      ensureWarm()
    } else if replacementAudioBuffer != nil, let currentProvider = pendingBargeInProvider {
      remintReplacementSessionForBargeIn(provider: currentProvider)
    }
    return true
  }

  private func startReplacementSessionForBargeIn(
    provider: RealtimeHubProvider,
    auth: HubAuth,
    ownerScope: RealtimeHubOwnerScope
  ) {
    guard
      RealtimeHubOwnerFence.acceptsBargeInReplacement(
        sessionOwner: ownerScope,
        replacementOwner: pendingBargeInOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    else {
      clearBargeInReplacementState()
      ensureWarm()
      return
    }
    startSession(provider: provider, auth: auth, ownerScope: ownerScope)
  }

  private func finishBargeInReplacementAfterSessionReady() {
    guard let pending = replacementAudioBuffer else { return }
    replacementAudioBuffer = nil
    pendingBargeInProvider = nil
    pendingBargeInAuth = nil
    pendingBargeInOwnerScope = nil
    guard let voiceSessionID else { return }
    VoiceTurnCoordinator.shared.send(
      .providerReplacementReady(
        turnID: pending.turnID,
        identity: pending.identity,
        sessionID: voiceSessionID,
        responseID: pending.responseID))
    guard VoiceTurnCoordinator.shared.isProviderConnectionReady(
      turnID: pending.turnID,
      sessionID: voiceSessionID,
      responseID: pending.responseID)
    else {
      session?.abandonInputTurn()
      log("RealtimeHub: discarded stale barge-in replacement before audio replay")
      return
    }
    if let live = session {
      live.beginInputTurn(
        turnID: pending.turnID,
        responseID: pending.responseID,
        interrupting: false)
    }
    flushBargeInReplacementAudioBuffer(pending.audioBuffer)
    if VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true {
      session?.commitInputTurn()
      VoiceTurnCoordinator.shared.send(
        .hubCommitAccepted(
          turnID: pending.turnID,
          sessionID: voiceSessionID,
          responseID: pending.responseID))
    }
  }

  /// Replays a turn captured while a regular warm session was being replaced.
  /// The provider input window opens before replay so Gemini's activity boundaries
  /// and OpenAI's event ownership remain tied to the original PTT turn.
  private func finishSessionReconnectAfterReady() {
    guard let pending = reconnectAudioBuffer, let live = session else { return }
    guard let voiceSessionID else { return }
    let admission = RealtimeInputAdmissionPolicy.decide(
      pending: pending,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      sessionContextFreshnessIdentity: sessionVoiceContextFreshnessIdentity)
    guard admission == .admit else {
      reconnectAudioBuffer = nil
      live.abandonInputTurn()
      VoiceTurnCoordinator.shared.send(
        .providerReconnectFailed(
          turnID: pending.turnID,
          identity: pending.identity,
          message: "realtime reconnect admission rejected: \(admission)"))
      log("RealtimeHub: rejected reconnect audio before provider admission: \(admission)")
      return
    }
    reconnectAudioBuffer = nil
    VoiceTurnCoordinator.shared.send(
      .providerReconnected(
        turnID: pending.turnID,
        identity: pending.identity,
        sessionID: voiceSessionID))
    guard VoiceTurnCoordinator.shared.isProviderConnectionReady(
      turnID: pending.turnID,
      sessionID: voiceSessionID)
    else {
      live.abandonInputTurn()
      log("RealtimeHub: reducer rejected reconnect before audio replay")
      return
    }
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    if live.supportsInputTranscriptionLanguage, !candidates.isEmpty {
      live.setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)
    }
    live.beginInputTurn(
      turnID: pending.turnID,
      responseID: pending.responseID,
      interrupting: pending.interrupting)
    for pcm16k in pending.audioBuffer {
      sendAudio(pcm16k, to: live)
    }
    if VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true {
      live.commitInputTurn()
      VoiceTurnCoordinator.shared.send(
        .hubCommitAccepted(
          turnID: pending.turnID,
          sessionID: voiceSessionID,
          responseID: pending.responseID))
    }
  }

  private func failBargeInReplacement(provider: RealtimeHubProvider, reason: String) {
    let failedBuffer = replacementAudioBuffer
    let hadCommittedTurn = failedBuffer.map {
      VoiceTurnCoordinator.shared.activeTurn?.id == $0.turnID
        && VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true
    } ?? false
    clearBargeInReplacementState()
    log(
      "RealtimeHub[\(provider.displayName)]: barge-in replacement failed "
        + "\(hadCommittedTurn ? "after commit" : "while recording") — \(reason)")
    realtimePlaybackEpoch += 1
    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
    exitVoiceUI(clearResponseGlow: true)
    if let failedBuffer {
      VoiceTurnCoordinator.shared.send(
        .providerReplacementFailed(
          turnID: failedBuffer.turnID,
          identity: failedBuffer.identity,
          message: reason))
    }
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
        self.realtimePlaybackEpoch = playbackEpoch
      }
    }
    player.onPlaybackIdle = { [weak self] playbackEpoch in
      Task { @MainActor in
        guard let self, self.realtimePlaybackEpoch == playbackEpoch else { return }
        if let lease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease,
          lease.lane == .nativeRealtime
        {
          if VoiceTurnCoordinator.shared.releaseOutput(lease) {
            if VoiceTurnCoordinator.shared.model.turn?.phase.isTerminal == true {
              self.exitVoiceUI()
              self.applyPendingSessionRefreshIfIdle()
            }
          }
        }
        self.clearResponseGlowIfRealtimeAudioIdle()
      }
    }
    return player
  }

  /// Replaces the provider's post-tool narration with the kernel's durable
  /// admission fact. A spawn receipt is not a child completion receipt, so this
  /// is the only spoken acknowledgement for a PTT spawn turn.
  private func playCanonicalSpawnAcknowledgement(_ text: String) {
    let acknowledgement = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !acknowledgement.isEmpty else { return }

    // A provider can begin a speculative response before its tool call returns.
    // Once the kernel accepts the spawn, that narration can no longer make
    // lifecycle claims. Stop it before taking the deterministic acknowledgement
    // lease so no stale audio competes with the canonical fact.
    takeOverVoiceOutputForAuthoritativeLocalResult()
    guard let lease = acquireVoiceOutput(.deterministicAgentAck, reason: "canonical_spawn_receipt")
    else { return }
    responseGlowGate.markPlaybackActive(lease: lease)
    FloatingBarVoicePlaybackService.shared.speakOneShot(acknowledgement, lease: lease)
  }

  /// Local results such as accepted agent receipts and verified/fail-closed
  /// screen evidence supersede any speculative provider narration for this
  /// turn. Keep the physical preemption and reducer lease release together so
  /// every authoritative answer can acquire its own deterministic lease.
  func takeOverVoiceOutputForAuthoritativeLocalResult() {
    if let activeLease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease {
      FloatingBarVoicePlaybackService.shared.interruptCurrentResponse(leaseID: activeLease.id)
      _ = VoiceTurnCoordinator.shared.releaseOutput(activeLease)
    }
    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
  }

  func acquireVoiceOutput(_ lane: VoiceOutputLane, reason: String) -> VoiceOutputLease? {
    guard let turnID = VoiceTurnCoordinator.shared.activeTurnID else {
      log(
        "RealtimeHub[\(providerTag)]: dropping \(lane.rawValue) output with no active PTT turn reason=\(reason)"
      )
      return nil
    }
    _ = FloatingBarVoicePlaybackService.shared.preemptFillerIfNeeded(
      for: lane,
      turnID: turnID)
    switch VoiceTurnCoordinator.shared.acquireOutput(lane, turnID: turnID) {
    case .acquired(let lease):
      return lease
    case .denied(let active):
      log(
        "RealtimeHub[\(providerTag)]: dropping \(lane.rawValue) output reason=\(reason) "
          + "active_lane=\(active.lane.rawValue)"
      )
      return nil
    case .staleTurn:
      log("RealtimeHub[\(providerTag)]: dropping stale \(lane.rawValue) output reason=\(reason)")
      return nil
    }
  }

  private func releaseVoiceOutputIfActive(_ lane: VoiceOutputLane) {
    guard let lease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease, lease.lane == lane else {
      return
    }
    _ = VoiceTurnCoordinator.shared.releaseOutput(lease)
  }

  /// Executes the reducer's exact native-audio stop effect. Terminal reduction
  /// clears the logical lease before effects run, so the terminal record is the
  /// authoritative fallback fence for this synchronous physical cleanup.
  @discardableResult
  func stopNativePlayback(lease: VoiceOutputLease) -> Bool {
    guard lease.lane == .nativeRealtime else { return false }
    let ownsActiveLease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease == lease
    let ownsTerminalTurn = VoiceTurnCoordinator.shared.activeTurnID == nil
      && VoiceTurnCoordinator.shared.model.lastTerminal?.turnID == lease.turnID
    guard ownsActiveLease || ownsTerminalTurn else {
      log("RealtimeHub: ignored stale native playback stop lease=\(lease.id)")
      return false
    }
    realtimePlaybackEpoch += 1
    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
    return true
  }

  // MARK: - PTT integration

  /// PTT-down: make sure the socket is warm and reset per-turn state. The typed
  /// result is the caller's fail-closed gate for buffered audio replay.
  @discardableResult
  func beginTurn(turnID requestedTurnID: VoiceTurnID? = nil) -> RealtimeInputPreparationResult {
    if discardMismatchedSessionIfNeeded() { ensureWarm() }
    turnPreparationTask?.cancel()
    turnPreparationTask = nil
    // Barge-in: was a reply from the previous turn still in flight when the user
    // started talking again?
    let providerResponseInFlight = reducerInterruptsPreviousTurn
    let voicePlaybackActive = FloatingBarVoicePlaybackService.shared.isSpeaking
    let bargeIn = providerResponseInFlight || reducerNativePlaybackActive || voicePlaybackActive
    let bargeInAction = RealtimeHubBargeInAction.decide(
      providerResponseInFlight: providerResponseInFlight,
      playbackActive: reducerNativePlaybackActive || voicePlaybackActive,
      strategy: session?.bargeInStrategy ?? .inSessionCancel)
    let supersedesPendingReplacement = replacementAudioBuffer != nil
    let requiresCompletedGeminiSessionBoundary =
      sessionProvider == .gemini && geminiSessionNeedsTurnBoundary
    let interruptedTurnIdempotencyKey = turnIdempotencyKey
    let interruptedTurnTask = bargeIn ? captureInterruptedTurnPayloadIfNeeded() : nil
    let turnID =
      requestedTurnID
      ?? VoiceTurnCoordinator.shared.activeTurnID
      ?? VoiceTurnCoordinator.shared.begin(intent: .hold)
    guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil else {
      log("RealtimeHub: refusing to begin provider input for a stale voice owner")
      return .rejected
    }
    if let pending = reconnectAudioBuffer, pending.turnID != turnID {
      reconnectAudioBuffer = nil
      log("RealtimeHub: discarded reconnect audio for a superseded rapid PTT turn")
    }
    let responseID = VoiceResponseID(UUID().uuidString)
    voiceResponseID = responseID
    realtimePlaybackEpoch += 1
    var deferredFreshSessionContextPrefetch = false
    turnTranscript = ""
    providerTranscriptFinalized = false
    lastInputTranscriptUpdateAt = nil
    assistantText = ""
    audioReceivedThisTurn = false
    lastExternalToolName = ""
    lastExternalToolErrorCode = ""
    turnIdempotencyKey = "voice:\(turnID.rawValue.uuidString.lowercased())"
    resetScreenGrounding(for: turnID)
    if let interruptedTurnTask, !supersedesPendingReplacement {
      if !providerResponseInFlight || session?.bargeInStrategy != .freshSession {
        enqueueTurnPersistence(idempotencyKey: interruptedTurnIdempotencyKey) { [weak self] in
          guard let interruptedTurn = await interruptedTurnTask.value else { return true }
          return await self?.persistTurnDirectlyToKernel(
            ownerID: interruptedTurn.ownerID,
            userText: interruptedTurn.userText,
            assistantText: interruptedTurn.assistantText,
            interrupted: true,
            idempotencyKey: interruptedTurn.idempotencyKey,
            acceptedSpawnOwnerID: interruptedTurn.acceptedSpawnOwnerID) ?? false
        }
      }
    }
    turnEpoch += 1
    let preparationEpoch = turnEpoch
    turnAudio16k.removeAll(keepingCapacity: true)
    earlyLIDTask = nil
    turnEarlyVerdictCode = nil
    fullLIDTask = nil
    testProviderTranscriptOverride = nil  // never leak a test override into a real turn
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
    lastTurnAt = Date()
    inputTurnActivityStartPending = false
    if bargeIn {
      pcmPlayer?.stop()  // stop the prior reply locally only for a real barge-in.
    }
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    responseGlowGate.clearImmediately()
    if supersedesPendingReplacement {
      if restartSessionForBargeIn(interruptedTurnTask: interruptedTurnTask) {
        deferredFreshSessionContextPrefetch = true
        log("RealtimeHub[gemini]: rotating pending replacement to the newest PTT turn")
      } else {
        session?.cancelActiveResponse()
      }
    } else if requiresCompletedGeminiSessionBoundary {
      if restartSessionForBargeIn(interruptedTurnTask: nil) {
        deferredFreshSessionContextPrefetch = true
        geminiSessionNeedsTurnBoundary = false
        log("RealtimeHub[gemini]: replacing completed-turn session before next PTT")
      } else {
        session?.cancelActiveResponse()
      }
    } else {
      switch bargeInAction {
      case .cancelInSession:
        // OpenAI exposes an explicit response.cancel path, so the warm socket and
        // conversation context survive while the next input buffer starts clean.
        log("RealtimeHub[\(providerTag)]: barge-in — interrupting in-flight reply (same session)")
        session?.cancelActiveResponse()
      case .replaceSession:
        // Gemini Live has no reliable in-session cancel for a streaming reply. Reusing
        // that socket can leave the next PTT turn queued behind the old generation, so
        // replace the connection and let the fresh session buffer this new turn while it opens.
        if restartSessionForBargeIn(interruptedTurnTask: interruptedTurnTask) {
          deferredFreshSessionContextPrefetch = true
          log("RealtimeHub: barge-in — replacing session for clean next turn")
        } else {
          session?.cancelActiveResponse()
        }
      case .stopPlaybackTail:
        log("RealtimeHub[\(providerTag)]: barge-in — stopping local playback tail")
      case .none:
        break
      }
    }
    if !deferredFreshSessionContextPrefetch {
      guard beginContextFreshInputPreparation(
        turnID: turnID,
        responseID: responseID,
        interrupting: providerResponseInFlight
      ) else {
        log("RealtimeHub: unable to establish a context-fresh PTT input boundary")
        return .rejected
      }
      turnPreparationTask = Task { @MainActor [weak self] in
        guard let self else { return }
        guard !Task.isCancelled else { return }
        guard await self.refreshVoiceContextSnapshot() else {
          self.failContextFreshInputPreparation(
            turnID: turnID,
            message: "Voice context is temporarily unavailable")
          return
        }
        guard !Task.isCancelled,
          self.contextFreshInputPreparationIsCurrent(
            turnID: turnID,
            preparationEpoch: preparationEpoch)
        else { return }
        let current = self.voiceSessionContext(for: self.currentOwnerScope)
        guard var pending = self.reconnectAudioBuffer,
          pending.turnID == turnID,
          pending.bindRequiredContextFreshnessIdentity(current.snapshotFreshnessIdentity)
        else {
          self.failContextFreshInputPreparation(
            turnID: turnID,
            message: "Voice context admission identity is unavailable")
          return
        }
        self.reconnectAudioBuffer = pending
        let needsSessionRefresh = self.session != nil
          && RealtimeVoiceContextRefreshPolicy.requiresRefresh(
            currentSnapshotIdentity: current.snapshotFreshnessIdentity,
            sessionSnapshotIdentity: self.sessionVoiceContextFreshnessIdentity)
        if needsSessionRefresh {
          log("RealtimeHub: reconnecting before PTT input so provider instructions match canonical context")
          self.pendingContextCacheReplacement = true
          self.teardownSession(preservingReconnectAudio: true)
        }
        guard !Task.isCancelled,
          self.contextFreshInputPreparationIsCurrent(
            turnID: turnID,
            preparationEpoch: preparationEpoch)
        else { return }
        self.ensureWarm()
        if await self.waitUntilActive(timeout: 15) {
          guard !Task.isCancelled,
            self.contextFreshInputPreparationIsCurrent(
              turnID: turnID,
              preparationEpoch: preparationEpoch)
          else { return }
          self.finishContextFreshInputOnCurrentSession()
        } else {
          guard !Task.isCancelled,
            self.contextFreshInputPreparationIsCurrent(
              turnID: turnID,
              preparationEpoch: preparationEpoch)
          else { return }
          self.inputTurnActivityStartPending = true
          log(
            "RealtimeHub: session not ready for context-fresh PTT input — will replay on connect")
        }
      }
    }
    return .accepted
  }

  private func captureInterruptedTurnPayloadIfNeeded() -> Task<InterruptedTurnPayload?, Never>? {
    if turnPersistenceLedger.pendingContinuityKeys.contains(turnIdempotencyKey)
      || turnPersistenceLedger.receipt(for: turnIdempotencyKey)?.accepted == true
      || !prefetchedVoiceContextTurnIDs.isDisjoint(
        with: KernelTurnProjection.stableTurnIDs(continuityKey: turnIdempotencyKey)
      )
    {
      return nil
    }
    let providerText = turnTranscript
    let localTask = fullLIDTask
    guard !providerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || localTask != nil
    else { return nil }
    let preferredLanguages = AssistantSettings.shared.voiceBaseLanguages
    let partialAssistantText = assistantText
    let idempotencyKey = turnIdempotencyKey
    let acceptedSpawnOwnerID = acceptedSpawnJournalReceiptByContinuityKey[idempotencyKey]?.ownerID
    guard let ownerID = VoiceTurnCoordinator.shared.activeTurn?.ownerID else { return nil }
    return Task {
      let resolution = await Self.resolveTranscript(
        providerText: providerText,
        preferredLanguages: preferredLanguages,
        localTask: localTask)
      guard !resolution.userText.isEmpty else { return nil }
      return InterruptedTurnPayload(
        ownerID: ownerID,
        userText: resolution.userText,
        assistantText: InterruptedTurnPayload.visibleAssistantText(
          partialAssistantText: partialAssistantText),
        idempotencyKey: idempotencyKey,
        acceptedSpawnOwnerID: acceptedSpawnOwnerID)
    }
  }

  /// Mic chunk (16 kHz PCM16 mono) → resample to the provider's rate → session.
  func feedAudio(_ pcm16k: Data, turnID requestedTurnID: VoiceTurnID? = nil) {
    // A first PTT can be buffering while its context-fresh session reconnects. Reconciliation
    // tears a session down and clears that buffer, so it is safe only when no turn owns audio.
    if VoiceTurnCoordinator.shared.activeTurnID == nil,
      discardMismatchedSessionIfNeeded()
    {
      ensureWarm()
    }
    if let requestedTurnID {
      guard requestedTurnID == VoiceTurnCoordinator.shared.activeTurnID,
        VoiceAudioIngressOwnership.accepts(
          turnID: requestedTurnID,
          activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
          capturingInput: reducerCapturingInput)
      else {
        log("RealtimeHub: dropping audio for closed/stale turn \(requestedTurnID)")
        return
      }
    }
    guard let turnID = requestedTurnID ?? VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil
    else {
      log("RealtimeHub: refusing audio ingress for a stale voice owner")
      return
    }
    bufferTurnAudio(pcm16k)
    if replacementAudioBuffer != nil {
      if replacementAudioBuffer?.appendAudio(pcm16k) == false {
        log(
          "RealtimeHub: replacement audio buffer reached "
            + "\(RealtimeReplacementAudioBuffer.maxBufferedAudioBytes) bytes; truncating turn audio"
        )
      }
      return
    }
    let activeTurnID = VoiceTurnCoordinator.shared.activeTurnID
    if var pending = reconnectAudioBuffer {
      if pending.turnID != activeTurnID {
        reconnectAudioBuffer = nil
        log("RealtimeHub: discarded reconnect audio for a superseded PTT turn")
      } else {
        if pending.appendAudio(pcm16k) == false {
          log(
            "RealtimeHub: reconnect audio buffer reached "
              + "\(RealtimeReconnectAudioBuffer.maxBufferedAudioBytes) bytes; truncating turn audio"
          )
        }
        reconnectAudioBuffer = pending
        return
      }
    }
    guard let s = session else {
      guard let activeTurnID, let responseID = voiceResponseID else {
        log("RealtimeHub[\(providerTag)]: dropping mic audio without a PTT turn identity")
        return
      }
      guard let identity = VoiceTurnCoordinator.shared.reserveEffectIdentity() else { return }
      var pending = RealtimeReconnectAudioBuffer(
        turnID: activeTurnID,
        responseID: responseID,
        identity: identity,
        interrupting: reducerInterruptsPreviousTurn)
      _ = pending.appendAudio(pcm16k)
      reconnectAudioBuffer = pending
      VoiceTurnCoordinator.shared.send(
        .providerReconnectStarted(
          turnID: activeTurnID,
          identity: identity,
          previousSessionID: voiceSessionID))
      log("RealtimeHub[\(providerTag)]: buffering mic audio until the reconnecting session is ready")
      ensureWarm()
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
    let pcm =
      rate == 16000 ? pcm16k : PushToTalkManager.resamplePCM16(pcm16k, from: 16000, to: rate)
    s.sendAudio(pcm)
  }

  /// PTT-up: end the turn; the model now responds (and may call tools).
  func commitTurn() -> RealtimeHubCommitResult {
    // Preserve a context-fresh reconnect buffer through PTT-up; its deferred commit is drained
    // by finishContextFreshInputOnCurrentSession once the replacement socket is ready.
    if VoiceTurnCoordinator.shared.activeTurnID == nil,
      discardMismatchedSessionIfNeeded()
    {
      ensureWarm()
    }
    guard let turnID = VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil
    else {
      log("RealtimeHub: rejected duplicate/stale physical commit before provider side effects")
      return .rejectedNoSession
    }
    guard VoiceTurnCoordinator.shared.canCommitHubTurn(turnID) else {
      if RealtimeHubCommitOwnershipPolicy.isAlreadyOwned(
        turn: VoiceTurnCoordinator.shared.activeTurn,
        requestedTurnID: turnID)
      {
        log("RealtimeHub: physical commit is already owned by the pending realtime turn")
        return .alreadyOwned
      }
      log("RealtimeHub: rejected duplicate/stale physical commit before provider side effects")
      return .rejectedNoSession
    }

    if let pending = replacementAudioBuffer {
      VoiceTurnCoordinator.shared.send(.hubCommitDeferredForReplacement(turnID: turnID))
      prepareAcceptedCommit()
      log(
        "RealtimeHub[\(providerTag)]: barge-in replacement not ready at commit — "
          + "deferring commit (bufferedChunks=\(pending.audioBuffer.count))"
      )
      return .deferredForReplacement
    }
    if let pending = reconnectAudioBuffer {
      VoiceTurnCoordinator.shared.send(.hubCommitDeferred(turnID: turnID))
      prepareAcceptedCommit(preservingContextPreparation: true)
      log(
        "RealtimeHub[\(providerTag)]: session reconnect not ready at commit — "
          + "deferring commit (bufferedChunks=\(pending.audioBuffer.count))"
      )
      ensureWarm()
      return .deferredForReconnect
    }
    guard session != nil, voiceSessionID != nil else {
      turnPreparationTask?.cancel()
      turnPreparationTask = nil
      inputTurnActivityStartPending = false
      exitVoiceUI(clearResponseGlow: true)
      return .rejectedNoSession
    }

    // The coordinator deliberately queues nested events while it is reducing
    // `.finalizeCapturedInput`.  Do not inspect the turn immediately after
    // sending this claim: that sees the prior `.finalizing` state and falsely
    // rejects a valid physical PTT release.  The reducer emits the provider
    // effect after it has applied this claim, and `commitClaimedHubInput` below
    // is the sole driver for the actual provider commit.
    VoiceTurnCoordinator.shared.send(.hubCommitClaimed(turnID: turnID))
    return .accepted
  }

  /// Performs the provider side of a physical hub commit after the reducer has
  /// applied its `hubCommitClaimed` state transition. This runs from the
  /// coordinator effect queue, so it cannot observe the stale state that
  /// existed before a nested commit claim was reduced.
  func commitClaimedHubInput(turnID: VoiceTurnID) {
    guard let activeTurn = VoiceTurnCoordinator.shared.activeTurn,
      activeTurn.id == turnID,
      activeTurn.phase == .awaitingResponse,
      activeTurn.hubCommitPending,
      VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil
    else {
      log("RealtimeHub: dropped stale claimed physical commit")
      return
    }

    guard let s = session, let voiceSessionID else {
      log("RealtimeHub: claimed physical commit lost its session before provider side effects")
      turnPreparationTask?.cancel()
      turnPreparationTask = nil
      inputTurnActivityStartPending = false
      VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .providerFailed))
      exitVoiceUI(clearResponseGlow: true)
      return
    }

    let candidates = AssistantSettings.shared.voiceBaseLanguages
    prepareAcceptedCommit()
    // Hint the provider's transcription with the identified language, entirely
    // synchronously: one configured language → hint it directly; several → whatever the
    // mid-hold verdict produced by now (nil clears any stale hint from a prior turn and
    // leaves the provider on auto-detect — same as today's behavior).
    if s.supportsInputTranscriptionLanguage, !candidates.isEmpty {
      s.setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)
    }
    if let voiceResponseID {
      // PTT-up can beat asynchronous context preparation. Queue begin before
      // commit on the session transport so Gemini always has activityStart and
      // OpenAI always has an immutable event identity.
      s.beginInputTurn(
        turnID: turnID,
        responseID: voiceResponseID,
        interrupting: reducerInterruptsPreviousTurn)
    }
    s.commitInputTurn()
    VoiceTurnCoordinator.shared.send(
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: voiceSessionID,
        responseID: voiceResponseID))
  }

  /// Prepare local state shared by immediate and deferred hub commits. Screen
  /// pixels are captured only by the kernel-authorized screenshot tool; voice
  /// commits themselves never attach an ambient frame.
  private func prepareAcceptedCommit(preservingContextPreparation: Bool = false) {
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    if !preservingContextPreparation {
      turnPreparationTask?.cancel()
      turnPreparationTask = nil
      inputTurnActivityStartPending = false
    }
    // Runs during the seconds the model spends answering; consumed at turn-done.
    if !turnAudio16k.isEmpty {
      let audio = turnAudio16k
      fullLIDTask = Task.detached(priority: .userInitiated) {
        await PTTLanguageIdentifier.shared.identify(pcm16k: audio, candidates: candidates)
      }
    }
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

  private static func resolveTranscript(
    providerText: String,
    preferredLanguages: [String],
    localTask: Task<PTTLanguageIdentifier.Verdict, Never>?
  ) async -> RealtimeHubTranscriptResolution {
    let trimmedProvider = providerText.trimmingCharacters(in: .whitespacesAndNewlines)
    let providerLanguage =
      trimmedProvider.isEmpty
      ? nil : PTTLanguageIdentifier.dominantLanguage(of: trimmedProvider, hints: [])
    let needsLocal =
      trimmedProvider.isEmpty
      || (!preferredLanguages.isEmpty
        && (providerLanguage.map { !preferredLanguages.contains($0) } ?? false))
    let verdict =
      needsLocal && localTask != nil
      ? await value(of: localTask!, timeoutMs: 20_000) : nil
    return RealtimeHubTranscriptPolicy.resolve(
      providerText: trimmedProvider,
      preferredLanguages: preferredLanguages,
      localTranscript: verdict?.transcript,
      localLanguage: verdict?.languageCode)
  }

  /// Abandon the turn without committing (silent tap / cancel). Must leave NO open
  /// turn behind, or the model answers the non-speech later.
  @discardableResult
  func cancelTurn(turnID requestedTurnID: VoiceTurnID) -> Bool {
    let activeOwner = VoiceTurnCoordinator.shared.activeTurnID == requestedTurnID
    let terminalOwner = VoiceTurnCoordinator.shared.activeTurnID == nil
      && VoiceTurnCoordinator.shared.model.lastTerminal?.turnID == requestedTurnID
    guard activeOwner || terminalOwner else {
      log("RealtimeHub: ignored stale cancelTurn id=\(requestedTurnID)")
      return false
    }
    let canceledPreparationTask = turnPreparationTask
    turnPreparationTask?.cancel()
    turnPreparationTask = nil
    inputTurnActivityStartPending = false
    reconnectAudioBuffer = nil
    realtimePlaybackEpoch += 1
    pcmPlayer?.stop()
    turnTranscript = ""
    providerTranscriptFinalized = false
    lastInputTranscriptUpdateAt = nil
    assistantText = ""
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
    let interruptedContinuityTask = bargeInContinuityTask
    bargeInContinuityTask = nil
    clearBargeInReplacementState()
    // Abandon the open turn WITHOUT tearing down the socket: close the speech window
    // and leave the reply gated off so the model never answers the silence. Keeps the
    // warm session (and its context) so the next real turn is instant and in-context.
    let terminalReason = VoiceTurnCoordinator.shared.model.lastTerminal
      .flatMap { $0.turnID == requestedTurnID ? $0.reason : nil }
    let replaceAbandonedSession = terminalReason != .success
    if terminalReason != .success {
      session?.abandonInputTurn()
    }
    if replaceAbandonedSession {
      // A canceled provider input may still emit commit/activity acknowledgements.
      // Give every abandoned turn a fresh socket boundary before a later turn
      // can enqueue new pending identities on the same transport.
      cancelContinuityFenceActive = true
      cancelContinuityFenceTurnID = requestedTurnID
      teardownSession()
      pendingSessionRefreshReason = "voice_context_changed"
      canceledTurnRewarmTask?.cancel()
      canceledTurnRewarmTask = Task { @MainActor [weak self] in
        if let canceledPreparationTask {
          await canceledPreparationTask.value
        }
        if let interruptedContinuityTask {
          await interruptedContinuityTask.value
        }
        guard let self, !Task.isCancelled else { return }
        let refreshed = await self.refreshVoiceContextAfterPersistenceFence(
          reason: "voice_context_changed")
        guard !Task.isCancelled else { return }
        guard refreshed else {
          self.canceledTurnRewarmTask = nil
          return
        }
        self.cancelContinuityFenceActive = false
        self.cancelContinuityFenceTurnID = nil
        self.canceledTurnRewarmTask = nil
        if self.pendingSessionRefreshReason == "voice_context_changed" {
          self.pendingSessionRefreshReason = nil
        }
        log("RealtimeHub: applying canceled-turn voice context refresh after continuity persistence")
        self.teardownSession()
        self.ensureWarm()
      }
    }
    exitVoiceUI(clearResponseGlow: true)
    if !replaceAbandonedSession {
      applyPendingSessionRefreshIfIdle()
    }
    return true
  }

  // MARK: - RealtimeHubSessionDelegate

  private func isCurrentSession(_ source: RealtimeHubSession) -> Bool {
    let isLiveSessionObject = source === session
    let sessionOwnerIsCurrent = RealtimeHubOwnerFence.canReuseWarmSession(
      sessionOwner: sessionOwnerScope,
      currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    guard
      RealtimeHubReconnectIdentityPolicy.admitsSessionCallback(
        isLiveSessionObject: isLiveSessionObject,
        sessionOwnerIsCurrent: sessionOwnerIsCurrent)
    else {
      if isLiveSessionObject {
        log("RealtimeHub: dropping socket callback after authenticated owner changed")
        discardSessionAfterOwnerChange()
        ensureWarm()
      }
      return false
    }
    return true
  }

  private func acceptsTurnEvent(
    _ identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) -> Bool {
    guard isCurrentSession(source), let identity else { return false }
    guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: identity.turnID) != nil else {
      log("RealtimeHub: dropping provider event after authenticated owner changed")
      return false
    }
    guard identity.turnID == VoiceTurnCoordinator.shared.activeTurnID,
      RealtimeHubEventOwnership.accepts(
        identity,
        activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
        activeResponseID: voiceResponseID)
    else {
      log(
        "RealtimeHub: dropping stale provider event turn=\(identity.turnID) "
          + "response=\(identity.responseID)")
      return false
    }
    return true
  }

  private func sendToolResultIfCurrent(
    source: RealtimeHubSession,
    callId: String,
    name: String,
    output: String,
    screenEvidence: RealtimeScreenEvidenceAttachment? = nil,
    expectedTurnEpoch: Int? = nil
  ) {
    guard isCurrentSession(source) else {
      log("RealtimeHub[\(providerTag)]: dropping stale tool result \(name)")
      return
    }
    let turnEpoch = expectedTurnEpoch ?? realtimeToolTurnEpoch
    let key = toolCallKey(callId: callId, name: name, turnEpoch: turnEpoch)
    guard turnEpoch == realtimeToolTurnEpoch,
      let identity = toolEffectIdentityByTransportKey[key]
    else {
      log("RealtimeHub[\(providerTag)]: dropping stale tool result \(name) epoch=\(turnEpoch)")
      return
    }
    toolEffectIdentityByTransportKey.removeValue(forKey: key)
    let turnID = VoiceTurnID(identity.generation)
    let deferredScreenProtocol = name == HubTool.screenshot.rawValue
      && screenGroundingState.protocolToken?.screenshotCallID == VoiceToolCallID(callId)
      && screenGroundingState.protocolToken?.screenshotIdentity == identity
    let toolIsActive = VoiceTurnCoordinator.shared.isToolEffectActive(
      turnID: turnID,
      callID: VoiceToolCallID(callId),
      identity: identity)
    guard toolIsActive || deferredScreenProtocol else {
      log("RealtimeHub[\(providerTag)]: dropping tool result after reducer revoked \(name)")
      return
    }
    if !deferredScreenProtocol {
      VoiceTurnCoordinator.shared.send(
        .toolFinishedScoped(
          turnID: turnID,
          identity: identity,
          callID: VoiceToolCallID(callId)))
    }
    let providerResult = RealtimeProviderToolResultPolicy.prepare(
      provider: effectiveProvider,
      name: name,
      output: output)
    if providerResult.wasOversized {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: "tool_result_full",
        to: "tool_result_error",
        reason: "capability_mismatch",
        outcome: .degraded,
        extra: [
          "tool": name,
          "original_bytes": providerResult.originalByteCount,
          "provider_bytes": providerResult.output.utf8.count,
          "user_visible": true,
        ])
    }
    log(
      "RealtimeHub[\(providerTag)]: tool result \(name) raw_bytes=\(providerResult.originalByteCount) "
        + "provider_bytes=\(providerResult.output.utf8.count) oversized=\(providerResult.wasOversized)"
    )
    if let screenEvidence {
      // `sendToolResult` crosses the provider session's serial queue. Do not mint the visual
      // receipt until that queue has accepted the exact image/function-response wire; scheduling
      // the asynchronous call is not yet a transport fact.
      logScreenEvidence(stage: "tool_wire_scheduled", evidence: screenEvidence.descriptor, callID: callId)
      source.sendToolResult(
        callId: callId,
        name: name,
        output: providerResult.output,
        screenEvidence: screenEvidence,
        onWireEnqueued: { [weak self, weak source] didEnqueue in
          DispatchQueue.main.async {
            guard let self, let source else { return }
            guard didEnqueue else {
              self.logScreenEvidence(
                stage: "tool_wire_enqueue_failed",
                evidence: screenEvidence.descriptor,
                callID: callId)
              self.rejectScreenEvidence(screenEvidence.descriptor, reason: "tool_wire_enqueue_failed")
              return
            }
            self.markScreenEvidenceTransportEnqueued(
              screenEvidence,
              source: source,
              callID: callId,
              turnEpoch: turnEpoch)
          }
        })
    } else {
      source.sendToolResult(
        callId: callId,
        name: name,
        output: providerResult.output)
    }
  }

  @discardableResult
  private func beginExternalRunAuthorityIfNeeded(
    turnID: VoiceTurnID,
    prompt: String
  ) -> Task<ExternalSurfaceRunBinding, Error> {
    if let state = externalRunAuthorityState, state.turnID == turnID {
      return state.task
    }
    let normalizedPrompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
    let sessionID = prefetchedVoiceContextSessionID
    let capturedOwnerID = RuntimeOwnerIdentity.currentOwnerId() ?? ""
    let task = Task<ExternalSurfaceRunBinding, Error> {
      guard !capturedOwnerID.isEmpty,
        RuntimeOwnerIdentity.currentOwnerId() == capturedOwnerID
      else {
        throw ExternalSurfaceAuthorityError(code: "external_surface_owner_unavailable")
      }
      guard !sessionID.isEmpty else {
        throw ExternalSurfaceAuthorityError(code: "realtime_voice_session_unavailable")
      }
      let runtime = AgentRuntimeProcess.shared
      return try await runtime.beginExternalSurfaceRun(
        clientId: Self.externalRunClientID,
        harnessMode: Self.externalRunHarnessMode,
        ownerID: capturedOwnerID,
        sessionID: sessionID,
        turnID: turnID.rawValue.uuidString.lowercased(),
        prompt: normalizedPrompt,
        mode: .act)
    }
    externalRunAuthorityState = .init(
      ownerID: capturedOwnerID,
      turnID: turnID,
      task: task)
    return task
  }

  private func invokeExternallyAuthorizedTool(
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callId: String,
    name: String,
    arguments: [String: Any],
    expectedTurnEpoch: Int,
    permissionTranscriptRequestStartedAt: Date? = nil
  ) {
    let now = Date()
    let transcript = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    let permissionRequestStartedAt = permissionTranscriptRequestStartedAt ?? now
    switch RealtimePermissionTranscriptSettlementPolicy.decision(
      toolName: name,
      transcriptIsFinal: providerTranscriptFinalized,
      hasTranscript: !transcript.isEmpty,
      lastTranscriptUpdate: lastInputTranscriptUpdateAt,
      requestStartedAt: permissionRequestStartedAt,
      now: now)
    {
    case .wait(let delay):
      Task { [weak self, source] in
        try? await Task.sleep(for: .seconds(delay))
        guard let self,
          self.isCurrentToolTurn(
            source: source,
            callId: callId,
            name: name,
            expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        self.invokeExternallyAuthorizedTool(
          source: source,
          turnID: turnID,
          identity: identity,
          callId: callId,
          name: name,
          arguments: arguments,
          expectedTurnEpoch: expectedTurnEpoch,
          permissionTranscriptRequestStartedAt: permissionRequestStartedAt)
      }
      return
    case .reject:
      log("RealtimeHub[\(providerTag)]: rejecting permission tool without settled voice transcript context")
      sendToolResultIfCurrent(
        source: source,
        callId: callId,
        name: name,
        output: "The permission tool could not be safely authorized because the voice transcript was unavailable.",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    case .execute:
      break
    }
    guard let promptSelection = RealtimeExternalRunPromptPolicy.promptForAuthorizedTool(
      transcript: transcript,
      isFinal: providerTranscriptFinalized,
      toolName: name,
      arguments: arguments)
    else {
      log("RealtimeHub[\(providerTag)]: rejecting permission tool without voice transcript context")
      sendToolResultIfCurrent(
        source: source,
        callId: callId,
        name: name,
        output: "The permission tool could not be safely authorized because the voice transcript was unavailable.",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    }
    if promptSelection.source == .authorizedToolFallback {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: "provider_transcript",
        to: "authorized_tool",
        reason: "capability_mismatch",
        outcome: .recovered,
        extra: ["user_visible": true])
      log("RealtimeHub[\(providerTag)]: executing authorized tool without final provider transcript")
    }
    executeExternallyAuthorizedTool(
      source: source,
      turnID: turnID,
      identity: identity,
      callId: callId,
      name: name,
      arguments: arguments,
      expectedTurnEpoch: expectedTurnEpoch,
      runPrompt: promptSelection.prompt)
  }

  private func executeExternallyAuthorizedTool(
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callId: String,
    name: String,
    arguments: [String: Any],
    expectedTurnEpoch: Int,
    runPrompt: String
  ) {
    guard isCurrentToolTurn(
        source: source,
        callId: callId,
        name: name,
        expectedTurnEpoch: expectedTurnEpoch)
    else { return }
    let invocationID = RealtimeExternalToolInvocationIdentity.make(
      turnID: turnID,
      providerCallID: callId,
      toolName: name)
    let runTask = beginExternalRunAuthorityIfNeeded(turnID: turnID, prompt: runPrompt)
    Task { [weak self, source] in
      guard let self else { return }
      do {
        let binding = try await runTask.value
        guard self.isCurrentToolTurn(
          source: source,
          callId: callId,
          name: name,
          expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        let inputHash = try AuthorizedToolExecution.inputHash(for: arguments)
        let invocation = RealtimeAuthorizedToolInvocation(
          invocationID: invocationID,
          binding: binding,
          turnID: turnID,
          callID: VoiceToolCallID(callId),
          effectIdentity: identity,
          canonicalToolName: name,
          inputHash: inputHash,
          sourceObjectID: ObjectIdentifier(source),
          turnEpoch: expectedTurnEpoch)
        self.authorizedRealtimeInvocations[invocationID] = invocation
        defer {
          self.authorizedRealtimeInvocations.removeValue(forKey: invocationID)
          self.authorizedRealtimeScreenshotImages.removeValue(forKey: invocationID)
        }
        let output = try await AgentRuntimeProcess.shared.invokeExternalSurfaceTool(
          clientId: Self.externalRunClientID,
          harnessMode: Self.externalRunHarnessMode,
          binding: binding,
          invocationID: invocationID,
          toolName: name,
          input: arguments)
        // The tool may complete after a barge-in or owner/session replacement.
        // Never let that stale completion mutate either journal ownership or the
        // visible pill projection.
        guard self.isCurrentToolTurn(
          source: source,
          callId: callId,
          name: name,
          expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        self.lastExternalToolName = name
        self.lastExternalToolErrorCode = ""
        if name == "spawn_agent" {
          let spawnOutcome = RealtimeSpawnAgentToolOutcome.classify(
            output: output,
            expectedContinuityKey: self.turnIdempotencyKey)
          let expectedContinuityKey = "voice:\(turnID.rawValue.uuidString.lowercased())"
          switch spawnOutcome {
          case .accepted(let receipt) where receipt.continuityKey == expectedContinuityKey:
            self.acceptedSpawnJournalReceiptByContinuityKey[receipt.continuityKey] =
              AcceptedSpawnJournalReceipt(ownerID: binding.ownerID, receipt: receipt)
            self.turnPersistenceLedger.recordAcceptedReceipt(for: receipt.continuityKey)
            self.lastTurnDiagnostics = [
              "provider": self.providerTag,
              "provider_transcript": self.turnTranscript,
              "provider_transcript_language": "",
              "saved_user_text": self.turnTranscript,
              "used_local_transcript": "false",
              "local_transcript": "",
              "local_language": "",
              "assistant_reply": receipt.assistantText,
              "provider_assistant_reply": self.assistantText,
              "external_tool_name": name,
              "external_tool_error": "",
            ]
            VoiceTurnCoordinator.shared.send(
              .authoritativeLocalResultAcceptedScoped(
                turnID: turnID,
                identity: identity,
                callID: VoiceToolCallID(callId),
                kind: .spawnReceipt))
            self.assistantText = receipt.assistantText
            self.playCanonicalSpawnAcknowledgement(receipt.assistantText)
            if let pill = receipt.pillProjection {
              AgentPillsManager.shared.upsertSpawnedPill(
                id: pill.pillID,
                query: pill.objective,
                title: pill.title,
                sessionId: pill.sessionID,
                runId: pill.runID,
                attemptId: pill.attemptID,
                provider: pill.provider,
                producingJournalSurface: FloatingControlBarManager.shared.realtimeVoiceSurfaceReference())
            }
          case .setupNeeded(let provider):
            self.lastExternalToolErrorCode = "provider_setup_needed"
            self.sendToolResultIfCurrent(
              source: source,
              callId: callId,
              name: name,
              output: RealtimeProviderToolResultPolicy.rejectedOutput(
                code: "provider_setup_needed",
                message: provider.setupNeededStatus,
                preservingCanonicalEnvelopeFrom: output),
              expectedTurnEpoch: expectedTurnEpoch)
            VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .providerFailed))
            return
          case .accepted, .rejected:
            log("RealtimeHub[\(self.providerTag)]: spawn_agent rejected without a canonical child receipt")
            self.sendToolResultIfCurrent(
              source: source,
              callId: callId,
              name: name,
              output: RealtimeProviderToolResultPolicy.rejectedOutput(
                code: "realtime_spawn_rejected",
                message: "The background agent could not start. Please try again.",
                preservingCanonicalEnvelopeFrom: output),
              expectedTurnEpoch: expectedTurnEpoch)
            VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .providerFailed))
            return
          }
        }
        let screenshotImage = self.authorizedRealtimeScreenshotImages.removeValue(
          forKey: invocationID)
        self.sendToolResultIfCurrent(
          source: source,
          callId: callId,
          name: name,
          output: output,
          screenEvidence: screenshotImage,
          expectedTurnEpoch: expectedTurnEpoch)
      } catch {
        let code = (error as? ExternalSurfaceAuthorityError)?.code
          ?? "external_surface_tool_failed"
        guard self.isCurrentToolTurn(
          source: source,
          callId: callId,
          name: name,
          expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        self.lastExternalToolName = name
        self.lastExternalToolErrorCode = code
        log("RealtimeHub[\(self.providerTag)]: kernel rejected tool \(name) code=\(code)")
        self.sendToolResultIfCurrent(
          source: source,
          callId: callId,
          name: name,
          output: RealtimeProviderToolResultPolicy.rejectedOutput(
            code: code,
            message: "The tool could not be authorized. Please try again."),
          expectedTurnEpoch: expectedTurnEpoch)
      }
    }
  }

  private func executeAuthorizedRealtimeTool(
    _ command: AuthorizedToolExecution
  ) async -> AuthorizedRealtimeToolExecutionResult {
    guard let invocation = authorizedRealtimeInvocations[command.invocationID] else {
      return .failed(Self.authorizedRealtimeToolError(code: "unknown_realtime_invocation"))
    }
    let activeSourceObjectID = session.map(ObjectIdentifier.init)
    let activeToolIdentity = VoiceTurnCoordinator.shared.activeTurn?
      .toolEffectIdentities[invocation.callID]
    guard RealtimeAuthorizedToolOwnership.accepts(
      command: command,
      invocation: invocation,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      activeToolIdentity: activeToolIdentity,
      activeSourceObjectID: activeSourceObjectID,
      currentTurnEpoch: realtimeToolTurnEpoch)
    else {
      log("RealtimeHub: rejected stale/mismatched authorized realtime tool command")
      return .failed(
        Self.authorizedRealtimeToolError(code: "stale_realtime_tool_authorization"))
    }
    guard AuthorizedToolExecution.isOwnerCurrent(command.ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    guard RealtimeAuthorizedInvocationReplayGate.shouldExecute(
      invocationID: command.invocationID,
      completedInvocationIDs: completedAuthorizedRealtimeInvocationIDs)
    else {
      log("RealtimeHub: rejected replayed authorized realtime tool command")
      return .failed(
        Self.authorizedRealtimeToolError(code: "replayed_realtime_tool_authorization"))
    }
    completedAuthorizedRealtimeInvocationIDs.insert(command.invocationID)

    guard let tool = HubTool(rawValue: command.canonicalToolName) else {
      return .failed(Self.authorizedRealtimeToolError(code: "unsupported_realtime_tool"))
    }
    switch tool {
    case .getTasks:
      await TasksStore.shared.loadDashboardTasks(expectedOwnerID: command.ownerID)
      guard AuthorizedToolExecution.isOwnerCurrent(command.ownerID) else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      let overdue = TasksStore.shared.overdueTasks
      let today = TasksStore.shared.todaysTasks
      func list(_ items: [TaskActionItem]) -> String {
        items.prefix(15).map { "- \($0.description) [id:\($0.id)]" }.joined(separator: "\n")
      }
      var output = ""
      if !overdue.isEmpty { output += "Overdue (\(overdue.count)):\n\(list(overdue))\n" }
      if !today.isEmpty { output += "Due today (\(today.count)):\n\(list(today))\n" }
      return .succeeded(output.isEmpty ? "No tasks overdue or due today." : output)

    case .askHigherModel:
      let query = (command.input["query"] as? String) ?? turnTranscript
      let toolContext = (command.input["context"] as? String) ?? ""
      let kernelContext = voiceSessionContext(for: currentOwnerScope)
      guard kernelContext.isResolved else {
        return .failed(Self.authorizedRealtimeToolError(code: "kernel_context_unavailable"))
      }
      return await escalateToHigherModel(
        query,
        kernelSemanticGuidance: kernelContext.semanticGuidance,
        kernelContext: kernelContext.rendered,
        stableCacheIdentity: kernelContext.stableCacheIdentity,
        dynamicContextIdentity: kernelContext.dynamicContextIdentity,
        contextPlanID: kernelContext.planID,
        toolContext: toolContext,
        ownerID: command.ownerID)

    case .screenshot:
      // Preserve the original descriptor before suspension. The timeout branch must never read
      // mutable `screenEvidence` after a barge-in, because that may already belong to a new turn.
      let capturedEvidence = screenEvidence?.descriptor
      let currentEvidence = await screenEvidenceForAuthorizedScreenshot()
      let invocationIsCurrent = isCurrentAuthorizedRealtimeInvocation(command, invocation: invocation)
      guard invocationIsCurrent else {
        return .failed(Self.authorizedRealtimeToolError(code: "stale_realtime_tool_authorization"))
      }
      guard let captureResult = Self.performOwnerBoundPhysicalEffect(
        expectedOwnerID: command.ownerID,
        effect: { [currentEvidence] in [currentEvidence] })
      else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      let evidence = captureResult[0]
      guard let evidence,
        evidence.descriptor.turnID == VoiceTurnCoordinator.shared.activeTurnID,
        let jpeg = evidence.jpeg,
        evidence.descriptor.canVerifyCurrentScreen
      else {
        guard let failureEvidence = RealtimeScreenEvidenceToolExecutionPolicy.failureEvidence(
          capturedEvidence: capturedEvidence,
          commandTurnID: invocation.turnID,
          activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
          invocationIsCurrent: invocationIsCurrent)
        else {
          return .failed(Self.authorizedRealtimeToolError(code: "stale_realtime_tool_authorization"))
        }
        rejectScreenEvidence(failureEvidence, reason: "capture_unavailable")
        return .succeeded(screenshotToolResultTextForCurrentProvider(attachment: nil))
      }
      let attachment = RealtimeScreenEvidenceAttachment(descriptor: evidence.descriptor, jpeg: jpeg)
      // The provider receives these exact pre-overlay pixels only inside the matching tool
      // response. Gemini must not race a separate realtime video frame against an unblocked
      // function, and a later pointer-selected display can never replace this evidence.
      authorizedRealtimeScreenshotImages[command.invocationID] = attachment
      return .succeeded(screenshotToolResultTextForCurrentProvider(attachment: attachment))

    case .pointClick:
      guard let x = Self.finiteCoordinate(command.input["x"]),
        let y = Self.finiteCoordinate(command.input["y"])
      else {
        return .succeeded(
          "Could not click: point_click requires finite numeric x and y coordinates.")
      }
      guard Self.click(
        at: CGPoint(x: x, y: y),
        expectedOwnerID: command.ownerID)
      else {
        return AuthorizedToolExecution.isOwnerCurrent(command.ownerID)
          ? .succeeded("Could not click.")
          : .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      return .succeeded("Clicked at \(Int(x)), \(Int(y)).")

    default:
      return .failed(Self.authorizedRealtimeToolError(code: "wrong_realtime_executor_tool"))
    }
  }

  private nonisolated static func authorizedRealtimeToolError(code: String) -> String {
    #"{"ok":false,"error":{"code":"\#(code)"}}"#
  }

  private nonisolated static func authorizedRealtimeOwnerChangedError() -> String {
    authorizedRealtimeToolError(code: AuthorizedToolExecution.Rejection.ownerChangedDuringExecution.code)
  }

  func hubDidConnect(source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    lastWarmAt = Date()
    hubConnected = true  // authenticated + ready — PTT may now route turns to the hub
    let replayedReconnectTurn = reconnectAudioBuffer != nil
    let replayedReplacementTurn = replacementAudioBuffer != nil
    if replayedReplacementTurn {
      finishBargeInReplacementAfterSessionReady()
    }
    if replayedReconnectTurn {
      finishSessionReconnectAfterReady()
    }
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID, let voiceSessionID,
      VoiceTurnCoordinator.shared.activeTurn?.route == .hubWarmWait
    {
      VoiceTurnCoordinator.shared.send(.hubReady(turnID: turnID, sessionID: voiceSessionID))
    }
    log("RealtimeHub: connected (\(sessionProvider?.displayName ?? "?"))")
    if let fallback = fallbackProvider, let reason = pendingFailoverReason,
      sessionProvider == fallback
    {
      let primary = RealtimeHubSettings.shared.provider
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: primary.rawValue,
        to: fallback.rawValue,
        reason: reason,
        outcome: .recovered,
        extra: ["user_visible": false])
      pendingFailoverReason = nil
    }
    // Transport readiness has no authority to open provider input. Reconnect
    // and replacement replay paths above require an exact context admission;
    // an ordinary warm connection waits for prepareHubInput -> beginTurn.
  }

  func hubDidReceiveInputTranscript(
    _ text: String,
    isFinal: Bool,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source) else { return }
    let automationSelection = RealtimeAutomationTranscriptOverridePolicy.select(
      providerText: text,
      providerIsFinal: isFinal,
      forcedText: testProviderTranscriptOverride)
    if automationSelection.usedOverride {
      turnTranscript = automationSelection.text
      providerTranscriptFinalized = automationSelection.isFinal
      lastInputTranscriptUpdateAt = Date()
      return
    }
    if isFinal {
      if !text.isEmpty { turnTranscript = text }
      providerTranscriptFinalized = !turnTranscript.trimmingCharacters(
        in: .whitespacesAndNewlines).isEmpty
    } else {
      turnTranscript += text
    }
    if !text.isEmpty { lastInputTranscriptUpdateAt = Date() }
    // Don't surface Gemini's LIVE partial transcript on the bar: on a quiet/near-silent
    // hold it transcribes background noise into random words (the bar shows "…" on commit
    // instead). turnTranscript is still kept for the agent-warm heuristic and the final.
    // The realtime model and kernel route intent. This transport driver never
    // performs a second text heuristic to decide whether an agent should attach.
  }

  func hubDidReceiveAudio(
    _ pcm24k: Data,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source), let identity else { return }
    guard !screenGroundingState.suppressesProviderOutput else { return }
    guard !RealtimeAcceptedSpawnPresentationPolicy.suppressesProviderContinuation(
      hasCanonicalSpawnReceipt: acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] != nil)
    else { return }
    guard !VoiceTurnCoordinator.shared.outputSnapshot.providerOutputSuppressed
    else { return }
    guard let lease = acquireVoiceOutput(.nativeRealtime, reason: "provider_audio") else { return }
    if let voiceSessionID {
      guard let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
      else { return }
      VoiceTurnCoordinator.shared.send(
        .providerResponseStartedScoped(
          turnID: lease.turnID,
          identity: providerIdentity,
          sessionID: voiceSessionID,
          responseID: identity.responseID))
    }
    // If PTT muted music/system output while listening, make sure the model's
    // reply is audible even if capture teardown restore is delayed by hardware.
    SystemAudioMuteController.shared.restore()
    guard let pcmPlayer, pcmPlayer.enqueue(pcm24k) else {
      // The coordinator reserves the output lease before the physical enqueue.
      // Only a previously scheduled chunk means playback actually started.
      let playbackAlreadyStarted = audioReceivedThisTurn
      switch RealtimeNativeAudioScheduleFailureAction.decide(
        playbackAlreadyStarted: playbackAlreadyStarted)
      {
      case .keepTextFallback:
        log(
          "RealtimeHub[\(providerTag)]: first native audio chunk could not be scheduled; keeping text fallback armed"
        )
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "realtime_hub",
          from: "native_realtime",
          to: "selected_voice_fallback",
          reason: "enqueue_failed",
          outcome: .degraded,
          extra: ["user_visible": false])
        VoiceTurnCoordinator.shared.send(
          .playbackDrainedScoped(
            turnID: lease.turnID,
            identity: lease.identity,
            leaseID: lease.id))
      case .failTurnAfterPartialPlayback:
        log(
          "RealtimeHub[\(providerTag)]: native audio stream failed after playback started; refusing duplicate full-text fallback"
        )
        VoiceTurnCoordinator.shared.send(
          .playbackFailedScoped(
            turnID: lease.turnID,
            identity: lease.identity,
            leaseID: lease.id,
            message: "native PCM enqueue failed"))
      }
      return
    }
    audioReceivedThisTurn = true
    realtimePlaybackEpoch = pcmPlayer.playbackEpoch
    responseGlowGate.markPlaybackActive(lease: lease)
  }

  func hubDidEmitText(
    _ text: String,
    isFinal: Bool,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source), let identity else { return }
    guard !screenGroundingState.suppressesProviderOutput else { return }
    guard !RealtimeAcceptedSpawnPresentationPolicy.suppressesProviderContinuation(
      hasCanonicalSpawnReceipt: acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] != nil)
    else { return }
    guard !VoiceTurnCoordinator.shared.outputSnapshot.providerOutputSuppressed
    else { return }
    if !text.isEmpty {
      assistantText += text
      if let turnID = VoiceTurnCoordinator.shared.activeTurnID,
        let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
      {
        VoiceTurnCoordinator.shared.send(
          .providerResponseStartedScoped(
            turnID: turnID,
            identity: providerIdentity,
            sessionID: voiceSessionID,
            responseID: identity.responseID))
      }
    }
    if isFinal {
      let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      // Fallback only: if the model produced text but no native audio this turn,
      // speak it through the selected app voice. Normally both providers stream
      // spoken audio (played by StreamingPCMPlayer) so this stays unused.
      if !audioReceivedThisTurn, !reply.isEmpty,
        let lease = acquireVoiceOutput(.selectedVoiceFallback, reason: "text_no_native_audio")
      {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "realtime_hub",
          from: "native_realtime",
          to: "selected_voice_fallback",
          reason: "capability_mismatch",
          outcome: .degraded,
          extra: ["user_visible": false])
        responseGlowGate.markPlaybackActive(lease: lease)
        FloatingBarVoicePlaybackService.shared.speakOneShot(reply, lease: lease)
      } else if !audioReceivedThisTurn, reply.isEmpty {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "realtime_hub",
          from: "native_realtime",
          to: "none",
          reason: "capability_mismatch",
          outcome: .exhausted,
          extra: ["user_visible": true])
      }
      if !reply.isEmpty { log("RealtimeHub: reply received chars=\(reply.count)") }
    }
  }


  func hubDidRequestTool(
    name: String,
    callId: String,
    argumentsJSON: String,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source), let eventIdentity = identity else { return }
    let toolTurnEpoch = realtimeToolTurnEpoch
    let transportKey = toolCallKey(callId: callId, name: name, turnEpoch: toolTurnEpoch)
    guard toolEffectIdentityByTransportKey[transportKey] == nil,
      let turnID = VoiceTurnCoordinator.shared.activeTurnID
    else {
      log("RealtimeHub[\(providerTag)]: dropping duplicate tool call \(name) id=\(callId)")
      return
    }
    guard let toolIdentity = VoiceTurnCoordinator.shared.reserveEffectIdentity() else { return }
    toolEffectIdentityByTransportKey[transportKey] = toolIdentity
    VoiceTurnCoordinator.shared.send(
      .toolStartedScoped(
        turnID: turnID,
        identity: toolIdentity,
        callID: VoiceToolCallID(callId)))
    guard VoiceTurnCoordinator.shared.isToolEffectActive(
      turnID: turnID,
      callID: VoiceToolCallID(callId),
      identity: toolIdentity)
    else {
      toolEffectIdentityByTransportKey.removeValue(forKey: transportKey)
      log("RealtimeHub[\(providerTag)]: reducer rejected tool call \(name) id=\(callId)")
      return
    }
    if name == HubTool.screenshot.rawValue {
      admitScreenScreenshotRequest(
        source: source,
        turnID: turnID,
        responseID: eventIdentity.responseID,
        callID: callId,
        screenshotIdentity: toolIdentity,
        turnEpoch: toolTurnEpoch)
    }
    let arguments =
      (try? JSONSerialization.jsonObject(with: Data(argumentsJSON.utf8)) as? [String: Any]) ?? [:]
    if name == HubTool.reportScreenObservation.rawValue {
      handleScreenObservationReport(
        source: source,
        turnID: turnID,
        callId: callId,
        reportIdentity: toolIdentity,
        arguments: arguments,
        expectedTurnEpoch: toolTurnEpoch)
      return
    }
    invokeExternallyAuthorizedTool(
      source: source,
      turnID: turnID,
      identity: toolIdentity,
      callId: callId,
      name: name,
      arguments: arguments,
      expectedTurnEpoch: toolTurnEpoch)
  }

  private func handleScreenObservationReport(
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    callId: String,
    reportIdentity: VoiceEffectIdentity,
    arguments: [String: Any],
    expectedTurnEpoch: Int
  ) {
    let answer = String(((arguments["answer"] as? String) ?? "").prefix(1_200))
    let accepted = resolveScreenObservation(
      answer: answer,
      source: source,
      turnID: turnID,
      expectedTurnEpoch: expectedTurnEpoch,
      callID: callId,
      reportIdentity: reportIdentity)
    sendToolResultIfCurrent(
      source: source,
      callId: callId,
      name: HubTool.reportScreenObservation.rawValue,
      output: RealtimeHubTools.screenObservationResult(accepted: accepted),
      expectedTurnEpoch: expectedTurnEpoch)
  }

  @discardableResult
  private func resolveScreenObservation(
    answer: String,
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    expectedTurnEpoch: Int,
    callID: String,
    reportIdentity: VoiceEffectIdentity
  ) -> Bool {
    let knownApplicationNames = NSWorkspace.shared.runningApplications.compactMap(\.localizedName)
    let decision = RealtimeScreenGroundingPolicy.reportDecision(
      state: screenGroundingState,
      answer: answer,
      sourceObjectID: ObjectIdentifier(source),
      activeTurnID: turnID,
      activeResponseID: voiceResponseID,
      currentTurnEpoch: expectedTurnEpoch,
      knownApplicationNames: knownApplicationNames)
    guard decision == .accepted, case .awaitingReport(let receipt) = screenGroundingState else {
      let reason: String
      switch decision {
      case .evidenceUnavailable: reason = "evidence_unavailable"
      case .transportNotDispatched: reason = "transport_not_dispatched"
      case .staleReceipt: reason = "stale_receipt"
      case .contradictoryApplication: reason = "contradictory_application"
      case .emptyAnswer: reason = "empty_answer"
      case .accepted: reason = "evidence_state_changed"
      }
      if case .awaitingReport = screenGroundingState {
        rejectScreenEvidence(screenEvidence?.descriptor, reason: reason)
      } else {
        // A report that races ahead of the screenshot result is rejected to the provider but
        // never cached or redeemed. The original screenshot call may still complete normally.
        log("RealtimeHub: rejected screen report without a current transport receipt reason=\(reason)")
      }
      return false
    }
    screenGroundingState = .accepted(receipt)
    logScreenEvidence(stage: "report_accepted", evidence: receipt.descriptor, callID: callID)
    return completeScreenEvidenceProtocol(
      receipt.protocolToken,
      outcome: .verified(
        reportCallID: VoiceToolCallID(callID),
        reportIdentity: reportIdentity),
      answer: RealtimeScreenGroundingPolicy.presentedAnswer(evidence: receipt.descriptor, answer: answer))
      == .completed
  }

  func hubDidFinishTurn(identity: RealtimeHubEventIdentity?, source: RealtimeHubSession) {
    guard acceptsTurnEvent(identity, source: source), let identity else { return }
    hubReconnectStrikes = 0  // a completed provider cycle proves the hub works.
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID {
      _ = resolvePendingScreenEvidenceBeforeProviderTermination(
        turnID: turnID,
        reason: .providerNoResponse)
    }
    let pendingToolCount = VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs.count ?? 0
    let hasCanonicalSpawnReceipt =
      acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] != nil
    let postToolContinuationRequired =
      VoiceTurnCoordinator.shared.activeTurn?.postToolContinuationRequired == true
        && RealtimeAcceptedSpawnPresentationPolicy.requiresProviderContinuation(
          hasCanonicalSpawnReceipt: hasCanonicalSpawnReceipt)
    if RealtimeProviderTurnDoneDisposition.decide(
      pendingToolCount: pendingToolCount,
      postToolContinuationRequired: postToolContinuationRequired)
      == .awaitToolContinuation
    {
      log(
        "RealtimeHub[\(providerTag)]: provider cycle done with \(pendingToolCount) tool result(s) pending; waiting for post-tool continuation"
      )
      if let turnID = VoiceTurnCoordinator.shared.activeTurnID,
        let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
      {
        VoiceTurnCoordinator.shared.send(
          .providerTurnFinishedScoped(
            turnID: turnID,
            identity: providerIdentity,
            sessionID: voiceSessionID,
            responseID: identity.responseID))
      }
      return
    }
    if sessionProvider == .gemini {
      geminiSessionNeedsTurnBoundary = true
      pendingSessionRefreshReason = "voice_context_changed"
    }
    var heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    if let forced = testProviderTranscriptOverride {
      testProviderTranscriptOverride = nil
      heard = forced
      log("RealtimeHub: TEST override provider transcript → \"\(forced.prefix(60))\"")
    }
    let providerReply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    let acceptedSpawnOwnerID = acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey]?.ownerID
    let reply = acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey]?.receipt.assistantText
      ?? providerReply
    log(
      "RealtimeHub[\(providerTag)]: turn done — transcript_chars=\(heard.count) audio=\(audioReceivedThisTurn)"
    )
    if reducerNativePlaybackActive {
      log("RealtimeHub[\(providerTag)]: server turn done; waiting for local playback to drain")
    }
    // Record the completed turn to the kernel; chat UI updates from ordered journal replay.
    if VoiceTurnCoordinator.shared.activeTurn?.journalFinalization == .pending {
      let completedTurnIdempotencyKey = turnIdempotencyKey
      guard let completedTurnOwnerID = VoiceTurnCoordinator.shared.activeTurn?.ownerID else {
        if let activeTurnID = VoiceTurnCoordinator.shared.activeTurnID {
          VoiceTurnCoordinator.shared.send(.cancel(turnID: activeTurnID, reason: .cancelled))
        }
        return
      }
      let candidates = AssistantSettings.shared.voiceBaseLanguages
      let fullTask = fullLIDTask
      let provider = providerTag
      enqueueTurnPersistence(
        idempotencyKey: completedTurnIdempotencyKey,
        retainingReceipt: true
      ) { [weak self] in
        let resolution = await Self.resolveTranscript(
          providerText: heard,
          preferredLanguages: candidates,
          localTask: fullTask)
        if resolution.usedLocalTranscript {
          log(
            "RealtimeHub: provider transcript language did not match the configured voice languages; using bounded local decode for continuity"
          )
        }
        let accepted = await self?.persistTurnDirectlyToKernel(
          ownerID: completedTurnOwnerID,
          userText: resolution.userText,
          assistantText: reply,
          interrupted: false,
          idempotencyKey: completedTurnIdempotencyKey,
          acceptedSpawnOwnerID: acceptedSpawnOwnerID) ?? false
        self?.lastTurnDiagnostics = [
          "provider": provider,
          "provider_transcript": heard,
          "provider_transcript_language": resolution.providerLanguage ?? "",
          "saved_user_text": resolution.userText,
          "used_local_transcript": resolution.usedLocalTranscript ? "true" : "false",
          "local_transcript": resolution.localTranscript ?? "",
          "local_language": resolution.localLanguage ?? "",
          "assistant_reply": reply,
          "provider_assistant_reply": providerReply,
          "external_tool_name": self?.lastExternalToolName ?? "",
          "external_tool_error": self?.lastExternalToolErrorCode ?? "",
        ]
        return accepted
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
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.activeTurn?.providerFinished != true,
      let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
    {
      VoiceTurnCoordinator.shared.send(
        .providerTurnFinishedScoped(
          turnID: turnID,
          identity: providerIdentity,
          sessionID: voiceSessionID,
          responseID: identity.responseID))
      if VoiceTurnCoordinator.shared.outputSnapshot.activeLease == nil {
        exitVoiceUI()
        applyPendingSessionRefreshIfIdle()
      }
    } else {
      exitVoiceUI()
      applyPendingSessionRefreshIfIdle()
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
    let key = toolCallKey(callId: callId, name: name, turnEpoch: expectedTurnEpoch)
    guard let identity = toolEffectIdentityByTransportKey[key]
    else { return false }
    let callID = VoiceToolCallID(callId)
    return RealtimeToolTurnOwnership.accepts(
      turnID: VoiceTurnID(identity.generation),
      identity: identity,
      sourceObjectID: ObjectIdentifier(source),
      turnEpoch: expectedTurnEpoch,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      activeToolIdentity: VoiceTurnCoordinator.shared.activeTurn?.toolEffectIdentities[callID],
      activeSourceObjectID: session.map(ObjectIdentifier.init),
      currentTurnEpoch: realtimeToolTurnEpoch)
  }

  private func clearRealtimeToolTracking() {
    realtimeToolTurnEpoch += 1
    toolEffectIdentityByTransportKey.removeAll()
    authorizedRealtimeInvocations.removeAll()
    authorizedRealtimeScreenshotImages.removeAll()
    acceptedSpawnJournalReceiptByContinuityKey.removeAll()
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
    var resolvedScreenProtocol = false
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID {
      resolvedScreenProtocol = resolvePendingScreenEvidenceBeforeProviderTermination(
        turnID: turnID,
        reason: .providerFailed)
    }
    // Capture while the reducer still owns this turn. `.providerReconnectFailed`
    // or `.finish` synchronously terminalizes it and `cancelTurn` clears the
    // transcript, so starting this obligation any later loses the just-spoken
    // user turn from the next shared-context snapshot.
    let interruptedTurnTask = captureInterruptedTurnPayloadIfNeeded()
    if let interruptedTurnTask {
      // Register the continuity obligation synchronously, before any terminal
      // reducer event below can schedule the next context refresh. Enqueuing
      // only after transcript resolution creates a TOCTOU window where the
      // next PTT turn can snapshot the journal without this failed turn.
      let failedTurnContinuityKey = turnIdempotencyKey
      _ = RealtimeProviderFailureContinuity.registerCapturedTurn(
        in: turnPersistenceLedger,
        continuityKey: failedTurnContinuityKey,
        capturedTurnTask: interruptedTurnTask
      ) { [weak self] interruptedTurn in
        await self?.persistTurnDirectlyToKernel(
          ownerID: interruptedTurn.ownerID,
          userText: interruptedTurn.userText,
          assistantText: interruptedTurn.assistantText,
          interrupted: true,
          idempotencyKey: interruptedTurn.idempotencyKey,
          acceptedSpawnOwnerID: interruptedTurn.acceptedSpawnOwnerID) ?? false
      }
    }
    // A socket we intentionally dropped is detached in teardownSession() before it's
    // released, so its death-rattle never reaches us — only the live session's errors
    // land here.
    if let reconnect = reconnectAudioBuffer {
      VoiceTurnCoordinator.shared.send(
        .providerReconnectFailed(
          turnID: reconnect.turnID,
          identity: reconnect.identity,
          message: "realtime provider reconnect failed"))
    }
    // Re-read after the scoped reconnect failure: that event may already have
    // terminalized the turn, and the generic error tail must not finish it twice.
    let activeTurn = VoiceTurnCoordinator.shared.activeTurn
    let ownsActiveHubTurn = RealtimeHubErrorOwnership.owns(
      route: activeTurn?.route,
      activeSessionID: voiceSessionID)
    let hasActiveTurn = ownsActiveHubTurn
    let terminalToolName = lastExternalToolName.isEmpty ? "none" : lastExternalToolName
    let terminalToolErrorCode = lastExternalToolErrorCode.isEmpty ? "none" : lastExternalToolErrorCode
    let terminalHadAcceptedSpawn =
      acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] != nil
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
    let fingerprint = provider.flatMap { APIKeyService.byokKey($0.byokProvider) }.map(
      APIKeyService.byokFingerprint)
    var credentialFailureClass: CredentialFailureClass?
    if let provider, !RealtimeHubCloseClassifier.isExpectedLifecycleClose(closeCategory) {
      var failureClass = CredentialHealthManager.classifyProviderClose(
        message: message, provider: provider)
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
      if closeCategory == .expectedSessionRotation { return true }
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
      log(
        "RealtimeHub: session closed —\(categoryText) provider=\(providerTag) aliveFor=\(Int(aliveFor))s\(safeMessage)"
      )
    }
    log(
      "RealtimeHub: provider close terminal state tool=\(terminalToolName) "
        + "tool_error=\(terminalToolErrorCode) accepted_spawn=\(terminalHadAcceptedSpawn)"
    )
    if let sessionRotationPlan = RealtimeHubCloseClassifier.sessionRotationPlan(
      for: closeCategory,
      hasActiveTurn: hasActiveTurn)
    {
      recoverFromExpectedSessionRotation(sessionRotationPlan, activeTurn: activeTurn)
      return
    }
    if replacementAudioBuffer != nil, let failedProvider = provider {
      let replacementFailoverReason = failoverReason(for: credentialFailureClass)
      let mayFailOver = credentialFailureClass.map { shouldFailoverToAlternate(for: $0) } ?? true
      if mayFailOver,
        failoverBargeInReplacement(
          from: failedProvider,
          reason: replacementFailoverReason)
      {
        return
      }
      failBargeInReplacement(provider: failedProvider, reason: message)
      teardownSession()
      return
    }
    if ownsActiveHubTurn, !resolvedScreenProtocol, activeTurn?.providerFinished != true {
      terminateActiveHubTurn(activeTurn)
    }
    teardownSession()
    // Provider switching changes the user's voice identity and can fragment model-local
    // context. Only switch for stable credential/quota classes; transient fast closes
    // re-warm the same provider and rely on the shared continuity packet.
    if case .providerAuthFailed = credentialFailureClass {
      if aliveFor < 10, failoverToAlternateProvider(reason: "auth") { return }
      return
    }
    if case .providerQuotaExceeded = credentialFailureClass {
      if failoverToAlternateProvider(reason: "quota") { return }
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
      pendingFailoverReason = nil
    }
    guard !reconnectPending, hubReconnectStrikes < Self.maxReconnectStrikes else { return }
    hubReconnectStrikes += 1
    reconnectPending = true
    let reconnectOwnerBoundaryGeneration = ownerBoundaryGeneration
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
      guard let self else { return }
      guard self.ownerBoundaryGeneration == reconnectOwnerBoundaryGeneration else { return }
      self.reconnectPending = false
      if self.session == nil { self.ensureWarm() }
    }
  }

  /// OpenAI limits realtime sessions to sixty minutes. Rotation is a normal
  /// transport lifecycle event: keep the provider choice, replace the retired
  /// socket immediately, and let the reducer terminalize an interrupted turn.
  private func recoverFromExpectedSessionRotation(
    _ plan: RealtimeHubSessionRotationPlan,
    activeTurn: VoiceTurn?
  ) {
    if plan == .terminateActiveTurnAndRewarm {
      terminateActiveHubTurn(activeTurn)
    }
    teardownSession()
    hubReconnectStrikes = 0
    reconnectPending = false
    ensureWarm()
  }

  /// A warm background socket must never terminate a Deepgram/Omni fallback
  /// turn. The reducer deduplicates repeated terminal events, keeping the UI in
  /// a single actionable terminal projection when transport callbacks race.
  private func terminateActiveHubTurn(_ activeTurn: VoiceTurn?) {
    pcmPlayer?.stop()
    realtimePlaybackEpoch += 1
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if let turnID = activeTurn?.id {
      VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .providerFailed))
    }
    exitVoiceUI(clearResponseGlow: true)
  }

  /// Return the floating bar from its PTT voice state to compact after a hub turn.
  private func exitVoiceUI(clearResponseGlow: Bool = false) {
    if clearResponseGlow
      || (!audioReceivedThisTurn && !FloatingBarVoicePlaybackService.shared.isSpeaking)
    {
      responseGlowGate.clearImmediately()
    }
    VoiceTurnCoordinator.shared.refreshPresentation()
  }

  private func clearResponseGlowIfRealtimeAudioIdle() {
    responseGlowGate.scheduleIdleClear()
  }

  // MARK: - Tools

  /// ask_higher_model — reuse the EXISTING prompt-cached /v2/chat/completions
  /// (no new backend route). Returns the assistant text for the model to speak.
  private func escalateToHigherModel(
    _ query: String,
    kernelSemanticGuidance: String,
    kernelContext: String,
    stableCacheIdentity: String,
    dynamicContextIdentity: String,
    contextPlanID: String,
    toolContext: String,
    ownerID: String
  ) async -> AuthorizedRealtimeToolExecutionResult
  {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    let body = RealtimeHubTools.escalationBody(
      query: query,
      kernelSemanticGuidance: kernelSemanticGuidance,
      kernelContext: kernelContext,
      stableCacheIdentity: stableCacheIdentity,
      dynamicContextIdentity: dynamicContextIdentity,
      contextPlanID: contextPlanID,
      toolContext: toolContext)
    let t0 = Date()
    do {
      let answer = try await APIClient.shared.askHigherModel(
        body: body,
        expectedOwnerID: ownerID)
      let ms = Int(Date().timeIntervalSince(t0) * 1000)
      log(
        "RealtimeHub: ask_higher_model ← \(ModelQoS.Claude.defaultSelection) OK in \(ms)ms (\(answer.count) chars)"
      )
      return .succeeded(answer)
    } catch AuthError.userChangedDuringRequest {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    } catch {
      log("RealtimeHub: ask_higher_model failed — \(error.localizedDescription)")
      return .succeeded("I ran into an error reaching the model.")
    }
  }

  /// Executes a synchronous physical effect only while the immutable command
  /// owner is still current. Because this check and closure run on MainActor
  /// without suspension, an account-switch callback cannot interleave between
  /// the fence and the physical operation.
  @MainActor
  static func performOwnerBoundPhysicalEffect<T>(
    expectedOwnerID: String,
    ownerIsCurrent: (String) -> Bool = { AuthorizedToolExecution.isOwnerCurrent($0) },
    effect: () -> T
  ) -> T? {
    guard ownerIsCurrent(expectedOwnerID) else { return nil }
    return effect()
  }

  /// Local synthetic mouse click (point_click tool).
  @discardableResult
  static func click(
    at point: CGPoint,
    expectedOwnerID: String,
    ownerIsCurrent: (String) -> Bool = { AuthorizedToolExecution.isOwnerCurrent($0) },
    postEvents: (CGPoint) -> Bool = { point in
      guard
        let down = CGEvent(
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
  ) -> Bool {
    performOwnerBoundPhysicalEffect(
      expectedOwnerID: expectedOwnerID,
      ownerIsCurrent: ownerIsCurrent,
      effect: { postEvents(point) }) ?? false
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

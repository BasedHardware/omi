import AppKit
import CoreGraphics
import Foundation
import OmiSupport
import VoiceTurnDomain

@MainActor
final class RealtimeHubController: NSObject, RealtimeHubSessionDelegate {
  static let shared = RealtimeHubController()

  var session: RealtimeHubSession?
  var voiceSessionID: VoiceSessionID?
  /// Shared with the screen-evidence receipt extension to fence image dispatch to one response.
  var voiceResponseID: VoiceResponseID?
  var sessionProvider: RealtimeHubProvider?
  var sessionAuth: HubAuth?
  /// Sessions detach from logical ownership synchronously, then close on their
  /// transport queue. Retain them until that queue drains so an effective-owner
  /// transition can await every teardown already initiated by reducer effects.
  var detachedSessionsAwaitingDrain: [ObjectIdentifier: RealtimeHubSession] = [:]
  struct PhysicalSessionOwnerBinding {
    let sourceID: ObjectIdentifier
    let ownerScope: RealtimeHubOwnerScope
  }
  /// Replaced atomically with each physical session. The identity fields are
  /// immutable and the object identifier prevents a scope from drifting onto a
  /// different socket through an independent property assignment.
  var sessionOwnerBinding: PhysicalSessionOwnerBinding?
  #if DEBUG
    /// Installed only for the lifetime of one local-profile `ptt_test_turn`.
    /// Production builds have no provider-warm bypass surface.
    var localProfileTransportAuthority: RealtimeLocalProfileTransportAuthority?
  #endif
  var sessionOwnerScope: RealtimeHubOwnerScope? {
    guard let session, let binding = sessionOwnerBinding,
      binding.sourceID == ObjectIdentifier(session)
    else { return nil }
    return binding.ownerScope
  }
  var pcmPlayer: StreamingPCMPlayer?
  lazy var responseGlowGate = RealtimeResponseGlowGate { [weak self] active, lease in
    guard self != nil, let lease,
      VoiceTurnCoordinator.shared.activeTurnID == lease.turnID
    else { return }
    VoiceTurnCoordinator.shared.publish(.responseActiveChanged(turnID: lease.turnID, active: active))
  }
  // Per-turn state.
  var turnTranscript = ""
  var providerTranscriptFinalized = false
  /// Last provider input-transcript mutation for the active PTT turn. Permission
  /// tools use this only to wait for a stable live transcript; it is reset with
  /// every turn and is never persisted.
  /// Screen-evidence telemetry records only whether this current turn saw a transcript event.
  var lastInputTranscriptUpdateAt: Date?
  var assistantText = ""
  var audioReceivedThisTurn = false
  /// Stable per-turn key for kernel idempotent voice-turn persistence.
  var turnIdempotencyKey = ""
  /// (a) Pure cache of the typed kernel voice-context snapshot. Rebuild via
  /// `refreshVoiceContextSnapshot` / `fetchVoiceContextSnapshot` on relaunch.
  var prefetchedVoiceContext = ""
  var prefetchedVoiceContextSessionID = ""
  var prefetchedVoiceContextFreshnessIdentity = ""
  var prefetchedVoiceContextPlanID = ""
  var prefetchedVoiceStableCacheIdentity = ""
  var prefetchedVoiceDynamicContextIdentity = ""
  var pendingContextCacheReplacement = false
  var prefetchedVoiceSemanticGuidance = ""
  /// Exact Node registry projection from the bridge init handshake. Empty is a
  /// fail-closed value until the runtime has declared available adapters.
  var registeredDirectedProviderIDs: [String] = []
  var prefetchedVoiceContextTurnIDs: Set<String> = []
  var prefetchedVoiceContextOwnerScope: RealtimeHubOwnerScope?
  /// Typed snapshot identity baked into the current warm session's instructions.
  var sessionVoiceContextFreshnessIdentity = ""
  /// A PTT current-screen answer is grounded in exactly one pre-overlay, turn-scoped image.
  /// It is never ambient context and is released on terminal/cancel paths.
  var screenEvidence: RealtimeScreenEvidence?
  var screenEvidenceReadiness: RealtimeScreenEvidenceReadiness?
  var screenGroundingState: RealtimeScreenGroundingState = .inactive
  /// Latest safe protocol disposition, surfaced only through the non-production automation
  /// bridge. This lets a PTT probe distinguish a provider wait from a local lifecycle failure.
  var lastScreenEvidenceProtocolCompletion: RealtimeScreenEvidenceProtocolCompletion = .notRun
  var authorizedRealtimeScreenshotImages: [String: RealtimeScreenEvidenceAttachment] = [:]
  var screenFailurePresented = false
  var voiceContextPrefetchTask: Task<Void, Never>?
  var voiceContextRefreshGeneration: UInt64 = 0
  var turnPreparationTask: Task<Void, Never>?
  /// (b) Genuinely local: in-flight write Tasks + optional completion receipts.
  /// Receipts shadow kernel acceptance only until consumed; on relaunch they are
  /// rebuilt via `RealtimeHubContinuityRestore.kernelOwnsExchange`, never disk.
  let turnPersistenceLedger = RealtimeTurnPersistenceLedger()
  struct AcceptedSpawnJournalReceipt {
    let ownerID: String
    let receipt: RealtimeSpawnJournalReceipt
  }
  /// (c) Shadow truth: mirrors a kernel-accepted spawn exchange for this process.
  /// Authoritative owner is the kernel journal / voice-context turn IDs; restore
  /// through `RealtimeHubContinuityRestore` + `RealtimeTurnJournalAuthority`.
  var acceptedSpawnJournalReceiptByContinuityKey: [String: AcceptedSpawnJournalReceipt] = [:]
  let legacyVoiceJournalImportStore = LegacyVoiceJournalImportStore.shared
  var legacyVoiceJournalImportTask: Task<Void, Never>?
  var legacyVoiceJournalImportedOwners = Set<String>()
  var deferredSessionRefreshTask: Task<Void, Never>?
  var canceledTurnRewarmTask: Task<Void, Never>?
  var bargeInContinuityTask: Task<Void, Never>?
  var bargeInReplacementGeneration: UInt64 = 0
  var pendingBargeInProvider: RealtimeHubProvider?
  var pendingBargeInAuth: HubAuth?
  var pendingBargeInOwnerScope: RealtimeHubOwnerScope?
  /// Gemini input-transcription events do not carry a stable per-item ID. Once a
  /// turn completes, require a fresh provider session before accepting another PTT
  /// turn so a late event from A can never be attributed to B.
  var geminiSessionNeedsTurnBoundary = false

  // Per-turn language identification (multi-language PTT).
  /// Local copy of this turn's mic audio (16 kHz s16le mono) for on-device language ID.
  var turnAudio16k = Data()
  /// Monotonic turn counter guarding async language-ID results against cross-turn races.
  var turnEpoch = 0
  /// The provider input window is already open for this logical turn. This is
  /// deliberately separate from `reconnectAudioBuffer`: the manager needs to
  /// avoid a second `beginTurn` when a warm-wait callback arrives immediately
  /// after the controller replayed the buffered turn.
  var admittedInputTurnID: VoiceTurnID?
  /// Early (mid-hold) language verdict — kicked off ~1.5 s into the hold so it's already
  /// computed by PTT-up and the provider hint adds zero perceived latency.
  var earlyLIDTask: Task<PTTLanguageIdentifier.Verdict, Never>?
  /// Language code from the early verdict for THIS turn (nil = none arrived in time).
  /// Written by the early task's continuation, consumed synchronously at commit — so
  /// commit never awaits anything and can never drop a turn on a guard.
  var turnEarlyVerdictCode: String?
  /// Full-buffer decode kicked at commit; supplies the fallback transcript when the
  /// provider's transcript comes back in a language the user doesn't speak.
  var fullLIDTask: Task<PTTLanguageIdentifier.Verdict, Never>?
  /// Diagnostics of the last completed turn, for the `ptt_test_turn` automation action.
  var lastTurnDiagnostics: [String: String] = [:]
  /// TEST SEAM (ptt_test_turn only, bridge is non-prod-only): replaces the provider's
  /// transcript for the next turn-done, simulating a provider-side language misdetect
  /// (the "Russian speech transcribed as Italian" case) — the one input that can't be
  /// forced from outside. Everything downstream (mismatch check, local-transcript
  /// fallback, persistence) runs the real path. Cleared after one use.
  var testProviderTranscriptOverride: String?
  /// Harness-visible outcome of the most recent externally authorized tool.
  /// An empty error means the kernel accepted and executed the proposal.
  var lastExternalToolName = ""
  var lastExternalToolErrorCode = ""
  static let maxTurnAudioBytes = 3_840_000  // 120 s @ 16 kHz s16le
  static let earlyLIDBytes = 48_000  // 1.5 s
  /// Transport correlation only. Logical pending-tool ownership and completion
  /// live in `VoiceTurn`; each correlation returns the reducer-issued identity.
  var toolEffectIdentityByTransportKey: [String: VoiceEffectIdentity] = [:]
  /// (b) Genuinely local: in-flight begin-external-run Task handle. Kernel owns
  /// the resulting binding; this Task dies with the process and is not rebuilt.
  struct ExternalRunAuthorityState {
    let ownerID: String
    let turnID: VoiceTurnID
    let task: Task<ExternalSurfaceRunBinding, Error>
  }
  struct ExternalRunTerminalizationResult: Sendable {
    let binding: ExternalSurfaceRunBinding?
    let cleanupCapability: RuntimeOwnerTransitionCleanupCapability?
    let closed: Bool
    let failureCode: String?
  }
  enum ExternalRunBindingResolution: Sendable {
    case bound(ExternalSurfaceRunBinding)
    case failed(String)
  }
  struct TrackedExternalRunTerminalization {
    let ownerID: String
    let terminalStatus: ExternalSurfaceRunTerminalStatus
    let errorCode: String?
    let task: Task<ExternalRunTerminalizationResult, Never>
  }
  static let externalRunClientID = "omi-realtime-voice"
  static let externalRunHarnessMode = "piMono"
  var externalRunAuthorityState: ExternalRunAuthorityState?
  var externalRunTerminalizations: [UUID: TrackedExternalRunTerminalization] = [:]
  /// The begin RPC itself is bounded to 10 seconds. Two seconds of scheduling
  /// margin keeps owner replacement bounded without abandoning a request that
  /// can still create a physical kernel run. A task still in process startup is
  /// cancelled; AgentRuntimeProcess revalidates A immediately before its wire
  /// mutation, so it cannot create a late run after B becomes visible.
  static let ownerTransitionExternalRunBindingTimeout: Duration = .seconds(12)
  #if DEBUG
    var ownerBoundaryExternalRunCompletion:
      (
        @Sendable (
          ExternalSurfaceRunBinding,
          ExternalSurfaceRunTerminalStatus,
          String?,
          RuntimeOwnerTransitionCleanupCapability?
        ) async throws -> Void
      )?
  #endif
  /// (b) Genuinely local: in-flight authorized tool envelopes for this process.
  var authorizedRealtimeInvocations: [String: RealtimeAuthorizedToolInvocation] = [:]
  /// (b) Genuinely local delivery dedupe for this process. Kernel authorizes
  /// each run; this set only suppresses duplicate command delivery in-session.
  var completedAuthorizedRealtimeInvocationIDs: Set<String> = []
  var realtimeToolTurnEpoch = 0
  /// When the last PTT turn started — used to keep the socket warm via auto-reconnect
  /// only while the user is actively using it (Gemini idle-closes the WS ~2.5 min).
  var lastTurnAt: Date?
  var reconnectPending = false
  /// When the current warm socket last connected — used to tell a normal idle-close
  /// (survived a while → keep re-warming) from a fast config/auth failure (don't loop).
  var lastWarmAt: Date?
  /// Consecutive failed (re)connects with no surviving session — caps churn on a hard
  /// failure. Reset when a socket survives past the idle window or a turn completes.
  var hubReconnectStrikes = 0
  var pendingSessionRefreshReason: String?
  /// Invalidates delayed reconnect callbacks admitted by a previous owner.
  var ownerBoundaryGeneration: UInt64 = 0
  /// After this many consecutive fast failures (e.g. a stale/revoked key failing auth),
  /// the hub stops re-warming so it doesn't hammer a dead endpoint.
  static let maxReconnectStrikes = 5
  /// True only while a session is connected + authenticated for `sessionProvider`. This is
  /// what gates `isActive`: a PTT turn enters hub mode only when the hub is genuinely
  /// connected right now; otherwise it transparently uses the legacy cascade. Set in
  /// hubDidConnect (fires post-auth, on "ready") and cleared on teardown/error, so a
  /// stale/revoked key — which never connects — never costs the user a turn.
  var hubConnected = false
  /// Monotonic owner for realtime playback-idle callbacks. The PCM player can
  /// complete older buffers after a stop, rebuild, or newer audio chunk; only the
  /// latest scheduled playback epoch may publish a drain for the current lease.
  var realtimePlaybackEpoch = 0

  /// Log tag; an unbound handoff never infers a provider.
  var providerTag: String { RealtimeHubProviderLogTag.current(sessionProvider) }

  var reducerCapturingInput: Bool {
    VoiceTurnCoordinator.shared.activeTurn?.phase.isRecording == true
  }

  var reducerProviderActive: Bool {
    guard let phase = VoiceTurnCoordinator.shared.activeTurn?.phase else { return false }
    switch phase {
    case .awaitingResponse, .awaitingTools, .playing:
      return true
    case .idle, .pendingLockDecision, .recording, .lockedRecording, .finalizing,
      .awaitingJournal, .terminal:
      return false
    }
  }

  var reducerNativePlaybackActive: Bool {
    VoiceTurnCoordinator.shared.outputSnapshot.activeLease?.lane == .nativeRealtime
  }

  var reducerInterruptsPreviousTurn: Bool {
    VoiceTurnCoordinator.shared.activeTurn?.supersededTurnID != nil
  }

  var hasActiveVoiceTurn: Bool {
    VoiceTurnCoordinator.shared.activeTurnID != nil
  }

  var lifecycleSnapshot: RealtimeHubLifecycleSnapshot {
    RealtimeHubLifecycleSnapshot(
      capturingInput: reducerCapturingInput,
      providerActive: reducerProviderActive,
      playbackActive: reducerNativePlaybackActive,
      pendingToolCount: VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs.count ?? 0,
      coordinatorTurnActive: VoiceTurnCoordinator.shared.activeTurnID != nil,
      minting: minting)
  }

  /// In-flight ephemeral mint guard (managed users).
  var minting = false
  var mintGeneration: UInt64 = 0
  var mintOwnerScope: RealtimeHubOwnerScope?
  /// A Gemini active-reply barge-in replaces the whole session. Managed sessions
  /// need a fresh one-use token first, so hold early mic chunks/commit until the
  /// replacement session exists and can use its normal socket-open buffering.
  var replacementAudioBuffer: RealtimeReplacementAudioBuffer?
  /// A session can be replaced between PTT-down and its first microphone chunk.
  /// Preserve that one turn until the replacement session is authenticated, then
  /// replay it in order before committing.
  var reconnectAudioBuffer: RealtimeReconnectAudioBuffer?

  /// Failover chain: when the Auto-selected (primary) provider can't connect, the hub
  /// tries the OTHER realtime provider before dropping to the legacy Claude cascade.
  /// nil = on the primary; non-nil = the provider we failed over TO.
  var fallbackProvider: RealtimeHubProvider?
  /// Reason passed to ``failoverToAlternateProvider``; cleared after a successful connect on the alternate.
  var pendingFailoverReason: String?

  override init() {
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
  var effectiveProvider: RealtimeHubProvider {
    fallbackProvider ?? RealtimeHubSettings.shared.provider
  }

  var currentOwnerScope: RealtimeHubOwnerScope {
    RealtimeHubOwnerScope.capture(currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
  }

  func isOwnerScopeCurrent(_ scope: RealtimeHubOwnerScope) -> Bool {
    scope.isCurrent(currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
  }

  #if DEBUG
    func isAuthorizedLocalProfileTransport(_ source: RealtimeHubSession? = nil) -> Bool {
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
  func discardSessionAfterOwnerChange() {
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
    guard
      RuntimeOwnerIdentity.authorizesTransitionCleanup(
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
    admittedInputTurnID = nil
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

  func drainExternalRunTerminalizations(
    previousOwnerID: String?,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability
  ) async {
    guard
      RuntimeOwnerIdentity.authorizesTransitionCleanup(
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
      onComplete:
        @escaping @Sendable (
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
  func discardMismatchedSessionIfNeeded() -> Bool {
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

  func beginMint(ownerScope: RealtimeHubOwnerScope) -> UInt64? {
    guard !minting else { return nil }
    mintGeneration &+= 1
    minting = true
    mintOwnerScope = ownerScope
    return mintGeneration
  }

  @discardableResult
  func releaseMint(generation: UInt64, ownerScope: RealtimeHubOwnerScope) -> Bool {
    guard minting, mintGeneration == generation, mintOwnerScope == ownerScope else {
      return false
    }
    minting = false
    mintOwnerScope = nil
    return true
  }

  func acceptMintCompletionOrRewarm(
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
  func failoverToAlternateProvider(reason: String = "other") -> Bool {
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

  func failoverReason(for failureClass: CredentialFailureClass?) -> String {
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
  func failoverBargeInReplacement(
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

  func shouldFailoverToAlternate(for failureClass: CredentialFailureClass?) -> Bool {
    switch failureClass {
    case .providerAuthFailed, .providerQuotaExceeded:
      return true
    case .backendUnauthorized, .requiresLogin, .paywalled, .byokEnrollmentMismatch,
      .backendTransient, .providerTransient, .providerPolicyClose, .unknown, .none:
      return false
    }
  }

  func recordRealtimeMintFailure(
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

  /// PTT must distinguish a merely authenticated socket from a session that can
  /// accept this turn's canonical context. Callers always begin capture; this
  /// answer only chooses direct ingress versus bounded controller-owned buffering.
  var pttAdmission: RealtimePTTAdmission {
    let requirement = voiceSessionContext(for: currentOwnerScope)
    return RealtimePTTAdmissionPolicy.decide(
      requirementIsResolved: requirement.isResolved,
      transportIsReady: isTransportReady,
      bindingMatchesRequirement: requirement.snapshotFreshnessIdentity == sessionVoiceContextFreshnessIdentity)
  }

  func hasPendingInputPreparation(for turnID: VoiceTurnID?) -> Bool {
    guard let turnID else { return false }
    return reconnectAudioBuffer?.turnID == turnID || admittedInputTurnID == turnID
  }

  /// Non-production manager-harness facts. These describe ownership and
  /// admission only; they deliberately omit turn IDs, context payload, and
  /// provider text so a failed physical-path probe is diagnosable without
  /// exposing user content.
  func automationPTTInputDiagnostics() -> [String: String] {
    let requirement = voiceSessionContext(for: currentOwnerScope)
    let preparation: String
    if reconnectAudioBuffer != nil {
      preparation = "buffered"
    } else if admittedInputTurnID != nil {
      preparation = "admitted"
    } else {
      preparation = "none"
    }
    return [
      "ptt_admission": pttAdmission == .immediate ? "immediate" : "capture_and_buffer",
      "ptt_input_preparation": preparation,
      "ptt_rebind_attempts": "\(reconnectAudioBuffer?.rebindAttempts ?? 0)",
      "ptt_binding_matches_requirement":
        (requirement.isResolved && requirement.snapshotFreshnessIdentity == sessionVoiceContextFreshnessIdentity)
        ? "true" : "false",
      "ptt_handoff_pending": pendingSessionRefreshReason ?? "none",
    ]
  }

  /// The reducer selected the non-hub fallback for this logical turn. Drop only
  /// its pending physical replay so a late socket connect cannot revive audio
  /// that is now owned by the transcription lane.
  func abandonInputPreparation(turnID: VoiceTurnID) {
    guard reconnectAudioBuffer?.turnID == turnID else { return }
    turnPreparationTask?.cancel()
    turnPreparationTask = nil
    reconnectAudioBuffer = nil
    if admittedInputTurnID == turnID { admittedInputTurnID = nil }
    session?.abandonInputTurn()
    log("RealtimeHub: ptt_handoff event=fallback_cleanup turn=\(turnID.rawValue.uuidString)")
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

  /// Rewarm request that arrived mid PTT capture — retried at the clean
  /// end-of-turn points (hubDidFinishTurn / cancelTurn). Any teardownSession
  /// clears it: the rebuild that follows is what the deferred request wanted.
  private var pendingRewarmReason: String?

  /// Shared idle-only "drop and rebuild the warm session" used by discrete
  /// refresh events. Only acts when idle: a live session exists and we're
  /// neither mid-reply, mid-mint, nor mid barge-in replacement, so this never
  /// interrupts an active turn or races a connect already in flight. A request
  /// landing mid PTT capture (voice UI listening) is deferred to the end of
  /// the voice turn, not dropped: tearing down now would cut the audio being
  /// spoken, but skipping outright could leave a possibly-stale socket alive
  /// with no recovery (e.g. system wake during locked listening). teardown
  /// forces session=nil so ensureWarm() rebuilds (it would otherwise treat
  /// the stale socket as already-warm and no-op).
  private func forceRewarm(reason: String) {
    guard session != nil, !responding, !minting, !bargeInReplacementInFlight else { return }
    if barState?.isVoiceListening == true {
      pendingRewarmReason = reason
      return
    }
    log("RealtimeHub: \(reason) — re-warming session")
    teardownSession()
    ensureWarm()
  }

  /// Retry a rewarm deferred by forceRewarm once the voice turn has ended.
  private func firePendingRewarm() {
    guard let reason = pendingRewarmReason else { return }
    forceRewarm(reason: reason)
  }

  /// Headless E2E for the PTT language path: drives the REAL controller turn flow
  /// (beginTurn → paced feedAudio → commitTurn → turn-done) with a PCM file, so the
  /// early language ID, the provider hint, and the bubble fallback run exactly as a
  /// real hold-to-talk. `omi-ctl action ptt_test_turn pcm=/tmp/q.pcm [timeout=30]`.
  func registerPTTLanguageTestAction() {
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

  func runHeadlessPTTTurn(
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
          VoiceTurnCoordinator.shared.publish(.finish(turnID: staleTurnID, reason: .providerFailed))
        }
      }
      lastTurnDiagnostics = [:]
      let turnID = RealtimeAutomationTurnHarness.begin(on: VoiceTurnCoordinator.shared)
      VoiceTurnCoordinator.shared.publish(
        .selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
      // A real PTT press freezes the screen before its session/context work can
      // continue. Keep the probe at that same boundary: waiting for a warm socket
      // here lets a focus change masquerade as the screen the user asked about.
      prefetchVoiceContextSnapshotIfNeeded()
      let screenEvidenceCaptured = PushToTalkManager.shared.captureScreenEvidenceForAutomation(turnID: turnID)
      log(
        "RealtimeHub: headless PTT screen evidence capture="
          + (screenEvidenceCaptured ? "available" : "unavailable"))
      ensureWarm()
      guard await waitUntilActive(timeout: 15) else {
        _ = cancelTurn(turnID: turnID)
        VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerFailed))
        return ["error": "hub session did not become active (check sign-in / provider keys)"]
      }
      try? await Task.sleep(nanoseconds: 500_000_000)
      ensureWarm()
      guard await waitUntilActive(timeout: 15) else {
        _ = cancelTurn(turnID: turnID)
        VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerFailed))
        return ["error": "hub session did not become active after voice context prefetch"]
      }
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
      VoiceTurnCoordinator.shared.publish(.finalize(turnID: turnID))
      _ = commitTurn()
      let deadline = Date().addingTimeInterval(timeout)
      let canonicalContinuityKey = "voice:\(turnID.rawValue.uuidString.lowercased())"
      var redrive = false
      while Date() < deadline {
        let hasCanonicalSpawnReceipt =
          acceptedSpawnJournalReceiptByContinuityKey[canonicalContinuityKey] != nil
        switch RealtimeHeadlessPTTCompletionPolicy.terminalReason(
          for: turnID,
          lastTerminal: VoiceTurnCoordinator.shared.model.lastTerminal)
        {
        case .success:
          var result = lastTurnDiagnostics
          result["terminal_reason"] = VoiceTurnTerminalReason.success.rawValue
          return result
        case let reason?:
          return ["error": "voice turn terminated with \(reason.rawValue)"]
        case nil:
          break
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
    func runLocalProfileHeadlessPTTTurn(
      pcm16k: Data,
      timeout: Double,
      forceTranscript: String?,
      textOnly: Bool
    ) async -> [String: String] {
      guard !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress else {
        return ["error": "local-profile realtime transport unavailable during owner transition"]
      }
      guard let forceTranscript,
        !forceTranscript.trimmingCharacters(
          in: .whitespacesAndNewlines
        ).isEmpty
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
      VoiceTurnCoordinator.shared.publish(
        .selectRoute(turnID: turnID, route: .hub(sessionID: voiceSessionID)))
      beginTurn(turnID: turnID)
      if !textOnly {
        feedAudio(Data(pcm16k.prefix(3_200)), turnID: turnID)
      }
      VoiceTurnCoordinator.shared.publish(.finalize(turnID: turnID))
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
        VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerFailed))
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
          let pending =
            VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs
            .contains(VoiceToolCallID(callID)) == true
          if !pending {
            if let receipt = acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] {
              reply = receipt.receipt.assistantText
              break
            }
            VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerFailed))
            return ["error": "local-profile spawn_agent completed without a canonical journal receipt"]
          }
          try? await Task.sleep(nanoseconds: 50_000_000)
        }
        guard acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] != nil else {
          VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .toolTimeout))
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
    func waitUntilLocalProfileTransportReady(
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

    nonisolated static func localProfileSpawnArgumentsJSON(
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
  func registerRapidPTTBurstTestAction() {
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

  func runHeadlessRapidPTTBurst(
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
      VoiceTurnCoordinator.shared.publish(
        .selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
      beginTurn(turnID: turnID)
      var offset = 0
      while offset < clip.count {
        let end = min(offset + 3_200, clip.count)
        feedAudio(clip.subdata(in: offset..<end), turnID: turnID)
        offset = end
        try? await Task.sleep(nanoseconds: 100_000_000)
      }
      VoiceTurnCoordinator.shared.publish(.finalize(turnID: turnID))
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
  @objc private func systemDidWake() {
    forceRewarm(reason: "system woke (dropping possibly-stale socket)")
  }

  /// A local agent provider was just installed (or removed) — re-warm the
  /// session so the tool schema enum and provider instruction, both computed
  /// at session start, pick up the change. When a turn is in flight the
  /// change simply lands on the next reconnect.
  func refreshForLocalAgentProviderChange() {
    forceRewarm(reason: "local agent provider availability changed")
  }

  /// Voice languages changed: prewarm the LID model (a 1→2 language change would
  /// otherwise cold-load on the first turn) and rebuild an idle warm session so the
  /// new languages line lands in the system instruction now, not at the next re-mint.
  @objc private func voiceLanguagesChanged() {
    if !AssistantSettings.shared.voiceBaseLanguages.isEmpty {
      Task.detached(priority: .utility) { await PTTLanguageIdentifier.shared.prewarm() }
    }
    requestSessionHandoff(reason: .voiceLanguages)
  }

  @objc private func settingsChanged() {
    resetFailoverForProviderSettingsChange()
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
    let topLevelContext = combinedTopLevelVoiceContinuityContext()
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
    // A brand-new session IS the rebuild a deferred rewarm wanted — also covers
    // restartSessionForBargeIn, which replaces the session without teardownSession.
    pendingRewarmReason = nil
    // Both providers stream native spoken audio (24k PCM) → StreamingPCMPlayer;
    // selected app voice playback handles any no-audio fallback.
    if pcmPlayer == nil {
      pcmPlayer = makePCMPlayer()
    }
    s.start()
    log(
      "RealtimeHub: warming \(provider.displayName) session "
        + "(\(auth.isEphemeral ? "ephemeral/managed" : "client-direct/BYOK"), "
        + "continuityTurns=\(voiceContinuityTurns.count), contextChars=\(topLevelContext.count))")
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
    pendingRewarmReason = nil  // the rebuild that follows any teardown is what the deferral wanted
    pendingCompletedAgentDeltaAckIds.removeAll()
    pendingCompletedAgentDeltaHighWaterMs = nil
    clearRealtimeToolTracking()
  }

  private func clearBargeInReplacementState() {
    pendingBargeInReplacement = nil
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
    pendingBargeInReplacement = PendingBargeInReplacementTurn()
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
    if provider == .gemini, let speculativeScreenshot {
      session?.sendVideoFrame(speculativeScreenshot, mime: "image/jpeg")
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
    if bargeIn {
      preserveInterruptedTurnForContinuity()
    }
    responding = false
    realtimePlaybackActive = false
    realtimePlaybackEpoch += 1
    var replacementSessionOwnsInputTurn = false
    turnTranscript = ""
    assistantText = ""
    speculativeWarmDone = false
    speculativeScreenshot = nil
    audioReceivedThisTurn = false
    turnGeneration &+= 1
    let screenshotTurnGeneration = turnGeneration
    suppressAssistantOutputForCurrentTurn = false
    turnRecorded = false
    earlyUserMessageShown = false
    earlyUserMessageId = nil
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
    lastTurnAt = Date()
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
        guard self.turnGeneration == screenshotTurnGeneration else { return }
        self.speculativeScreenshot = jpeg
        if self.sessionProvider == .gemini, let jpeg {
          self.session?.sendVideoFrame(jpeg, mime: "image/jpeg")
        }
      }
    }
  }

  private func preserveInterruptedTurnForContinuity() {
    guard !turnRecorded else { return }
    let heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !heard.isEmpty else { return }
    let partialReply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    let interruptedReply: String
    if partialReply.isEmpty {
      interruptedReply = "Interrupted before the assistant finished responding."
    } else {
      interruptedReply = "\(partialReply)\n\n[Interrupted by the next push-to-talk turn before completion.]"
    }
    turnRecorded = true
    rememberVoiceContinuityTurn(userText: heard, assistantText: interruptedReply, interrupted: true)
    // Runs synchronously in beginTurn before earlyUserMessageId is reset, so this is
    // still the interrupted turn's bubble id.
    FloatingControlBarManager.shared.recordVoiceTurn(
      userText: heard, assistantText: interruptedReply, earlyUserMessageId: earlyUserMessageId)
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
    firePendingRewarm()
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
  }

  func hubDidReceiveInputTranscript(_ text: String, isFinal: Bool, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    if isFinal {
      if !text.isEmpty { turnTranscript = text }
      // OpenAI marks the input transcript final before/as the model starts replying —
      // surface the question in chat now instead of waiting for the whole turn.
      showUserQuestionEarly()
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
      return
    }
    requestSessionHandoff(reason: .providerSettings)
  }

  /// The only ordinary session-maintenance entrypoint. A captured PTT turn
  /// owns bounded audio while this method changes a physical binding; all other
  /// maintenance defers until the reducer reports an idle lifecycle.
  func requestSessionHandoff(
    reason: RealtimeHubSessionHandoffReason,
    preservingReconnectAudio: Bool = false
  ) {
    let hasBufferedTurn = preservingReconnectAudio && reconnectAudioBuffer != nil
    let decision = RealtimeHubSessionHandoffPolicy.decide(
      bindingMatchesRequirement: false,
      canReplaceIdleSession: RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot),
      hasBufferedTurn: hasBufferedTurn,
      rebindAttempts: reconnectAudioBuffer?.rebindAttempts ?? 0)
    switch decision {
    case .keepActive:
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
    case .getTaskAgentStatus:
      runToolAndSpeak(
        source: source,
        callId: callId, name: name, detail: "coordinator_open_loops_and_completion_delta",
        emptyText: "No active agent attention items.",
        errorText: "Could not read the agent coordinator right now.",
        expectedTurnEpoch: toolTurnEpoch
      ) {
        do {
          let openLoops = try await DesktopCoordinatorService.shared.openLoopsJSON()
          if let completionDelta = await DesktopCoordinatorService.shared.peekCompletedAgentDelta(surfaceKind: "ptt") {
            self.pendingCompletedAgentDeltaAckIds = completionDelta.ids
            self.pendingCompletedAgentDeltaHighWaterMs = completionDelta.completedAtHighWaterMs
            return """
              \(openLoops)

              # Completed Agent Delta
              \(completionDelta.prompt)
              """
          }
          if self.coordinatorOpenLoopsIsEmpty(openLoops) {
            let fallback = TaskAgentStatusRegistry.shared.combinedSummary()
            if !fallback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
              return """
                No open coordinator loops or newly completed canonical agent deltas.

                # Legacy/Floating Agent Status
                \(fallback)
                """
            }
          }
          return openLoops
        } catch {
          logError("RealtimeHub[\(self.providerTag)]: coordinator status fallback failed", error: error)
          return TaskAgentStatusRegistry.shared.combinedSummary()
        }
      }
    case .manageAgentPills:
      let action =
        ((arguments["action"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines))
        .flatMap { $0.isEmpty ? nil : $0 } ?? "list"
      let agentId = (arguments["agent_id"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
      guard Self.userExplicitlyRequestedPillManagement(action: action, transcript: turnTranscript) else {
        log("RealtimeHub[\(providerTag)]: blocked manage_agent_pills action=\(action) without explicit user request")
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "Dismissal blocked: only dismiss or clear floating agent pills when the user explicitly asks.")
        return
      }
      let result = AgentPillsManager.shared.manage(action: action, agentId: agentId)
      log("RealtimeHub[\(providerTag)]: tool manage_agent_pills action=\(action)")
      sendToolResultIfCurrent(source: source, callId: callId, name: name, output: result)
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
      let description =
        (arguments["description"] as? String)?
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
      let title =
        (arguments["title"] as? String)?
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
      let brief = arg("brief")
      let title = (arguments["title"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
      let providerName = AgentPillsManager.DirectedProvider.normalizedRawValue(arguments["provider"] as? String)
      Task { [weak self] in
        guard let self else { return }
        await self.handleRealtimeDelegationRequest(
          brief: brief,
          title: title,
          providerName: providerName,
          source: source,
          callId: callId,
          name: name,
          expectedTurnEpoch: toolTurnEpoch)
      }
    case .setupAgentProvider:
      let setupProviderName = ((arguments["provider"] as? String) ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: " ", with: "")
      if !providerName.isEmpty && providerName != "openclaw" && providerName != "hermes"
        && providerName != "codex"
      {
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "Unsupported agent provider '\(providerName)'. Use 'hermes', 'openclaw', or 'codex'.",
          expectedTurnEpoch: toolTurnEpoch)
        return
      }
      let userRequestText = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
      Task { @MainActor [weak self] in
        guard let self else { return }
        let resolution = await LocalAgentProviderRouting.resolveSpawnWithAutoInstall(
          brief: brief,
          requestedProvider: requestedProvider,
          userRequestText: userRequestText.isEmpty ? nil : userRequestText,
          title: title,
          onInstallStart: { [weak self] provider in
            guard let self else { return }
            let status = LocalAgentProviderInstaller.installingStatus(for: provider)
            log("RealtimeHub[\(self.providerTag)]: auto-installing \(provider.rawValue)")
            if !self.audioReceivedThisTurn {
              self.barState?.isVoiceResponseActive = true
              self.speak(status)
            }
          }
        )
        // The install await can take many seconds; bail if the session/turn moved on
        // so we don't speak or mutate state for a turn that's no longer active.
        guard self.isCurrentSession(source) else { return }
        switch resolution {
        case .setupRequired(let provider, let setupPrompt, let spokenStatus):
          self.assistantText = setupPrompt
          self.barState?.isVoiceResponseActive = true
          if !self.audioReceivedThisTurn {
            self.speak(spokenStatus)
          }
          self.suppressAssistantOutputForCurrentTurn = true
          log("RealtimeHub[\(self.providerTag)]: tool spawn_agent provider=\(provider.rawValue) unavailable")
          self.sendToolResultIfCurrent(
            source: source, callId: callId, name: name,
            output: "Error: \(setupPrompt)")
          return
        case .spawn(let plan):
          let model = ShortcutSettings.shared.selectedModel.isEmpty
            ? ModelQoS.Claude.defaultSelection : ShortcutSettings.shared.selectedModel
          let pill = AgentPillsManager.shared.spawnFromUserQuery(
            brief, model: model, fromVoice: false,
            preFetchedTitle: plan.title,
            preFetchedAck: plan.ack,
            bridgeHarnessOverride: plan.harnessOverride,
            spawnContext: plan.context)
          log("RealtimeHub[\(self.providerTag)]: tool spawn_agent → AgentBridge pill=\"\(pill.title)\" model=\(model) provider=\(plan.selectedProvider?.rawValue ?? "default") titled=\(title?.isEmpty == false) fallback=\(plan.usedFallback)")
          if !self.audioReceivedThisTurn {
            let existingAck = self.assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
            let ack = existingAck.isEmpty ? plan.ack : existingAck
            self.assistantText = ack
            self.barState?.isVoiceResponseActive = true
            self.speak(ack)
          }
          self.suppressAssistantOutputForCurrentTurn = true
          let toolOutput: String
          if let fallbackNote = plan.fallbackNote {
            toolOutput = "Agent started with fallback. \(fallbackNote)"
          } else {
            toolOutput = "Agent started."
          }
          self.sendToolResultIfCurrent(
            source: source, callId: callId, name: name,
            output: toolOutput)
        }
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "\(setupProvider.displayName) is already set up. \(setupBrief?.isEmpty == false ? "Task started." : "")",
          expectedTurnEpoch: toolTurnEpoch)
        return
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
    case "codex": directedProvider = .codex
    case "": directedProvider = nil
    default:
      sendToolResultIfCurrent(
        source: source, callId: callId, name: name,
        output: "Unsupported agent provider '\(providerName)'. Use 'hermes', 'openclaw', or 'codex'.",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    }
    var directedProvider = dispatch.primary
    var routedFallbacks = dispatch.fallbacks
    log("RealtimeHub[\(providerTag)]: spawn_agent dispatch \(dispatch.reason)")

    let resolution = await AgentDelegationResolver.shared.resolve(
      .init(
        surface: .realtimeVoice,
        userText: userText,
        proposedBrief: brief,
        proposedTitle: title,
        proposedAck: nil,
        directedProvider: directedProvider,
        topLevelContext: combinedTopLevelVoiceContinuityContext(),
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

    if let resolverProvider = resolution.directedProvider, resolverProvider != directedProvider {
      // The resolver explicitly redirected the provider; respect it and drop
      // the auto-route chain, which was computed for a different primary.
      directedProvider = resolverProvider
      routedFallbacks = []
    }
    if let directedProvider {
      // Dispatch gates on full health (installed AND wired AND authed), not
      // binary presence — a not-onboarded provider must not get a doomed spawn.
      let health = AgentProviderHealth.report(for: directedProvider)
      guard health.readiness == .ready else {
        let setupPrompt = "\(health.detail) I can set it up for you."
        assistantText = setupPrompt
        barState?.isVoiceResponseActive = true
        if !audioReceivedThisTurn {
          FloatingBarVoicePlaybackService.shared.speakOneShot(directedProvider.setupNeededStatus)
        }
        suppressAssistantOutputForCurrentTurn = true
        log("RealtimeHub[\(providerTag)]: tool spawn_agent provider=\(directedProvider.rawValue) not ready (\(health.readiness.rawValue))")
        sendToolResultIfCurrent(
          source: source, callId: callId, name: name,
          output: "Error: \(health.detail)"
            + " Offer to set it up for the user; if they agree, call setup_agent_provider with provider=\"\(directedProvider.rawValue)\" and their original task as brief.",
          expectedTurnEpoch: expectedTurnEpoch)
        return
      }
    }

    let model =
      ShortcutSettings.shared.selectedModel.isEmpty
      ? ModelQoS.Claude.defaultSelection : ShortcutSettings.shared.selectedModel
    guard
      let pill = AgentDelegationExecutor.shared.spawnResolvedDelegation(
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

    pill.fallbackProviders = routedFallbacks
    log("RealtimeHub[\(providerTag)]: tool spawn_agent → canonical pill=\"\(pill.title)\" model=\(model) provider=\(directedProvider?.rawValue ?? "default") fallbacks=\(routedFallbacks.count) titled=\(title?.isEmpty == false)")
    let shouldAllowNativePostSpawnAck = !audioReceivedThisTurn
    if !audioReceivedThisTurn {
      let existingAck = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      let resolvedAck = resolution.ack?.trimmingCharacters(in: .whitespacesAndNewlines)
      let ack =
        existingAck.isEmpty
        ? (resolvedAck?.isEmpty == false ? resolvedAck! : "Starting a background agent.")
        : existingAck
      assistantText = ack
    }
    // Defer durable chat-history handoff recording to hubDidFinishTurn so the
    // final ASR transcript is used instead of a partial interim transcript.
    pendingVoiceAgentHandoff = (title: pill.title, brief: resolvedBrief)
    suppressAssistantOutputForCurrentTurn = !shouldAllowNativePostSpawnAck
    // When the router picked the provider (not the user), tell the model so
    // it can narrate the choice — the routing decision should be observable
    // to the user, not just to the logs. Explicit mentions and default-
    // orchestrator spawns keep the exact legacy result text.
    let startedOutput: String
    if let directedProvider, dispatch.reason != "explicit" {
      startedOutput =
        "Agent started via \(directedProvider.displayName) — Omi picked it as the best fit for this task. In your brief acknowledgment, mention that \(directedProvider.displayName) is handling it."
    } else {
      startedOutput = "Agent started."
    }
    sendToolResultIfCurrent(
      source: source, callId: callId, name: name,
      output: startedOutput,
      expectedTurnEpoch: expectedTurnEpoch)
  }

  func hubDidFinishTurn(source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    guard pendingRealtimeToolCallIds.isEmpty else {
      log(
        "RealtimeHub[\(providerTag)]: deferring turn done with \(pendingRealtimeToolCallIds.count) tool result(s) pending"
      )
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
    // A turn-done delivered late — after the user already began the next capture —
    // must leave that capture alone: beginTurn already wiped this turn's transcript
    // buffers (nothing left to record) and reset turnRecorded for the new turn,
    // exitVoiceUI would clear the live listening/locked state and collapse the bar
    // mid-hold, and the pending rewarm would tear the session down mid-turn. All of
    // it stays parked for the new turn's own clean end.
    if barState?.isVoiceListening == true {
      log("RealtimeHub[\(providerTag)]: late turn-done during a new capture — leaving voice UI untouched")
      return
    }
    // Record the completed turn into chat history (+ backend sync) in the background.
    // The hub plays its reply itself and never routes through the query path, so this is
    // the only place voice turns get persisted. Idempotent per turn; recordVoiceTurn is
    // fire-and-forget so it never stalls the warm socket or the next PTT press.
    if !turnRecorded {
      turnRecorded = true
      if let handoff = pendingVoiceAgentHandoff {
        pendingVoiceAgentHandoff = nil
        let assistantText = "Started background agent \"\(handoff.title)\" for: \(handoff.brief)"
        rememberVoiceContinuityTurn(userText: heard, assistantText: assistantText, interrupted: false)
        FloatingControlBarManager.shared.recordVoiceAgentHandoff(
          userText: heard,
          agentTitle: handoff.title,
          agentBrief: handoff.brief,
          earlyUserMessageId: earlyUserMessageId)
      } else {
        log("RealtimeHub: handoff requested reason=\(reason.rawValue) mode=idle")
      }
      if session != nil { teardownSession(preservingReconnectAudio: hasBufferedTurn) }
      ensureWarm()
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
    firePendingRewarm()
  }

  func applyPendingSessionRefreshIfIdle() {
    guard let reason = pendingSessionRefreshReason,
      RealtimeHubLifecyclePolicy.canReplaceSession(lifecycleSnapshot)
    else { return }
    pendingSessionRefreshReason = nil
    if reason == "voice_context_changed" {
      deferredSessionRefreshTask?.cancel()
      deferredSessionRefreshTask = Task { @MainActor [weak self] in
        guard let self else { return }
        if await self.refreshVoiceContextAfterPersistenceFence(reason: reason) {
          self.canceledTurnRewarmTask = nil
          log("RealtimeHub: applying deferred voice context refresh after turn persistence")
          self.requestSessionHandoff(reason: .persistedVoiceContext)
        }
        self.deferredSessionRefreshTask = nil
      }
      return
    }
    log("RealtimeHub: applying deferred \(reason) session handoff")
    if reason == RealtimeHubSessionHandoffReason.providerSettings.rawValue {
      resetFailoverForProviderSettingsChange()
    }
    guard let typedReason = RealtimeHubSessionHandoffReason(rawValue: reason) else {
      return
    }
    requestSessionHandoff(reason: typedReason)
  }

  /// Waits for every persistence write visible at the fence, refreshes context,
  /// and retries if either a new turn or a new write appears across an await.
  /// Callers decide when it is safe to release any stronger reconnect gate.
  func refreshVoiceContextAfterPersistenceFence(reason: String) async -> Bool {
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

  func resetFailoverForProviderSettingsChange() {
    // A new pick (user or Auto/AutoModelSelector) re-evaluates from the primary.
    // This reset moves with session replacement so an active fallback turn keeps
    // a coherent provider identity until it terminates.
    fallbackProvider = nil
    pendingFailoverReason = nil
  }

}

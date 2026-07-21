import Combine
import Foundation
import SwiftUI

/// A visible background-agent projection launched from the Ask Omi floating
/// bar. Execution is owned by the canonical Omi agent runtime; this model only
/// drives the floating/notch-less pill UI.
@MainActor
final class AgentPill: ObservableObject, Identifiable {
  enum Status: Equatable {
    case queued
    case starting
    case running
    case done
    case stopped
    case failed(String)

    var displayLabel: String {
      switch self {
      case .queued: return "Queued"
      case .starting, .running: return "Running"
      case .done: return "Done"
      case .stopped: return "Stopped"
      case .failed: return "Failed"
      }
    }

    var tintColor: Color {
      switch self {
      case .queued: return Color(red: 0.20, green: 0.86, blue: 1.0)
      case .starting, .running: return Color(red: 1.0, green: 0.80, blue: 0.40)
      case .done: return Color(red: 0.27, green: 0.92, blue: 0.46)
      case .stopped: return Color(red: 0.64, green: 0.66, blue: 0.70)
      case .failed: return Color(red: 1.0, green: 0.42, blue: 0.42)
      }
    }

    var machineLabel: String {
      switch self {
      case .queued: return "queued"
      case .starting: return "starting"
      case .running: return "running"
      case .done: return "done"
      case .stopped: return "stopped"
      case .failed: return "failed"
      }
    }

    var isFinished: Bool {
      switch self {
      case .done, .stopped, .failed: return true
      default: return false
      }
    }

  }

  let id: UUID
  let query: String
  let createdAt: Date
  let model: String
  let ownerID: String
  let bridgeHarnessOverride: AgentHarnessMode?
  @Published private(set) var providerIdentity: AgentHarnessMode?
  var canonicalSessionId: String?
  var canonicalRunId: String?
  var canonicalAttemptId: String?
  /// Exact parent journal surface that owns this pill's `agentSpawn` block.
  /// This stays pinned even if the user switches chats while the run is active.
  var producingJournalSurface: AgentSurfaceReference?

  @Published var title: String
  @Published var status: Status = .queued
  @Published var latestActivity: String = "Queued…"
  @Published var transcript: [String] = []
  @Published var aiMessage: ChatMessage?
  @Published var conversationMessages: [ChatMessage] = []
  @Published var completedAt: Date?
  @Published var viewedAt: Date?
  @Published var suggestedFollowUps: [String] = []
  @Published var contentRevision: Int = 0

  /// Convenience: how long the agent has been running (or ran).
  var elapsed: TimeInterval {
    (completedAt ?? Date()).timeIntervalSince(createdAt)
  }

  init(
    id: UUID = UUID(),
    query: String,
    model: String,
    bridgeHarnessOverride: AgentHarnessMode? = nil,
    ownerID: String? = nil
  ) {
    self.id = id
    self.query = query
    self.model = model
    self.ownerID = ownerID ?? RuntimeOwnerIdentity.currentOwnerId() ?? ""
    self.bridgeHarnessOverride = bridgeHarnessOverride
    self.providerIdentity = bridgeHarnessOverride
    self.title = AgentPill.deriveTitle(from: query)
    self.createdAt = Date()
  }

  /// Provider provenance is kernel-authored and may arrive after the local
  /// projection is created (snapshot hydration/restart). It is display truth,
  /// never execution authority; `bridgeHarnessOverride` remains the immutable
  /// launch request for locally-created pills.
  func applyCanonicalProviderIdentity(_ rawValue: String?) {
    guard let rawValue,
      let provider = AgentRuntimeRouting.harnessMode(from: rawValue),
      provider == .hermes || provider == .openclaw,
      providerIdentity != provider
    else { return }
    providerIdentity = provider
  }

  func markContentChanged() {
    contentRevision &+= 1
  }

  /// Pull a short uppercase title out of the query for the pill popover header.
  /// "open google.com and find vegan ramen" → "OPEN GOOGLE.COM"
  private static func deriveTitle(from query: String) -> String {
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    let words =
      trimmed
      .split(separator: " ", maxSplits: 4, omittingEmptySubsequences: true)
      .prefix(3)
      .map(String.init)
    let joined = words.joined(separator: " ").uppercased()
    if joined.count > 32 {
      return String(joined.prefix(32)) + "…"
    }
    return joined.isEmpty ? "AGENT" : joined
  }
}

enum AgentOwnerBoundSpawnResult<Value: Sendable>: Sendable {
  case rejectedBeforeDispatch
  case staleReceipt(Value)
  case accepted(Value)
}

/// Singleton that owns visible `AgentPill` projections. It never owns agent
/// execution; spawn/continue/stop delegate to the canonical runtime.
struct AgentPillProducerJournalIntent: Sendable {
  let surface: AgentSurfaceReference
  let userText: String
  let assistantText: String
}

/// One policy controls when a visible pill needs another canonical read. A
/// terminal child run is not converged until its visible pill is terminal and
/// the producing journal turn carries the corresponding completion block.
@MainActor
struct AgentPillLifecycleConvergencePolicy {
  static func requiresCanonicalReconciliation(
    status: AgentPill.Status,
    requiresJournalCompletion: Bool,
    hasTerminalJournalCompletion: Bool,
    hasTerminalJournalMaterializationFailure: Bool,
    hasPendingFollowUp: Bool
  ) -> Bool {
    hasPendingFollowUp || !status.isFinished
      || (requiresJournalCompletion && !hasTerminalJournalCompletion
        && !hasTerminalJournalMaterializationFailure)
  }

  static func shouldStartCanonicalPoll(
    projectedStatusIsTerminal: Bool,
    pillStatus: AgentPill.Status,
    hasCanonicalTerminalDetail: Bool,
    isPolling: Bool
  ) -> Bool {
    guard !isPolling else { return false }
    // A successful list projection proves only the run's status. Its
    // completion text remains owned by `get_agent_run`; poll exactly once
    // when that text has not reached the local terminal message yet.
    // Cancellation and failure receipts have deterministic local text, so
    // they do not need a second canonical read.
    if projectedStatusIsTerminal {
      return pillStatus == .done && !hasCanonicalTerminalDetail
    }
    return !pillStatus.isFinished
  }
}

enum AgentPillTerminalJournalMaterializationDecision: Equatable {
  case materialize(status: String, output: String)
  case awaitingCanonicalDetail
  case unavailable
}

/// The runtime session list is status-only. A successful completion is not
/// journal-ready until the corresponding `get_agent_run` result has supplied
/// its canonical final output. This small pure policy is intentionally shared
/// by the materializer and its ordering regression test.
struct AgentPillTerminalJournalMaterializationPolicy {
  static func decision(
    status: AgentPill.Status,
    canonicalRunID: String?,
    canonicalDetailRunID: String?,
    canonicalDetailOutput: String?
  ) -> AgentPillTerminalJournalMaterializationDecision {
    switch status {
    case .done:
      guard let canonicalRunID, !canonicalRunID.isEmpty else { return .unavailable }
      guard canonicalDetailRunID == canonicalRunID else { return .awaitingCanonicalDetail }
      let output = canonicalDetailOutput?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      return .materialize(status: "completed", output: output.isEmpty ? "Done." : output)
    case .stopped:
      return .materialize(status: "stopped", output: "Stopped by user")
    case .failed(let error):
      return .materialize(status: "failed", output: "Background agent failed: \(error)")
    case .queued, .starting, .running:
      return .unavailable
    }
  }
}

private struct AgentPillLifecycleConvergenceEntry: Codable {
  let runId: String
  let canonicalStatus: String
  let projectedStatus: String?
  let completionMaterialized: Bool
  let converged: Bool
}

private struct AgentPillLifecycleConvergenceSnapshot: Codable {
  let entries: [AgentPillLifecycleConvergenceEntry]
  let missingRequestedRunIds: [String]
  let canonicalReadError: String?
}

@MainActor
final class AgentPillsManager: ObservableObject {
  static let shared = AgentPillsManager()

  @Published private(set) var pills: [AgentPill] = []

  /// Configurable soft cap so the row never grows past a reasonable width.
  private let maxPills: Int = 8

  /// INV-8: ephemeral UI only — tracks in-flight projection poll/send tasks per pill;
  /// canonical run truth lives in the kernel (`canonicalSessionId` / `canonicalRunId`).
  private var runTasksByPill: [UUID: Task<Void, Never>] = [:]
  private var runAttemptGenerationByPill: [UUID: Int] = [:]
  private var viewedExpirationWorkItemsByPill: [UUID: DispatchWorkItem] = [:]
  private var pendingFollowUpsByPill: [UUID: [PendingAgentFollowUp]] = [:]
  private var producingJournalSurfaceByPill: [UUID: AgentSurfaceReference] = [:]

  private let viewedFinishedTTL: TimeInterval = 10 * 60

  private var projectionSyncCancellable: AnyCancellable?
  private var projectionRefreshTask: Task<Void, Never>?
  private let projectionBootstrapAttempts = 20
  /// A long-running child can outlive the one-shot poll that created its
  /// Swift pill (for example during a PTT replacement). Reconciliation is a
  /// single owner-scoped repair loop over canonical run state, not a second
  /// lifecycle store or another source of completion truth.
  private var canonicalReconciliationTask: Task<Void, Never>?
  private var canonicalReconciliationGeneration = 0
  /// Completion is only durable once the producing assistant journal turn
  /// contains the matching `agentCompletion` block. A terminal pill message
  /// is useful UI, but it is not evidence that PTT can retrieve the result.
  private var terminalJournalMaterializedPillIDs = Set<UUID>()
  private struct CanonicalTerminalRunDetail {
    let runID: String
    let finalText: String
  }
  /// A completed session-list row has status truth but not its final output.
  /// This records the exact run whose canonical detail has been applied, so
  /// a status-only row can never journal the placeholder "Done." first.
  private var terminalCanonicalDetailsByPill = [UUID: CanonicalTerminalRunDetail]()
  /// A legacy/historical pill can outlive the journal row that originally
  /// produced it. `appendAgentCompletion` already makes a bounded retry; do
  /// not turn a definitive miss into an app-lifetime control-plane poll.
  /// Canonical run state remains the visible terminal truth in that case.
  private var terminalJournalMaterializationFailedPillIDs = Set<UUID>()
  private var terminalJournalMaterializationTasks = [UUID: Task<Void, Never>]()
  private var terminalJournalMaterializationGenerationByPill = [UUID: Int]()
  private var ownerChangeCancellable: AnyCancellable?
  private var runtimeReadyCancellable: AnyCancellable?

  private init() {
    projectionSyncCancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
      .receive(on: RunLoop.main)
      .sink { [weak self] _ in
        self?.applyRuntimeProjections()
      }
    scheduleProjectionBootstrap()
    ownerChangeCancellable = NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)
      .sink { [weak self] _ in
        MainActor.assumeIsolated {
          self?.resetOwnerProjection()
        }
      }
    runtimeReadyCancellable = NotificationCenter.default.publisher(for: .agentRuntimeDidBecomeReady)
      .receive(on: RunLoop.main)
      .sink { [weak self] _ in
        self?.scheduleProjectionBootstrap()
      }
  }

  #if DEBUG
    /// Hermetic tests that only exercise in-memory projection state must not
    /// let the singleton's eager refresh start the real shared agent runtime.
    func quiesceProjectionRefreshForTesting() {
      projectionRefreshTask?.cancel()
      projectionRefreshTask = nil
    }
  #endif

  private struct PendingAgentFollowUp {
    let text: String
    let attachments: [ChatAttachment]
  }

  func resetOwnerProjection() {
    projectionRefreshTask?.cancel()
    projectionRefreshTask = nil
    canonicalReconciliationTask?.cancel()
    canonicalReconciliationTask = nil
    canonicalReconciliationGeneration &+= 1
    for task in terminalJournalMaterializationTasks.values { task.cancel() }
    terminalJournalMaterializationTasks.removeAll()
    terminalJournalMaterializedPillIDs.removeAll()
    terminalCanonicalDetailsByPill.removeAll()
    terminalJournalMaterializationFailedPillIDs.removeAll()
    for task in runTasksByPill.values { task.cancel() }
    for item in viewedExpirationWorkItemsByPill.values { item.cancel() }
    runTasksByPill.removeAll()
    runAttemptGenerationByPill.removeAll()
    viewedExpirationWorkItemsByPill.removeAll()
    pendingFollowUpsByPill.removeAll()
    producingJournalSurfaceByPill.removeAll()
    pills.removeAll()
    scheduleProjectionBootstrap()
  }

  /// The floating bar is created before auth restoration can publish the
  /// runtime owner. A one-shot refresh in that window silently returned with
  /// an empty local projection, leaving completed canonical children absent
  /// until some unrelated UI interaction rehydrated them.
  private func scheduleProjectionBootstrap() {
    projectionRefreshTask?.cancel()
    log("AgentPills: scheduling canonical projection bootstrap")
    projectionRefreshTask = Task { @MainActor [weak self] in
      guard let self else { return }
      log("AgentPills: canonical projection bootstrap started")
      for _ in 0..<projectionBootstrapAttempts {
        guard !Task.isCancelled else { return }
        guard RuntimeOwnerIdentity.currentOwnerId() != nil else {
          try? await Task.sleep(nanoseconds: 250_000_000)
          continue
        }
        guard await AgentRuntimeProcess.shared.isReadyForDirectControl() else {
          try? await Task.sleep(nanoseconds: 250_000_000)
          continue
        }
        log("AgentPills: canonical projection bootstrap requesting control read")
        if await refreshProjectedPillsFromKernel() {
          return
        }
        try? await Task.sleep(nanoseconds: 250_000_000)
      }
      guard !Task.isCancelled else { return }
      log("AgentPills: projection bootstrap did not reach a ready runtime")
    }
  }

  static func performOwnerBoundSpawn<Value: Sendable>(
    ownerID: String,
    currentOwnerID: @escaping @MainActor () -> String? = {
      RuntimeOwnerIdentity.currentOwnerId()
    },
    dispatch: () async throws -> Value
  ) async rethrows -> AgentOwnerBoundSpawnResult<Value> {
    guard !ownerID.isEmpty, currentOwnerID() == ownerID else {
      return .rejectedBeforeDispatch
    }
    let value = try await dispatch()
    guard currentOwnerID() == ownerID else { return .staleReceipt(value) }
    return .accepted(value)
  }

  func bindProducingJournalSurface(
    pillID: UUID,
    surface: AgentSurfaceReference
  ) {
    producingJournalSurfaceByPill[pillID] = surface
    pills.first(where: { $0.id == pillID })?.producingJournalSurface = surface
  }

  func producingJournalSurface(for pillID: UUID) -> AgentSurfaceReference? {
    pills.first(where: { $0.id == pillID })?.producingJournalSurface
      ?? producingJournalSurfaceByPill[pillID]
  }

  enum DirectedProvider: String, Equatable {
    case hermes
    case openclaw
    case codex

    var displayName: String {
      switch self {
      case .hermes: return "Hermes"
      case .openclaw: return "OpenClaw"
      case .codex: return "Codex"
      }
    }

    var harnessMode: AgentHarnessMode {
      switch self {
      case .hermes: return .hermes
      case .openclaw: return .openclaw
      case .codex: return .codex
      }
    }

    var executableName: String {
      switch self {
      case .hermes: return "hermes"
      case .openclaw: return "openclaw"
      // Codex reaches Omi's ACP bridge through the `codex-acp` adapter
      // (`@zed-industries/codex-acp`); that binary is what proves the Codex
      // runtime is installed, since the OpenAI `codex` CLI has no native ACP.
      case .codex: return "codex-acp"
      }
    }

    var commandEnvironmentName: String {
      switch self {
      case .hermes: return "OMI_HERMES_ADAPTER_COMMAND"
      case .openclaw: return "OMI_OPENCLAW_ADAPTER_COMMAND"
      case .codex: return "OMI_CODEX_ADAPTER_COMMAND"
      }
    }

    var setupNeededStatus: String {
      "\(displayName) needs setup"
    }
  }

  struct Snapshot: Encodable {
    let id: String
    let title: String
    let status: String
    let latestActivity: String
    let query: String
    let createdAt: String
    let completedAt: String?
  }

  /// Spawn a visible pill projection backed by a canonical background-agent
  /// session/run in the Omi runtime.
  @discardableResult
  func spawn(
    query: String,
    model: String,
    originSurface: DesktopCoordinatorOriginSurface,
    fromVoice: Bool = false,
    preFetchedTitle: String? = nil,
    preFetchedAck: String? = nil,
    systemPromptSuffix: String? = nil,
    bridgeHarnessOverride: AgentHarnessMode? = nil,
    producerJournalIntent: AgentPillProducerJournalIntent? = nil,
    onAccepted: (@MainActor (Result<AgentPill, Error>) -> Void)? = nil
  ) -> AgentPill {
    let pillId = UUID()
    let spawnOwnerID = RuntimeOwnerIdentity.currentOwnerId() ?? ""
    let pill = AgentPill(
      id: pillId,
      query: query,
      model: model,
      bridgeHarnessOverride: bridgeHarnessOverride,
      ownerID: spawnOwnerID)
    if let preFetchedTitle, !preFetchedTitle.isEmpty {
      pill.title = preFetchedTitle
    }

    trimForNewPillIfNeeded()
    if pills.count >= maxPills {
      // Last-resort trim: drop the oldest non-active pill. Never clean up
      // the pill the user is actively viewing in the agent chat surface —
      // doing so would drop the window state to stale/blank content.
      let activeChatPillID = FloatingControlBarManager.shared.activeAgentChatPillID
      if let victimID = pills.first(where: { $0.id != activeChatPillID })?.id {
        cleanup(pillID: victimID)
      }
    }

    let surfaceRef = AgentSurfaceReference.floatingPill(pillId: pill.id)
    pills.append(pill)
    if let producerJournalIntent {
      bindProducingJournalSurface(pillID: pill.id, surface: producerJournalIntent.surface)
    }

    pill.status = .starting
    if let preFetchedAck, !preFetchedAck.isEmpty {
      pill.latestActivity = preFetchedAck
    } else {
      pill.latestActivity = "Starting…"
    }
    AgentRuntimeStatusStore.shared.beginRequest(surface: surfaceRef, statusText: pill.latestActivity)

    // If the router already returned a title we don't need a second
    // Haiku call for title generation. Otherwise kick one off in the
    // background to upgrade the heuristic title.
    if preFetchedTitle == nil {
      Task { [weak pill] in
        guard let pill else { return }
        guard let result = await AgentPillsManager.generateTitleAndAck(for: pill.query) else { return }
        await MainActor.run {
          guard RuntimeOwnerIdentity.currentOwnerId() == pill.ownerID else { return }
          pill.title = result.title
          if pill.latestActivity == "Warming up…" || pill.latestActivity == "Starting…" {
            pill.latestActivity = result.ack
          }
        }
      }
    }

    let workingDirectory = FloatingControlBarManager.shared.sharedFloatingProvider?.workingDirectory
    let modelForSpawn =
      bridgeHarnessOverride == nil
      ? (FloatingControlBarManager.shared.sharedFloatingProvider?.modelOverride ?? pill.model)
      : nil
    let generation = nextRunAttemptGeneration(for: pill.id)
    let runTask = Task { @MainActor [weak self, weak pill, onAccepted] in
      guard !Task.isCancelled else {
        onAccepted?(.failure(CancellationError()))
        return
      }
      guard let self, let pill else {
        onAccepted?(.failure(CancellationError()))
        return
      }
      do {
        let producerJournal = producerJournalIntent.map {
          DesktopCoordinatorProducerJournalDescriptor(
            surface: $0.surface,
            continuityKey: "floating_spawn:\(pill.id.uuidString)",
            pillId: pill.id,
            userText: $0.userText,
            assistantText: $0.assistantText,
            objective: pill.query,
            title: pill.title
          )
        }
        let ownerBoundReceipt = try await Self.performOwnerBoundSpawn(
          ownerID: spawnOwnerID
        ) {
          try await DesktopCoordinatorService.shared.spawnAgent(
            objective: pill.query,
            title: pill.title,
            pillId: pill.id,
            originSurface: originSurface,
            provider: bridgeHarnessOverride?.rawValue,
            parentRunId: nil,
            visible: true,
            model: modelForSpawn,
            harnessMode: bridgeHarnessOverride,
            cwd: workingDirectory,
            producerJournal: producerJournal
          )
        }
        let accepted: DesktopCoordinatorSpawnedAgent
        switch ownerBoundReceipt {
        case .accepted(let receipt):
          accepted = receipt
        case .staleReceipt(let receipt):
          Task {
            _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(
              runId: receipt.runId)
          }
          self.removeRenderedProjection(pillID: pill.id)
          onAccepted?(.failure(AuthError.userChangedDuringRequest))
          return
        case .rejectedBeforeDispatch:
          // Keep a user-initiated spawn visible instead of vanishing.
          self.fail(
            pill: pill,
            errorText: AgentFailureTranscriptFormatter.userFacingFailure(
              for: AuthError.userChangedDuringRequest,
              harnessMode: bridgeHarnessOverride ?? pill.providerIdentity))
          onAccepted?(.failure(AuthError.userChangedDuringRequest))
          return
        }
        if Task.isCancelled || !self.isCurrentRunAttempt(pillID: pill.id, generation: generation)
          || !self.pills.contains(where: { $0.id == pill.id }) || pill.status.isFinished
        {
          Task {
            _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: accepted.runId)
          }
          onAccepted?(.failure(CancellationError()))
          return
        }
        pill.canonicalSessionId = accepted.sessionId
        self.updateCanonicalRun(
          for: pill,
          runId: accepted.runId,
          attemptId: accepted.attemptId,
          preservingAttemptForSameRun: false
        )
        pill.title = accepted.title
        pill.status = .running
        pill.completedAt = nil
        pill.suggestedFollowUps = []
        pill.latestActivity = "Working…"
        Self.ensureStreamingAssistantMessage(for: pill)
        pill.markContentChanged()
        AgentRuntimeStatusStore.shared.recordAcceptedRun(
          surface: surfaceRef,
          sessionId: accepted.sessionId,
          runId: accepted.runId,
          attemptId: accepted.attemptId,
          statusText: "Working…"
        )
        self.ensureCanonicalReconciliation()
        if fromVoice {
          if let acknowledgement = producerJournalIntent?.assistantText,
            !acknowledgement.isEmpty
          {
            FloatingBarVoicePlaybackService.shared.speakOneShot(acknowledgement)
          } else {
            FloatingBarVoicePlaybackService.shared.speakBackgroundAgentKickoff()
          }
        }
        onAccepted?(.success(pill))
        let queuedFollowUps = self.pendingFollowUpsByPill.removeValue(forKey: pill.id) ?? []
        if !queuedFollowUps.isEmpty {
          self.continueAgent(
            from: pill,
            text: queuedFollowUps.map(\.text).joined(separator: "\n\n"),
            attachments: queuedFollowUps.flatMap(\.attachments)
          )
          return
        }
        await self.pollCanonicalRun(for: pill, generation: generation)
      } catch {
        onAccepted?(.failure(error))
        guard !Task.isCancelled,
          RuntimeOwnerIdentity.currentOwnerId() == spawnOwnerID,
          self.isCurrentRunAttempt(pillID: pill.id, generation: generation)
        else { return }
        AgentRuntimeStatusStore.shared.recordLocalFailure(
          surface: surfaceRef,
          error: AgentFailureTranscriptFormatter.userFacingFailure(
            for: error,
            harnessMode: bridgeHarnessOverride ?? pill.providerIdentity)
        )
        self.fail(
          pill: pill,
          errorText: AgentFailureTranscriptFormatter.userFacingFailure(
            for: error,
            harnessMode: bridgeHarnessOverride ?? pill.providerIdentity))
      }
    }
    runTasksByPill[pill.id] = runTask

    return pill
  }

  /// Send a follow-up to the same canonical background-agent session.
  func continueAgent(
    from pill: AgentPill,
    text: String,
    attachments: [ChatAttachment] = [],
    completion: (@MainActor (VoiceNonHubCompletionOutcome) -> Void)? = nil
  ) {
    // The floating agent runs locally with disk access, so attachments are
    // handed off by local_path in the prompt (see attachmentContextPrompt) —
    // no upload round-trip needed. The visible bubble still renders the files
    // through the shared ChatResource card UI.
    let prompt: String
    if let context = ChatProvider.attachmentContextPrompt(for: attachments) {
      prompt = text.isEmpty ? context : "\(text)\n\n\(context)"
    } else {
      prompt = text
    }
    guard let sessionId = pill.canonicalSessionId else {
      pendingFollowUpsByPill[pill.id, default: []].append(PendingAgentFollowUp(text: text, attachments: attachments))
      pill.latestActivity = "Queued follow-up until the agent starts…"
      pill.markContentChanged()
      completion?(.providerFailed)
      return
    }
    pill.status = .running
    pill.completedAt = nil
    pill.suggestedFollowUps = []
    pill.latestActivity = "Interrupting current run…"
    pill.conversationMessages.append(
      ChatMessage(text: text, sender: .user, resources: attachments.map(ChatResource.attachment))
    )
    Self.ensureStreamingAssistantMessage(for: pill)
    pill.markContentChanged()
    let workingDirectory = FloatingControlBarManager.shared.sharedFloatingProvider?.workingDirectory
    let activeRunId = pill.canonicalRunId
    runTasksByPill[pill.id]?.cancel()
    let generation = nextRunAttemptGeneration(for: pill.id)
    let runTask = Task { @MainActor [weak self, weak pill] in
      guard let self, let pill else { return }
      guard !Task.isCancelled else { return }
      do {
        if let activeRunId, !activeRunId.isEmpty, !pill.status.isFinished {
          switch await self.cancelActiveRunBeforeFollowUp(runId: activeRunId, pill: pill, generation: generation) {
          case .stopped:
            break
          case .cancelled:
            completion?(.providerFailed)
            return
          case .failed:
            pendingFollowUpsByPill[pill.id, default: []].append(
              PendingAgentFollowUp(text: text, attachments: attachments))
            pill.latestActivity = "Queued follow-up until the current run stops…"
            pill.markContentChanged()
            await self.pollCanonicalRun(for: pill, generation: generation)
            guard self.pills.contains(where: { $0.id == pill.id }) else { return }
            let queuedFollowUps = self.pendingFollowUpsByPill.removeValue(forKey: pill.id) ?? []
            if !queuedFollowUps.isEmpty {
              self.continueAgent(
                from: pill,
                text: queuedFollowUps.map(\.text).joined(separator: "\n\n"),
                attachments: queuedFollowUps.flatMap(\.attachments)
              )
            }
            completion?(.providerFailed)
            return
          }
          guard !Task.isCancelled else { return }
          guard self.pills.contains(where: { $0.id == pill.id }) else { return }
        }
        pill.latestActivity = "Working on your follow-up…"
        Self.ensureStreamingAssistantMessage(for: pill)
        pill.markContentChanged()
        let result = try await DesktopCoordinatorService.shared.continueAgent(
          sessionId: sessionId,
          prompt: prompt,
          originSurface: .floatingBar,
          model: pill.bridgeHarnessOverride == nil ? pill.model : nil,
          cwd: workingDirectory
        )
        guard !Task.isCancelled, self.isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
        guard pill.canonicalSessionId == sessionId else { return }
        self.updateCanonicalRun(
          for: pill,
          runId: result.runId ?? pill.canonicalRunId,
          attemptId: result.attemptId,
          preservingAttemptForSameRun: true
        )
        self.apply(
          inspection: result, to: pill, expectedRunId: pill.canonicalRunId, expectedAttemptId: pill.canonicalAttemptId)
        if !pill.status.isFinished {
          await self.pollCanonicalRun(for: pill, generation: generation)
        }
        let journalAccepted = await self.persistTerminalProjection(for: pill)
        completion?(journalAccepted ? .journalAccepted : .journalFailed)
      } catch {
        guard !Task.isCancelled, self.isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
        self.fail(pill: pill, errorText: error.localizedDescription)
        completion?(.providerFailed)
      }
    }
    runTasksByPill[pill.id] = runTask
  }

  private func terminalJournalMaterializationDecision(
    for pill: AgentPill
  ) -> AgentPillTerminalJournalMaterializationDecision {
    let canonicalDetail = terminalCanonicalDetailsByPill[pill.id]
    return AgentPillTerminalJournalMaterializationPolicy.decision(
      status: pill.status,
      canonicalRunID: pill.canonicalRunId,
      canonicalDetailRunID: canonicalDetail?.runID,
      canonicalDetailOutput: canonicalDetail?.finalText
    )
  }

  private func persistTerminalProjection(for pill: AgentPill) async -> Bool {
    guard pill.status.isFinished, pill.producingJournalSurface != nil else { return false }
    let expectedRunID = pill.canonicalRunId
    let message = pill.conversationMessages.last(where: { $0.sender == .ai && !$0.isStreaming })
    let resources = message?.displayResources ?? []
    let status: String
    let output: String
    switch terminalJournalMaterializationDecision(for: pill) {
    case .materialize(let resolvedStatus, let resolvedOutput):
      status = resolvedStatus
      output = resolvedOutput
    case .awaitingCanonicalDetail, .unavailable:
      return false
    }
    let accepted = await FloatingControlBarManager.shared.recordPillTerminalCompletion(
      ownerID: pill.ownerID,
      pillID: pill.id,
      producingSurface: pill.producingJournalSurface,
      runId: pill.canonicalRunId,
      userText: pill.query,
      title: pill.title,
      assistantText: output,
      status: status,
      resources: resources
    )
    guard accepted,
      pill.canonicalRunId == expectedRunID,
      pills.contains(where: { $0.id == pill.id })
    else { return false }
    terminalJournalMaterializedPillIDs.insert(pill.id)
    terminalJournalMaterializationFailedPillIDs.remove(pill.id)
    return true
  }

  private func ensureTerminalJournalMaterialization(for pill: AgentPill) {
    guard pill.status.isFinished,
      pill.producingJournalSurface != nil,
      !terminalJournalMaterializedPillIDs.contains(pill.id),
      !terminalJournalMaterializationFailedPillIDs.contains(pill.id),
      terminalJournalMaterializationTasks[pill.id] == nil
    else { return }
    switch terminalJournalMaterializationDecision(for: pill) {
    case .awaitingCanonicalDetail:
      // `mergeProjectedPills` has already started the one canonical
      // poll that owns this successful run's final output.
      return
    case .unavailable:
      terminalJournalMaterializationFailedPillIDs.insert(pill.id)
      log("AgentPills: terminal journal materialization unavailable; retaining canonical terminal pill")
      return
    case .materialize:
      break
    }
    let pillID = pill.id
    let runID = pill.canonicalRunId
    let generation = (terminalJournalMaterializationGenerationByPill[pillID] ?? 0) + 1
    terminalJournalMaterializationGenerationByPill[pillID] = generation
    terminalJournalMaterializationTasks[pillID] = Task { @MainActor [weak self, weak pill] in
      defer {
        if let self,
          self.terminalJournalMaterializationGenerationByPill[pillID] == generation
        {
          self.terminalJournalMaterializationTasks[pillID] = nil
          self.terminalJournalMaterializationGenerationByPill[pillID] = nil
        }
      }
      guard let self, let pill,
        pill.canonicalRunId == runID,
        self.pills.contains(where: { $0.id == pillID })
      else { return }
      let materialized = await self.persistTerminalProjection(for: pill)
      guard pill.canonicalRunId == runID,
        self.pills.contains(where: { $0.id == pillID })
      else { return }
      if !materialized {
        // The shared kernel helper has already retried the lookup. This
        // can only be an unrecoverable historical producer mismatch for
        // this stable run; keeping the canonical done pill is safer than
        // repeatedly spending direct-control capacity forever.
        self.terminalJournalMaterializationFailedPillIDs.insert(pillID)
        log("AgentPills: terminal journal materialization unavailable; retaining canonical terminal pill")
      }
    }
  }

  private enum ActiveRunCancellationResult {
    case stopped
    case cancelled
    case failed
  }

  private func nextRunAttemptGeneration(for pillID: UUID) -> Int {
    let next = (runAttemptGenerationByPill[pillID] ?? 0) + 1
    runAttemptGenerationByPill[pillID] = next
    return next
  }

  private func isCurrentRunAttempt(pillID: UUID, generation: Int) -> Bool {
    runAttemptGenerationByPill[pillID] == generation
  }

  private func updateCanonicalRun(
    for pill: AgentPill,
    runId nextRunId: String?,
    attemptId nextAttemptId: String?,
    preservingAttemptForSameRun: Bool
  ) {
    let previousRunId = pill.canonicalRunId
    pill.canonicalRunId = nextRunId
    if nextRunId != previousRunId {
      terminalJournalMaterializationTasks[pill.id]?.cancel()
      terminalJournalMaterializationTasks[pill.id] = nil
      terminalJournalMaterializedPillIDs.remove(pill.id)
      terminalCanonicalDetailsByPill[pill.id] = nil
      terminalJournalMaterializationFailedPillIDs.remove(pill.id)
      pill.canonicalAttemptId = nextAttemptId
    } else if preservingAttemptForSameRun {
      pill.canonicalAttemptId = nextAttemptId ?? pill.canonicalAttemptId
    } else {
      pill.canonicalAttemptId = nextAttemptId
    }
  }

  private func cancelActiveRunBeforeFollowUp(runId: String, pill: AgentPill, generation: Int) async
    -> ActiveRunCancellationResult
  {
    do {
      _ = try await DesktopCoordinatorService.shared.cancelAgentRun(runId: runId, reason: "Interrupted by follow-up")
    } catch {
      logError("AgentPills: failed to cancel active run before follow-up", error: error)
      return .failed
    }
    for _ in 0..<20 {
      if Task.isCancelled { return .cancelled }
      guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return .cancelled }
      guard pill.canonicalRunId == runId else { return .cancelled }
      do {
        let inspection = try await DesktopCoordinatorService.shared.inspectAgentRun(runId: runId)
        let status = inspection.status
        if ["succeeded", "completed", "failed", "timed_out", "orphaned", "cancelled"].contains(status) {
          return .stopped
        }
        pill.latestActivity = status == "cancelling" ? "Stopping current run…" : "Waiting for current run to stop…"
        pill.markContentChanged()
      } catch {
        logError("AgentPills: failed to inspect active run before follow-up", error: error)
        return .failed
      }
      try? await Task.sleep(nanoseconds: 250_000_000)
    }
    return .failed
  }

  /// Force-dismiss a pill.
  func dismiss(pillID: UUID) {
    // If the pill being dismissed is the one currently shown in the Ask Omi
    // surface, leave the agent surface first so conversationSurface does
    // not stay as .agent(id) pointing to a removed pill — which would leave
    // the view falling through to blank/stale Omi content. (Codex P2.)
    if FloatingControlBarManager.shared.activeAgentChatPillID == pillID {
      FloatingControlBarManager.shared.leaveActiveAgentSurfaceFromPillDismiss()
    }
    cleanup(pillID: pillID)
  }

  func stop(pillID: UUID) {
    guard let pill = pills.first(where: { $0.id == pillID }), !pill.status.isFinished else { return }
    log("AgentPills: stopping pill \(pill.title)")
    let runId = pill.canonicalRunId
    runTasksByPill[pillID]?.cancel()
    runTasksByPill[pillID] = nil
    pill.status = .stopped
    pill.latestActivity = "Stopped by user"
    pill.completedAt = Date()
    Self.clearStreamingAssistantMessage(for: pill)
    pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
    pill.markContentChanged()
    if pill.viewedAt != nil {
      scheduleViewedExpiration(for: pill)
    }
    AgentRuntimeStatusStore.shared.recordLocalCancellation(
      surface: .floatingPill(pillId: pillID),
      message: "Stopped by user"
    )
    ensureTerminalJournalMaterialization(for: pill)
    if let runId, !runId.isEmpty {
      Task {
        _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: runId)
      }
    }
  }

  func markViewed(pillID: UUID) {
    guard let pill = pills.first(where: { $0.id == pillID }) else { return }
    pill.viewedAt = Date()
    scheduleViewedExpiration(for: pill)
    expireViewedFinishedPills(now: Date())
  }

  private func scheduleViewedExpiration(for pill: AgentPill) {
    viewedExpirationWorkItemsByPill[pill.id]?.cancel()
    guard pill.status.isFinished else { return }

    let pillID = pill.id
    let workItem = DispatchWorkItem { [weak self] in
      Task { @MainActor [weak self] in
        guard let self else { return }
        // If the pill is the one the user is actively viewing when the
        // timer fires, the expiration is skipped this round but the
        // timer must be re-armed — otherwise the one-shot DispatchWorkItem
        // is consumed and auto-expiration is permanently disabled for a
        // viewed finished pill even after the user navigates away.
        if FloatingControlBarManager.shared.activeAgentChatPillID == pillID {
          if let pill = self.pills.first(where: { $0.id == pillID }) {
            self.scheduleViewedExpiration(for: pill)
          }
          return
        }
        self.expireViewedFinishedPills(now: Date())
        self.viewedExpirationWorkItemsByPill[pillID] = nil
      }
    }
    viewedExpirationWorkItemsByPill[pillID] = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + viewedFinishedTTL, execute: workItem)
  }

  private func expireViewedFinishedPills(now: Date = Date()) {
    let activeChatPillID = FloatingControlBarManager.shared.activeAgentChatPillID
    let expiredIDs =
      pills
      .filter { pill in
        guard pill.status.isFinished, let viewedAt = pill.viewedAt else { return false }
        // Never expire the pill the user is actively viewing in the
        // floating bar's agent chat — otherwise the active chat
        // disappears/reverts while they are still reading it.
        guard pill.id != activeChatPillID else { return false }
        return now.timeIntervalSince(viewedAt) >= viewedFinishedTTL
      }
      .map(\.id)
    for id in expiredIDs {
      cleanup(pillID: id)
    }
  }

  private func trimForNewPillIfNeeded() {
    expireViewedFinishedPills()
    guard pills.count >= maxPills else { return }

    let activeChatPillID = FloatingControlBarManager.shared.activeAgentChatPillID

    if let oldestDoneID =
      pills
      .filter({ $0.status == .done && $0.id != activeChatPillID })
      .sorted(by: { ($0.completedAt ?? $0.createdAt) < ($1.completedAt ?? $1.createdAt) })
      .first?.id
    {
      cleanup(pillID: oldestDoneID)
      return
    }

    if let oldestFinishedID =
      pills
      .filter({ $0.status.isFinished && $0.id != activeChatPillID })
      .sorted(by: { ($0.completedAt ?? $0.createdAt) < ($1.completedAt ?? $1.createdAt) })
      .first?.id
    {
      cleanup(pillID: oldestFinishedID)
    }
  }

  @discardableResult
  func dismiss(pillIdString: String) -> Bool {
    guard let id = findPillId(from: pillIdString) else { return false }
    guard let pill = pills.first(where: { $0.id == id }) else { return false }
    if let runId = pill.canonicalRunId, !runId.isEmpty {
      Task {
        try? await DesktopCoordinatorService.shared.dismissFloatingRunAttention(runId: runId)
        await refreshProjectedPillsFromKernel()
      }
    }
    dismiss(pillID: id)
    return true
  }

  func replaceWithAutomationPills(count requestedCount: Int) -> [AgentPill] {
    let ids = pills.map(\.id)
    for id in ids {
      cleanup(pillID: id)
    }

    let count = min(max(requestedCount, 1), maxPills)
    let seeded = (0..<count).map { index -> AgentPill in
      let pill = AgentPill(query: "Automation subagent \(index + 1)", model: ModelQoS.Claude.defaultSelection)
      pill.title = index == 0 ? "SLEEP FOR 5" : "Sleep Subagent"
      if index == 0 {
        let aiMessage = ChatMessage(text: "Automation output for subagent \(index + 1).", sender: .ai)
        pill.status = .done
        pill.latestActivity = "Done — automation output."
        pill.aiMessage = aiMessage
        pill.conversationMessages = [
          ChatMessage(text: pill.query, sender: .user),
          aiMessage,
        ]
        pill.completedAt = Date()
      } else {
        pill.status = .running
        pill.latestActivity = "Working…"
        Self.ensureStreamingAssistantMessage(for: pill)
        pill.completedAt = nil
      }
      pill.markContentChanged()
      return pill
    }
    pills = seeded
    return seeded
  }

  private func cleanup(pillID: UUID) {
    let pill = pills.first(where: { $0.id == pillID })
    let shouldCancelRun = pill?.status.isFinished == false
    let runId = pill?.canonicalRunId
    runTasksByPill[pillID]?.cancel()
    runTasksByPill[pillID] = nil
    terminalJournalMaterializationTasks[pillID]?.cancel()
    terminalJournalMaterializationTasks[pillID] = nil
    terminalJournalMaterializedPillIDs.remove(pillID)
    terminalCanonicalDetailsByPill[pillID] = nil
    terminalJournalMaterializationFailedPillIDs.remove(pillID)
    runAttemptGenerationByPill[pillID] = nil
    viewedExpirationWorkItemsByPill[pillID]?.cancel()
    viewedExpirationWorkItemsByPill[pillID] = nil
    pendingFollowUpsByPill[pillID] = nil
    producingJournalSurfaceByPill[pillID] = nil
    pills.removeAll { $0.id == pillID }
    if shouldCancelRun, let runId, !runId.isEmpty {
      Task {
        _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: runId)
      }
    }
  }

  private func removeRenderedProjection(pillID: UUID) {
    runTasksByPill[pillID]?.cancel()
    runTasksByPill[pillID] = nil
    terminalJournalMaterializationTasks[pillID]?.cancel()
    terminalJournalMaterializationTasks[pillID] = nil
    terminalJournalMaterializedPillIDs.remove(pillID)
    terminalCanonicalDetailsByPill[pillID] = nil
    terminalJournalMaterializationFailedPillIDs.remove(pillID)
    runAttemptGenerationByPill[pillID] = nil
    viewedExpirationWorkItemsByPill[pillID]?.cancel()
    viewedExpirationWorkItemsByPill[pillID] = nil
    pendingFollowUpsByPill[pillID] = nil
    producingJournalSurfaceByPill[pillID] = nil
    pills.removeAll { $0.id == pillID }
  }

  /// Remove all completed (done or failed) pills.
  func clearCompleted() {
    let ids = pills.filter { $0.status.isFinished }.map(\.id)
    for id in ids {
      cleanup(pillID: id)
    }
  }

  private func isFinished(_ status: AgentPill.Status) -> Bool {
    status.isFinished
  }

  func snapshots(limit: Int = 20) -> [Snapshot] {
    let ownerID = RuntimeOwnerIdentity.currentOwnerId()
    let formatter = ISO8601DateFormatter()
    return
      pills
      .filter { $0.ownerID == ownerID }
      .sorted { $0.createdAt > $1.createdAt }
      .prefix(limit)
      .map { pill in
        Snapshot(
          id: pill.id.uuidString,
          title: pill.title,
          status: pill.status.machineLabel,
          latestActivity: pill.latestActivity,
          query: pill.query,
          createdAt: formatter.string(from: pill.createdAt),
          completedAt: pill.completedAt.map { formatter.string(from: $0) }
        )
      }
  }

  @discardableResult
  func refreshProjectedPillsFromKernel() async -> Bool {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return false }
    do {
      let floating = try await DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)
      guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
      mergeProjectedPills(from: floating)
      return true
    } catch {
      guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
      logError("AgentPills: failed to refresh projected pills from kernel", error: error)
      applyRuntimeProjections()
      return false
    }
  }

  /// Resolve an agent identity for timeline open-by-id.
  /// Fast path: in-memory pill. Then refresh floating projections once.
  /// Then hydrate via session/run/externalRef from DesktopCoordinatorService.
  @discardableResult
  func resolveAndPresentAgent(
    pillId: UUID?,
    sessionId: String?,
    runId: String?
  ) async -> Bool {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return false }
    let preference = AgentTimelineHydratePreference.make(
      pillId: pillId,
      sessionId: sessionId,
      runId: runId
    )
    guard !preference.keys.isEmpty else {
      log("AgentPills: resolveAndPresentAgent called with empty identity")
      return false
    }

    if findPill(matching: preference) != nil {
      return true
    }

    await refreshProjectedPillsFromKernel()
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
    if findPill(matching: preference) != nil {
      return true
    }

    let hydrated = await hydratePillFromKernel(preference: preference, ownerID: ownerID)
    if hydrated {
      return findPill(matching: preference) != nil
    }

    log(
      "AgentPills: resolveAndPresentAgent failed after refresh+hydrate "
        + "pillId=\(pillId?.uuidString ?? "nil") "
        + "sessionId=\(sessionId ?? "nil") "
        + "runId=\(runId ?? "nil")"
    )
    return false
  }

  /// Package-visible for hermetic preference-matching tests.
  func findPill(matching preference: AgentTimelineHydratePreference) -> AgentPill? {
    let ownerID = RuntimeOwnerIdentity.currentOwnerId()
    let ownedPills = pills.filter { $0.ownerID == ownerID }
    guard
      let matched = preference.firstMatchingKey(
        runIdMatches: { runId in ownedPills.contains(where: { $0.canonicalRunId == runId }) },
        sessionIdMatches: { sessionId in ownedPills.contains(where: { $0.canonicalSessionId == sessionId }) },
        pillIdMatches: { pillId in ownedPills.contains(where: { $0.id == pillId }) }
      )
    else {
      return nil
    }
    switch matched {
    case .runId(let runId):
      return ownedPills.first(where: { $0.canonicalRunId == runId })
    case .sessionId(let sessionId):
      return ownedPills.first(where: { $0.canonicalSessionId == sessionId })
    case .pillId(let pillId):
      return ownedPills.first(where: { $0.id == pillId })
    }
  }

  /// Test hook: replace in-memory pills without kernel I/O.
  func replacePillsForTesting(_ next: [AgentPill]) {
    pills = next
    terminalJournalMaterializedPillIDs.removeAll()
    terminalCanonicalDetailsByPill.removeAll()
    terminalJournalMaterializationFailedPillIDs.removeAll()
    objectWillChange.send()
  }

  private func hydratePillFromKernel(
    preference: AgentTimelineHydratePreference,
    ownerID: String
  ) async -> Bool {
    do {
      for key in preference.keys {
        guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
        switch key {
        case .runId(let runId):
          let inspection = try await DesktopCoordinatorService.shared.inspectAgentRun(runId: runId)
          guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
          if upsertHydratedPill(
            pillId: preference.keys.compactMap { key -> UUID? in
              if case .pillId(let id) = key { return id }
              return nil
            }.first,
            sessionId: inspection.sessionId,
            runId: inspection.runId ?? runId,
            attemptId: inspection.attemptId,
            title: nil,
            query: nil,
            provider: inspection.provider
          ) {
            return true
          }
        case .sessionId(let sessionId):
          let snapshot = await DesktopCoordinatorService.shared.awarenessSnapshot()
          guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
          if let session = snapshot.sessions.first(where: { $0.sessionId == sessionId }) {
            let resolvedPillId =
              (session.externalRefKind == "pill"
                ? session.externalRefId.flatMap(UUID.init(uuidString:))
                : nil)
              ?? preference.keys.compactMap { key -> UUID? in
                if case .pillId(let id) = key { return id }
                return nil
              }.first
            if upsertHydratedPill(
              pillId: resolvedPillId,
              sessionId: session.sessionId ?? sessionId,
              runId: session.runId,
              attemptId: session.attemptId,
              title: session.title,
              query: nil,
              provider: session.provider
            ) {
              return true
            }
          }
          let floating = try await DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)
          guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
          if let entry = floating.first(where: {
            canonicalString($0["sessionId"]) == sessionId
          }) {
            mergeProjectedPills(from: [entry])
            return findPill(matching: preference) != nil
          }
        case .pillId(let pillId):
          let floating = try await DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)
          guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
          if let entry = floating.first(where: { canonicalPillId(from: $0) == pillId }) {
            mergeProjectedPills(from: [entry])
            return findPill(matching: preference) != nil
          }
          let snapshot = await DesktopCoordinatorService.shared.awarenessSnapshot()
          guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return false }
          if let session = snapshot.sessions.first(where: {
            $0.externalRefKind == "pill" && $0.externalRefId == pillId.uuidString
          }) {
            if upsertHydratedPill(
              pillId: pillId,
              sessionId: session.sessionId,
              runId: session.runId,
              attemptId: session.attemptId,
              title: session.title,
              query: nil,
              provider: session.provider
            ) {
              return true
            }
          }
        }
      }
    } catch {
      logError("AgentPills: kernel hydrate failed", error: error)
    }
    return false
  }

  @discardableResult
  private func upsertHydratedPill(
    pillId: UUID?,
    sessionId: String?,
    runId: String?,
    attemptId: String?,
    title: String?,
    query: String?,
    provider: String?
  ) -> Bool {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return false }
    let trimmedSession = sessionId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let trimmedRun = runId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    guard !trimmedSession.isEmpty || !trimmedRun.isEmpty || pillId != nil else {
      return false
    }
    let id = pillId ?? UUID()
    let model =
      ShortcutSettings.shared.selectedModel.isEmpty
      ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
    let pill: AgentPill
    if let existing = pills.first(where: { $0.id == id && $0.ownerID == ownerID }) {
      pill = existing
    } else if let existing = pills.first(where: {
      $0.ownerID == ownerID
        && ((!trimmedRun.isEmpty && $0.canonicalRunId == trimmedRun)
          || (!trimmedSession.isEmpty && $0.canonicalSessionId == trimmedSession))
    }) {
      pill = existing
    } else {
      pill = AgentPill(
        id: id,
        query: (query?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false)
          ? query! : "Background agent",
        model: model,
        ownerID: ownerID
      )
      pills.append(pill)
    }
    pill.producingJournalSurface = producingJournalSurfaceByPill[pill.id]
    if let title, !title.isEmpty {
      pill.title = title
    } else if pill.title.isEmpty {
      pill.title = "Background agent"
    }
    if !trimmedSession.isEmpty {
      pill.canonicalSessionId = trimmedSession
    }
    if !trimmedRun.isEmpty {
      updateCanonicalRun(
        for: pill,
        runId: trimmedRun,
        attemptId: attemptId,
        preservingAttemptForSameRun: true
      )
    } else if let attemptId, !attemptId.isEmpty {
      pill.canonicalAttemptId = attemptId
    }
    pill.applyCanonicalProviderIdentity(provider)
    Self.ensureStreamingAssistantMessage(for: pill)
    pill.markContentChanged()
    objectWillChange.send()
    return true
  }

  @MainActor
  func upsertSpawnedPill(
    id: UUID,
    query: String,
    title: String,
    sessionId: String,
    runId: String,
    attemptId: String?,
    provider: String? = nil,
    producingJournalSurface: AgentSurfaceReference? = nil
  ) {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    let model =
      ShortcutSettings.shared.selectedModel.isEmpty
      ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
    let pill: AgentPill
    if let existing = pills.first(where: { $0.id == id && $0.ownerID == ownerID }) {
      pill = existing
    } else {
      pill = AgentPill(
        id: id,
        query: query.isEmpty ? "Background agent" : query,
        model: model,
        ownerID: ownerID)
      pills.append(pill)
    }
    pill.title = title.isEmpty ? "Background agent" : title
    pill.canonicalSessionId = sessionId
    updateCanonicalRun(
      for: pill,
      runId: runId,
      attemptId: attemptId,
      preservingAttemptForSameRun: false
    )
    pill.applyCanonicalProviderIdentity(provider)
    if let producingJournalSurface {
      bindProducingJournalSurface(pillID: pill.id, surface: producingJournalSurface)
    }
    // A delayed duplicate spawn receipt must not turn a terminal pill back
    // into a running row after the completion was already projected.
    guard !pill.status.isFinished else { return }
    pill.status = .running
    pill.completedAt = nil
    pill.latestActivity = "Working…"
    Self.ensureStreamingAssistantMessage(for: pill)
    pill.markContentChanged()
    AgentRuntimeStatusStore.shared.recordAcceptedRun(
      surface: .floatingPill(pillId: pill.id),
      sessionId: sessionId,
      runId: runId,
      attemptId: attemptId,
      statusText: "Working…"
    )
    ensureCanonicalReconciliation()
    startCanonicalRunPolling(for: pill)
    objectWillChange.send()
  }

  private func startCanonicalRunPolling(for pill: AgentPill) {
    runTasksByPill[pill.id]?.cancel()
    let generation = nextRunAttemptGeneration(for: pill.id)
    runTasksByPill[pill.id] = Task { @MainActor [weak self, weak pill] in
      guard let self, let pill else { return }
      await self.pollCanonicalRun(for: pill, generation: generation)
    }
  }

  private func mergeProjectedPills(from floating: [[String: Any]]) {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    var seen = Set<UUID>()
    var missingPillIDCount = 0
    var missingSessionIDCount = 0
    var missingRunIDCount = 0
    for entry in floating {
      guard let pillId = canonicalPillId(from: entry) else {
        missingPillIDCount += 1
        continue
      }
      guard let sessionId = canonicalString(entry["sessionId"]) else {
        missingSessionIDCount += 1
        continue
      }
      guard let runId = canonicalString(entry["runId"]) else {
        missingRunIDCount += 1
        continue
      }
      seen.insert(pillId)
      let query = (entry["query"] as? String) ?? (entry["latestActivity"] as? String) ?? ""
      let model =
        ShortcutSettings.shared.selectedModel.isEmpty
        ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
      let pill: AgentPill
      if let existing = pills.first(where: { $0.id == pillId && $0.ownerID == ownerID }) {
        pill = existing
      } else {
        pill = AgentPill(
          id: pillId,
          query: query.isEmpty ? "Background agent" : query,
          model: model,
          ownerID: ownerID)
        pills.append(pill)
      }
      pill.producingJournalSurface = producingJournalSurfaceByPill[pill.id]
      if let title = entry["title"] as? String, !title.isEmpty {
        pill.title = title
      }
      pill.canonicalSessionId = sessionId
      updateCanonicalRun(
        for: pill,
        runId: runId,
        attemptId: canonicalString(entry["attemptId"]),
        preservingAttemptForSameRun: false
      )
      pill.applyCanonicalProviderIdentity(canonicalString(entry["provider"]))
      let projectedStatus = (entry["status"] as? String) ?? "running"
      applyProjectedStatus(projectedStatus, to: pill)
      if let activity = entry["latestActivity"] as? String, !activity.isEmpty {
        pill.latestActivity = activity
      }
      reconcileProjectedPillRun(entryStatus: projectedStatus, pill: pill)
      ensureTerminalJournalMaterialization(for: pill)
      pill.markContentChanged()
    }
    if !floating.isEmpty {
      log(
        "AgentPills: canonical projection source=\(floating.count) accepted=\(seen.count) "
          + "missing_pill_id=\(missingPillIDCount) missing_session_id=\(missingSessionIDCount) "
          + "missing_run_id=\(missingRunIDCount)"
      )
    }
    let removable = pills.filter { pill in
      Self.shouldRemoveRenderedProjection(
        status: pill.status,
        isPolling: runTasksByPill[pill.id] != nil,
        isSeenInRuntimeSnapshot: seen.contains(pill.id),
        hasLocalTransientState: hasLocalTransientState(pillID: pill.id)
      )
    }
    for pill in removable {
      removeRenderedProjection(pillID: pill.id)
    }
    objectWillChange.send()
    ensureCanonicalReconciliation()
  }

  /// Runtime session lists are intentionally an active-work snapshot and can
  /// omit a run immediately after it completes. A finished pill remains a
  /// user-visible attention item until the normal viewed/dismissed retention
  /// policy removes it; a refresh must not orphan it from the hover list.
  nonisolated static func shouldRemoveRenderedProjection(
    status: AgentPill.Status,
    isPolling: Bool,
    isSeenInRuntimeSnapshot: Bool,
    hasLocalTransientState: Bool
  ) -> Bool {
    guard !isPolling, !status.isFinished else { return false }
    return !isSeenInRuntimeSnapshot && !hasLocalTransientState
  }

  private func applyRuntimeProjections() {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    for pill in pills where pill.ownerID == ownerID {
      if let projection = AgentRuntimeStatusStore.shared.floatingPillProjection(pillId: pill.id) {
        Self.apply(projection: projection, to: pill)
      } else if let runId = pill.canonicalRunId,
        let projection = AgentRuntimeStatusStore.shared.projection(for: .floatingBarRun(runId: runId))
      {
        Self.apply(projection: projection, to: pill)
      }
    }
  }

  private func applyProjectedStatus(_ status: String, to pill: AgentPill) {
    if pill.status.isFinished && !isTerminalProjectedStatus(status) {
      return
    }
    switch status {
    case "queued":
      pill.status = .queued
    case "starting":
      pill.status = .starting
    case "running", "waiting_input", "waiting_approval", "cancelling":
      pill.status = .running
    case "succeeded", "completed":
      pill.status = .done
    case "cancelled":
      pill.status = .stopped
    case "failed", "timed_out", "orphaned":
      pill.status = .failed("Agent failed")
    default:
      break
    }
  }

  private func reconcileProjectedPillRun(entryStatus: String, pill: AgentPill) {
    guard shouldPollCanonicalRun(for: pill, projectedStatus: entryStatus) else { return }
    startCanonicalRunPolling(for: pill)
  }

  private func shouldPollCanonicalRun(for pill: AgentPill, projectedStatus: String) -> Bool {
    guard pill.canonicalRunId?.isEmpty == false else { return false }
    return AgentPillLifecycleConvergencePolicy.shouldStartCanonicalPoll(
      projectedStatusIsTerminal: isTerminalProjectedStatus(projectedStatus),
      pillStatus: pill.status,
      hasCanonicalTerminalDetail: terminalCanonicalDetailsByPill[pill.id]?.runID == pill.canonicalRunId,
      isPolling: runTasksByPill[pill.id] != nil
    )
  }

  private func isTerminalProjectedStatus(_ status: String) -> Bool {
    switch status {
    case "succeeded", "completed", "cancelled", "failed", "timed_out", "orphaned":
      return true
    default:
      return false
    }
  }

  private func canonicalPillId(from entry: [String: Any]) -> UUID? {
    guard let idString = canonicalString(entry["pillId"]) ?? canonicalString(entry["id"]) else { return nil }
    return UUID(uuidString: idString)
  }

  private func canonicalString(_ value: Any?) -> String? {
    guard let text = value as? String else { return nil }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  private func hasLocalTransientState(pillID: UUID) -> Bool {
    pendingFollowUpsByPill[pillID]?.isEmpty == false
  }

  private func hasTerminalJournalCompletion(for pill: AgentPill) -> Bool {
    let materialized = FloatingControlBarManager.shared.hasMaterializedAgentCompletion(
      pillID: pill.id,
      runID: pill.canonicalRunId
    )
    if materialized {
      terminalJournalMaterializedPillIDs.insert(pill.id)
    } else {
      terminalJournalMaterializedPillIDs.remove(pill.id)
    }
    return materialized
  }

  private func hasTerminalJournalMaterializationFailure(for pill: AgentPill) -> Bool {
    terminalJournalMaterializationFailedPillIDs.contains(pill.id)
  }

  private func needsCanonicalReconciliation() -> Bool {
    pills.contains { pill in
      AgentPillLifecycleConvergencePolicy.requiresCanonicalReconciliation(
        status: pill.status,
        requiresJournalCompletion: pill.producingJournalSurface != nil,
        hasTerminalJournalCompletion: hasTerminalJournalCompletion(for: pill),
        hasTerminalJournalMaterializationFailure: hasTerminalJournalMaterializationFailure(for: pill),
        hasPendingFollowUp: hasLocalTransientState(pillID: pill.id)
      )
    }
  }

  private func ensureCanonicalReconciliation() {
    guard canonicalReconciliationTask == nil,
      needsCanonicalReconciliation(),
      let ownerID = RuntimeOwnerIdentity.currentOwnerId()
    else { return }
    canonicalReconciliationGeneration &+= 1
    let generation = canonicalReconciliationGeneration
    canonicalReconciliationTask = Task { @MainActor [weak self] in
      defer {
        if let self, self.canonicalReconciliationGeneration == generation {
          self.canonicalReconciliationTask = nil
        }
      }
      while !Task.isCancelled {
        guard let self, RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
        await self.refreshProjectedPillsFromKernel()
        guard self.needsCanonicalReconciliation() else { return }
        try? await Task.sleep(nanoseconds: 750_000_000)
      }
    }
  }

  /// Non-production automation reads this cross-surface contract without
  /// returning prompts, completion text, or other raw agent output.
  func lifecycleConvergenceSnapshot(runIDs: Set<String>) async -> String {
    do {
      let canonical = try await DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)
      let requested = Set(runIDs.filter { !$0.isEmpty })
      let entries = canonical.compactMap { entry -> AgentPillLifecycleConvergenceEntry? in
        guard let runId = canonicalString(entry["runId"]), requested.isEmpty || requested.contains(runId) else {
          return nil
        }
        let canonicalStatus = canonicalString(entry["status"]) ?? "unknown"
        let pill = pills.first(where: { $0.canonicalRunId == runId })
        let projectedStatus = pill?.status.machineLabel
        let completionMaterialized = pill.map { hasTerminalJournalCompletion(for: $0) } ?? false
        let canonicalTerminal = isTerminalProjectedStatus(canonicalStatus)
        return AgentPillLifecycleConvergenceEntry(
          runId: runId,
          canonicalStatus: canonicalStatus,
          projectedStatus: projectedStatus,
          completionMaterialized: completionMaterialized,
          converged: !canonicalTerminal || (pill?.status.isFinished == true && completionMaterialized)
        )
      }
      let returned = Set(entries.map(\.runId))
      let snapshot = AgentPillLifecycleConvergenceSnapshot(
        entries: entries.sorted { $0.runId < $1.runId },
        missingRequestedRunIds: requested.subtracting(returned).sorted(),
        canonicalReadError: nil
      )
      return encodeLifecycleConvergenceSnapshot(snapshot)
    } catch {
      let snapshot = AgentPillLifecycleConvergenceSnapshot(
        entries: [],
        missingRequestedRunIds: runIDs.sorted(),
        canonicalReadError: error.localizedDescription
      )
      return encodeLifecycleConvergenceSnapshot(snapshot)
    }
  }

  private func encodeLifecycleConvergenceSnapshot(_ snapshot: AgentPillLifecycleConvergenceSnapshot) -> String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(snapshot), let json = String(data: data, encoding: .utf8) else {
      return #"{"entries":[],"missingRequestedRunIds":[],"canonicalReadError":"encoding_failed"}"#
    }
    return json
  }

  func snapshotJSON(limit: Int = 20) -> String {
    let payload: [String: [Snapshot]] = ["floating_agent_pills": snapshots(limit: limit)]
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    guard let data = try? encoder.encode(payload), let json = String(data: data, encoding: .utf8) else {
      return "{\"floating_agent_pills\":[]}"
    }
    return json
  }

  func statusSummary(limit: Int = 8) -> String {
    let recent = snapshots(limit: limit)
    guard !recent.isEmpty else {
      return "No floating agent pills are running or recently finished."
    }
    let lines = recent.map { snapshot in
      "- \(snapshot.title) [\(snapshot.id.prefix(8))]: \(snapshot.status); \(snapshot.latestActivity)"
    }
    return "Floating agent pills:\n" + lines.joined(separator: "\n")
  }

  private func findPillId(from text: String) -> UUID? {
    let needle = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !needle.isEmpty else { return nil }
    if let exact = UUID(uuidString: text) {
      return pills.first(where: { $0.id == exact })?.id
    }
    return pills.first { pill in
      let id = pill.id.uuidString.lowercased()
      return id == needle || id.hasPrefix(needle)
    }?.id
  }

  private func pollCanonicalRun(for pill: AgentPill, generation: Int) async {
    defer {
      if isCurrentRunAttempt(pillID: pill.id, generation: generation) {
        runTasksByPill[pill.id] = nil
      }
    }
    while !Task.isCancelled {
      guard RuntimeOwnerIdentity.currentOwnerId() == pill.ownerID else { return }
      guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
      guard pills.contains(where: { $0.id == pill.id }) else { return }
      guard let runId = pill.canonicalRunId, !runId.isEmpty else { return }
      let attemptId = pill.canonicalAttemptId
      do {
        let inspection = try await DesktopCoordinatorService.shared.inspectAgentRun(
          runId: runId
        )
        guard RuntimeOwnerIdentity.currentOwnerId() == pill.ownerID else { return }
        guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
        guard pill.canonicalRunId == runId else {
          ScreenContextToolTelemetry.trackInvariant(
            "stale_inspection_ignored",
            context: ScreenContextTelemetryContext.from(
              surfaceRef: .floatingPill(pillId: pill.id),
              runId: runId
            ),
            properties: [
              "expected_run_id": runId,
              "current_run_id": pill.canonicalRunId ?? "",
            ]
          )
          return
        }
        if let attemptId, pill.canonicalAttemptId != attemptId {
          ScreenContextToolTelemetry.trackInvariant(
            "stale_inspection_ignored",
            context: ScreenContextTelemetryContext.from(
              surfaceRef: .floatingPill(pillId: pill.id),
              runId: runId
            ),
            properties: [
              "expected_attempt_id": attemptId,
              "current_attempt_id": pill.canonicalAttemptId ?? "",
            ]
          )
          return
        }
        apply(inspection: inspection, to: pill, expectedRunId: runId, expectedAttemptId: attemptId)
        if pill.status.isFinished { return }
      } catch {
        logError("AgentPills: failed to inspect canonical run \(runId)", error: error)
      }
      try? await Task.sleep(nanoseconds: 2_000_000_000)
    }
  }

  private func apply(
    inspection: DesktopCoordinatorAgentRunInspection,
    to pill: AgentPill,
    expectedRunId: String?,
    expectedAttemptId: String?
  ) {
    if let expectedRunId, let inspectedRunId = inspection.runId, inspectedRunId != expectedRunId {
      return
    }
    if let expectedAttemptId, let inspectedAttemptId = inspection.attemptId, inspectedAttemptId != expectedAttemptId {
      return
    }
    if let expectedRunId, pill.canonicalRunId != expectedRunId {
      return
    }
    if let expectedAttemptId, pill.canonicalAttemptId != expectedAttemptId {
      return
    }
    if pill.status.isFinished && !isTerminalProjectedStatus(inspection.status) {
      return
    }
    pill.canonicalSessionId = inspection.sessionId ?? pill.canonicalSessionId
    updateCanonicalRun(
      for: pill,
      runId: inspection.runId ?? pill.canonicalRunId,
      attemptId: inspection.attemptId,
      preservingAttemptForSameRun: true
    )
    switch inspection.status {
    case "queued", "starting":
      pill.status = .starting
      pill.latestActivity = "Starting…"
      Self.ensureStreamingAssistantMessage(for: pill)
    case "running", "waiting_input", "waiting_approval", "cancelling":
      pill.status = .running
      pill.latestActivity = inspection.status == "cancelling" ? "Stopping…" : "Working…"
      Self.ensureStreamingAssistantMessage(for: pill)
    case "succeeded", "completed":
      if let canonicalRunID = pill.canonicalRunId, !canonicalRunID.isEmpty {
        terminalCanonicalDetailsByPill[pill.id] = CanonicalTerminalRunDetail(
          runID: canonicalRunID,
          finalText: inspection.finalText ?? ""
        )
      }
      finish(
        pill: pill,
        finalText: inspection.finalText,
        resources: inspection.artifacts.map(ChatResource.artifact)
      )
    case "cancelled":
      pill.status = .stopped
      pill.latestActivity = "Stopped by user"
      pill.completedAt = Date()
      Self.clearStreamingAssistantMessage(for: pill)
      pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
      ensureTerminalJournalMaterialization(for: pill)
    case "failed", "timed_out", "orphaned":
      fail(pill: pill, errorText: inspection.errorMessage ?? "Agent failed")
    default:
      if let finalText = inspection.finalText, !finalText.isEmpty {
        finish(pill: pill, finalText: finalText)
      }
    }
    pill.markContentChanged()
    if pill.status.isFinished, pill.viewedAt != nil {
      scheduleViewedExpiration(for: pill)
    }
  }

  private func finish(pill: AgentPill, finalText: String?, resources: [ChatResource] = []) {
    let trimmed = finalText?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !trimmed.isEmpty || !resources.isEmpty {
      let messageText = trimmed.isEmpty ? "Done." : trimmed
      Self.removeEmptyStreamingAssistantMessages(for: pill)
      var finalMessage = Self.currentAssistantMessage(for: pill) ?? ChatMessage(text: messageText, sender: .ai)
      finalMessage.text = messageText
      finalMessage.resources = resources
      finalMessage.isStreaming = false
      Self.upsertAssistantMessage(finalMessage, for: pill)
      pill.latestActivity = ChatContinuityInvariants.agentPreviewText(
        prompt: pill.query,
        output: messageText
      )
    } else {
      Self.clearStreamingAssistantMessage(for: pill)
      pill.latestActivity = "Done"
    }
    pill.status = .done
    pill.completedAt = Date()
    pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
    pill.markContentChanged()
    ensureTerminalJournalMaterialization(for: pill)
  }

  private func fail(pill: AgentPill, errorText: String) {
    let sanitized = AgentFailureTranscriptFormatter.userFacingFailure(
      errorText,
      harnessMode: pill.bridgeHarnessOverride ?? pill.providerIdentity)
    pill.status = .failed(sanitized)
    pill.latestActivity = sanitized
    pill.completedAt = Date()
    Self.clearStreamingAssistantMessage(for: pill)
    Self.ensureFailureMessage(sanitized, for: pill)
    pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
    pill.markContentChanged()
    ensureTerminalJournalMaterialization(for: pill)
  }

  private static func ensureStreamingAssistantMessage(for pill: AgentPill) {
    if let aiMessage = pill.aiMessage, aiMessage.isStreaming {
      if !pill.conversationMessages.contains(where: { $0.id == aiMessage.id }) {
        pill.conversationMessages.append(aiMessage)
      }
      return
    }

    if let index = pill.conversationMessages.lastIndex(where: { $0.sender == .ai && $0.isStreaming }) {
      pill.aiMessage = pill.conversationMessages[index]
      return
    }

    if pill.conversationMessages.isEmpty {
      pill.conversationMessages = [ChatMessage(text: pill.query, sender: .user)]
    }

    var streamingMessage = ChatMessage(text: "", sender: .ai)
    streamingMessage.isStreaming = true
    pill.aiMessage = streamingMessage
    pill.conversationMessages.append(streamingMessage)
  }

  private static func clearStreamingAssistantMessage(for pill: AgentPill) {
    guard let aiMessage = pill.aiMessage, aiMessage.isStreaming else { return }
    let hasVisibleContent =
      !aiMessage.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      || !aiMessage.contentBlocks.isEmpty
      || !aiMessage.displayResources.isEmpty

    if hasVisibleContent {
      var completedMessage = aiMessage
      completedMessage.isStreaming = false
      pill.aiMessage = completedMessage
      if let index = pill.conversationMessages.firstIndex(where: { $0.id == completedMessage.id }) {
        pill.conversationMessages[index] = completedMessage
      }
    } else {
      pill.aiMessage = nil
      pill.conversationMessages.removeAll { $0.id == aiMessage.id }
    }
  }

  private static func removeEmptyStreamingAssistantMessages(for pill: AgentPill) {
    pill.conversationMessages.removeAll { message in
      message.sender == .ai
        && message.isStreaming
        && !hasVisibleAssistantContent(message)
    }
    if let aiMessage = pill.aiMessage,
      aiMessage.isStreaming,
      !hasVisibleAssistantContent(aiMessage)
    {
      pill.aiMessage = nil
    }
  }

  private static func currentAssistantMessage(for pill: AgentPill) -> ChatMessage? {
    if let aiMessage = pill.aiMessage, hasVisibleAssistantContent(aiMessage) {
      return aiMessage
    }
    return pill.conversationMessages.last { message in
      message.sender == .ai && hasVisibleAssistantContent(message)
    }
  }

  private static func hasVisibleAssistantContent(_ message: ChatMessage) -> Bool {
    !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      || !message.contentBlocks.isEmpty
      || !message.displayResources.isEmpty
  }

  private static func upsertAssistantMessage(_ message: ChatMessage, for pill: AgentPill) {
    pill.aiMessage = message
    if pill.conversationMessages.isEmpty {
      pill.conversationMessages = [
        ChatMessage(text: pill.query, sender: .user),
        message,
      ]
    } else if let index = pill.conversationMessages.firstIndex(where: { $0.id == message.id }) {
      pill.conversationMessages[index] = message
    } else if !pill.conversationMessages.contains(where: { $0.id == message.id }) {
      pill.conversationMessages.append(message)
    }
  }

  private func handle(messages: [ChatMessage], since: Int, for pill: AgentPill) {
    guard messages.count > since else { return }
    let recent = Array(messages.suffix(from: since))
    var displayMessages = recent.filter { message in
      let trimmed = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
      return message.sender == .user
        || !trimmed.isEmpty
        || message.isStreaming
        || !message.contentBlocks.isEmpty
        || !message.displayResources.isEmpty
    }
    if displayMessages.contains(where: { message in
      message.sender == .ai
        && !message.isStreaming
        && Self.hasVisibleAssistantContent(message)
    }) {
      displayMessages.removeAll { message in
        message.sender == .ai
          && message.isStreaming
          && !Self.hasVisibleAssistantContent(message)
      }
    }
    if !displayMessages.isEmpty {
      pill.conversationMessages = displayMessages
      pill.markContentChanged()
    }
    guard let aiMessage = recent.last(where: { $0.sender == .ai }) else { return }
    pill.aiMessage = aiMessage
    pill.markContentChanged()

    if pill.status.isFinished {
      return
    }

    if pill.status == .starting {
      pill.status = .running
    }

    let activity = Self.describeActivity(for: aiMessage)
    if !activity.isEmpty && activity != pill.latestActivity {
      pill.latestActivity = activity
      pill.transcript.append(activity)
      pill.markContentChanged()
    }

    if !aiMessage.isStreaming, Self.hasVisibleAssistantContent(aiMessage) {
      Self.removeEmptyStreamingAssistantMessages(for: pill)
      pill.status = .done
      pill.completedAt = pill.completedAt ?? Date()
      pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
      pill.markContentChanged()
      if pill.viewedAt != nil {
        scheduleViewedExpiration(for: pill)
      }
    }
  }

  /// Pill-bar activity string for an AI message. While a message is still
  /// streaming, skip partial text chunks so the pill does not flicker through
  /// mid-token labels like "O..." or "Open..." before the final response lands.
  /// Tool calls still show immediately because they are atomic activity.
  private static func describeActivity(for message: ChatMessage) -> String {
    for block in message.contentBlocks.reversed() {
      switch block {
      case .toolCall(_, let name, _, _, let input, _):
        let display = ChatContentBlock.displayName(for: name)
        if let input, !input.summary.isEmpty {
          return "\(display) — \(input.summary)"
        }
        return display
      case .text(_, let text):
        guard !message.isStreaming else { continue }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
          return String(trimmed.prefix(110))
        }
      case .agentSpawn(_, _, _, _, let title, let objective, _):
        let label = objective.isEmpty ? title : objective
        let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
          return String(trimmed.prefix(110))
        }
      case .agentCompletion(_, _, _, _, let title, let promptSnippet, let output, _):
        let preview = ChatContinuityInvariants.agentPreviewText(
          prompt: promptSnippet.isEmpty ? title : promptSnippet,
          output: output
        )
        let trimmed = preview.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
          return String(trimmed.prefix(110))
        }
      case .thinking, .discoveryCard:
        continue
      }
    }
    let trimmedFallback = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
    if !message.isStreaming, !trimmedFallback.isEmpty {
      return String(trimmedFallback.prefix(110))
    }
    return "Working…"
  }

  private func complete(pill: AgentPill, provider: ChatProvider, finalText: String?) {
    let trimmedFinalText = finalText?.trimmingCharacters(in: .whitespacesAndNewlines)
    if let trimmedFinalText, !trimmedFinalText.isEmpty {
      if pill.aiMessage?.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false {
        Self.removeEmptyStreamingAssistantMessages(for: pill)
        var finalMessage = Self.currentAssistantMessage(for: pill) ?? ChatMessage(text: trimmedFinalText, sender: .ai)
        finalMessage.text = trimmedFinalText
        finalMessage.isStreaming = false
        Self.upsertAssistantMessage(finalMessage, for: pill)
      }
      pill.latestActivity = ChatContinuityInvariants.agentPreviewText(
        prompt: pill.query,
        output: trimmedFinalText
      )
      pill.markContentChanged()
    }
    if let projection = AgentRuntimeStatusStore.shared.floatingPillProjection(pillId: pill.id) {
      Self.apply(projection: projection, to: pill)
      if projection.status.isTerminal {
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        if pill.viewedAt != nil {
          scheduleViewedExpiration(for: pill)
        }
        return
      }
    }
    if let errorText = provider.displayErrorMessage, !errorText.isEmpty {
      pill.status = .failed(errorText)
      pill.latestActivity = errorText
      pill.completedAt = Date()
      Self.ensureFailureMessage(errorText, for: pill)
      pill.markContentChanged()
    } else if let trimmedFinalText, !trimmedFinalText.isEmpty {
      pill.status = .done
      pill.completedAt = Date()
      pill.markContentChanged()
    } else {
      pill.status = .failed("Agent ended before reporting a final result")
      pill.completedAt = Date()
      pill.latestActivity = "Agent ended before reporting a final result"
      Self.ensureFailureMessage("Agent ended before reporting a final result", for: pill)
      pill.markContentChanged()
    }
    pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
    if pill.viewedAt != nil {
      scheduleViewedExpiration(for: pill)
    }
    // Keep the provider + stream alive after completion so a voice/text follow-up
    // can continue THIS agent's session with full context. They're torn down on
    // dismiss, or when the pill is trimmed at the maxPills cap (see cleanup()).
  }

  private static func ensureFailureMessage(_ errorText: String, for pill: AgentPill) {
    let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorText) ?? "Failed: \(errorText)"
    let failureMessage = ChatMessage(text: failureText, sender: .ai)
    if pill.conversationMessages.isEmpty {
      pill.conversationMessages = [
        ChatMessage(text: pill.query, sender: .user),
        failureMessage,
      ]
    } else if !pill.conversationMessages.contains(where: { message in
      message.sender == .ai
        && message.text.trimmingCharacters(in: .whitespacesAndNewlines) == failureMessage.text
    }) {
      pill.conversationMessages.append(failureMessage)
    }
    pill.aiMessage = failureMessage
  }

  private static func apply(projection: AgentRunProjection, to pill: AgentPill) {
    if pill.status == .stopped && projection.status != .cancelled {
      return
    }
    if pill.status.isFinished && !projection.status.isTerminal {
      return
    }

    switch projection.status {
    case .queued:
      pill.status = .queued
      ensureStreamingAssistantMessage(for: pill)
    case .starting, .running, .waitingInput, .waitingApproval, .cancelling:
      pill.status = .running
      pill.completedAt = nil
      ensureStreamingAssistantMessage(for: pill)
    case .succeeded:
      if let statusText = projection.statusText?.trimmingCharacters(in: .whitespacesAndNewlines),
        !statusText.isEmpty
      {
        removeEmptyStreamingAssistantMessages(for: pill)
        var finalMessage = currentAssistantMessage(for: pill) ?? ChatMessage(text: statusText, sender: .ai)
        finalMessage.text = statusText
        finalMessage.isStreaming = false
        upsertAssistantMessage(finalMessage, for: pill)
        pill.latestActivity = String(statusText.prefix(140))
      } else if let last = currentAssistantMessage(for: pill) {
        let trimmed = last.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
          pill.latestActivity = String(trimmed.prefix(140))
        }
        clearStreamingAssistantMessage(for: pill)
      } else {
        clearStreamingAssistantMessage(for: pill)
      }
      pill.status = .done
      pill.completedAt = projection.completedAt ?? Date()
      pill.markContentChanged()
    case .failed, .timedOut, .orphaned:
      let message = projection.failure?.displayMessage ?? projection.errorMessage ?? "Agent failed"
      pill.status = .failed(message)
      pill.latestActivity = message
      pill.completedAt = projection.completedAt ?? Date()
      clearStreamingAssistantMessage(for: pill)
      ensureFailureMessage(message, for: pill)
      pill.markContentChanged()
    case .cancelled:
      pill.status = .stopped
      pill.latestActivity = "Stopped by user"
      pill.completedAt = projection.completedAt ?? Date()
      clearStreamingAssistantMessage(for: pill)
      pill.markContentChanged()
    case .idle:
      break
    }
    if !projection.status.isTerminal, let statusText = projection.statusText, !statusText.isEmpty {
      pill.latestActivity = statusText
      pill.markContentChanged()
    }
  }

  /// Tiny heuristic to suggest 1–2 follow-ups based on the original query.
  /// "Open chat" is intentionally omitted — the popover already has a
  /// dedicated "Open in chat" button, so adding it as a chip would duplicate.
  private static func deriveFollowUps(for pill: AgentPill) -> [String] {
    let lower = pill.query.lowercased()
    if lower.contains("email") || lower.contains("reply") {
      return ["Open thread", "Check for replies"]
    }
    if lower.contains("search") || lower.contains("find") || lower.contains("look") {
      return ["Open results", "Refine search"]
    }
    if lower.contains("schedule") || lower.contains("book") || lower.contains("calendar") {
      return ["Open calendar", "Add reminder"]
    }
    return ["Run again"]
  }

  /// Ask Claude Haiku for a short title (3–5 words, present participle) and
  /// a one-sentence acknowledgement we can speak aloud. Returns nil if the
  /// API key isn't available or the call fails — the caller keeps the
  /// existing heuristic title in that case.
  /// Short, instant acknowledgements spoken the moment a voice query spawns
  /// a pill. Random pick so consecutive PTT queries don't sound identical.
  private static let instantAcks: [String] = [
    "On it.",
    "Got it.",
    "Sure thing.",
    "Working on it.",
    "Alright, doing that now.",
    "Let me get that started.",
    "Okay, on it.",
  ]

  fileprivate static func randomAck() -> String {
    instantAcks.randomElement() ?? "On it."
  }

  fileprivate static func generateTitleAndAck(for query: String) async -> (title: String, ack: String)? {
    // Route through the desktop-backend's OpenAI-compatible proxy at
    // /v2/chat/completions instead of hitting api.anthropic.com directly.
    // This way we don't need a BYOK key (no partial-BYOK 403 risk), and
    // the request goes through the user's existing Firebase auth + plan.
    let baseURL = await APIClient.shared.rustBackendURL
    guard !baseURL.isEmpty else {
      log("AgentPill: title gen skipped — rustBackendURL empty")
      return nil
    }
    let normalized = baseURL.hasSuffix("/") ? baseURL : baseURL + "/"
    guard let url = URL(string: normalized + "v2/chat/completions") else {
      log("AgentPill: title gen failed — bad URL")
      return nil
    }

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = 8
    do {
      let headers = try await APIClient.shared.buildHeaders(requireAuth: true)
      for (k, v) in headers { request.setValue(v, forHTTPHeaderField: k) }
    } catch {
      log("AgentPill: title gen skipped — auth header unavailable (\(error.localizedDescription))")
      return nil
    }

    let prompt = """
      The user just kicked off a background agent with this request:

      "\(query)"

      Reply with a JSON object on a single line, no prose, no markdown:
      {"title":"<3-5 word imperative title in Title Case, no trailing punctuation>","ack":"<one short spoken acknowledgement, max 7 words, friendly tone, e.g. 'Got it, building Mario now.'>"}
      """

    // OpenAI-compatible body. The backend translates to Anthropic upstream.
    let body: [String: Any] = [
      "model": "claude-haiku-4-5-20251001",
      "max_tokens": 120,
      "messages": [["role": "user", "content": prompt]],
      "stream": false,
    ]
    do {
      request.httpBody = try JSONSerialization.data(withJSONObject: body)
      let (data, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse else {
        log("AgentPill: title gen failed — no HTTP response")
        return nil
      }
      guard (200..<300).contains(http.statusCode) else {
        let body = String(data: data.prefix(200), encoding: .utf8) ?? "<binary>"
        log("AgentPill: title gen HTTP \(http.statusCode) — \(body)")
        return nil
      }
      // OpenAI shape: { choices: [{ message: { content: "..." } }] }
      guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
        let choices = json["choices"] as? [[String: Any]],
        let firstChoice = choices.first,
        let message = firstChoice["message"] as? [String: Any],
        let text = message["content"] as? String
      else {
        log("AgentPill: title gen response shape unexpected")
        return nil
      }
      let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard let payloadData = trimmed.data(using: .utf8),
        let payload = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any],
        let title = (payload["title"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
        let ack = (payload["ack"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
        !title.isEmpty, !ack.isEmpty
      else {
        log("AgentPill: title gen JSON parse failed — raw: \(String(trimmed.prefix(200)))")
        return nil
      }
      log("AgentPill: title gen ok — title=\"\(title)\" ack=\"\(ack)\"")
      return (title: String(title.prefix(40)), ack: String(ack.prefix(120)))
    } catch {
      log("AgentPill: title gen threw — \(error.localizedDescription)")
      return nil
    }
  }
}

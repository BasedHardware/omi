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

    let id = UUID()
    let query: String
    let createdAt: Date
    let model: String
    /// Mutable (unlike the other identity fields) because a provider startup
    /// fallback can move the pill onto the next directed provider — or the
    /// Omi default agent (`nil`) — before the task produced any output.
    @Published private(set) var bridgeHarnessOverride: AgentHarnessMode?
    var canonicalSessionId: String?
    var canonicalRunId: String?
    var canonicalAttemptId: String?

    /// Remaining auto-route fallback chain (a `nil` entry is the default Omi
    /// orchestrator). When this pill fails, the manager consumes the chain and
    /// respawns the task on the next provider. Empty for explicitly directed
    /// pills — a user who names an agent should not be silently rerouted.
    var fallbackProviders: [AgentPillsManager.DirectedProvider?] = []

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

    /// Directed providers that already failed during startup for this pill —
    /// drives the deterministic fallback chain and caps the retry attempts.
    private(set) var failedStartupProviders: [AgentPillsManager.DirectedProvider] = []
    /// Provider-switch notices pinned above the streamed transcript so the
    /// fallback handoff stays visible after new messages rebuild the list.
    private(set) var providerFallbackNotices: [ChatMessage] = []
    /// True once the current provider attempt produced any task output (text
    /// or tool/thinking content blocks). Gates the startup-fallback path.
    private(set) var hasProducedTaskOutput = false

    var currentDirectedProvider: AgentPillsManager.DirectedProvider? {
        bridgeHarnessOverride.flatMap { AgentPillsManager.DirectedProvider(harnessMode: $0) }
    }

    func markTaskOutputProduced() {
        hasProducedTaskOutput = true
    }

    /// Move the pill onto the next link of the startup-fallback chain and
    /// surface the switch in the pill's chat and activity line.
    func adoptFallbackProvider(
        _ next: AgentPillsManager.DirectedProvider?,
        afterStartupFailureOf failed: AgentPillsManager.DirectedProvider
    ) {
        failedStartupProviders.append(failed)
        bridgeHarnessOverride = next?.harnessMode
        hasProducedTaskOutput = false
        // The retry spawns a fresh canonical session/run; drop the failed
        // attempt's ids so follow-ups queue for the new run instead of
        // targeting the dead session.
        canonicalSessionId = nil
        canonicalRunId = nil
        canonicalAttemptId = nil
        let notice = "\(failed.displayName) failed to start — continuing with \(next?.displayName ?? "Omi's default agent")."
        providerFallbackNotices.append(ChatMessage(text: notice, sender: .ai))
        conversationMessages = providerFallbackNotices + conversationMessages.filter { $0.sender == .user }
        status = .starting
        completedAt = nil
        latestActivity = notice
        markContentChanged()
    }

    /// Convenience: how long the agent has been running (or ran).
    var elapsed: TimeInterval {
        (completedAt ?? Date()).timeIntervalSince(createdAt)
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

    var displayName: String {
      switch self {
      case .hermes: return "Hermes"
      case .openclaw: return "OpenClaw"
      }
    }

    var harnessMode: AgentHarnessMode {
      switch self {
      case .hermes: return .hermes
      case .openclaw: return .openclaw
      }
    }

    var executableName: String {
      switch self {
      case .hermes: return "hermes"
      case .openclaw: return "openclaw"
      }
    }

    enum DirectedProvider: String, Equatable, CaseIterable {
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
            case .codex: return "codex"
            }
        }

        var commandEnvironmentName: String {
            switch self {
            case .hermes: return "OMI_HERMES_ADAPTER_COMMAND"
            case .openclaw: return "OMI_OPENCLAW_ADAPTER_COMMAND"
            case .codex: return "OMI_CODEX_ADAPTER_COMMAND"
            }
        }

        /// Shell command that installs this agent's CLI on macOS. Surfaced by the
        /// install helper so a user can connect a named-but-missing agent in one tap.
        var installCommand: String {
            switch self {
            case .hermes: return "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
            case .openclaw: return "curl -fsSL https://openclaw.ai/install.sh | bash"
            case .codex: return "npm install -g @openai/codex"
            }
        }

        var docsURL: String {
            switch self {
            case .hermes: return "https://hermes-agent.nousresearch.com"
            case .openclaw: return "https://docs.openclaw.ai/install"
            case .codex: return "https://developers.openai.com/codex/cli"
            }
        }

        /// Spoken/typed forms that select this agent by name in a voice/chat request.
        var aliases: [String] {
            switch self {
            case .hermes: return ["hermes", "nous"]
            case .openclaw: return ["openclaw", "open claw"]
            case .codex: return ["codex"]
            }
        }

        /// The installable local provider matching a harness, if any (Claude Code / Omi AI have none).
        init?(harness: AgentHarnessMode) {
            switch harness {
            case .hermes: self = .hermes
            case .openclaw: self = .openclaw
            case .codex: self = .codex
            case .acp, .piMono: return nil
            }
        }

        var setupNeededStatus: String {
            "\(displayName) needs setup"
        }

        /// Canonical install one-liner from the provider's official docs —
        /// what we show the user (and the model) when the provider is missing.
        var installCommand: String {
            switch self {
            case .hermes: return "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
            case .openclaw: return "curl -fsSL https://openclaw.ai/install.sh | bash"
            // The Codex CLI has no ACP mode, so the codex-acp bridge is
            // required alongside it for task execution.
            case .codex: return "npm install -g @openai/codex @agentclientprotocol/codex-acp"
            }
        }

        /// Install command safe for the UNATTENDED install run by
        /// `LocalAgentProviderInstaller` (pipe stdio, no TTY): the canonical
        /// curl installers launch interactive onboarding/setup stages that
        /// would hang a non-interactive shell, so these variants skip them
        /// (flags documented by each provider's installer).
        var unattendedInstallCommand: String {
            switch self {
            case .hermes: return "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --non-interactive"
            case .openclaw: return "curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard"
            case .codex: return "npm install -g @openai/codex @agentclientprotocol/codex-acp"
            }
        }

        /// Where `unattendedInstallCommand` downloads from — shown verbatim
        /// in the native install confirmation dialog.
        var installSourceDomain: String {
            switch self {
            case .hermes: return "hermes-agent.nousresearch.com"
            case .openclaw: return "openclaw.ai"
            case .codex: return "registry.npmjs.org"
            }
        }

        /// Official install documentation page.
        var installDocsURL: String {
            switch self {
            case .hermes: return "https://hermes-agent.nousresearch.com/docs/getting-started/installation"
            case .openclaw: return "https://docs.openclaw.ai/install"
            case .codex: return "https://github.com/openai/codex"
            }
        }

        /// Interactive step the user must run themselves after the install
        /// command (the unattended install never attempts interactive logins).
        var postInstallNote: String? {
            switch self {
            case .hermes: return "run `hermes setup` to finish configuring it"
            case .openclaw: return "run `openclaw onboard --install-daemon` to finish onboarding"
            case .codex: return "run `codex login` if you haven't signed in"
            }
        }

        /// Canonical normalization for provider names arriving in model tool
        /// arguments ("Open Claw" → "openclaw"): trim whitespace, lowercase,
        /// drop internal spaces. Shared by every spawn_agent /
        /// setup_agent_provider surface so parsing can never drift.
        static func normalizedRawValue(_ raw: String?) -> String {
            (raw ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
                .replacingOccurrences(of: " ", with: "")
        }

        /// Shared unsupported-provider tool error — identical wording across
        /// spawn_agent and setup_agent_provider on every surface.
        static func unsupportedProviderMessage(_ name: String) -> String {
            "Unsupported agent provider '\(name)'. Supported providers: openclaw, hermes, codex."
        }
    }

    /// Canonical directed-provider order — used for prompt listings and as
    /// the fixed preference order of the startup fallback chain.
    nonisolated static let orderedDirectedProviders: [DirectedProvider] = [.openclaw, .hermes, .codex]

    /// Providers to try after the given startup failures: the remaining
    /// AVAILABLE directed providers in fixed order, then the Omi default
    /// agent (`nil`) as the final link. Caps total attempts at the requested
    /// provider + at most 2 directed fallbacks + the default agent.
    nonisolated static func fallbackChain(
        afterFailed failed: [DirectedProvider],
        available: [DirectedProvider]
    ) -> [DirectedProvider?] {
        let remainingDirectedSlots = max(0, orderedDirectedProviders.count - failed.count)
        var chain: [DirectedProvider?] = orderedDirectedProviders
            .filter { available.contains($0) && !failed.contains($0) }
            .prefix(remainingDirectedSlots)
            .map { Optional($0) }
        chain.append(nil)
        return chain
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

    struct Snapshot: Encodable {
        let id: String
        let title: String
        let status: String
        /// Provider currently running the pill — a directed provider rawValue
        /// ("openclaw"/"hermes"/"codex") or "omi" for the default agent.
        /// Reflects startup fallbacks, so the hub can tell which provider a
        /// retried pill actually landed on.
        let provider: String
        let latestActivity: String
        let query: String
        let createdAt: String
        let completedAt: String?
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
        // Word form: "two agents", "three tasks", "five test agents"
        let wordToNumber: [String: Int] = [
            "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        ]
        let wordPattern = #"\b(two|three|four|five|six|seven|eight)(?:\s+\S+){0,5}\s+\#(nounGroup)\b"#
        if let regex = try? NSRegularExpression(pattern: wordPattern),
            let match = regex.firstMatch(in: lower, range: NSRange(lower.startIndex..., in: lower)),
            match.numberOfRanges > 1,
            let range = Range(match.range(at: 1), in: lower),
            let n = wordToNumber[String(lower[range])]
        {
            return min(n, 8)
        }
        return 1
    }

    nonisolated static func providerDirective(from text: String) -> ProviderDirective? {
        providerDirective(from: text, contextualPreviousRequest: nil)
    }

    nonisolated static func providerDirective(
        from text: String,
        contextualPreviousRequest: String?
    ) -> ProviderDirective? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        let providerPattern = "(open\\s*claw|openclaw|hermes|codex)"
        let patterns = [
            #"(?i)^\s*(?:please\s+)?(?:(?:i\s+)?meant\s+)?(?:ask|tell|ping|message|run|use|try)\s+\#(providerPattern)\b(?:\s+(.*))?$"#,
            #"(?i)^\s*(?:please\s+)?\#(providerPattern)\s*[:,\-]\s*(.*)$"#,
        ]

        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let range = NSRange(trimmed.startIndex..., in: trimmed)
            guard let match = regex.firstMatch(in: trimmed, range: range), match.numberOfRanges >= 2 else { continue }
            guard let providerRange = Range(match.range(at: 1), in: trimmed) else { continue }
            let providerToken = trimmed[providerRange]
                .lowercased()
                .replacingOccurrences(of: " ", with: "")
            let provider: DirectedProvider
            switch providerToken {
            case "openclaw": provider = .openclaw
            case "hermes": provider = .hermes
            case "codex": provider = .codex
            default: continue
            }

            let restIndex = match.numberOfRanges > 2 ? 2 : NSNotFound
            let rest: String
            if restIndex != NSNotFound,
                let restRange = Range(match.range(at: restIndex), in: trimmed) {
                rest = String(trimmed[restRange]).trimmingCharacters(in: .whitespacesAndNewlines)
            } else {
                rest = ""
            }
            let contextualObjective = contextualPreviousRequest
                .flatMap { providerObjective(from: $0) }?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let objective: String
            if rest.isEmpty, isProviderCorrection(trimmed), contextualObjective?.isEmpty == false {
                objective = contextualObjective!
            } else {
                objective = rest.isEmpty ? "Say how it's going." : rest
            }
            return ProviderDirective(
                provider: provider,
                rewrittenQuery: objective,
                title: provider.displayName,
                ack: "Asking \(provider.displayName)."
            )
        }

        return fuzzyProviderDirective(from: trimmed, contextualPreviousRequest: contextualPreviousRequest)
    }

    /// Fallback for the strict provider pattern above: catches STT mishears and
    /// typos ("ask codecs ...", "run open flaw ...", "tell hermies ...") that the
    /// exact token list misses. Only fires on an explicit directive shape (a lead
    /// verb) and only when the leading word(s) resolve confidently to an installable
    /// directed provider, so it never hijacks an ordinary task like "run tests".
    private nonisolated static func fuzzyProviderDirective(
        from trimmed: String,
        contextualPreviousRequest: String?
    ) -> ProviderDirective? {
        let verbPattern =
            #"(?i)^\s*(?:please\s+)?(?:(?:i\s+)?meant\s+)?(?:ask|tell|ping|message|run|use|try)\s+(.+)$"#
        guard let regex = try? NSRegularExpression(pattern: verbPattern) else { return nil }
        let range = NSRange(trimmed.startIndex..., in: trimmed)
        guard let match = regex.firstMatch(in: trimmed, range: range),
            match.numberOfRanges > 1,
            let remainderRange = Range(match.range(at: 1), in: trimmed)
        else { return nil }

        let remainder = String(trimmed[remainderRange]).trimmingCharacters(in: .whitespacesAndNewlines)
        let words = remainder.split(separator: " ").map(String.init)
        guard let (harness, consumed) = AgentSpeechMatcher.resolveLeadingProvider(words),
            let provider = DirectedProvider(harness: harness)
        else { return nil }

        let rest = words.dropFirst(consumed).joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let contextualObjective = contextualPreviousRequest
            .flatMap { providerObjective(from: $0) }?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let objective: String
        if rest.isEmpty, isProviderCorrection(trimmed), contextualObjective?.isEmpty == false {
            objective = contextualObjective!
        } else {
            objective = rest.isEmpty ? "Say how it's going." : rest
        }
        return ProviderDirective(
            provider: provider,
            rewrittenQuery: objective,
            title: provider.displayName,
            ack: "Asking \(provider.displayName)."
        )
    }

    nonisolated static func providerObjective(from text: String) -> String {
        let original = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !original.isEmpty else { return original }
        let patterns = [
            #"(?i)^\s*(?:please\s+)?(?:ask|tell|ping|message|run|use|try)\s+\S+\s+(?:to|about)\s+(.+)$"#,
            #"(?i)^\s*(?:please\s+)?(?:ask|tell|ping|message|run|use|try)\s+\S+\s+(.+)$"#,
        ]
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let range = NSRange(original.startIndex..., in: original)
            guard let match = regex.firstMatch(in: original, range: range),
                  match.numberOfRanges > 1,
                  let objectiveRange = Range(match.range(at: 1), in: original) else {
                continue
            }
            let objective = original[objectiveRange].trimmingCharacters(in: .whitespacesAndNewlines)
            if !objective.isEmpty {
                return objective
            }
        }
        return original
    }

    private nonisolated static func isProviderCorrection(_ text: String) -> Bool {
        let lower = text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        return lower.hasPrefix("i meant")
            || lower.hasPrefix("meant")
            || lower.hasSuffix("instead")
            || lower.contains(" instead of ")
    }

    /// User control-plane request from the floating bar UI: create a visible sibling
    /// background agent. This is intentionally separate from an agent's own tool use;
    /// existing floating agents still cannot self-spawn nested pills.
    nonisolated static func floatingAgentHandoff(for text: String) -> FloatingAgentHandoff? {
        let original = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !original.isEmpty else { return nil }
        let lower = text.lowercased()
        // Exclude question-style starters — informational queries like
        // "how do I start a background agent?" or "can you explain how to run
        // agents?" should answer inline, not spawn a pill.
        let questionStarters = [
            "how do i", "how do you", "how to", "what is", "what are", "what does",
            "what can", "whats", "can you explain", "could you explain",
            "explain how", "tell me about", "tell me how", "why", "is it",
            "are agents", "do agents", "does the agent",
            // Modal question starters — queries like "can I run agents in the
            // background?", "will agents run while I work?", or "should I start
            // an agent?" contain an agent noun + an action verb but are questions,
            // not imperatives, so they should answer inline, not spawn a pill.
            "can i", "could i", "should i", "would i", "will agents",
            "will the agent", "may i", "do i need", "do i have",
        ]
        let trimmedLower = lower.trimmingCharacters(in: .whitespacesAndNewlines)
        if questionStarters.contains(where: { trimmedLower.hasPrefix($0) }) {
            return nil
        }
        // Negation guard (fully scoped): only suppress spawn when a negation
        // word appears in direct construction with BOTH a spawn action AND an
        // agent noun — e.g. "don't spawn an agent", "no agent", "without a
        // pill". Every pattern requires agent-noun proximity so unrelated
        // negation words (e.g. "don't make me laugh, spawn an agent") do not
        // false-suppress legitimate spawns. (Cubic P1 — tightens prior scoped
        // guard.)
        let agentNoun = Self.agentNounPattern
        let article = #"(?:a|an|any)\s+"#
        let negationOptOuts = [
            // "don't spawn an agent", "do not create a pill", "don't run agents"
            #"\b(?:don'?t|do not|never)\s+(?:spawn|start|launch|kick\s+off|create|make|run)\s+(?:"# + article + #")?"# + agentNoun + #"\b"#,
            // "no agent", "not an agent", "no pills", "not a subagent"
            #"\b(?:no|not)\s+(?:"# + article + #")?"# + agentNoun + #"\b"#,
            // "without spawning an agent", "without a pill",
            // "without creating subagents"
            #"\bwithout\s+(?:(?:spawning|creating|making|starting|launching|running)\s+(?:"# + article + #")?|"# + article + #")?"# + agentNoun + #"\b"#,
            // "not spawning an agent", "never creating pills"
            #"\b(?:not|never)\s+(?:spawning|creating|making|starting|launching|running)\s+(?:"# + article + #")?"# + agentNoun + #"\b"#,
        ]
        if negationOptOuts.contains(where: { lower.range(of: $0, options: .regularExpression) != nil }) {
            return nil
        }
        let agentPattern = #"\b"# + Self.agentNounPattern + #"\b"#
        let actionPattern = #"\b(?:spawn|start|launch|kick\s+off|create|make|run)\b"#
        guard lower.range(of: agentPattern, options: .regularExpression) != nil else { return nil }
        guard lower.range(of: actionPattern, options: .regularExpression) != nil else { return nil }

        return FloatingAgentHandoff(
            originalRequest: original,
            agentTask: extractFloatingAgentTask(from: original) ?? original
        )
    }

    nonisolated static func explicitlyRequestsFloatingAgent(_ text: String) -> Bool {
        floatingAgentHandoff(for: text) != nil
    }

    private nonisolated static func extractFloatingAgentTask(from text: String) -> String? {
        let nounPattern = #"\b"# + Self.agentNounPattern + #"\b"#
        guard let regex = try? NSRegularExpression(pattern: nounPattern, options: [.caseInsensitive]) else {
            return nil
        }
        let range = NSRange(text.startIndex..., in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              let matchRange = Range(match.range, in: text)
        else {
            return nil
        }

        var task = String(text[matchRange.upperBound...])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let connectorPattern = #"^(?:to|for|that\s+can|that\s+will|which\s+can|which\s+will|and)\s+"#
        if let connectorRegex = try? NSRegularExpression(pattern: connectorPattern, options: [.caseInsensitive]) {
            task = connectorRegex.stringByReplacingMatches(
                in: task,
                range: NSRange(task.startIndex..., in: task),
                withTemplate: ""
            )
            .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard task.split(whereSeparator: \.isWhitespace).count >= 2 else { return nil }
        return task
    }

    /// Spawn one or more pills for a user query. If the query says "spawn 3
    /// agents" we create 3 pills (each runs the same task on the shared
    /// queue). Returns the first pill so callers can inspect it.
    @discardableResult
    func spawnFromUserQuery(
        _ query: String,
        model: String,
        fromVoice: Bool = false,
        preFetchedTitle: String? = nil,
        preFetchedAck: String? = nil,
        bridgeHarnessOverride: AgentHarnessMode? = nil
    ) -> AgentPill {
        let count = AgentPillsManager.parseAgentCount(from: query)
        if count <= 1 {
            return spawn(
                query: query,
                model: model,
                fromVoice: fromVoice,
                preFetchedTitle: preFetchedTitle,
                preFetchedAck: preFetchedAck,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
        }
        var first: AgentPill?
        for i in 1...count {
            let labelled = "[\(i)/\(count)] \(query)"
            // Only the first pill speaks the acknowledgement when N > 1,
            // otherwise we'd hear N overlapping voices. Only the first pill
            // gets the pre-fetched title/ack — the others fall back to their
            // own title generation since their query text differs (the
            // [i/N] prefix changes the model's output).
            let pill = spawn(
                query: labelled,
                model: model,
                fromVoice: fromVoice && first == nil,
                preFetchedTitle: first == nil ? preFetchedTitle : nil,
                preFetchedAck: first == nil ? preFetchedAck : nil,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
            if first == nil { first = pill }
        }
        return first ?? spawn(query: query, model: model, fromVoice: fromVoice, bridgeHarnessOverride: bridgeHarnessOverride)
    }

    @discardableResult
    func spawnFromHandoff(
        _ handoff: FloatingAgentHandoff,
        model: String,
        fromVoice: Bool = false,
        preFetchedTitle: String? = nil,
        preFetchedAck: String? = nil,
        bridgeHarnessOverride: AgentHarnessMode? = nil
    ) -> AgentPill {
        let count = AgentPillsManager.parseAgentCount(from: handoff.originalRequest)
        if count <= 1 {
            return spawn(
                query: handoff.agentTask,
                model: model,
                fromVoice: fromVoice,
                preFetchedTitle: preFetchedTitle,
                preFetchedAck: preFetchedAck,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
        }
        var first: AgentPill?
        for i in 1...count {
            let labelled = "[\(i)/\(count)] \(handoff.agentTask)"
            let pill = spawn(
                query: labelled,
                model: model,
                fromVoice: fromVoice && first == nil,
                preFetchedTitle: first == nil ? preFetchedTitle : nil,
                preFetchedAck: first == nil ? preFetchedAck : nil,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
            if first == nil { first = pill }
        }
        return first ?? spawn(
            query: handoff.agentTask,
            model: model,
            fromVoice: fromVoice,
            bridgeHarnessOverride: bridgeHarnessOverride
        )
    }

    /// Spawn a visible pill projection backed by a canonical background-agent
    /// session/run in the Omi runtime.
    @discardableResult
    func spawn(
        query: String,
        model: String,
        fromVoice: Bool = false,
        preFetchedTitle: String? = nil,
        preFetchedAck: String? = nil,
        systemPromptSuffix: String? = nil,
        bridgeHarnessOverride: AgentHarnessMode? = nil
    ) -> AgentPill {
        let pill = AgentPill(query: query, model: model, bridgeHarnessOverride: bridgeHarnessOverride)
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

        pill.status = .starting
        if let preFetchedAck, !preFetchedAck.isEmpty {
            pill.latestActivity = preFetchedAck
        } else {
            pill.latestActivity = "Starting…"
        }
        AgentRuntimeStatusStore.shared.beginRequest(surface: surfaceRef, statusText: pill.latestActivity)

        // For voice queries, play a cached deterministic kickoff sample before
        // the runtime accepts the run so the user always hears confirmation
        // without falling back to a different system voice.
        if fromVoice {
            FloatingBarVoicePlaybackService.shared.speakBackgroundAgentKickoff()
        }

        // If the router already returned a title we don't need a second
        // Haiku call for title generation. Otherwise kick one off in the
        // background to upgrade the heuristic title.
        if preFetchedTitle == nil {
            Task { [weak pill] in
                guard let pill else { return }
                guard let result = await AgentPillsManager.generateTitleAndAck(for: pill.query) else { return }
                await MainActor.run {
                    pill.title = result.title
                    if pill.latestActivity == "Warming up…" || pill.latestActivity == "Starting…" {
                        pill.latestActivity = result.ack
                    }
                }
            }
        }

        startProviderAttempt(for: pill)

        return pill
    }

    /// Wire one canonical-run attempt for a pill: coordinator spawn, accepted
    /// run bookkeeping, and status polling. Used by the initial spawn and by
    /// startup-fallback retries — a retry replaces the failed attempt's run
    /// task but keeps the same pill (id, chat surface, transcript). Reads the
    /// pill's CURRENT bridgeHarnessOverride so a retry lands on the provider
    /// the fallback moved the pill to.
    private func startProviderAttempt(for pill: AgentPill) {
        // A retry displaces the failed attempt's still-registered run task;
        // the initial spawn has nothing to displace.
        runTasksByPill[pill.id]?.cancel()

        let surfaceRef = AgentSurfaceReference.floatingPill(pillId: pill.id)
        let bridgeHarnessOverride = pill.bridgeHarnessOverride
        let workingDirectory = FloatingControlBarManager.shared.sharedFloatingProvider?.workingDirectory
        // Directed provider pills must not inherit the floating bar's Claude
        // model override: those harnesses can reject Omi's Claude aliases, so
        // leave model selection to the provider-native default.
        let modelForSpawn = bridgeHarnessOverride == nil
            ? (FloatingControlBarManager.shared.sharedFloatingProvider?.modelOverride ?? pill.model)
            : nil
        let runTask = Task { @MainActor [weak self, weak pill] in
            guard !Task.isCancelled else { return }
            guard let self, let pill else { return }
            do {
                let accepted = try await DesktopCoordinatorService.shared.spawnBackgroundAgent(
                    prompt: pill.query,
                    title: pill.title,
                    pillId: pill.id,
                    model: modelForSpawn,
                    harnessMode: bridgeHarnessOverride,
                    cwd: workingDirectory
                )
                pill.canonicalSessionId = accepted.sessionId
                pill.canonicalRunId = accepted.runId
                pill.canonicalAttemptId = accepted.attemptId
                if Task.isCancelled || !self.pills.contains(where: { $0.id == pill.id }) || pill.status.isFinished {
                    Task {
                        _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: accepted.runId)
                    }
                    return
                }
                pill.title = accepted.title
                pill.status = .running
                pill.completedAt = nil
                pill.suggestedFollowUps = []
                pill.latestActivity = "Working…"
                // Keep any provider-fallback notices pinned above the brief so
                // the handoff stays visible after the retry's accept rebuilds
                // the transcript (empty on a first attempt).
                pill.conversationMessages = pill.providerFallbackNotices + [ChatMessage(text: pill.query, sender: .user)]
                Self.ensureStreamingAssistantMessage(for: pill)
                pill.markContentChanged()
                AgentRuntimeStatusStore.shared.recordAcceptedRun(
                    surface: surfaceRef,
                    sessionId: accepted.sessionId,
                    runId: accepted.runId,
                    attemptId: accepted.attemptId,
                    statusText: "Working…"
                )
                let queuedFollowUps = self.pendingFollowUpsByPill.removeValue(forKey: pill.id) ?? []
                if !queuedFollowUps.isEmpty {
                    self.continueAgent(
                        from: pill,
                        text: queuedFollowUps.map(\.text).joined(separator: "\n\n"),
                        attachments: queuedFollowUps.flatMap(\.attachments)
                    )
                    return
                }
                await self.pollCanonicalRun(for: pill)
            } catch {
                guard !Task.isCancelled else { return }
                AgentRuntimeStatusStore.shared.recordLocalFailure(
                    surface: surfaceRef,
                    error: error.localizedDescription
                )
                self.fail(pill: pill, errorText: error.localizedDescription)
            }
        }
        runTasksByPill[pill.id] = runTask
    }

    /// Deterministic startup fallback: when a directed provider fails before
    /// its task produced any output, retry the same brief on the next link of
    /// the fallback chain (remaining available providers in
    /// `orderedDirectedProviders` order, then the Omi default agent).
    /// Returns true when a retry was scheduled — the caller must not commit a
    /// terminal failed state in that case.
    private func attemptProviderStartupFallback(for pill: AgentPill, errorText: String) -> Bool {
        // Only directed pills fall back; the Omi default agent (nil override)
        // is already the last link of the chain.
        guard let failedProvider = pill.currentDirectedProvider else { return false }
        // HARD SAFETY RULE: never fall back once the failed attempt produced
        // any task output (text delta or tool activity). Re-running a
        // partially-executed brief could repeat side effects (e.g. double-send
        // a message), so mid-task failures must surface as failures instead of
        // retrying on another provider.
        guard !pill.hasProducedTaskOutput else { return false }
        // A user-stopped pill never retries.
        guard pill.status != .stopped else { return false }

        let available = Self.orderedDirectedProviders.filter { LocalAgentProviderDetector.isAvailable($0) }
        let chain = Self.fallbackChain(afterFailed: pill.failedStartupProviders + [failedProvider], available: available)
        guard let next = chain.first else { return false }

        log(
            "AgentPill: provider fallback \(failedProvider.rawValue) → \(next?.rawValue ?? "omi-default") "
                + "for pill \(pill.id.uuidString.prefix(8)) after startup failure: \(errorText)"
        )
        pill.adoptFallbackProvider(next, afterStartupFailureOf: failedProvider)
        // Clear the failed attempt's terminal projection right away so a
        // stray publish from another surface can't re-apply the stale failure
        // to the retried pill before its next query begins. statusText stays
        // nil so the fallback notice keeps owning the activity line.
        AgentRuntimeStatusStore.shared.beginRequest(
            surface: .floatingPill(pillId: pill.id),
            statusText: nil
        )
        startProviderAttempt(for: pill)
        return true
    }

    /// Classify a completed attempt for the startup-fallback path. ALLOWLIST
    /// gate on the structured failure the Node runtime reports: a retry on
    /// another provider is eligible ONLY when the run terminated `.failed`
    /// with `failure.phase == "startup"` — the runtime sets that tag
    /// exclusively at sites strictly before adapter dispatch (activation
    /// gate, adapter registration, session binding; see
    /// agent/src/runtime/failures.ts), so it proves the brief never started
    /// executing. Everything else returns nil and surfaces as a normal
    /// terminal failure: timeouts and orphaned runs (the adapter may still be
    /// executing remotely), execution-phase or unclassified errors, and runs
    /// that ended with no error and no result. Retrying any of those could
    /// re-run already-executed work and duplicate side effects.
    nonisolated static func startupFallbackFailure(projection: AgentRunProjection?) -> AgentRuntimeFailure? {
        guard let projection,
            projection.status == .failed,
            let failure = projection.failure,
            failure.isStartupPhase
        else { return nil }
        return failure
    }

    // MARK: - Voice follow-up (continue THIS agent's session)

    /// Tap the pill's mic button: start recording if idle, or stop + transcribe +
    /// send if this pill is already recording.
    func toggleFollowUpVoice(for pill: AgentPill) {
        if recordingPillID == pill.id {
            log("AgentPills: voice follow-up STOP tapped for \(pill.title)")
            recordingPillID = nil
            PushToTalkManager.shared.endPillFollowUp()
        } else if recordingPillID == nil {
            log("AgentPills: voice follow-up START tapped for \(pill.title)")
            recordingPillID = pill.id
            // Routes through the realtime omni STT (hub pipeline); the transcript comes
            // back into continueAgent(from:text:) for THIS pill's session.
            PushToTalkManager.shared.startPillFollowUp(for: pill)
        }
    }

    /// Send a follow-up to the same canonical background-agent session.
    func continueAgent(from pill: AgentPill, text: String, attachments: [ChatAttachment] = []) {
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
            return
        }
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
            return pill
        }
        pills = seeded
        return seeded
    }

    private func cleanup(pillID: UUID) {
        if recordingPillID == pillID {
            recordingPillID = nil
            PushToTalkManager.shared.cancelPillFollowUp(for: pillID)
        }
        let pill = pills.first(where: { $0.id == pillID })
        let shouldCancelRun = pill?.status.isFinished == false
        let runId = pill?.canonicalRunId
        runTasksByPill[pillID]?.cancel()
        runTasksByPill[pillID] = nil
        viewedExpirationWorkItemsByPill[pillID]?.cancel()
        viewedExpirationWorkItemsByPill[pillID] = nil
        pendingFollowUpsByPill[pillID] = nil
        pills.removeAll { $0.id == pillID }
        if shouldCancelRun, let runId, !runId.isEmpty {
            Task {
                _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: runId)
            }
        }
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
        let formatter = ISO8601DateFormatter()
        return pills
            .sorted { $0.createdAt > $1.createdAt }
            .prefix(limit)
            .map { pill in
                Snapshot(
                    id: pill.id.uuidString,
                    title: pill.title,
                    status: pill.status.machineLabel,
                    provider: pill.currentDirectedProvider?.rawValue ?? "omi",
                    latestActivity: pill.latestActivity,
                    query: pill.query,
                    createdAt: formatter.string(from: pill.createdAt),
                    completedAt: pill.completedAt.map { formatter.string(from: $0) }
                )
            }
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

    func manage(action: String, agentId: String?) -> String {
        switch action.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "list", "status":
            return statusSummary()
        case "dismiss":
            guard let agentId, !agentId.isEmpty else {
                return "Missing agent_id. Call get_task_agent_status first and pass the floating_agent_pills id."
            }
            return dismiss(pillIdString: agentId)
                ? "Dismissed floating agent pill \(agentId)."
                : "No floating agent pill matched \(agentId)."
        case "clear_completed":
            let count = pills.filter { $0.status.isFinished }.count
            clearCompleted()
            return "Cleared \(count) completed floating agent pill(s)."
        default:
            return "Unknown action. Use list, dismiss, or clear_completed."
        }
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

    private func pollCanonicalRun(for pill: AgentPill) async {
        while !Task.isCancelled {
            guard pills.contains(where: { $0.id == pill.id }) else { return }
            guard let runId = pill.canonicalRunId else { return }
            do {
                let inspection = try await DesktopCoordinatorService.shared.inspectAgentRun(
                    runId: runId
                )
                apply(inspection: inspection, to: pill)
                if pill.status.isFinished { return }
            } catch {
                logError("AgentPills: failed to inspect canonical run \(runId)", error: error)
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
    }

    private func apply(inspection: DesktopCoordinatorAgentRunInspection, to pill: AgentPill) {
        pill.canonicalSessionId = inspection.sessionId ?? pill.canonicalSessionId
        pill.canonicalRunId = inspection.runId ?? pill.canonicalRunId
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
        case "failed", "timed_out", "orphaned":
            // Startup fallback runs before any terminal state is committed so
            // a directed provider that failed to start can hand the same brief
            // to the next provider in the chain. Only `failed` runs whose
            // structured runtime failure proves the adapter never began
            // executing are eligible (see startupFallbackFailure); timeouts
            // and orphaned runs may still be executing remotely and must
            // surface as failures instead.
            if inspection.status == "failed",
                let startupFailure = Self.startupFallbackFailure(
                    projection: AgentRuntimeStatusStore.shared.floatingPillProjection(pillId: pill.id)),
                attemptProviderStartupFallback(for: pill, errorText: startupFailure.displayMessage)
            {
                return
            }
            fail(pill: pill, errorText: inspection.errorMessage ?? "Agent failed")
        default:
            if let finalText = inspection.finalText, !finalText.isEmpty {
                finish(pill: pill, finalText: finalText)
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

    private func finish(pill: AgentPill, finalText: String?, resources: [ChatResource] = []) {
        let trimmed = finalText?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmed.isEmpty || !resources.isEmpty {
            // Real task output arrived — from here on, provider startup
            // fallback is permanently off for this pill (a later follow-up
            // turn that fails at startup must fail visibly, not silently
            // re-run the brief on another provider).
            pill.markTaskOutputProduced()
            let messageText = trimmed.isEmpty ? "Done." : trimmed
            var finalMessage = pill.aiMessage ?? ChatMessage(text: messageText, sender: .ai)
            finalMessage.text = messageText
            finalMessage.resources = resources
            finalMessage.isStreaming = false
            pill.aiMessage = finalMessage
            if pill.conversationMessages.isEmpty {
                pill.conversationMessages = [
                    ChatMessage(text: pill.query, sender: .user),
                    finalMessage,
                ]
            } else if let index = pill.conversationMessages.firstIndex(where: { $0.id == finalMessage.id }) {
                pill.conversationMessages[index] = finalMessage
            } else if !pill.conversationMessages.contains(where: { $0.id == finalMessage.id }) {
                pill.conversationMessages.append(finalMessage)
            }
            pill.latestActivity = String(messageText.prefix(140))
            FloatingControlBarManager.shared.recordAgentArtifactCompletion(
                pillID: pill.id,
                runId: pill.canonicalRunId,
                title: pill.title,
                finalText: trimmed,
                resources: resources
            )
        } else {
            Self.clearStreamingAssistantMessage(for: pill)
            pill.latestActivity = "Done"
        }
        pill.status = .done
        pill.completedAt = Date()
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        pill.markContentChanged()
    }

    private func fail(pill: AgentPill, errorText: String) {
        pill.status = .failed(errorText)
        pill.latestActivity = errorText
        pill.completedAt = Date()
        Self.clearStreamingAssistantMessage(for: pill)
        Self.ensureFailureMessage(errorText, for: pill)
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        pill.markContentChanged()
        // Canonical run failures land here (not in complete()), so the
        // auto-route fallback chain must be consumed on this path too.
        attemptProviderFallback(for: pill)
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

    private func handle(messages: [ChatMessage], since: Int, for pill: AgentPill) {
        guard messages.count > since else { return }
        let recent = Array(messages.suffix(from: since))
        // Any real assistant output (streamed text or tool/thinking blocks)
        // marks the attempt as executing — from that point on, provider
        // startup fallback is permanently off for the attempt (hard safety
        // rule in attemptProviderStartupFallback).
        if !pill.hasProducedTaskOutput,
            recent.contains(where: { message in
                message.sender == .ai
                    && (!message.contentBlocks.isEmpty
                        || !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }) {
            pill.markTaskOutputProduced()
        }
        let displayMessages = recent.filter { message in
            let trimmed = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
            return message.sender == .user
                || !trimmed.isEmpty
                || message.isStreaming
                || !message.contentBlocks.isEmpty
                || !message.displayResources.isEmpty
        }
        if !displayMessages.isEmpty {
            pill.conversationMessages = pill.providerFallbackNotices + displayMessages
            pill.markContentChanged()
        }
        guard let aiMessage = recent.last(where: { $0.sender == .ai }) else { return }
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

    private func complete(pill: AgentPill, provider: ChatProvider, finalText: String?, allowStartupFallback: Bool = false) {
        let trimmedFinalText = finalText?.trimmingCharacters(in: .whitespacesAndNewlines)
        // Startup fallback runs before any terminal state is committed so a
        // directed provider that failed to start can hand the same brief to
        // the next provider in the chain. Only initial runs are eligible —
        // follow-up turns (continueAgent) never retry on another provider —
        // and only runs whose structured failure proves the adapter never
        // began executing (see startupFallbackFailure).
        if allowStartupFallback,
            trimmedFinalText?.isEmpty != false,
            let startupFailure = Self.startupFallbackFailure(
                projection: AgentRuntimeStatusStore.shared.floatingPillProjection(pillId: pill.id)),
            attemptProviderStartupFallback(for: pill, errorText: startupFailure.displayMessage) {
            return
        }
        if let trimmedFinalText, !trimmedFinalText.isEmpty {
            if pill.aiMessage?.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false {
                var finalMessage = pill.aiMessage ?? ChatMessage(text: trimmedFinalText, sender: .ai)
                finalMessage.text = trimmedFinalText
                finalMessage.isStreaming = false
                pill.aiMessage = finalMessage
                if pill.conversationMessages.isEmpty {
                    pill.conversationMessages = [
                        ChatMessage(text: pill.query, sender: .user),
                        finalMessage,
                    ]
                } else if let index = pill.conversationMessages.firstIndex(where: { $0.id == finalMessage.id }) {
                    pill.conversationMessages[index] = finalMessage
                } else {
                    pill.conversationMessages.append(finalMessage)
                }
            }
            pill.latestActivity = String(trimmedFinalText.prefix(140))
            pill.markContentChanged()
        }
        if let projection = AgentRuntimeStatusStore.shared.floatingPillProjection(pillId: pill.id) {
            Self.apply(projection: projection, to: pill)
            if projection.status.isTerminal {
                attemptProviderFallback(for: pill)
                pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
                if pill.viewedAt != nil {
                    scheduleViewedExpiration(for: pill)
                }
                return
            }
          }
        }
        if let errorText = provider.errorMessage, !errorText.isEmpty {
            pill.status = .failed(errorText)
            pill.latestActivity = errorText
            pill.completedAt = Date()
            Self.ensureFailureMessage(errorText, for: pill)
            pill.markContentChanged()
            attemptProviderFallback(for: pill)
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
            attemptProviderFallback(for: pill)
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

    /// Spawn a manually-driven setup pill that installs/repairs a local agent
    /// provider via AgentProviderInstaller's deterministic recipe, then — on a
    /// verified-healthy result — dispatches the user's original task to the
    /// freshly set-up provider. Consent must be collected upstream (voice
    /// confirmation or an explicit tool/bridge call).
    @discardableResult
    func spawnProviderSetup(provider: DirectedProvider, thenBrief: String?) -> AgentPill {
        let pill = AgentPill(query: "Set up \(provider.displayName)", model: ModelQoS.Claude.defaultSelection)
        pill.title = "Setting up \(provider.displayName)"
        pill.status = .running
        pill.latestActivity = "Checking \(provider.displayName)…"
        trimForNewPillIfNeeded()
        pills.append(pill)

        let steps = AgentProviderInstaller.plan(for: provider)
        let dispatchBrief: @MainActor () -> Void = { [weak self, weak pill] in
            guard let self else { return }
            if let thenBrief, !thenBrief.isEmpty {
                let task = self.spawn(
                    query: thenBrief,
                    model: pill?.model ?? ModelQoS.Claude.defaultSelection,
                    fromVoice: false,
                    preFetchedTitle: provider.displayName,
                    bridgeHarnessOverride: provider.harnessMode
                )
                task.fallbackProviders = [nil]
            }
        }

        guard !steps.isEmpty else {
            pill.status = .done
            pill.completedAt = Date()
            pill.latestActivity = "\(provider.displayName) is already set up."
            pill.markContentChanged()
            dispatchBrief()
            return pill
        }

        let pillID = pill.id
        Task {
            let result = await AgentProviderInstaller.run(steps: steps) { line in
                Task { @MainActor in
                    guard let pill = AgentPillsManager.shared.pills.first(where: { $0.id == pillID }) else { return }
                    pill.latestActivity = String(line.prefix(140))
                    pill.transcript.append(line)
                    pill.markContentChanged()
                }
            }
            // The shared Node runtime reads adapter commands from its
            // environment only at process start, so a provider installed
            // mid-session is invisible to a running runtime ("Adapter not
            // registered"). Restart it before dispatching the task; if a
            // request is momentarily active, retry once. Dispatch is gated on
            // the restart succeeding — dispatching into a stale runtime would
            // fail and fall back to the default orchestrator, silently
            // substituting a provider the user explicitly asked for.
            var runtimeRestarted = false
            if case .success = result, AgentProviderHealth.report(for: provider).readiness == .ready {
                await MainActor.run {
                    guard let pill = AgentPillsManager.shared.pills.first(where: { $0.id == pillID }) else { return }
                    pill.latestActivity = "Restarting agent runtime to pick up \(provider.displayName)…"
                    pill.markContentChanged()
                }
                for attempt in 1...2 {
                    do {
                        try await AgentRuntimeProcess.shared.restart(harnessMode: provider.harnessMode.rawValue)
                        runtimeRestarted = true
                        break
                    } catch {
                        log("AgentPills: runtime restart after \(provider.rawValue) setup failed (attempt \(attempt)): \(error)")
                        if attempt == 1 {
                            try? await Task.sleep(nanoseconds: 2_000_000_000)
                        }
                    }
                }
            }
            await MainActor.run {
                guard let pill = AgentPillsManager.shared.pills.first(where: { $0.id == pillID }) else { return }
                switch result {
                case .success:
                    let health = AgentProviderHealth.report(for: provider)
                    if health.readiness == .ready, runtimeRestarted {
                        pill.status = .done
                        pill.completedAt = Date()
                        pill.latestActivity = "\(provider.displayName) is ready."
                        pill.markContentChanged()
                        dispatchBrief()
                    } else if health.readiness == .ready {
                        pill.status = .failed("Agent runtime is busy")
                        pill.completedAt = Date()
                        pill.latestActivity =
                            "\(provider.displayName) is installed, but the agent runtime is busy and couldn't restart. Ask for your task again in a moment."
                        pill.markContentChanged()
                    } else {
                        pill.status = .failed(health.detail)
                        pill.completedAt = Date()
                        pill.latestActivity = "Setup finished but \(provider.displayName) is still not ready: \(health.detail)"
                        pill.markContentChanged()
                    }
                case .failed(let step, let message):
                    pill.status = .failed("\(step): \(message)")
                    pill.completedAt = Date()
                    pill.latestActivity = "Setup failed at \(step): \(message)"
                    pill.markContentChanged()
                }
            }
        }
        return pill
    }

    /// Consume the pill's auto-route fallback chain after a terminal failure:
    /// respawn the same task on the next installed provider (a `nil` hop is the
    /// default Omi orchestrator). Idempotent — the chain is consumed on first
    /// call, so repeated terminal projections can't spawn duplicate retries.
    @discardableResult
    func attemptProviderFallback(for pill: AgentPill) -> Bool {
        guard case .failed = pill.status else { return false }
        guard !pill.fallbackProviders.isEmpty else { return false }
        var chain = pill.fallbackProviders
        pill.fallbackProviders = []

        var hop: DirectedProvider?
        var foundHop = false
        while !chain.isEmpty {
            let candidate = chain.removeFirst()
            if let provider = candidate {
                if AgentProviderHealth.report(for: provider).readiness == .ready {
                    hop = provider
                    foundHop = true
                    break
                }
            } else {
                hop = nil  // default Omi orchestrator terminal fallback
                foundHop = true
                break
            }
        }
        guard foundHop else { return false }

        let display = hop?.displayName ?? "Omi"
        log("AgentPills: pill '\(pill.title)' failed — falling back to \(display)")
        pill.latestActivity = "Failed — retrying with \(display)"
        pill.markContentChanged()

        let successor = spawn(
            query: pill.query,
            model: pill.model,
            fromVoice: false,
            preFetchedTitle: pill.title,
            bridgeHarnessOverride: hop?.harnessMode
        )
        successor.fallbackProviders = chain
        successor.latestActivity = "Retrying via \(display)…"
        successor.markContentChanged()
        return true
    }

    private static func ensureFailureMessage(_ errorText: String, for pill: AgentPill) {
        guard let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorText) else { return }
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

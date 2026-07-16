import Combine
import Foundation

/// Owns in-flight import connector runs so progress, success, and failure
/// survive the connector sheet being closed and reopened, and so the same
/// connector cannot be started twice while a run is in flight.
///
/// Memory-only by design: a run dies with the process, so persisting run
/// state would show progress for work that no longer exists after relaunch.
/// A failed run's state is retained until the next run for the same connector
/// starts, so an error landing while the sheet is closed still surfaces on
/// reopen. A succeeded run's state is retained only until it has been shown
/// and dismissed (see `acknowledgeSuccess`); after that the persisted
/// connector snapshot is the source of truth.
@MainActor
final class ConnectorImportRunner: ObservableObject {
  static let shared = ConnectorImportRunner()

  enum Phase: Equatable {
    case running
    case succeeded
    case failed
  }

  struct RunState: Equatable {
    var phase: Phase
    var progressTitle: String
    var progressDetail: String
    var statusMessage: String?
    var errorMessage: String?
  }

  enum RunOutcome {
    case success(message: String)
    case failure(message: String)
  }

  /// Live progress reporting handed to a run's operation. Updates are
  /// dropped once the run they were issued for is no longer the current
  /// run, so a sink leaked past completion cannot corrupt a newer run.
  struct ProgressSink {
    fileprivate weak var runner: ConnectorImportRunner?
    fileprivate let connectorID: String
    fileprivate let runToken: UUID

    @MainActor
    func update(title: String, detail: String) {
      runner?.applyProgress(connectorID: connectorID, runToken: runToken, title: title, detail: detail)
    }
  }

  @Published private(set) var runs: [String: RunState] = [:]

  private var tasks: [String: Task<Void, Never>] = [:]
  private var runTokens: [String: UUID] = [:]

  func isRunning(_ connectorID: String) -> Bool {
    tasks[connectorID] != nil
  }

  /// Starts a run for the connector and owns its task. Ignored when a run
  /// for the same connector is already in flight. Returns the run's task
  /// so callers (and tests) can await completion, or nil when deduplicated.
  @discardableResult
  func start(
    connectorID: String,
    progressTitle: String,
    progressDetail: String,
    operation: @escaping @MainActor (ProgressSink) async -> RunOutcome
  ) -> Task<Void, Never>? {
    guard tasks[connectorID] == nil else { return nil }

    let token = UUID()
    runTokens[connectorID] = token
    runs[connectorID] = RunState(
      phase: .running,
      progressTitle: progressTitle,
      progressDetail: progressDetail,
      statusMessage: nil,
      errorMessage: nil
    )

    let sink = ProgressSink(runner: self, connectorID: connectorID, runToken: token)
    let task = Task { [weak self] in
      let outcome = await operation(sink)
      self?.finish(connectorID: connectorID, runToken: token, outcome: outcome)
    }
    tasks[connectorID] = task
    return task
  }

  /// Clears a succeeded run's retained state once the user has seen it —
  /// call when a sheet that displayed the success is dismissed. Failed runs
  /// are deliberately kept until the next start so an error that lands
  /// while the sheet is closed still surfaces on reopen.
  func acknowledgeSuccess(connectorID: String) {
    guard tasks[connectorID] == nil, runs[connectorID]?.phase == .succeeded else { return }
    runs[connectorID] = nil
    runTokens[connectorID] = nil
  }

  private func applyProgress(connectorID: String, runToken: UUID, title: String, detail: String) {
    guard runTokens[connectorID] == runToken, runs[connectorID]?.phase == .running else { return }
    runs[connectorID]?.progressTitle = title
    runs[connectorID]?.progressDetail = detail
  }

  private func finish(connectorID: String, runToken: UUID, outcome: RunOutcome) {
    guard runTokens[connectorID] == runToken, var state = runs[connectorID] else { return }
    tasks[connectorID] = nil
    switch outcome {
    case .success(let message):
      state.phase = .succeeded
      state.statusMessage = message
      state.errorMessage = nil
    case .failure(let message):
      state.phase = .failed
      state.statusMessage = nil
      state.errorMessage = message
    }
    runs[connectorID] = state
  }
}

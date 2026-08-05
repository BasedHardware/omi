import Foundation

/// Translates between the connector import vocabulary
/// (`ConnectorImportOperations.Outcome`, `ConnectorImportRunner.RunOutcome`)
/// and the background refresh vocabulary (``ConnectorRefreshResult``).
///
/// Pure and total: every `IntegrationConnectTelemetry.ErrorClass` case lands in
/// exactly one bucket via an exhaustive switch, so a newly added class cannot
/// silently default into "retry forever". `ConnectorRefreshOutcomeMapperTests`
/// pins the full table.
@MainActor
enum ConnectorRefreshOutcomeMapper {
  /// Maps a connector import outcome to a refresh result.
  static func result(from outcome: ConnectorImportOperations.Outcome) -> ConnectorRefreshResult {
    switch outcome {
    case .success(let syncResult, _):
      return .success(
        ConnectorRefreshMetrics(
          sourceCount: syncResult.sourceCount,
          memoryCount: syncResult.memoryCount,
          newItems: syncResult.newItems
        )
      )
    case .failure(let message, let failureClass):
      let reason = failureClass ?? IntegrationConnectTelemetry.ErrorClass.fromMessage(message)
      return result(for: reason)
    }
  }

  /// Buckets a closed failure class.
  ///
  /// - Credential, grant, and configuration classes park the connector: retrying
  ///   them unattended either fails identically or raises a consent dialog.
  /// - `.noContent` is a **success** with zero counts. A read that legitimately
  ///   found nothing is not a failure and must not consume a retry budget.
  /// - Everything else is transient and gets exponential backoff.
  static func result(for reason: ConnectorRefreshFailureReason) -> ConnectorRefreshResult {
    switch reason {
    case .notSignedIn, .sessionExpired, .noBrowser, .decryptFailed, .configuration,
      .storeNotFound, .authorizationDenied, .permission, .authentication:
      return .needsUserAction(reason: reason)
    case .noContent:
      return .success(ConnectorRefreshMetrics(sourceCount: 0, memoryCount: 0, newItems: 0))
    case .network, .timeout, .cancelled, .rateLimit, .conflict, .invalidResponse,
      .resourceExhausted, .unknown:
      return .transientFailure(reason: reason)
    }
  }

  /// True for the classes that only a user-initiated reconnect can clear.
  /// Drives the `auth` vs `other` fallback reason dimension.
  static func isUserActionClass(_ reason: ConnectorRefreshFailureReason) -> Bool {
    if case .needsUserAction = result(for: reason) { return true }
    return false
  }

  /// Bridges a refresh result back to the shared import runner, which owns
  /// single-flight, run state, and the terminal telemetry emit. Messages are
  /// short, bounded, and content-free.
  static func runOutcome(
    for result: ConnectorRefreshResult,
    connectorID: String
  ) -> ConnectorImportRunner.RunOutcome {
    let name = IntegrationConnectTelemetry.integrationName(forConnectorID: connectorID)
    switch result {
    case .success(let metrics):
      return .success(
        message: successMessage(name: name, metrics: metrics),
        metrics: ConnectorImportRunner.RunMetrics(
          sourceCount: metrics.sourceCount,
          memoryCount: metrics.memoryCount
        )
      )
    case .transientFailure(let reason):
      return .failure(
        message: "\(name) sync didn't complete. Omi will retry automatically.",
        metrics: ConnectorImportRunner.RunMetrics(failureClass: reason)
      )
    case .needsUserAction(let reason):
      return .failure(
        message: "\(name) needs to be reconnected before it can sync again.",
        metrics: ConnectorImportRunner.RunMetrics(failureClass: reason)
      )
    }
  }

  private static func successMessage(name: String, metrics: ConnectorRefreshMetrics) -> String {
    guard let newItems = metrics.newItems, newItems > 0 else {
      return "\(name) is up to date."
    }
    return "\(name) synced \(newItems.formatted()) new items."
  }
}

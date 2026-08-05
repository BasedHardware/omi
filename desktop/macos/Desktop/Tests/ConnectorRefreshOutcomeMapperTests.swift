import XCTest

@testable import Omi_Computer

/// Pins the full failure-class → refresh-result table. The mapper's switch is
/// exhaustive, so a newly added `ErrorClass` case is a compile error there — and
/// `testEveryErrorClassCaseIsMapped` makes it a test failure here too, forcing a
/// deliberate bucket choice instead of a silent default.
@MainActor
final class ConnectorRefreshOutcomeMapperTests: XCTestCase {
  /// Expected bucket for every case of `IntegrationConnectTelemetry.ErrorClass`.
  private enum Bucket {
    case needsUserAction
    case transientFailure
    case success
  }

  private let expected: [IntegrationConnectTelemetry.ErrorClass: Bucket] = [
    .notSignedIn: .needsUserAction,
    .sessionExpired: .needsUserAction,
    .noBrowser: .needsUserAction,
    .decryptFailed: .needsUserAction,
    .configuration: .needsUserAction,
    .storeNotFound: .needsUserAction,
    .authorizationDenied: .needsUserAction,
    .permission: .needsUserAction,
    .authentication: .needsUserAction,
    .noContent: .success,
    .network: .transientFailure,
    .timeout: .transientFailure,
    .cancelled: .transientFailure,
    .rateLimit: .transientFailure,
    .conflict: .transientFailure,
    .invalidResponse: .transientFailure,
    .resourceExhausted: .transientFailure,
    .unknown: .transientFailure,
  ]

  private func bucket(of result: ConnectorRefreshResult) -> Bucket {
    switch result {
    case .success: return .success
    case .transientFailure: return .transientFailure
    case .needsUserAction: return .needsUserAction
    }
  }

  func testAuthFailureClassesMapToNeedsUserAction() {
    let authClasses: [IntegrationConnectTelemetry.ErrorClass] = [
      .notSignedIn, .sessionExpired, .authentication, .authorizationDenied,
      .decryptFailed, .noBrowser, .permission, .storeNotFound, .configuration,
    ]

    for errorClass in authClasses {
      let outcome = ConnectorImportOperations.Outcome.failure(
        message: "connector failed",
        failureClass: errorClass
      )
      XCTAssertEqual(
        ConnectorRefreshOutcomeMapper.result(from: outcome),
        .needsUserAction(reason: errorClass),
        "\(errorClass.rawValue) must park the connector rather than retry into a dialog"
      )
      XCTAssertTrue(ConnectorRefreshOutcomeMapper.isUserActionClass(errorClass))
    }
  }

  func testNetworkAndTimeoutMapToTransientFailure() {
    for errorClass in [IntegrationConnectTelemetry.ErrorClass.network, .timeout, .rateLimit] {
      let outcome = ConnectorImportOperations.Outcome.failure(
        message: "connector failed",
        failureClass: errorClass
      )
      XCTAssertEqual(
        ConnectorRefreshOutcomeMapper.result(from: outcome),
        .transientFailure(reason: errorClass)
      )
      XCTAssertFalse(ConnectorRefreshOutcomeMapper.isUserActionClass(errorClass))
    }
  }

  /// A read that legitimately found nothing is not a failure and must not
  /// consume the retry budget or park the connector.
  func testEmptyResultMapsToSuccessWithZeroItems() {
    let outcome = ConnectorImportOperations.Outcome.failure(
      message: "No durable memories found in that text.",
      failureClass: .noContent
    )

    XCTAssertEqual(
      ConnectorRefreshOutcomeMapper.result(from: outcome),
      .success(ConnectorRefreshMetrics(sourceCount: 0, memoryCount: 0, newItems: 0))
    )
  }

  func testSuccessOutcomeCarriesCounts() {
    let outcome = ConnectorImportOperations.Outcome.success(
      ConnectorImportOperations.SyncResult(sourceCount: 41, memoryCount: 7, newItems: 3),
      message: "done"
    )

    XCTAssertEqual(
      ConnectorRefreshOutcomeMapper.result(from: outcome),
      .success(ConnectorRefreshMetrics(sourceCount: 41, memoryCount: 7, newItems: 3))
    )
  }

  func testEveryErrorClassCaseIsMapped() {
    XCTAssertEqual(
      expected.count,
      IntegrationConnectTelemetry.ErrorClass.allCases.count,
      "a new ErrorClass case needs an explicit background-refresh bucket — "
        + "defaulting it into transient retry would loop against a dead credential"
    )

    for errorClass in IntegrationConnectTelemetry.ErrorClass.allCases {
      guard let expectedBucket = expected[errorClass] else {
        XCTFail("\(errorClass.rawValue) has no declared background-refresh bucket")
        continue
      }
      XCTAssertEqual(
        bucket(of: ConnectorRefreshOutcomeMapper.result(for: errorClass)),
        expectedBucket,
        "\(errorClass.rawValue) landed in the wrong bucket"
      )
    }
  }

  func testRunOutcomeThreadsFailureClassAndStaysContentFree() {
    let failure = ConnectorRefreshOutcomeMapper.runOutcome(
      for: .needsUserAction(reason: .sessionExpired),
      connectorID: "calendar"
    )

    switch failure {
    case .failure(let message, let metrics):
      XCTAssertEqual(metrics.failureClass, .sessionExpired)
      XCTAssertEqual(message, "Google Calendar needs to be reconnected before it can sync again.")
    case .success:
      XCTFail("needsUserAction must map to a runner failure")
    }

    let success = ConnectorRefreshOutcomeMapper.runOutcome(
      for: .success(ConnectorRefreshMetrics(sourceCount: 9, memoryCount: 4, newItems: 2)),
      connectorID: "apple-notes"
    )

    switch success {
    case .success(let message, let metrics):
      XCTAssertEqual(metrics.sourceCount, 9)
      XCTAssertEqual(metrics.memoryCount, 4)
      XCTAssertEqual(message, "Apple Notes synced 2 new items.")
    case .failure:
      XCTFail("success must map to a runner success")
    }
  }
}

import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class DesktopUpdatePolicyManagerTests: XCTestCase {
  private enum FetchError: Error {
    case unavailable
  }

  private actor PolicySequence {
    private var results: [Result<DesktopUpdatePolicyResponse, FetchError>]

    init(_ results: [Result<DesktopUpdatePolicyResponse, FetchError>]) {
      self.results = results
    }

    func next() throws -> DesktopUpdatePolicyResponse {
      try results.removeFirst().get()
    }
  }

  func testMalformedRequiredPolicyUsesStableManualRecoveryPage() throws {
    let data = Data(
      """
      {
        "id": "legacy-repair",
        "active": true,
        "severity": "required",
        "download_url": "file:///Applications/Omi.app",
        "can_dismiss": false
      }
      """.utf8
    )

    let policy = try JSONDecoder().decode(DesktopUpdatePolicyResponse.self, from: data)

    XCTAssertTrue(policy.isRequired)
    XCTAssertEqual(policy.downloadURL, DesktopUpdatePolicyResponse.stableManualDownloadURL.absoluteString)
    XCTAssertFalse(policy.canDismiss)
  }

  func testMalformedPolicyCannotBecomeBlocking() throws {
    let data = Data(
      """
      {
        "id": 42,
        "active": "yes",
        "severity": "critical",
        "cta_text": 7,
        "download_url": "javascript:alert(1)"
      }
      """.utf8
    )

    let policy = try JSONDecoder().decode(DesktopUpdatePolicyResponse.self, from: data)

    XCTAssertFalse(policy.active)
    XCTAssertEqual(policy.severity, .none)
    XCTAssertEqual(policy.ctaText, "Download latest")
    XCTAssertEqual(policy.downloadURL, DesktopUpdatePolicyResponse.stableManualDownloadURL.absoluteString)
  }

  func testUnavailableRefreshClearsStaleRequiredPolicy() async {
    let required = DesktopUpdatePolicyResponse(
      id: "legacy-repair",
      active: true,
      severity: .required,
      maximumBuildNumber: 11507,
      latestBuildNumber: 12070,
      title: "Update required",
      message: "Install the latest Omi desktop app.",
      ctaText: "Download latest",
      downloadURL: DesktopUpdatePolicyResponse.stableManualDownloadURL.absoluteString,
      canDismiss: false
    )
    let sequence = PolicySequence([.success(required), .failure(.unavailable)])
    let suiteName = "DesktopUpdatePolicyManagerTests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let manager = DesktopUpdatePolicyManager(
      fetchPolicy: { _ in try await sequence.next() },
      currentBuildProvider: { 11400 },
      now: { Date(timeIntervalSince1970: 1_700_000_000) },
      defaults: defaults
    )

    await manager.refreshNow(force: true)
    XCTAssertEqual(manager.visiblePolicy?.id, "legacy-repair")

    await manager.refreshNow(force: true)
    XCTAssertNil(manager.visiblePolicy)
  }
}

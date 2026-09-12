import Foundation
import XCTest

/// Owns only its unique domain; cleanup cannot remove another fixture's keys.
final class IsolatedTestDefaults: Sendable {
  let suiteName = "omi.tests.\(UUID().uuidString)"

  /// Return an independently owned handle. Retaining that handle in a teardown
  /// closure would bind it to XCTest's actor and prevent async API injection.
  func makeDefaults() throws -> sending UserDefaults {
    try XCTUnwrap(UserDefaults(suiteName: suiteName))
  }

  func cleanUp() {
    UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName)
  }

  deinit {
    cleanUp()
  }
}

extension XCTestCase {
  /// Teardown retains the domain identity, never the subject's defaults handle.
  func makeIsolatedDefaults() throws -> sending UserDefaults {
    let fixture = IsolatedTestDefaults()
    addTeardownBlock { fixture.cleanUp() }
    return try fixture.makeDefaults()
  }
}

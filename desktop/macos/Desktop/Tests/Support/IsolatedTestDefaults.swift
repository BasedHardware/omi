import Foundation
import XCTest

/// Owns only its unique domain; cleanup cannot remove another fixture's keys.
final class IsolatedTestDefaults {
  let suiteName = "omi.tests.\(UUID().uuidString)"
  let defaults: UserDefaults

  init() throws {
    defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
  }

  func cleanUp() {
    defaults.removePersistentDomain(forName: suiteName)
  }

  deinit {
    cleanUp()
  }
}

extension XCTestCase {
  /// Teardown retains the domain owner even if the subject retains the defaults.
  @MainActor
  func makeIsolatedDefaults() throws -> UserDefaults {
    let fixture = try IsolatedTestDefaults()
    addTeardownBlock { fixture.cleanUp() }
    return fixture.defaults
  }
}

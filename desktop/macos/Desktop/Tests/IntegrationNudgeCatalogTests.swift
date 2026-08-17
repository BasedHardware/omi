import XCTest

@testable import Omi_Computer

/// The catalog is data, and wrong data here is invisible until a user sees the
/// wrong card. These are the structural invariants a reviewer would otherwise
/// have to check by eye on every future entry.
final class IntegrationNudgeCatalogTests: XCTestCase {
  func testEveryRouteResolvesToARealConnectorOrDestination() {
    let importIDs = Set(ImportConnector.all.map(\.id))
    let exportIDs = Set(MemoryExportDestination.allCases.map(\.rawValue))

    for entry in IntegrationNudgeCatalog.all {
      switch entry.route {
      case .importConnector(let id):
        XCTAssertTrue(
          importIDs.contains(id),
          "catalog entry '\(id)' has no matching ImportConnector, so its Connect button opens nothing"
        )
      case .exportDestination(let id):
        XCTAssertTrue(
          exportIDs.contains(id),
          "catalog entry '\(id)' has no matching MemoryExportDestination"
        )
      }
    }
  }

  /// The route id alone collides — ChatGPT and Claude are both an import and an
  /// export — so the telemetry id is what every store key and analytics
  /// dimension is built from. A duplicate would silently merge two
  /// integrations' nudge histories.
  func testTelemetryIDsAreUnique() {
    let ids = IntegrationNudgeCatalog.allTelemetryIDs
    XCTAssertEqual(Set(ids).count, ids.count, "duplicate telemetry ids: \(ids)")
  }

  func testChatGPTAndClaudeExistOnBothSidesWithDistinctIdentities() {
    XCTAssertNotNil(IntegrationNudgeCatalog.importEntry(connectorID: "chatgpt"))
    XCTAssertNotNil(IntegrationNudgeCatalog.exportEntry(destinationID: "chatgpt"))
    XCTAssertNotEqual(
      IntegrationNudgeCatalog.importEntry(connectorID: "chatgpt")?.telemetryID,
      IntegrationNudgeCatalog.exportEntry(destinationID: "chatgpt")?.telemetryID
    )
  }

  /// Every integration must carry onboarding copy, because the connector sheet
  /// renders it for both halves of the catalog. An entry with an empty pitch
  /// would render a heading over nothing.
  func testEveryEntryCarriesCompleteOnboardingCopy() {
    for entry in IntegrationNudgeCatalog.all {
      XCTAssertFalse(entry.displayName.isEmpty, "\(entry.telemetryID) has no display name")
      XCTAssertFalse(entry.pitch.isEmpty, "\(entry.telemetryID) has no pitch")
      XCTAssertFalse(entry.dataScope.isEmpty, "\(entry.telemetryID) does not say what Omi reads")
      XCTAssertEqual(
        entry.useCases.count, 3,
        "\(entry.telemetryID) should name exactly three concrete use cases"
      )
      for useCase in entry.useCases {
        XCTAssertFalse(useCase.isEmpty, "\(entry.telemetryID) has an empty use case")
      }
    }
  }

  /// Every connector the Apps tab can show must have onboarding copy, so the
  /// "What you get" section never silently disappears for one row.
  func testEveryImportConnectorHasCatalogCopy() {
    for connector in ImportConnector.all {
      XCTAssertNotNil(
        IntegrationNudgeCatalog.importEntry(connectorID: connector.id),
        "import connector '\(connector.id)' has no catalog entry"
      )
    }
  }

  func testEveryExportDestinationHasCatalogCopy() {
    for destination in MemoryExportDestination.allCases {
      XCTAssertNotNil(
        IntegrationNudgeCatalog.exportEntry(destinationID: destination.rawValue),
        "export destination '\(destination.rawValue)' has no catalog entry"
      )
    }
  }

  /// Every trigger the catalog declares must be reachable by the matcher. A
  /// browser keyword that no longer survives token-boundary matching, or an
  /// entry whose triggers were emptied, would silently stop nudging.
  func testEveryDeclaredTriggerActuallyMatchesSomething() {
    for entry in IntegrationNudgeCatalog.all {
      for trigger in entry.triggers {
        switch trigger.match {
        case .application(let identifiers):
          XCTAssertFalse(identifiers.isEmpty, "\(trigger.id) declares no bundle identifiers")
          for identifier in identifiers {
            let window = IntegrationNudgeMatcher.Window(bundleIdentifier: identifier)
            XCTAssertEqual(
              IntegrationNudgeMatcher.match(window)?.entry.telemetryID,
              entry.telemetryID,
              "\(identifier) does not resolve back to \(entry.telemetryID)"
            )
          }
        case .browserTitle(let keywords):
          XCTAssertFalse(keywords.isEmpty, "\(trigger.id) declares no keywords")
          for keyword in keywords {
            let window = IntegrationNudgeMatcher.Window(
              bundleIdentifier: "com.google.Chrome",
              windowTitle: "Some Page — \(keyword)"
            )
            XCTAssertEqual(
              IntegrationNudgeMatcher.match(window)?.entry.telemetryID,
              entry.telemetryID,
              "keyword '\(keyword)' does not resolve back to \(entry.telemetryID)"
            )
          }
        }
      }
    }
  }

  /// Trigger ids are a bounded telemetry dimension; a duplicate across
  /// integrations would make the analytics unattributable.
  func testTriggerIDsAreUnique() {
    let ids = IntegrationNudgeCatalog.all.flatMap { $0.triggers.map(\.id) }
    XCTAssertEqual(Set(ids).count, ids.count, "duplicate trigger ids: \(ids)")
  }

  /// A bundle identifier claimed by two integrations makes the match order
  /// silently decide the product behavior.
  func testNoBundleIdentifierIsClaimedTwice() {
    var seen: [String: String] = [:]
    for entry in IntegrationNudgeCatalog.all {
      for trigger in entry.triggers {
        guard case .application(let identifiers) = trigger.match else { continue }
        for identifier in identifiers {
          if let owner = seen[identifier] {
            XCTFail("bundle id '\(identifier)' claimed by both \(owner) and \(entry.telemetryID)")
          }
          seen[identifier] = entry.telemetryID
        }
      }
    }
  }

  /// Omi's own bundle must never be a trigger — nudging the user about an
  /// integration while they are looking at the Apps tab is noise.
  func testOmiIsNotATrigger() {
    let omiIdentifiers = ["com.omi.computer-macos", "com.omi.computer-macos.beta", "com.omi.desktop-dev"]
    for entry in IntegrationNudgeCatalog.all {
      for trigger in entry.triggers {
        guard case .application(let identifiers) = trigger.match else { continue }
        for omi in omiIdentifiers {
          XCTAssertFalse(identifiers.contains(omi), "\(entry.telemetryID) triggers on Omi itself")
        }
      }
    }
  }
}

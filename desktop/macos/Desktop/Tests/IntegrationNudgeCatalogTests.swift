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

  /// Real window titles, read out of a developer's own Chrome and Arc history
  /// (95,577 titles) and filtered to the sites themselves. Only the account
  /// addresses are replaced; every shape here is one a browser really produced.
  ///
  /// Synthesizing a title out of the keyword ("Some Page — \(keyword)") would
  /// match by construction and prove nothing — which is exactly how a round of
  /// domain-style keywords (`chatgpt.com`, `claude.ai`, `notion.so`) passed
  /// while matching nothing a browser ever puts in a window title. The same trap
  /// caught two entries in the previous version of this fixture: "Reviewing a
  /// diff \\ Claude" and "Swift concurrency question - ChatGPT" were invented,
  /// and neither shape occurs once in the corpus.
  private static let observedBrowserTitles: [String: [String]] = [
    "gmail_web": ["Gmail", "Inbox (16,993) - me@gmail.com - Gmail"],
    // Google Workspace names the mailbox after the organization, so "Gmail"
    // never appears. 51% of the corpus's Gmail visits look like this.
    "gmail_workspace_web": [
      "Inbox (3,012) - me@umn.edu - University of Minnesota Twin Cities Mail"
    ],
    "x_web": ["Home / X", "(3) Home / X", "Sam Altman (@sama) / X"],
    // 2,108 of 2,798 chatgpt.com visits (75%) are titled exactly "ChatGPT"; the
    // rest carry the conversation's own name and are unrecognizable by title.
    "chatgpt_web": ["ChatGPT"],
    "claude_web": [
      "Claude", "New chat - Claude",
      "Monthly recurring revenue to annual projection - Claude",
    ],
    // Gemini prefixes its title with an invisible left-to-right mark.
    "gemini_web": [
      "Google Gemini", "\u{200E}Google Gemini",
      "BCI Input Ideas: Games, Typing, Music - Google Gemini",
    ],
  ]

  /// Every browser trigger must match a title a browser actually produces, and
  /// every native trigger must resolve back to its own entry.
  func testEveryDeclaredTriggerMatchesSomethingReal() {
    for entry in IntegrationNudgeCatalog.all {
      for trigger in entry.triggers {
        switch trigger.match {
        case .application(let identifiers):
          XCTAssertFalse(identifiers.isEmpty, "\(trigger.id) declares no bundle identifiers")
          for identifier in identifiers {
            XCTAssertEqual(
              IntegrationNudgeMatcher.match(.init(bundleIdentifier: identifier))?.entry.telemetryID,
              entry.telemetryID,
              "\(identifier) does not resolve back to \(entry.telemetryID)"
            )
          }

        case .browserTitleSite, .browserTitleGoogleWorkspaceMailbox:
          if case .browserTitleSite(let names) = trigger.match {
            XCTAssertFalse(names.isEmpty, "\(trigger.id) declares no site names")
          }
          guard let titles = Self.observedBrowserTitles[trigger.id] else {
            // `continue`, not `return`: returning here would skip every later
            // entry's assertions, including the native-app round-trips.
            XCTFail("browser trigger '\(trigger.id)' has no observed real titles to test against")
            continue
          }
          for title in titles {
            XCTAssertEqual(
              IntegrationNudgeMatcher.match(
                .init(bundleIdentifier: "com.google.Chrome", windowTitle: title)
              )?.entry.telemetryID,
              entry.telemetryID,
              "real title '\(title)' does not resolve to \(entry.telemetryID)"
            )
          }
        }
      }
    }
  }

  /// Pages *about* a tool are the false positive that matters, because a wrong
  /// nudge is worse than a missing one.
  func testPagesAboutAToolAreNotThatTool() {
    for title in [
      "ChatGPT vs Claude — a comparison",
      "anthropics/claude-code: the CLI",
      "Notion alternatives in 2026 — Blog",
      "Google Calendar tips for 2026 — Blog",
      "Why I quit Twitter — Substack",
      "Gmail is down again - Hacker News",
    ] {
      XCTAssertNil(
        IntegrationNudgeMatcher.match(
          .init(bundleIdentifier: "com.google.Chrome", windowTitle: title)),
        "'\(title)' should not match any integration"
      )
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

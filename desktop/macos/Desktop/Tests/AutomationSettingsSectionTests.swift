import XCTest

@testable import Omi_Computer

/// SET-01: `omi-ctl navigate settings <section>` sends the caller's string verbatim
/// (the documented examples are lowercase, e.g. `settings rewind`), but
/// `SettingsSection` raw values are Title Case with spaces — so the old strict
/// `init(rawValue:)` never matched and navigation silently stayed on General.
/// `automationMatch` must accept the exact raw value plus reasonable variants.
final class AutomationSettingsSectionTests: XCTestCase {
  typealias Section = SettingsContentView.SettingsSection

  func testExactRawValuesStillMatch() {
    for section in Section.allCases {
      XCTAssertEqual(Section.automationMatch(section.rawValue), section)
    }
  }

  func testLowercaseSingleWordSectionsMatch() {
    XCTAssertEqual(Section.automationMatch("rewind"), .rewind)
    XCTAssertEqual(Section.automationMatch("general"), .general)
    XCTAssertEqual(Section.automationMatch("advanced"), .advanced)
    XCTAssertEqual(Section.automationMatch("shortcuts"), .shortcuts)
    XCTAssertEqual(Section.automationMatch("about"), .about)
  }

  func testMultiWordVariantsMatch() {
    // Case-name style
    XCTAssertEqual(Section.automationMatch("planUsage"), .planUsage)
    XCTAssertEqual(Section.automationMatch("plan_usage"), .planUsage)
    XCTAssertEqual(Section.automationMatch("plan-usage"), .planUsage)
    // Raw-value style
    XCTAssertEqual(Section.automationMatch("plan and usage"), .planUsage)
    XCTAssertEqual(Section.automationMatch("plan-and-usage"), .planUsage)
    XCTAssertEqual(Section.automationMatch("aichat"), .aiChat)
    XCTAssertEqual(Section.automationMatch("ai_chat"), .aiChat)
    XCTAssertEqual(Section.automationMatch("AI Chat"), .aiChat)
    XCTAssertEqual(Section.automationMatch("floating-bar"), .floatingBar)
    XCTAssertEqual(Section.automationMatch("floatingBar"), .floatingBar)
    XCTAssertEqual(Section.automationMatch("FLOATING BAR"), .floatingBar)
  }

  func testMergedSidebarAliasesKeepDeepLinksRoutable() {
    // Merged nav (Account & Plan, Notifications & Privacy): the absorbed section
    // ids must stay resolvable for automation/deep links and map to their merged
    // sidebar item.
    XCTAssertEqual(Section.automationMatch("privacy"), .privacy)
    XCTAssertEqual(Section.automationMatch("plan-usage"), .planUsage)
    XCTAssertEqual(Section.privacy.sidebarItem, .notifications)
    XCTAssertEqual(Section.planUsage.sidebarItem, .account)
    XCTAssertEqual(Section.account.sidebarItem, .account)
    XCTAssertEqual(Section.notifications.sidebarItem, .notifications)
    // Raw values are the automation snapshot contract (omi-hardening-smoke SET-01,
    // e2e flow waits) — merged display labels must not leak into them.
    XCTAssertEqual(Section.planUsage.rawValue, "Plan and Usage")
    XCTAssertEqual(Section.privacy.rawValue, "Privacy")
    XCTAssertEqual(Section.account.displayTitle, "Account & Plan")
    XCTAssertEqual(Section.notifications.displayTitle, "Notifications & Privacy")
  }

  func testUnknownAndEmptyReturnNil() {
    XCTAssertNil(Section.automationMatch("nonsense-section"))
    XCTAssertNil(Section.automationMatch(""))
    XCTAssertNil(Section.automationMatch("---"))
  }

  func testEveryCaseReachableFromItsCaseName() {
    for section in Section.allCases {
      XCTAssertEqual(
        Section.automationMatch(String(describing: section)), section,
        "case name '\(String(describing: section))' must resolve to its own section")
    }
  }

  func testNormalizedKeysAreUnambiguousAcrossSections() {
    // Future-proofing: if a new case's normalized rawValue or case name ever collides
    // with an existing section's keys, automationMatch would silently pick the
    // declaration-order winner. Fail loud here instead.
    var owner: [String: Section] = [:]
    for section in Section.allCases {
      let keys = Set(
        [section.rawValue, String(describing: section)].map { raw in
          String(raw.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) })
            .lowercased()
        })
      for key in keys {
        if let existing = owner[key], existing != section {
          XCTFail("normalized key '\(key)' is claimed by both \(existing) and \(section)")
        }
        owner[key] = section
      }
    }
  }

  func testNavigationHandlerUsesTolerantMatch() throws {
    // Source invariant: the automation navigation handler must go through
    // automationMatch, not the strict rawValue init that caused SET-01.
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/DesktopHomeView.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)
    // Identifier-independent: assert the handler resolves via the tolerant matcher and
    // never via the strict rawValue init (renaming a local or reformatting must not
    // break or bypass this invariant).
    XCTAssertTrue(source.contains("SettingsSection.automationMatch("))
    XCTAssertFalse(source.contains("SettingsSection(rawValue:"))
  }
}

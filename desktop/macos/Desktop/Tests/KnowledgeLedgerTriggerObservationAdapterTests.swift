import Foundation
import XCTest

@testable import Omi_Computer

final class KnowledgeLedgerTriggerObservationAdapterTests: XCTestCase {
  func testMapsRewindMetadataWithoutReadingImageOrVideoPaths() throws {
    let screenshot = Screenshot(
      id: 42,
      timestamp: Date(timeIntervalSince1970: 1_750_000_000),
      appName: "Slack",
      windowTitle: "#release — Omi",
      imagePath: "/private/should-not-be-read.jpg",
      videoChunkPath: "/private/should-not-be-read.mp4",
      frameOffset: 7,
      ocrText: "Ship the release after the budget review."
    )

    let observation = KnowledgeLedgerTriggerObservationAdapter.fromRewindScreenshot(screenshot)

    XCTAssertEqual(observation.eventID, "42")
    XCTAssertEqual(observation.text, "Ship the release after the budget review.")
    XCTAssertEqual(observation.appName, "slack")
    XCTAssertEqual(observation.windowTitle, "#release — omi")
    XCTAssertEqual(observation.occurredAt, screenshot.timestamp)

    let encoded = try JSONEncoder().encode(observation)
    let payload = try XCTUnwrap(String(data: encoded, encoding: .utf8))
    XCTAssertFalse(payload.contains("should-not-be-read"))
    XCTAssertFalse(payload.contains("imagePath"))
    XCTAssertFalse(payload.contains("videoChunkPath"))
  }

  func testObservationDrivesKeywordRegexAppAndWindowMatching() throws {
    let row = try KnowledgeLedgerTriggerRow(
      id: "rewind-release",
      triggerCondition: [
        "schema_version": "jit_trigger.v1",
        "match_mode": "all",
        "keywords": ["release"],
        "regex": [#"ship\s+the\s+release"#],
        "apps": ["Slack"],
        "windows": ["#release"],
      ]
    )
    let trigger = try compiled(row)
    let screenshot = Screenshot(
      id: 7,
      timestamp: Date(timeIntervalSince1970: 1_750_000_000),
      appName: "Slack",
      windowTitle: "#release — Omi",
      ocrText: "Ship the release after the budget review."
    )

    let decision = KnowledgeLedgerTriggerEvaluator.evaluate(
      trigger,
      observation: KnowledgeLedgerTriggerObservationAdapter.fromRewindScreenshot(screenshot),
      day: "2026-08-23"
    )

    XCTAssertEqual(decision.status, .match)
    XCTAssertEqual(decision.reason, "all_conditions_satisfied")
    XCTAssertEqual(decision.matchedConditions, ["app", "keywords", "regex", "window"])
  }

  func testBoundsOCRAndSelectorsAndPreservesMissingScreenshotID() {
    let longOCR = String(repeating: "x", count: KnowledgeLedgerTriggerObservation.maxTextCharacters + 500)
    let longApp = String(repeating: "A", count: KnowledgeLedgerTriggerObservationAdapter.maxSelectorCharacters + 40)
    let longWindow = String(repeating: "W", count: KnowledgeLedgerTriggerObservationAdapter.maxSelectorCharacters + 40)
    let screenshot = Screenshot(
      id: nil,
      appName: "  \(longApp)  ",
      windowTitle: "  \(longWindow)  ",
      ocrText: longOCR
    )

    let observation = KnowledgeLedgerTriggerObservationAdapter.fromRewindScreenshot(screenshot)

    XCTAssertNil(observation.eventID)
    XCTAssertEqual(observation.text.count, KnowledgeLedgerTriggerObservation.maxTextCharacters)
    XCTAssertEqual(observation.appName?.count, KnowledgeLedgerTriggerObservationAdapter.maxSelectorCharacters)
    XCTAssertEqual(observation.windowTitle?.count, KnowledgeLedgerTriggerObservationAdapter.maxSelectorCharacters)
  }

  func testEmptyOCRDoesNotCreateAKeywordMatch() throws {
    let row = try KnowledgeLedgerTriggerRow(
      id: "rewind-empty",
      triggerCondition: ["keywords": ["release"]]
    )
    let trigger = try compiled(row)
    let screenshot = Screenshot(id: nil, appName: "Slack", ocrText: nil)

    let decision = KnowledgeLedgerTriggerEvaluator.evaluate(
      trigger,
      observation: KnowledgeLedgerTriggerObservationAdapter.fromRewindScreenshot(screenshot),
      day: "2026-08-23"
    )

    XCTAssertEqual(decision.status, .noMatch)
    XCTAssertEqual(decision.reason, "condition_not_satisfied")
  }

  private func compiled(_ row: KnowledgeLedgerTriggerRow) throws -> KnowledgeLedgerCompiledTrigger {
    guard case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compile(row) else {
      XCTFail("expected valid trigger")
      throw KnowledgeLedgerTriggerCompileFailure.malformed("test fixture failed")
    }
    return trigger
  }
}

import XCTest

@testable import Omi_Computer

/// Regression coverage for `TaskSourceClassification` / `TaskSourceSubcategory`.
///
/// The task-extraction LLM schema (TaskAssistant tool schema) and the extraction
/// prompt both advertise a `commitment` subcategory ("user agreed/committed to
/// doing something asked of them"), but `TaskSourceSubcategory` had no matching
/// case. `TaskSourceSubcategory(rawValue: "commitment")` returned nil, so
/// `from(category:subcategory:)` dropped the whole classification — the
/// highest-signal committed-to tasks lost their origin and fell out of the
/// Direct Request filter.
final class TaskSourceClassificationTests: XCTestCase {
  func testCommitmentSubcategoryDecodes() {
    XCTAssertEqual(TaskSourceSubcategory(rawValue: "commitment"), .commitment)
  }

  func testCommitmentClassifiesUnderDirectRequest() {
    let classification = TaskSourceClassification.from(
      category: "direct_request", subcategory: "commitment")
    XCTAssertNotNil(classification, "A commitment task must not lose its classification")
    XCTAssertEqual(classification?.category, .direct_request)
    XCTAssertEqual(classification?.subcategory, .commitment)
    XCTAssertTrue(classification?.isValid ?? false)
  }

  func testCommitmentIsAValidDirectRequestSubcategory() {
    XCTAssertTrue(TaskSourceCategory.direct_request.validSubcategories.contains(.commitment))
  }
}

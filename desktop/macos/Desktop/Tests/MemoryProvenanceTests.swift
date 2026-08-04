import XCTest

@testable import Omi_Computer

/// "Where this came from" is only worth a section if it can answer the question.
/// It used to read four fields the memories API does not have — `source`,
/// `sourceApp`, `inputDeviceName`, `confidence` — so every synced memory
/// rendered the heading above a bare timestamp while its capture device and
/// capturing app sat in the data unread.
final class MemoryProvenanceTests: XCTestCase {

  func testCaptureDeviceIsReportedWhenTheServerSendsNoSourceField() {
    let memory = makeMemory()

    let facts = MemoryProvenance.facts(for: memory, deviceLabel: "Mac")

    XCTAssertEqual(facts.map(\.label), ["Mac"])
    XCTAssertEqual(facts.first?.icon, "laptopcomputer")
  }

  func testCapturingAppIsReadFromTheAppTag() {
    // The app is carried as a tag, not a field; reading only `sourceApp` meant
    // never naming the app for any memory that came back from the server.
    let memory = makeMemory(tags: ["focus", "focused", "app:Codex", "has-message"])

    let facts = MemoryProvenance.facts(for: memory, deviceLabel: "Mac")

    XCTAssertEqual(facts.map(\.label), ["Mac", "Codex"])
  }

  func testUnknownAppTagIsNotPresentedAsAnAnswer() {
    // "Unknown Application/Browser" is the extractor saying it could not tell.
    // Repeating it as provenance is worse than showing nothing.
    for value in ["app:Unknown", "app:Unknown Application/Browser", "app:   "] {
      let facts = MemoryProvenance.facts(for: makeMemory(tags: [value]), deviceLabel: nil)
      XCTAssertTrue(facts.isEmpty, "\(value) should not be presented as the capturing app")
    }
  }

  func testLocallyKnownFieldsStillDescribeAMemoryThatNeverRoundTripped() {
    let memory = makeMemory(
      manuallyAdded: true, source: "desktop", confidence: 0.82, inputDeviceName: "MacBook Pro Mic")

    let facts = MemoryProvenance.facts(for: memory, deviceLabel: nil)

    XCTAssertEqual(
      facts.map(\.label), ["Desktop", "Added by you", "MacBook Pro Mic", "82% confidence"])
  }

  /// The device label is the better answer when both exist: "This Mac" names
  /// the machine, "Desktop" only names the client kind.
  func testDeviceLabelSupersedesTheGenericSourceName() {
    let memory = makeMemory(source: "desktop")

    let facts = MemoryProvenance.facts(for: memory, deviceLabel: "This Mac")

    XCTAssertEqual(facts.map(\.label), ["This Mac"])
  }

  func testNothingKnownProducesNoChips() {
    XCTAssertTrue(MemoryProvenance.facts(for: makeMemory(), deviceLabel: nil).isEmpty)
  }

  private func makeMemory(
    tags: [String] = [],
    manuallyAdded: Bool = false,
    source: String? = nil,
    confidence: Double? = nil,
    inputDeviceName: String? = nil
  ) -> ServerMemory {
    ServerMemory(
      id: "m1",
      content: "content",
      category: .system,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: manuallyAdded,
      scoring: nil,
      source: source,
      confidence: confidence,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: tags,
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: inputDeviceName,
      windowTitle: nil,
      headline: nil
    )
  }
}

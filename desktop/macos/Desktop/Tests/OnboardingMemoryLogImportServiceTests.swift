import XCTest

@testable import Omi_Computer

final class OnboardingMemoryLogImportServiceTests: XCTestCase {
  func testIssue12442TenLineChatGPTExportParsesWithoutProvider() throws {
    let input = """
      [long-term] My name is Dennis Cox.
      [long-term] Call me Captain Stormy or Dennis.
      [long-term] I live in Edmonton, Alberta, Canada.
      [long-term] I am a Canadian Navy veteran.
      [long-term] I run Stormy Sailors Maker Lab.
      [long-term] I use Linux, macOS, WordPress, servers, QR systems, and maker technology.
      [long-term] I value direct communication and honest disagreement.
      [long-term] I prefer concise answers for simple questions and detailed explanations for complex ones.
      [long-term] My long-term goal is to live aboard a motor vessel on Canada's west coast.
      [long-term] The Tactical Pirate is one of my major maker projects.
      """

    let memories = try XCTUnwrap(
      OnboardingMemoryLogImportService.extractTaggedMemories(from: input))

    XCTAssertEqual(memories.count, 10)
    XCTAssertEqual(memories.first, "[long-term] My name is Dennis Cox.")
    XCTAssertEqual(
      memories.last,
      "[long-term] The Tactical Pirate is one of my major maker projects.")
  }

  func testTaggedParserHandlesExportWrappersBulletsUnknownAndDuplicates() throws {
    let input = """
      ```text
      - [recent] Prefers direct answers.
      2. [2026-08-30] Started a maker project.
      * [unknown] Enjoys sailing.
      [RECENT] Prefers direct answers.
      ```
      """

    let memories = try XCTUnwrap(
      OnboardingMemoryLogImportService.extractTaggedMemories(from: input))

    XCTAssertEqual(
      memories,
      [
        "[recent] Prefers direct answers.",
        "[2026-08-30] Started a maker project.",
        "Enjoys sailing.",
      ])
  }

  func testUnstructuredPasteDoesNotQualifyForLocalTaggedImport() {
    XCTAssertNil(
      OnboardingMemoryLogImportService.extractTaggedMemories(
        from: "I prefer concise answers and I enjoy sailing."))
  }

  func testMixedTaggedAndUntaggedPasteDoesNotSilentlyDropContent() {
    XCTAssertNil(
      OnboardingMemoryLogImportService.extractTaggedMemories(
        from: """
          [long-term] Prefers direct answers.
          Enjoys sailing.
          """))
  }

  func testExtractionErrorsMapToBoundedFailureClasses() {
    XCTAssertEqual(
      OnboardingMemoryLogImportService.failure(
        for: APIError.httpError(statusCode: 429, detail: "sensitive detail")),
      .rateLimited)
    XCTAssertEqual(
      OnboardingMemoryLogImportService.failure(
        for: APIError.httpError(statusCode: 503, detail: "sensitive detail")),
      .server)
    XCTAssertEqual(
      OnboardingMemoryLogImportService.failure(for: URLError(.notConnectedToInternet)),
      .network)
  }
}

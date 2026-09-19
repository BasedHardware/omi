import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the conversation summary pane's selection policy:
/// primary summary promotion (cross-platform selector parity), the
/// structured-overview fallback, secondary "App Insights" rows, and the
/// suggested-apps exclusion that the `$0` shadow used to break.
final class ConversationSummarySelectionTests: XCTestCase {
  private func conversation(
    appResults: [AppResponse],
    overview: String = "First-party overview",
    sections: [SummarySection] = []
  ) -> ServerConversation {
    ServerConversation(
      id: "conversation-1",
      createdAt: Date(timeIntervalSince1970: 1_700_000_000),
      updatedAt: nil,
      startedAt: Date(timeIntervalSince1970: 1_700_000_000),
      finishedAt: Date(timeIntervalSince1970: 1_700_000_060),
      structured: Structured(
        title: "Title",
        overview: overview,
        emoji: "💬",
        category: "other",
        actionItems: [],
        events: [],
        sections: sections
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: appResults,
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )
  }

  private func appResponse(appId: String?, content: String) throws -> AppResponse {
    let appIdJSON = appId.map { "\"\($0)\"" } ?? "null"
    let json = #"{"app_id": \#(appIdJSON), "content": "\#(content)"}"#
    return try JSONDecoder().decode(AppResponse.self, from: Data(json.utf8))
  }

  private func app(id: String, capabilities: [String] = ["memories"]) throws -> OmiApp {
    let capabilitiesJSON = capabilities.map { "\"\($0)\"" }.joined(separator: ",")
    let json = #"{"id": "\#(id)", "name": "\#(id)", "capabilities": [\#(capabilitiesJSON)]}"#
    return try JSONDecoder().decode(OmiApp.self, from: Data(json.utf8))
  }

  // MARK: - Primary summary

  func testAppAttributionUsesSourceKindEvenWithoutAnAppID() {
    let unattributed = ConversationSummarySelection.Primary(content: "App note", kind: .app, appId: nil, resultIndex: 0)
    XCTAssertEqual(unattributed.appDisplayName(resolvedName: nil), "Unknown App")
    XCTAssertEqual(unattributed.appDisplayName(resolvedName: " "), "Unknown App")
    XCTAssertEqual(unattributed.appDisplayName(resolvedName: " Custom App "), "Custom App")
    let overview = ConversationSummarySelection.Primary(content: "Note", kind: .overview, appId: nil, resultIndex: nil)
    XCTAssertNil(overview.appDisplayName(resolvedName: nil))
  }

  func testPrimarySummaryPromotesTheFirstAppResult() throws {
    let result = try appResponse(appId: "general-summary", content: "App-produced summary")
    let conversation = conversation(appResults: [result])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "App-produced summary")
    XCTAssertEqual(primary.kind, .app)
    XCTAssertEqual(primary.appId, "general-summary")
    XCTAssertEqual(primary.resultIndex, 0)
  }

  func testPrimarySummaryFallsBackToStructuredOverviewWithoutAppResults() {
    let conversation = conversation(appResults: [])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "First-party overview")
    XCTAssertEqual(primary.kind, .overview)
    XCTAssertNil(primary.appId)
    XCTAssertNil(primary.resultIndex)
  }

  func testPrimarySummaryFallsBackToStructuredOverviewWhenAppResultIsBlank() throws {
    let blank = try appResponse(appId: "general-summary", content: "")
    let conversation = conversation(appResults: [blank])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "First-party overview")
    XCTAssertEqual(primary.kind, .overview)
    XCTAssertNil(primary.appId)
  }

  func testPrimarySummarySkipsBlankLeadingResultsToTheNextUsableOne() throws {
    let blank = try appResponse(appId: "app-a", content: "")
    let usable = try appResponse(appId: "app-b", content: "B content")
    let conversation = conversation(appResults: [blank, usable])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "B content")
    XCTAssertEqual(primary.appId, "app-b")
    XCTAssertEqual(primary.resultIndex, 1)
  }

  // MARK: - Secondary (App Insights) rows

  func testSecondaryResultsExcludeThePromotedPrimary() throws {
    let first = try appResponse(appId: "app-a", content: "a")
    let second = try appResponse(appId: "app-b", content: "b")
    let conversation = conversation(appResults: [first, second])

    let secondary = ConversationSummarySelection.secondaryResults(for: conversation)

    XCTAssertEqual(secondary.map(\.result.appId), ["app-b"])
  }

  func testSecondaryResultsOmitBlankRows() throws {
    let blank = try appResponse(appId: "app-a", content: "")
    let conversation = conversation(appResults: [blank])

    let secondary = ConversationSummarySelection.secondaryResults(for: conversation)

    XCTAssertTrue(secondary.isEmpty)
  }

  func testSecondaryResultIdentitySurvivesDuplicateIDsAndUnattributedDecodes() throws {
    func decode() throws -> ServerConversation {
      conversation(appResults: [
        try appResponse(appId: "same", content: "Primary"),
        try appResponse(appId: "same", content: "Second"),
        try appResponse(appId: nil, content: "Third"),
        try appResponse(appId: nil, content: "Fourth"),
      ])
    }
    let first = ConversationSummarySelection.secondaryResults(for: try decode())
    let refreshed = ConversationSummarySelection.secondaryResults(for: try decode())
    XCTAssertEqual(first.map(\.id), [1, 2, 3])
    XCTAssertEqual(refreshed.map(\.id), first.map(\.id))
    XCTAssertEqual(first.map(\.result.content), ["Second", "Third", "Fourth"])
  }

  func testSourcesResolveOnlyLoadedTranscriptIdentitiesAndDeduplicate() {
    let segment = TranscriptSegment(
      id: "local", backendId: "backend", text: "Evidence.", speaker: "SPEAKER_00", isUser: false, personId: nil,
      start: 0, end: 1)
    XCTAssertEqual(
      ConversationSummarySelection.resolvableSourceIDs(
        ["missing", "backend", "backend", "local"], segments: [segment]), ["backend", "local"])
    XCTAssertEqual(ConversationSummarySelection.resolvableSourceIDs(["backend"], segments: []), [])
  }

  func testEvidenceInvalidationChangesDetailRevisionWithoutChangingSummaryText() {
    let sourced = SummarySection(heading: "Decision", bodyMarkdown: "Approved.", sourceSegmentIDs: ["old-source"])
    let cleared = SummarySection(heading: "Decision", bodyMarkdown: "Approved.", sourceSegmentIDs: [])
    let before = conversation(appResults: [], overview: "## Decision\n\nApproved.", sections: [sourced])
    let after = conversation(appResults: [], overview: "## Decision\n\nApproved.", sections: [cleared])
    XCTAssertNotEqual(
      ConversationSummaryRevision(conversation: before), ConversationSummaryRevision(conversation: after))
  }

  // MARK: - Suggested apps ($0-shadow regression)

  func testSuggestedAppsExcludeAppsThatAlreadyProducedResults() throws {
    let produced = try app(id: "app-a")
    let fresh = try app(id: "app-b")
    let chatOnly = try app(id: "app-c", capabilities: ["chat"])
    let result = try appResponse(appId: "app-a", content: "a")

    let suggested = ConversationSummarySelection.suggestedApps([produced, fresh, chatOnly], results: [result])

    XCTAssertEqual(suggested.map(\.id), ["app-b"])
  }

  func testSuggestedAppsRegressionInnerShadowComparedAResultToItself() throws {
    // The replaced inline closure compared `$0.appId == $0.id` on the
    // appsResults entry — always true — so ANY existing result emptied the
    // section. Here app-b never produced a result and must still be offered.
    let fresh = try app(id: "app-b")
    let unrelatedResult = try appResponse(appId: "app-a", content: "a")

    let suggested = ConversationSummarySelection.suggestedApps([fresh], results: [unrelatedResult])

    XCTAssertEqual(suggested.map(\.id), ["app-b"])
  }

  // MARK: - Shared parity contract

  func testSharedSummaryContractVectors() throws {
    let testFile = URL(fileURLWithPath: #filePath)
    let repositoryRoot =
      testFile
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let fixtureURL = repositoryRoot.appendingPathComponent("contracts/parity/conversation_summary.json")
    let fixture = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any])
    let cases = try XCTUnwrap(fixture["cases"] as? [[String: Any]])
    XCTAssertFalse(cases.isEmpty)

    for testCase in cases {
      let id = try XCTUnwrap(testCase["id"] as? String)
      let conversation = try conversation(from: try XCTUnwrap(testCase["conversation"] as? [String: Any]))
      let expected = try XCTUnwrap(testCase["expected"] as? [String: Any])
      let primary = ConversationSummarySelection.primarySummary(for: conversation)

      XCTAssertEqual(primary.kind.rawValue, try XCTUnwrap(expected["kind"] as? String), "case \(id)")
      XCTAssertEqual(primary.content, try XCTUnwrap(expected["content"] as? String), "case \(id)")
      XCTAssertEqual(primary.appId, expected["app_id"] as? String, "case \(id)")
      XCTAssertEqual(primary.resultIndex, expected["result_index"] as? Int, "case \(id)")
    }
  }

  private func conversation(from fixture: [String: Any]) throws -> ServerConversation {
    let structured = try XCTUnwrap(fixture["structured"] as? [String: Any])
    let sectionValues = (structured["sections"] as? [[String: Any]]) ?? []
    let sections = try sectionValues.map { value -> SummarySection in
      SummarySection(
        heading: try XCTUnwrap(value["heading"] as? String),
        bodyMarkdown: try XCTUnwrap(value["body_markdown"] as? String),
        sourceSegmentIDs: (value["source_segment_ids"] as? [String]) ?? []
      )
    }
    let appValues = (fixture["apps_results"] as? [[String: Any]]) ?? []
    let apps = try appValues.map { value -> AppResponse in
      let data = try JSONSerialization.data(withJSONObject: value)
      return try JSONDecoder().decode(AppResponse.self, from: data)
    }
    return conversation(
      appResults: apps,
      overview: (structured["overview"] as? String) ?? "",
      sections: sections
    )
  }
}

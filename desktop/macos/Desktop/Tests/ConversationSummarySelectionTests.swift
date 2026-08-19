import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the conversation summary pane's selection policy:
/// primary summary promotion (mobile `getSummarizedApp` parity), the
/// structured-overview fallback, secondary "App Insights" rows, and the
/// suggested-apps exclusion that the `$0` shadow used to break.
final class ConversationSummarySelectionTests: XCTestCase {
  private func conversation(
    appResults: [AppResponse],
    overview: String = "First-party overview"
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
        events: []
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

  func testPrimarySummaryPromotesTheFirstAppResult() throws {
    let result = try appResponse(appId: "general-summary", content: "App-produced summary")
    let conversation = conversation(appResults: [result])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "App-produced summary")
    XCTAssertEqual(primary.appId, "general-summary")
  }

  func testPrimarySummaryFallsBackToStructuredOverviewWithoutAppResults() {
    let conversation = conversation(appResults: [])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "First-party overview")
    XCTAssertNil(primary.appId)
  }

  func testPrimarySummaryFallsBackToStructuredOverviewWhenAppResultIsBlank() throws {
    let blank = try appResponse(appId: "general-summary", content: "")
    let conversation = conversation(appResults: [blank])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "First-party overview")
    XCTAssertNil(primary.appId)
  }

  func testPrimarySummarySkipsBlankLeadingResultsToTheNextUsableOne() throws {
    let blank = try appResponse(appId: "app-a", content: "")
    let usable = try appResponse(appId: "app-b", content: "B content")
    let conversation = conversation(appResults: [blank, usable])

    let primary = ConversationSummarySelection.primarySummary(for: conversation)

    XCTAssertEqual(primary.content, "B content")
    XCTAssertEqual(primary.appId, "app-b")
  }

  // MARK: - Secondary (App Insights) rows

  func testSecondaryResultsExcludeThePromotedPrimary() throws {
    let first = try appResponse(appId: "app-a", content: "a")
    let second = try appResponse(appId: "app-b", content: "b")
    let conversation = conversation(appResults: [first, second])

    let secondary = ConversationSummarySelection.secondaryResults(for: conversation)

    XCTAssertEqual(secondary.map(\.appId), ["app-b"])
  }

  func testSecondaryResultsKeepEverythingWhenNoResultIsUsable() throws {
    let blank = try appResponse(appId: "app-a", content: "")
    let conversation = conversation(appResults: [blank])

    let secondary = ConversationSummarySelection.secondaryResults(for: conversation)

    XCTAssertEqual(secondary.map(\.appId), ["app-a"])
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
}

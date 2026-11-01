import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationSummaryAppPickerTests: XCTestCase {
  private func app(
    id: String, name: String, author: String = "", capabilities: [String] = ["memories"],
    enabled: Bool = true
  ) throws -> OmiApp {
    let data = try JSONSerialization.data(withJSONObject: [
      "id": id, "name": name, "author": author, "capabilities": capabilities, "enabled": enabled,
    ])
    return try JSONDecoder().decode(OmiApp.self, from: data)
  }

  func testLoadsOnlyInstalledSummaryAppsAndSearchesNameOrAuthor() async throws {
    let summary = try app(id: "summary", name: "Meeting Notes", author: "Acme")
    let another = try app(id: "another", name: "Follow Ups", author: "Northstar")
    let chatOnly = try app(id: "chat", name: "Chat Helper", capabilities: ["chat"])
    let disabled = try app(id: "disabled", name: "Old Summary", enabled: false)
    let picker = ConversationSummaryAppPicker { _, _ in [summary, another, chatOnly, disabled] }

    await picker.load()

    XCTAssertEqual(picker.phase, .ready)
    XCTAssertEqual(picker.apps.map(\.id), ["summary", "another"])
    picker.searchText = "  NOTES  "
    XCTAssertEqual(picker.visibleApps.map(\.id), ["summary"])
    picker.searchText = "northSTAR"
    XCTAssertEqual(picker.visibleApps.map(\.id), ["another"])
    picker.searchText = "missing"
    XCTAssertTrue(picker.visibleApps.isEmpty)
    picker.searchText = " "
    XCTAssertEqual(picker.visibleApps.map(\.id), ["summary", "another"])
  }

  func testLoadsAllPagesWithoutDuplicatingApps() async throws {
    let firstPage = try (0..<100).map { try app(id: "app-\($0)", name: "App \($0)") }
    let finalApp = try app(id: "last", name: "Last")
    var offsets: [Int] = []
    let picker = ConversationSummaryAppPicker { offset, limit in
      XCTAssertEqual(limit, 100)
      offsets.append(offset)
      return offset == 0 ? firstPage : [firstPage[0], finalApp]
    }

    await picker.load()

    XCTAssertEqual(offsets, [0, 100])
    XCTAssertEqual(picker.apps.count, 101)
    XCTAssertEqual(picker.apps.last?.id, "last")
  }

  func testFailureCanRetryAndEmptyResponseIsNotAnError() async throws {
    enum FetchFailure: Error { case unavailable }
    let summary = try app(id: "summary", name: "Summary")
    var attempts = 0
    let picker = ConversationSummaryAppPicker { _, _ in
      attempts += 1
      if attempts == 1 { throw FetchFailure.unavailable }
      return attempts == 2 ? [summary] : []
    }

    await picker.load()
    XCTAssertEqual(picker.phase, .failed)
    XCTAssertTrue(picker.apps.isEmpty)

    await picker.load()
    XCTAssertEqual(picker.phase, .ready)
    XCTAssertEqual(picker.apps.map(\.id), ["summary"])

    await picker.load()
    XCTAssertEqual(picker.phase, .ready)
    XCTAssertTrue(picker.apps.isEmpty)
  }
}

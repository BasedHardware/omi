import GRDB
import XCTest

@testable import Omi_Computer

/// The legacy Insight assistant runs only when context buckets are off (the stable default), and
/// its SQL is chosen by a model reading on-screen OCR. These tests drive the production
/// investigation entry point against a real pool and assert it cannot mutate omi.db and never
/// returns excluded apps' rows, with no dependency on bucket state.
final class InsightInvestigationSQLTests: XCTestCase {
  private static func makePool() async throws -> (directory: URL, pool: DatabasePool) {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("insight-investigation-sql-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let pool = try DatabasePool(path: directory.appendingPathComponent("test.sqlite").path)
    try await pool.write { db in
      try db.execute(sql: "CREATE TABLE screenshots (id INTEGER PRIMARY KEY, appName TEXT, windowTitle TEXT)")
      try db.execute(sql: "CREATE TABLE action_items (id INTEGER PRIMARY KEY, completed INTEGER NOT NULL)")
      try db.execute(sql: "INSERT INTO screenshots VALUES (1, 'Xcode', 'visible-window')")
      try db.execute(sql: "INSERT INTO screenshots VALUES (2, 'Secrets', 'excluded-window')")
      try db.execute(sql: "INSERT INTO action_items VALUES (42, 0)")
    }
    return (directory, pool)
  }

  private static func investigate(_ query: String, pool: DatabasePool) async -> String {
    await InsightAssistant.executeInvestigationSQL(query, excludedApps: ["Secrets"]) { @MainActor toolCall in
      XCTAssertEqual(toolCall.name, "execute_sql")
      return await ChatToolExecutor.executeSQL(toolCall.arguments, dbQueue: pool, expectedOwnerID: nil)
    }
  }

  func testInvestigationSQLRefusesMutationsAndLeavesDatabaseUnchanged() async throws {
    let (directory, pool) = try await Self.makePool()
    defer { try? FileManager.default.removeItem(at: directory) }

    let readOnlyError = "Error: this SQL surface is read-only. Use SELECT or read-only WITH queries."
    let mutations = [
      "DELETE FROM screenshots WHERE id > 0",
      "UPDATE action_items SET completed = 1 WHERE id = 42",
      "INSERT INTO action_items (id, completed) VALUES (43, 0)",
      "WITH doomed AS (SELECT id FROM screenshots) DELETE FROM screenshots WHERE id IN doomed",
    ]
    for mutation in mutations {
      let result = await Self.investigate(mutation, pool: pool)
      XCTAssertEqual(result, readOnlyError, "mutation must be refused: \(mutation)")
    }

    let screenshotCount = try await pool.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM screenshots")
    }
    let actionItemCount = try await pool.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM action_items")
    }
    let completed = try await pool.read { db in
      try Int.fetchOne(db, sql: "SELECT completed FROM action_items WHERE id = 42")
    }
    XCTAssertEqual(screenshotCount, 2)
    XCTAssertEqual(actionItemCount, 1)
    XCTAssertEqual(completed, 0)
  }

  func testInvestigationSQLAppliesExcludedAppFilter() async throws {
    let (directory, pool) = try await Self.makePool()
    defer { try? FileManager.default.removeItem(at: directory) }

    let result = await Self.investigate("SELECT appName, windowTitle FROM screenshots", pool: pool)

    XCTAssertTrue(result.contains("visible-window"), "non-excluded rows stay visible: \(result)")
    XCTAssertFalse(result.contains("excluded-window"), "excluded app rows must not reach the model: \(result)")
    XCTAssertFalse(result.contains("Secrets"), "excluded app rows must not reach the model: \(result)")
  }

  func testInsightProductionLoopRoutesEverySQLCallThroughHardenedHelper() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // -> Tests/
      .deletingLastPathComponent()  // -> Desktop/
      .appendingPathComponent("Sources/ProactiveAssistants/Assistants/Insight/InsightAssistant.swift")
    // The behavioral tests above drive the helper; this guards that both investigation phases
    // still call it, rather than rebuilding an unfiltered, writable execute_sql call inline.
    // omi-test-quality: source-inspection -- static contract: Insight SQL must use the read-only filtered helper
    let source = try String(contentsOf: sourceURL, encoding: .utf8)
    XCTAssertEqual(
      source.components(separatedBy: "await Self.executeInvestigationSQL(query, excludedApps: excluded)").count - 1, 2,
      "Phase 1 and Phase 2 execute_sql handlers must both route through executeInvestigationSQL")
    XCTAssertEqual(
      source.components(separatedBy: "ChatToolExecutor.execute(").count - 1, 1,
      "only executeInvestigationSQL may hand a tool call to ChatToolExecutor")
    XCTAssertNil(
      source.range(of: "\"read_only\""),
      "read_only is set by InsightSQLPrivacy.investigationToolCall, never conditionally inline")
  }

  func testInvestigationToolCallIsAlwaysReadOnlyAndFiltered() {
    let toolCall = InsightSQLPrivacy.investigationToolCall(
      query: "SELECT id FROM screenshots", excludedApps: ["Secrets"])

    XCTAssertEqual(toolCall.name, "execute_sql")
    XCTAssertEqual(toolCall.arguments["read_only"] as? Bool, true)
    XCTAssertEqual(
      toolCall.arguments["query"] as? String,
      "SELECT id FROM (SELECT * FROM screenshots WHERE appName NOT IN ('Secrets')) AS screenshots")

    let unfilteredToolCall = InsightSQLPrivacy.investigationToolCall(
      query: "SELECT id FROM screenshots", excludedApps: [])
    XCTAssertEqual(unfilteredToolCall.arguments["read_only"] as? Bool, true)
  }
}

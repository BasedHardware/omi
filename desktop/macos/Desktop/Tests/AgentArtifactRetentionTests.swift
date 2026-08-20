import XCTest

@testable import Omi_Computer

/// Regression coverage for agent `tool-output` JSON retention.
///
/// Oversized control-tool results were written under
/// `~/Library/Application Support/Omi/Artifacts/.../tool-output` and never
/// deleted, filling disks. The sweep removes files older than a week and
/// leaves user-facing run artifacts alone.
final class AgentArtifactRetentionTests: XCTestCase {
  func testStaleFilesBeyondRetentionAreSelected() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let dir = URL(fileURLWithPath: "/tmp/omi-tool-output")
    let fresh = (url: dir.appendingPathComponent("fresh.json"), modified: now.addingTimeInterval(-60))
    let stale = (
      url: dir.appendingPathComponent("stale.json"),
      modified: now.addingTimeInterval(-(AgentArtifactRetention.toolOutputRetention + 60))
    )

    let purge = AgentArtifactRetention.staleToolOutputURLs(
      [fresh, stale], now: now, retention: AgentArtifactRetention.toolOutputRetention)

    XCTAssertEqual(purge, [stale.url], "only files older than the retention window are swept")
  }

  func testExactlyAtRetentionBoundaryIsKept() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let dir = URL(fileURLWithPath: "/tmp/omi-tool-output")
    let atBoundary = (
      url: dir.appendingPathComponent("boundary.json"),
      modified: now.addingTimeInterval(-AgentArtifactRetention.toolOutputRetention)
    )
    let purge = AgentArtifactRetention.staleToolOutputURLs(
      [atBoundary], now: now, retention: AgentArtifactRetention.toolOutputRetention)
    XCTAssertTrue(purge.isEmpty, "a file exactly at the boundary is not yet stale")
  }

  func testPruneDeletesExpiredToolOutputAndLeavesFreshAndUserArtifacts() throws {
    let fileManager = FileManager.default
    let root = fileManager.temporaryDirectory.appendingPathComponent(
      "omi-artifact-retention-\(UUID().uuidString)", isDirectory: true)
    defer { try? fileManager.removeItem(at: root) }

    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let staleDate = now.addingTimeInterval(-(AgentArtifactRetention.toolOutputRetention + 60))
    let freshDate = now.addingTimeInterval(-60)

    let staleURL =
      root
      .appendingPathComponent(AgentArtifactRetention.toolOutputDirectoryName, isDirectory: true)
      .appendingPathComponent("owner", isDirectory: true)
      .appendingPathComponent("session-old", isDirectory: true)
      .appendingPathComponent("list_agent_sessions-stale.json")
    let freshURL =
      root
      .appendingPathComponent(AgentArtifactRetention.toolOutputDirectoryName, isDirectory: true)
      .appendingPathComponent("owner", isDirectory: true)
      .appendingPathComponent("session-new", isDirectory: true)
      .appendingPathComponent("list_agent_sessions-fresh.json")
    let deliveredURL =
      root
      .appendingPathComponent("owner-1", isDirectory: true)
      .appendingPathComponent("session-1", isDirectory: true)
      .appendingPathComponent("run-1", isDirectory: true)
      .appendingPathComponent("attempt-1", isDirectory: true)
      .appendingPathComponent("answer.md")

    try fileManager.createDirectory(at: staleURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try fileManager.createDirectory(at: freshURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try fileManager.createDirectory(at: deliveredURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data("{\"sessions\":[]}\n".utf8).write(to: staleURL)
    try Data("{\"sessions\":[]}\n".utf8).write(to: freshURL)
    try Data("# keep me\n".utf8).write(to: deliveredURL)
    try fileManager.setAttributes([.modificationDate: staleDate], ofItemAtPath: staleURL.path)
    try fileManager.setAttributes([.modificationDate: freshDate], ofItemAtPath: freshURL.path)
    try fileManager.setAttributes([.modificationDate: staleDate], ofItemAtPath: deliveredURL.path)

    let deleted = AgentArtifactRetention.pruneExpiredToolOutputs(
      in: root, now: now, fileManager: fileManager)

    XCTAssertEqual(deleted, 1)
    XCTAssertFalse(fileManager.fileExists(atPath: staleURL.path))
    XCTAssertFalse(
      fileManager.fileExists(atPath: staleURL.deletingLastPathComponent().path),
      "empty session directories under tool-output should be removed")
    XCTAssertTrue(fileManager.fileExists(atPath: freshURL.path))
    XCTAssertEqual(try String(contentsOf: deliveredURL, encoding: .utf8), "# keep me\n")
  }
}

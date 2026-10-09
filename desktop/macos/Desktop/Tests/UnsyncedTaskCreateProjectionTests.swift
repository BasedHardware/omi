import Foundation
import XCTest

@testable import Omi_Computer

final class UnsyncedTaskCreateProjectionTests: XCTestCase {
  func testMinimalTaskPreservesAbsentOptionalValues() throws {
    let projection = try UnsyncedTaskCreateProjection(record: ActionItemRecord(description: "Call Alex"))

    XCTAssertEqual(projection.description, "Call Alex")
    XCTAssertFalse(projection.completed)
    XCTAssertNil(projection.dueAt)
    XCTAssertNil(projection.source)
    XCTAssertNil(projection.priority)
    XCTAssertNil(projection.category)
    XCTAssertNil(projection.metadataBox)
    XCTAssertNil(projection.relevanceScore)
    XCTAssertNil(projection.recurrenceRule)
    XCTAssertNil(projection.recurrenceParentId)
    XCTAssertNil(projection.goalId)
    XCTAssertNil(projection.workstreamId)
    XCTAssertNil(projection.owner)
    XCTAssertNil(projection.dueConfidence)
    XCTAssertNil(projection.provenance)
    XCTAssertNil(projection.status)
    XCTAssertNil(projection.sortOrder)
    XCTAssertNil(projection.indentLevel)
    XCTAssertNil(projection.conversationId)
    XCTAssertEqual(projection.isLocked, false)
  }

  func testProjectionPreservesLatestCreateSupportedFields() throws {
    let dueAt = Date(timeIntervalSince1970: 1_800_000_000)
    let record = ActionItemRecord(
      id: 41,
      description: "Send the updated report",
      completed: true,
      source: "manual",
      conversationId: "conversation-1",
      priority: "high",
      category: "work",
      dueAt: dueAt,
      recurrenceRule: "weekly",
      recurrenceParentId: "series-1",
      canonicalTaskId: "server-owned-canonical-id",
      taskStatus: "completed",
      taskOwner: "user",
      goalId: "goal-1",
      workstreamId: "workstream-1",
      dueConfidence: 0.95,
      provenanceJson: Self.fullProvenance,
      supersededBy: "server-owned-lineage-id",
      isLocked: true,
      screenshotId: 72,
      confidence: 0.8,
      sourceApp: "Local app",
      windowTitle: "Local window",
      contextSummary: "Local-only summary",
      currentActivity: "Local activity",
      metadataJson: #"{"source_category":"communication","tags":["report"],"confidence":0.8}"#,
      sortOrder: 12,
      indentLevel: 2,
      relevanceScore: 83,
      agentStatus: "completed",
      agentSessionName: "local-session",
      agentPrompt: "Local agent prompt",
      agentPlan: "Local agent plan",
      agentEditedFilesJson: #"["/private/example.txt"]"#,
      chatSessionId: "local-chat",
      fromStaged: true)

    let projection = try UnsyncedTaskCreateProjection(record: record)

    XCTAssertEqual(projection.description, record.description)
    XCTAssertTrue(projection.completed)
    XCTAssertEqual(projection.dueAt, dueAt)
    XCTAssertEqual(projection.source, "manual")
    XCTAssertEqual(projection.conversationId, "conversation-1")
    XCTAssertEqual(projection.priority?.rawValue, "high")
    XCTAssertEqual(projection.category, "work")
    XCTAssertEqual(projection.metadataBox?.value?["source_category"] as? String, "communication")
    XCTAssertEqual(projection.metadataBox?.value?["tags"] as? [String], ["report"])
    XCTAssertEqual(projection.metadataBox?.value?["confidence"] as? Double, 0.8)
    XCTAssertEqual(projection.relevanceScore, 83)
    XCTAssertEqual(projection.recurrenceRule, "weekly")
    XCTAssertEqual(projection.recurrenceParentId, "series-1")
    XCTAssertEqual(projection.goalId, "goal-1")
    XCTAssertEqual(projection.workstreamId, "workstream-1")
    XCTAssertEqual(projection.owner?.rawValue, "user")
    XCTAssertEqual(projection.dueConfidence, 0.95)
    XCTAssertEqual(projection.status?.rawValue, "completed")
    XCTAssertEqual(projection.sortOrder, 12)
    XCTAssertEqual(projection.indentLevel, 2)
    XCTAssertEqual(projection.isLocked, true)

    let evidence = try XCTUnwrap(projection.provenance?.first)
    XCTAssertEqual(projection.provenance?.count, 1)
    XCTAssertEqual(evidence.id, "conversation-1")
    XCTAssertEqual(evidence.kind.rawValue, "local_screen")
    XCTAssertEqual(evidence.scope.rawValue, "device_local")
    XCTAssertEqual(evidence.deviceId, "device-1")
    XCTAssertEqual(evidence.startSeconds, 12.5)
    XCTAssertEqual(evidence.endSeconds, 21.5)
    XCTAssertEqual(evidence.excerptHash, String(repeating: "a", count: 64))
    XCTAssertEqual(evidence.transcriptSegmentIds, ["segment-1", "segment-2"])
    XCTAssertEqual(evidence.version, "revision-2")
  }

  func testProjectionSnapshotsFieldsRatherThanRetainingMutableRecord() throws {
    var record = ActionItemRecord(
      description: "Latest local title", completed: true, recurrenceRule: "daily", taskOwner: "user")
    let projection = try UnsyncedTaskCreateProjection(record: record)
    record.description = "Changed later"
    record.completed = false
    record.recurrenceRule = nil
    record.taskOwner = "other"

    XCTAssertEqual(projection.description, "Latest local title")
    XCTAssertTrue(projection.completed)
    XCTAssertEqual(projection.recurrenceRule, "daily")
    XCTAssertEqual(projection.owner?.rawValue, "user")
  }

  func testKnownCanonicalEnumValuesArePreserved() throws {
    for priority in ["high", "medium", "low"] {
      let record = ActionItemRecord(description: "Task", priority: priority)
      XCTAssertEqual(try UnsyncedTaskCreateProjection(record: record).priority?.rawValue, priority)
    }
    for owner in ["user", "other", "unknown"] {
      let record = ActionItemRecord(description: "Task", taskOwner: owner)
      XCTAssertEqual(try UnsyncedTaskCreateProjection(record: record).owner?.rawValue, owner)
    }
    for status in ["active", "completed", "cancelled", "superseded"] {
      let record = ActionItemRecord(description: "Task", completed: status == "completed", taskStatus: status)
      XCTAssertEqual(try UnsyncedTaskCreateProjection(record: record).status?.rawValue, status)
    }
  }

  func testLatestOfflineCompletionWinsOverCachedActiveStatus() throws {
    let record = ActionItemRecord(description: "Task", completed: true, taskStatus: "active")
    let projection = try UnsyncedTaskCreateProjection(record: record)

    XCTAssertTrue(projection.completed)
    XCTAssertEqual(projection.status?.rawValue, "completed")
  }

  func testLatestOfflineUndoWinsOverCachedCompletedStatus() throws {
    let record = ActionItemRecord(description: "Task", completed: false, taskStatus: "completed")
    let projection = try UnsyncedTaskCreateProjection(record: record)

    XCTAssertFalse(projection.completed)
    XCTAssertEqual(projection.status?.rawValue, "active")
  }

  func testAbsentStatusStaysOmittedWhenTaskIsCompleted() throws {
    let record = ActionItemRecord(description: "Task", completed: true)
    let projection = try UnsyncedTaskCreateProjection(record: record)

    XCTAssertTrue(projection.completed)
    XCTAssertNil(projection.status)
  }

  func testTerminalStatusesCannotBeResurrectedByInconsistentCompletedFlag() {
    for status in ["cancelled", "superseded"] {
      assertProjectionError(
        .invalidStatus, record: ActionItemRecord(description: "Task", completed: true, taskStatus: status))
    }
  }

  func testUnsupportedPriorityIsRejectedInsteadOfOmitted() {
    for value in ["urgent", "", " high ", "__unknown__"] {
      assertProjectionError(.invalidPriority, record: ActionItemRecord(description: "Task", priority: value))
    }
  }

  func testUnsupportedOwnerIsRejectedInsteadOfOmitted() {
    for value in ["team", "", "User", "__unknown__"] {
      assertProjectionError(.invalidOwner, record: ActionItemRecord(description: "Task", taskOwner: value))
    }
  }

  func testUnsupportedStatusIsRejectedInsteadOfOmitted() {
    for value in ["pending", "", "COMPLETE", "__unknown__"] {
      assertProjectionError(.invalidStatus, record: ActionItemRecord(description: "Task", taskStatus: value))
    }
  }

  func testMalformedMetadataIsRejectedInsteadOfSilentlyLost() {
    for value in ["", "{", "[]", "null", "42", #""not an object""#] {
      assertProjectionError(.invalidMetadata, record: ActionItemRecord(description: "Task", metadataJson: value))
    }
  }

  func testEmptyMetadataAndProvenanceRemainExplicitEmptyValues() throws {
    let record = ActionItemRecord(description: "Task", provenanceJson: "[]", metadataJson: "{}")
    let projection = try UnsyncedTaskCreateProjection(record: record)

    XCTAssertNotNil(projection.metadataBox)
    XCTAssertEqual(projection.metadataBox?.value?.count, 0)
    XCTAssertNotNil(projection.provenance)
    XCTAssertEqual(projection.provenance?.count, 0)
  }

  func testMalformedTypedProvenanceIsRejectedInsteadOfSilentlyLost() {
    for value in [
      "", "[", "{}", "null", "[{}]",
      #"[{"id":"source-1","kind":"conversation"}]"#,
      #"[{"id":42,"kind":"conversation","scope":"canonical"}]"#,
      #"[{"id":"source-1","kind":"conversation","scope":"canonical","start_seconds":"soon"}]"#,
    ] {
      assertProjectionError(.invalidProvenance, record: ActionItemRecord(description: "Task", provenanceJson: value))
    }
  }

  func testUnknownProvenanceEnumsAreRejectedDespiteGeneratedDecoderFallback() {
    for value in [
      #"[{"id":"source-1","kind":"future_source","scope":"canonical"}]"#,
      #"[{"id":"source-1","kind":"__unknown__","scope":"canonical"}]"#,
      #"[{"id":"source-1","kind":"conversation","scope":"future_scope"}]"#,
      #"[{"id":"source-1","kind":"conversation","scope":"__unknown__"}]"#,
    ] {
      assertProjectionError(.invalidProvenance, record: ActionItemRecord(description: "Task", provenanceJson: value))
    }
  }

  func testProjectionErrorsDoNotExposeSavedTaskContentOrMalformedPayload() {
    let secret = "private-customer-content"
    let record = ActionItemRecord(description: secret, provenanceJson: secret)
    XCTAssertThrowsError(try UnsyncedTaskCreateProjection(record: record)) { error in
      XCTAssertEqual(error as? UnsyncedTaskCreateProjection.ProjectionError, .invalidProvenance)
      XCTAssertFalse(error.localizedDescription.contains(secret))
    }
  }

  private func assertProjectionError(
    _ expected: UnsyncedTaskCreateProjection.ProjectionError,
    record: ActionItemRecord,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    XCTAssertThrowsError(try UnsyncedTaskCreateProjection(record: record), file: file, line: line) { error in
      XCTAssertEqual(error as? UnsyncedTaskCreateProjection.ProjectionError, expected, file: file, line: line)
    }
  }

  private static let fullProvenance = #"""
    [{"id":"conversation-1","kind":"local_screen","scope":"device_local","device_id":"device-1",
      "start_seconds":12.5,"end_seconds":21.5,"excerpt_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "transcript_segment_ids":["segment-1","segment-2"],"version":"revision-2"}]
    """#
}

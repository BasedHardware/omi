import XCTest

@testable import Omi_Computer

/// Regression tests for the conversation-end "N follow-ups ready" count.
/// The count must reflect only follow-ups the just-ended conversation produced —
/// never the whole open-task backlog, and never older tasks that pagination or a
/// cross-device sync brings in mid-session (new ids, but stale `createdAt`).
final class NotchMomentsFollowUpCountTests: XCTestCase {
  private func task(_ id: String, createdAt: Date) -> TaskActionItem {
    TaskActionItem(id: id, description: id, completed: false, createdAt: createdAt)
  }

  private let sessionStart = Date(timeIntervalSince1970: 1_000_000)

  func testExcludesPreExistingBacklog() {
    // Two tasks already open when the conversation started → baseline. No new tasks.
    let baseline: Set<String> = ["a", "b"]
    let tasks = [
      task("a", createdAt: sessionStart.addingTimeInterval(-3600)),
      task("b", createdAt: sessionStart.addingTimeInterval(-60)),
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: sessionStart), 0)
  }

  func testCountsOnlyTasksCreatedDuringSession() {
    let baseline: Set<String> = ["a"]
    let tasks = [
      task("a", createdAt: sessionStart.addingTimeInterval(-3600)),  // backlog
      task("new1", createdAt: sessionStart.addingTimeInterval(30)),  // produced now
      task("new2", createdAt: sessionStart.addingTimeInterval(90)),  // produced now
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: sessionStart), 2)
  }

  func testExcludesPaginatedOrSyncedOlderTasks() {
    // A new id (not in baseline) but with a `createdAt` before the session start —
    // e.g. an older task paginated in or synced from another device mid-recording.
    let baseline: Set<String> = ["a"]
    let tasks = [
      task("a", createdAt: sessionStart.addingTimeInterval(-3600)),
      task("older", createdAt: sessionStart.addingTimeInterval(-120)),  // must NOT count
      task("new", createdAt: sessionStart.addingTimeInterval(45)),  // counts
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: sessionStart), 1)
  }

  func testNilStartFallsBackToBaselineDiff() {
    // When the start time is unknown, fall back to id-diff only.
    let baseline: Set<String> = ["a"]
    let tasks = [
      task("a", createdAt: sessionStart),
      task("new", createdAt: sessionStart),
    ]
    XCTAssertEqual(
      NotchMomentsCoordinator.followUpCount(tasks: tasks, baselineIds: baseline, since: nil), 1)
  }

  // The receipt contract is gone with the write it acknowledged (I1). What the
  // moment carries now is a proposal, and the guarantee worth pinning is that the
  // candidate identity survives the round trip through the transcript.

  func testSuggestedTaskCardRoundTripsCandidateIdentity() {
    let encoded = SuggestedTaskChatCard.encode(
      candidateID: "cand_abc123", description: "Send Sarah the budget")
    let parsed = SuggestedTaskChatCard.parse(encoded)

    XCTAssertEqual(parsed?.candidateID, "cand_abc123")
    XCTAssertEqual(parsed?.description, "Send Sarah the budget")
  }

  func testSuggestedTaskCardRejectsOrdinaryNotificationText() {
    XCTAssertNil(SuggestedTaskChatCard.parse("Omi noticed something"))
    XCTAssertNil(SuggestedTaskChatCard.parse("[Suggested task id=] no candidate"))
    XCTAssertNil(SuggestedTaskChatCard.parse("[Suggested task id=cand_1]"))
  }

  // The live-suggestion moment must fire only for a proposal Omi made just now.
  // A store load mid-conversation (all ids new to the coordinator, `createdAt`
  // stale) must not announce an old suggestion as a "just now" moment.

  private func suggestion(
    _ id: String, title: String = "task", createdAt: Date, now: Date
  ) -> SuggestedCandidate {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return SuggestedCandidate(
      id: id,
      title: title,
      detail: nil,
      accountGeneration: 1,
      isEditableTask: true,
      createdAt: formatter.string(from: createdAt))
  }

  private let now = Date(timeIntervalSince1970: 2_000_000)

  func testAnnouncesFreshUnknownSuggestionPreferringNewest() {
    let older = suggestion("a", createdAt: now.addingTimeInterval(-100), now: now)
    let newer = suggestion("b", createdAt: now.addingTimeInterval(-10), now: now)
    XCTAssertEqual(
      NotchMomentsCoordinator.suggestedMomentCandidate(
        candidates: [older, newer], knownIDs: [], now: now)?.id, "b")
  }

  func testBackfilledStoreLoadDoesNotAnnounceStaleSuggestions() {
    // First emission the coordinator ever sees, mid-conversation: every id is
    // new, but the proposals are old. Nothing may be announced.
    let stale = [
      suggestion("a", createdAt: now.addingTimeInterval(-3600), now: now),
      suggestion("b", createdAt: now.addingTimeInterval(-86_400), now: now),
    ]
    XCTAssertNil(
      NotchMomentsCoordinator.suggestedMomentCandidate(candidates: stale, knownIDs: [], now: now))
  }

  func testAlreadyAnnouncedSuggestionIsNotReAnnounced() {
    let fresh = suggestion("a", createdAt: now.addingTimeInterval(-30), now: now)
    XCTAssertNil(
      NotchMomentsCoordinator.suggestedMomentCandidate(
        candidates: [fresh], knownIDs: ["a"], now: now))
  }

  func testUnparseableCreatedAtFailsClosed() {
    XCTAssertNil(NotchMomentsCoordinator.suggestedCandidateCreatedAt("yesterday"))
    let fresh = suggestion("a", createdAt: now.addingTimeInterval(-30), now: now)
    let malformed = SuggestedCandidate(
      id: "b", title: "bad", detail: nil, accountGeneration: 1, isEditableTask: true,
      createdAt: "not-a-date")
    XCTAssertEqual(
      NotchMomentsCoordinator.suggestedMomentCandidate(
        candidates: [malformed, fresh], knownIDs: [], now: now)?.id, "a")
  }
}

import XCTest

@testable import Omi_Computer

@MainActor
final class CanonicalGoalsStoreTests: XCTestCase {
  func testLoadProjectsFocusedGoalAheadOfOtherActiveGoals() async throws {
    let api = FakeCanonicalGoalsClient()
    api.goals = [
      goal(id: "background", status: .background, rank: nil),
      goal(id: "focused", status: .focused, rank: 0),
    ]
    let owner = TestOwner("owner-a")
    let store = CanonicalGoalsStore(client: api, ownerIDProvider: { owner.value })

    store.activate(capability: try capability(generation: 7))
    await store.load()

    XCTAssertEqual(store.primaryFocusedGoal?.goalId, "focused")
    XCTAssertEqual(store.otherActiveGoals.map(\.goalId), ["background"])
    XCTAssertEqual(store.availability, .ready)
    XCTAssertEqual(api.goalRequestOwnerIDs, ["owner-a"])
  }

  func testSetFocusUsesSampledGenerationPrimaryReplacementAndReconciles() async throws {
    let api = FakeCanonicalGoalsClient()
    api.goals = [
      goal(id: "focused", status: .focused, rank: 0),
      goal(id: "background", status: .background, rank: nil),
    ]
    api.goalsAfterFocus = [
      goal(id: "focused", status: .background, rank: nil),
      goal(id: "background", status: .focused, rank: 0),
    ]
    let owner = TestOwner("owner-a")
    let store = CanonicalGoalsStore(client: api, ownerIDProvider: { owner.value })

    store.activate(capability: try capability(generation: 12))
    await store.load()
    let updated = await store.setAsFocus(goalID: "background")

    XCTAssertTrue(updated)
    XCTAssertEqual(api.focusRequests.count, 1)
    XCTAssertEqual(api.focusRequests[0].goalID, "background")
    XCTAssertEqual(api.focusRequests[0].replacementGoalID, "focused")
    XCTAssertEqual(api.focusRequests[0].accountGeneration, 12)
    XCTAssertEqual(api.focusRequests[0].expectedOwnerID, "owner-a")
    XCTAssertTrue(api.focusRequests[0].idempotencyKey.hasPrefix("goal-focus:background:"))
    XCTAssertEqual(store.primaryFocusedGoal?.goalId, "background")
  }

  func testUnavailableProjectionClearsCanonicalDataAndDoesNotRetainPriorOwnerState() async throws {
    let api = FakeCanonicalGoalsClient()
    api.goals = [goal(id: "owner-a", status: .focused, rank: 0)]
    let owner = TestOwner("owner-a")
    let store = CanonicalGoalsStore(client: api, ownerIDProvider: { owner.value })

    store.activate(capability: try capability(generation: 7))
    await store.load()
    XCTAssertEqual(store.goals.map(\.goalId), ["owner-a"])

    owner.value = "owner-b"
    await store.load()

    XCTAssertTrue(store.goals.isEmpty)
    XCTAssertEqual(store.availability, .unavailable("Goals are unavailable right now. Try again."))
  }

  func testUnavailableProjectionClearsDataWhenCanonicalFetchFails() async throws {
    let api = FakeCanonicalGoalsClient()
    api.goals = [goal(id: "focused", status: .focused, rank: 0)]
    let owner = TestOwner("owner-a")
    let store = CanonicalGoalsStore(client: api, ownerIDProvider: { owner.value })

    store.activate(capability: try capability(generation: 7))
    await store.load()
    XCTAssertEqual(store.goals.map(\.goalId), ["focused"])

    api.goalFetchError = .missing
    await store.load()

    XCTAssertTrue(store.goals.isEmpty)
    XCTAssertNil(store.selectedGoalDetail)
    XCTAssertEqual(store.availability, .unavailable("Goals are unavailable right now. Try again."))
  }

  func testDetailPolicyUsesAggregateTasksOnlyForDisplayAndVisibleFocusAcknowledgement() {
    let detail = OmiAPI.GoalDetailProjection(
      activeThreads: [],
      goal: goal(id: "goal-a", status: .focused, rank: 0),
      progressEvents: [],
      tasks: [
        actionItem(id: "complete", completed: true),
        actionItem(id: "next", completed: false),
        actionItem(id: "later", completed: false),
      ]
    )

    XCTAssertEqual(ChatFirstGoalDetailPolicy.completedTaskCount(in: detail), 1)
    XCTAssertEqual(ChatFirstGoalDetailPolicy.nextTaskIDs(in: detail), ["next", "later"])
    XCTAssertEqual(
      ChatFirstGoalProgressPolicy.summary(for: detail.goal),
      "Progress: 1 of 10"
    )
    XCTAssertEqual(
      ChatFirstGoalDetailPolicy.focusToAcknowledge(
        pendingFocus: .goal(id: "goal-a"),
        visibleGoalID: "goal-a"
      ),
      .goal(id: "goal-a")
    )
    XCTAssertNil(
      ChatFirstGoalDetailPolicy.focusToAcknowledge(
        pendingFocus: .goal(id: "goal-a"),
        visibleGoalID: "goal-b"
      )
    )
  }

  private func capability(generation: Int) throws -> ChatFirstCapabilityProjection {
    try XCTUnwrap(
      ChatFirstCapabilityProjection(
        control: OmiAPI.TaskWorkflowControl(
          accountGeneration: generation,
          chatFirstUi: true,
          workflowMode: .read
        )))
  }

  private func goal(id: String, status: OmiAPI.GoalStatus, rank: Int?) -> OmiAPI.GoalResponse {
    OmiAPI.GoalResponse(
      advice: nil,
      createdAt: "2027-01-01T08:00:00Z",
      currentValue: 1,
      desiredOutcome: "Finish \(id)",
      endedAt: nil,
      focusRank: rank,
      goalId: id,
      goalType: "numeric",
      horizonAt: nil,
      id: id,
      isActive: true,
      latestProgressSequence: nil,
      maxValue: 10,
      metric: nil,
      minValue: 0,
      source: .user,
      status: status,
      successCriteria: [],
      targetValue: 10,
      title: "Goal \(id)",
      unit: nil,
      updatedAt: "2027-01-10T08:00:00Z",
      whyItMatters: nil
    )
  }

  private func actionItem(id: String, completed: Bool) -> OmiAPI.ActionItemResponse {
    OmiAPI.ActionItemResponse(completed: completed, description_: id, id: id)
  }
}

private final class TestOwner {
  var value: String?

  init(_ value: String?) {
    self.value = value
  }
}

private final class FakeCanonicalGoalsClient: CanonicalGoalsClient, @unchecked Sendable {
  enum FakeError: Error {
    case missing
  }

  struct FocusRequest {
    let goalID: String
    let replacementGoalID: String?
    let accountGeneration: Int
    let idempotencyKey: String
    let expectedOwnerID: String?
  }

  var goals: [OmiAPI.GoalResponse] = []
  var goalsAfterFocus: [OmiAPI.GoalResponse]?
  var focusRequests: [FocusRequest] = []
  var goalRequestOwnerIDs: [String?] = []
  var goalFetchError: FakeError?
  private var hasFocused = false

  func getCanonicalGoals(
    includeEnded: Bool,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> [OmiAPI.GoalResponse] {
    goalRequestOwnerIDs.append(expectedOwnerId)
    if let goalFetchError { throw goalFetchError }
    if hasFocused, let goalsAfterFocus {
      return goalsAfterFocus
    }
    return goals
  }

  func getCanonicalGoalDetail(
    goalID: String,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.GoalDetailProjection {
    guard let goal = goals.first(where: { $0.goalId == goalID }) else { throw FakeError.missing }
    return OmiAPI.GoalDetailProjection(activeThreads: [], goal: goal, progressEvents: [], tasks: [])
  }

  func focusCanonicalGoal(
    goalID: String,
    replacementGoalID: String?,
    focusRank: Int?,
    accountGeneration: Int,
    idempotencyKey: String,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.GoalResponse {
    focusRequests.append(
      FocusRequest(
        goalID: goalID,
        replacementGoalID: replacementGoalID,
        accountGeneration: accountGeneration,
        idempotencyKey: idempotencyKey,
        expectedOwnerID: expectedOwnerId
      ))
    guard let goal = goals.first(where: { $0.goalId == goalID }) else { throw FakeError.missing }
    hasFocused = true
    return goal
  }
}

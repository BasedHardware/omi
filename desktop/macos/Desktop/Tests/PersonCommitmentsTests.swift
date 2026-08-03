import Foundation
import XCTest

@testable import Omi_Computer

/// The person profile's Commitments tab used to show only extracted prose, because no task
/// could name a person. Tasks now carry `assignee_person_id` / `assigner_person_id`, so these
/// tests pin the three things that has to get right:
///
///  * the client asks the backend for exactly one person's tasks,
///  * a profile is matched to a backend person by whole-value identity, never by prefix,
///  * assigned tasks and extracted open threads stay visibly separate — including when
///    there are none of either.
final class PersonCommitmentsTests: XCTestCase {

  // MARK: - Client

  func testGetActionItemsSendsPersonIdAndConversationId() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ActionItemsQueryURLProtocol.self]
    ActionItemsQueryURLProtocol.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
    defer { unsetenv("OMI_PYTHON_API_URL") }
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try await client.getActionItems(
      limit: 25, completed: false, conversationId: "conversation-1", personId: "person-sarah")

    let url = try XCTUnwrap(ActionItemsQueryURLProtocol.requestURL)
    let items = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
    let values = Dictionary(items.map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { first, _ in first })
    XCTAssertEqual(url.path, "/v1/action-items")
    XCTAssertEqual(values["person_id"], "person-sarah")
    XCTAssertEqual(values["conversation_id"], "conversation-1")
    XCTAssertEqual(values["completed"], "false")
  }

  func testGetActionItemsOmitsPersonIdByDefaultSoExistingCallersAreUnchanged() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ActionItemsQueryURLProtocol.self]
    ActionItemsQueryURLProtocol.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
    defer { unsetenv("OMI_PYTHON_API_URL") }
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try await client.getActionItems(limit: 25)

    let url = try XCTUnwrap(ActionItemsQueryURLProtocol.requestURL)
    let names = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.map(\.name) ?? []
    XCTAssertEqual(names, ["limit", "offset"])
  }

  func testPersonIdIsPercentEncodedSoItCannotForgeASecondParameter() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ActionItemsQueryURLProtocol.self]
    ActionItemsQueryURLProtocol.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
    defer { unsetenv("OMI_PYTHON_API_URL") }
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try await client.getActionItems(personId: "person&completed=true")

    let url = try XCTUnwrap(ActionItemsQueryURLProtocol.requestURL)
    let items = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
    XCTAssertEqual(items.map(\.name), ["limit", "offset", "person_id"])
    XCTAssertEqual(items.last?.value, "person&completed=true")
  }

  // MARK: - Wire decoding

  func testTaskDecodesBothPersonAttributionFields() throws {
    let json = #"""
      {"id":"task-1","description":"Send the budget","completed":false,
       "assignee_person_id":"person-sarah","assigner_person_id":"person-me"}
      """#
    let task = try JSONDecoder().decode(TaskActionItem.self, from: Data(json.utf8))

    XCTAssertEqual(task.assigneePersonId, "person-sarah")
    XCTAssertEqual(task.assignerPersonId, "person-me")
  }

  /// The legacy principal on the client: a task written before per-person attribution.
  func testLegacyTaskWithoutPersonFieldsStillDecodes() throws {
    let json = #"{"id":"task-legacy","description":"Pay the electricity bill","completed":false}"#
    let task = try JSONDecoder().decode(TaskActionItem.self, from: Data(json.utf8))

    XCTAssertNil(task.assigneePersonId)
    XCTAssertNil(task.assignerPersonId)
    XCTAssertEqual(task.description, "Pay the electricity bill")
  }

  // MARK: - Backend person resolution

  private func person(_ id: String, _ name: String) -> Person {
    Person(id: id, name: name)
  }

  func testProfileIdIsUsedWhenItAlreadyIsABackendPersonId() {
    let id = PersonCommitmentsMatcher.backendPersonID(
      profileID: "person-uuid",
      displayName: "Sarah Chen",
      contactName: nil,
      aliases: [],
      people: [person("person-uuid", "Sarah C.")])

    XCTAssertEqual(id, "person-uuid")
  }

  func testDisplayNameResolvesWhenTheProfileIdIsALocalSlug() {
    let id = PersonCommitmentsMatcher.backendPersonID(
      profileID: "sarah-chen",
      displayName: "Sarah Chen",
      contactName: nil,
      aliases: [],
      people: [person("person-uuid", "sarah chen")])

    XCTAssertEqual(id, "person-uuid", "the match must be case-insensitive on whole names")
  }

  func testContactNameAndAliasesAreTriedAfterTheDisplayName() {
    let people = [person("person-contact", "Sarah Chen"), person("person-alias", "Sazz")]

    XCTAssertEqual(
      PersonCommitmentsMatcher.backendPersonID(
        profileID: "local", displayName: "+1 555 0100", contactName: "Sarah Chen", aliases: [],
        people: people),
      "person-contact")
    XCTAssertEqual(
      PersonCommitmentsMatcher.backendPersonID(
        profileID: "local", displayName: "+1 555 0100", contactName: nil, aliases: ["Sazz"],
        people: people),
      "person-alias")
  }

  func testAPrefixOfAnotherNameNeverBorrowsTheirIdentity() {
    XCTAssertNil(
      PersonCommitmentsMatcher.backendPersonID(
        profileID: "sam", displayName: "Sam", contactName: nil, aliases: [],
        people: [person("person-samantha", "Samantha")]))
  }

  func testAProfileWithNoBackendPersonResolvesToNothing() {
    XCTAssertNil(
      PersonCommitmentsMatcher.backendPersonID(
        profileID: "sarah-chen", displayName: "Sarah Chen", contactName: nil, aliases: [],
        people: []))
  }

  // MARK: - Direction and ordering

  private func task(
    _ id: String,
    assignee: String? = nil,
    assigner: String? = nil,
    completed: Bool = false,
    dueAt: Date? = nil,
    taskStatus: String? = nil
  ) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0),
      dueAt: dueAt,
      taskStatus: taskStatus,
      assigneePersonId: assignee,
      assignerPersonId: assigner)
  }

  func testAssigneeIsOnThemAndAssignerIsOnYou() {
    let items = PersonCommitmentsMatcher.commitments(
      personID: "person-sarah",
      tasks: [
        task("they-act", assignee: "person-sarah"),
        task("you-act", assigner: "person-sarah"),
      ])

    XCTAssertEqual(
      items.map(\.direction),
      [.theyOweYou, .youOweThem])
    XCTAssertEqual(items.map(\.direction.label), ["On them", "On you"])
  }

  func testWhoHasToActWinsWhenThePersonIsOnBothSides() {
    let items = PersonCommitmentsMatcher.commitments(
      personID: "person-sarah",
      tasks: [task("both", assignee: "person-sarah", assigner: "person-sarah")])

    XCTAssertEqual(items.map(\.direction), [.theyOweYou])
  }

  func testTasksThatDoNotNameThisPersonAreDroppedRatherThanGuessed() {
    let items = PersonCommitmentsMatcher.commitments(
      personID: "person-sarah",
      tasks: [task("someone-else", assignee: "person-alex"), task("legacy-no-person")])

    XCTAssertTrue(items.isEmpty)
  }

  func testRetiredTasksAreNotShownAsCommitments() {
    let items = PersonCommitmentsMatcher.commitments(
      personID: "person-sarah",
      tasks: [
        task("cancelled", assignee: "person-sarah", taskStatus: "cancelled"),
        task("open", assignee: "person-sarah"),
      ])

    XCTAssertEqual(items.map(\.id), ["open"])
  }

  func testOpenTasksSortBeforeDoneAndSoonestDueLeads() {
    let soon = Date(timeIntervalSince1970: 1_000)
    let later = Date(timeIntervalSince1970: 2_000)
    let items = PersonCommitmentsMatcher.commitments(
      personID: "person-sarah",
      tasks: [
        task("done", assignee: "person-sarah", completed: true, dueAt: soon),
        task("undated", assignee: "person-sarah"),
        task("later", assignee: "person-sarah", dueAt: later),
        task("soon", assignee: "person-sarah", dueAt: soon),
      ])

    XCTAssertEqual(items.map(\.id), ["soon", "later", "undated", "done"])
  }

  // MARK: - Tab layout

  private func commitment(_ id: String) -> PersonCommitmentItem {
    PersonCommitmentItem(
      id: id, description: id, completed: false, dueAt: nil, direction: .theyOweYou)
  }

  func testAssignedTasksAndOpenThreadsRenderAsSeparateSections() {
    let layout = PersonCommitmentsTabLayout(
      assigned: [commitment("task-1")], openThreads: ["Never picked the venue"], state: .loaded)

    XCTAssertTrue(layout.showsAssignedRows)
    XCTAssertTrue(layout.showsOpenThreads)
    XCTAssertFalse(layout.showsAssignedPlaceholder)
    XCTAssertFalse(layout.showsEmptyState, "with content of either kind there is no empty state")
    XCTAssertEqual(layout.assigned.map(\.id), ["task-1"])
    XCTAssertEqual(layout.openThreads, ["Never picked the venue"])
  }

  func testOpenThreadsAloneNeverReadAsAssignedTasks() {
    let layout = PersonCommitmentsTabLayout(
      assigned: [], openThreads: ["Never picked the venue"], state: .loaded)

    XCTAssertFalse(layout.showsAssignedRows)
    XCTAssertTrue(layout.showsAssignedPlaceholder, "the assigned section states there are none")
    XCTAssertTrue(layout.showsOpenThreads)
    XCTAssertFalse(layout.showsEmptyState)
  }

  func testNothingAtAllShowsExactlyOneEmptyState() {
    let layout = PersonCommitmentsTabLayout(assigned: [], openThreads: [], state: .loaded)

    XCTAssertTrue(layout.showsEmptyState)
    XCTAssertFalse(layout.showsAssignedRows)
    XCTAssertFalse(layout.showsOpenThreads)
  }

  func testAPersonWithNoBackendRecordStillShowsTheirOpenThreads() {
    let layout = PersonCommitmentsTabLayout(
      assigned: [], openThreads: ["Never picked the venue"], state: .notLinked)

    XCTAssertTrue(layout.showsOpenThreads)
    XCTAssertTrue(layout.showsAssignedPlaceholder)
    XCTAssertFalse(layout.showsEmptyState)
  }

  func testLoadingShowsProgressAndNeverTheEmptyState() {
    for state in [PersonCommitmentsState.idle, .loading] {
      let layout = PersonCommitmentsTabLayout(assigned: [], openThreads: [], state: state)
      XCTAssertTrue(layout.showsAssignedProgress, "\(state)")
      XCTAssertFalse(layout.showsEmptyState, "\(state)")
      XCTAssertFalse(layout.showsAssignedPlaceholder, "\(state)")
    }
  }

  func testAFailedLoadReportsTheFailureRatherThanClaimingThereAreNone() {
    let layout = PersonCommitmentsTabLayout(
      assigned: [], openThreads: [], state: .failed(PersonCommitmentsModel.failureMessage))

    XCTAssertFalse(layout.showsAssignedPlaceholder)
    XCTAssertFalse(layout.showsAssignedRows)
  }

  // MARK: - Model

  @MainActor
  func testModelLoadsCommitmentsForAResolvedPerson() async {
    let source = StubPersonCommitmentsSource(
      people: [person("person-sarah", "Sarah Chen")],
      tasks: [task("they-act", assignee: "person-sarah")])
    let model = PersonCommitmentsModel(source: source)

    await model.load(profileID: "sarah-chen", displayName: "Sarah Chen", contactName: nil, aliases: [])

    XCTAssertEqual(model.state, .loaded)
    XCTAssertEqual(model.commitments.map(\.id), ["they-act"])
    XCTAssertEqual(source.requestedPersonIDs, ["person-sarah"])
  }

  @MainActor
  func testModelNeverCreatesAPersonForAnUnknownProfile() async {
    let source = StubPersonCommitmentsSource(people: [], tasks: [])
    let model = PersonCommitmentsModel(source: source)

    await model.load(profileID: "sarah-chen", displayName: "Sarah Chen", contactName: nil, aliases: [])

    XCTAssertEqual(model.state, .notLinked)
    XCTAssertTrue(model.commitments.isEmpty)
    XCTAssertTrue(source.requestedPersonIDs.isEmpty, "an unresolved profile must not query tasks")
  }

  @MainActor
  func testModelReportsADetailFreeFailure() async {
    let source = StubPersonCommitmentsSource(people: [], tasks: [], failure: URLError(.timedOut))
    let model = PersonCommitmentsModel(source: source)

    await model.load(profileID: "sarah-chen", displayName: "Sarah Chen", contactName: nil, aliases: [])

    XCTAssertEqual(model.state, .failed(PersonCommitmentsModel.failureMessage))
    XCTAssertTrue(model.commitments.isEmpty)
  }
}

// MARK: - Doubles

private final class StubPersonCommitmentsSource: PersonCommitmentsSource, @unchecked Sendable {
  private let lock = NSLock()
  private let peopleResult: [Person]
  private let tasksResult: [TaskActionItem]
  private let failure: (any Error)?
  private var requested: [String] = []

  init(people: [Person], tasks: [TaskActionItem], failure: (any Error)? = nil) {
    self.peopleResult = people
    self.tasksResult = tasks
    self.failure = failure
  }

  var requestedPersonIDs: [String] { lock.withLock { requested } }

  func people() async throws -> [Person] {
    if let failure { throw failure }
    return peopleResult
  }

  func tasks(personID: String) async throws -> [TaskActionItem] {
    lock.withLock { requested.append(personID) }
    if let failure { throw failure }
    return tasksResult
  }
}

private final class ActionItemsQueryURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var captured: URL?

  static func reset() { lock.withLock { captured = nil } }
  static var requestURL: URL? { lock.withLock { captured } }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url,
      let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    Self.lock.withLock { Self.captured = url }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(#"{"action_items":[],"has_more":false}"#.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

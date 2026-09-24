import XCTest

@testable import Omi_Computer

/// The conversation detail lists the devices that recorded its event and separates one on
/// request; these pin what it lists, how it labels a recording, and the separation flow.
final class ConversationCaptureRecordingsTests: XCTestCase {
  private static let utc = TimeZone(secondsFromGMT: 0) ?? .current
  private static let enUS = Locale(identifier: "en_US")
  /// 2026-09-23T12:58:00Z.
  private static let base = Date(timeIntervalSince1970: 1_790_168_280)

  /// Foundation separates times with narrow and thin no-break spaces; compare the words.
  private static func plain(_ text: String) -> String {
    String(text.unicodeScalars.map { CharacterSet.whitespaces.contains($0) ? " " : Character($0) })
  }

  private static func member(_ id: String, _ source: ConversationSource, start: Double?, end: Double?)
    -> ServerCaptureGroup.Member
  {
    ServerCaptureGroup.Member(
      id: id, source: source, startedAt: start.map { base.addingTimeInterval($0 * 60) },
      finishedAt: end.map { base.addingTimeInterval($0 * 60) })
  }

  private static func conversation(
    _ id: String, source: String = "omi", members: [ServerCaptureGroup.Member]? = nil
  ) throws -> ServerConversation {
    var conversation = try ProjectionRenderingFixture.decode {
      $0["id"] = id
      $0["source"] = source
      $0.removeValue(forKey: "client_processing")
    }
    conversation.captureGroup = members.map {
      ServerCaptureGroup(id: "event-1", primaryId: "desktop", revision: 3, members: $0)
    }
    return conversation
  }

  private static var meeting: [ServerCaptureGroup.Member] {
    [
      member("pendant-late", .omi, start: 33, end: 36),
      member("desktop", .desktop, start: 0, end: 62),
      member("pendant-early", .omi, start: 2, end: 30),
      member("desktop", .desktop, start: 0, end: 62),
    ]
  }

  // MARK: - What the detail lists

  func testRecordingsAreChronologicalDedupedAndMarkTheOpenOne() throws {
    let open = try Self.conversation("pendant-early", members: Self.meeting)
    let recordings = CaptureGroupPresentation.recordings(of: open)

    XCTAssertEqual(recordings.map(\.id), ["desktop", "pendant-early", "pendant-late"])
    XCTAssertEqual(recordings.map(\.source), [.desktop, .omi, .omi])
    XCTAssertEqual(recordings.filter(\.isCurrent).map(\.id), ["pendant-early"])
  }

  func testSingleRecordingAndUngroupedConversationsListNothing() throws {
    XCTAssertEqual(CaptureGroupPresentation.recordings(of: try Self.conversation("solo")), [])
    let alone = try Self.conversation("desktop", source: "desktop", members: [Self.meeting[1]])
    XCTAssertEqual(CaptureGroupPresentation.recordings(of: alone), [], "A group of one is just a conversation")
  }

  func testOpenConversationMissingFromStaleMembershipIsStillListed() throws {
    let open = try Self.conversation("fresh", members: [Self.meeting[0]])
    let recordings = CaptureGroupPresentation.recordings(of: open)

    XCTAssertEqual(Set(recordings.map(\.id)), ["pendant-late", "fresh"])
    XCTAssertEqual(recordings.first { $0.isCurrent }?.id, "fresh")
  }

  func testUndatedRecordingsSortAfterDatedOnes() throws {
    let members = [Self.member("undated", .phone, start: nil, end: nil), Self.meeting[1]]
    let recordings = CaptureGroupPresentation.recordings(of: try Self.conversation("desktop", members: members))
    XCTAssertEqual(recordings.map(\.id), ["desktop", "undated"])
  }

  func testLabelsNameTheDeviceAndItsTimeWindow() {
    let window = CaptureGroupRecording(
      id: "p", source: .omi, startedAt: Self.base.addingTimeInterval(33 * 60),
      finishedAt: Self.base.addingTimeInterval(36 * 60), isCurrent: false)
    let label = Self.plain(CaptureGroupPresentation.label(of: window, locale: Self.enUS, timeZone: Self.utc))
    XCTAssertTrue(label.hasPrefix("omi · 1:31"), label)
    XCTAssertTrue(label.hasSuffix("1:34 PM"), label)

    let openEnded = CaptureGroupRecording(
      id: "d", source: .desktop, startedAt: Self.base, finishedAt: nil, isCurrent: true)
    XCTAssertEqual(
      Self.plain(CaptureGroupPresentation.label(of: openEnded, locale: Self.enUS, timeZone: Self.utc)),
      "Desktop · 12:58 PM")

    let undated = CaptureGroupRecording(id: "w", source: .appleWatch, startedAt: nil, finishedAt: nil, isCurrent: false)
    XCTAssertEqual(CaptureGroupPresentation.label(of: undated), "Apple Watch")
  }

  func testDeviceStackDrawsUpToThreeRecordingsInStartOrderAndCountsThemAll() throws {
    let recordings = CaptureGroupPresentation.recordings(
      of: try Self.conversation(
        "desktop",
        members: Self.meeting + [Self.member("phone", .phone, start: 40, end: 50)]))
    XCTAssertEqual(CaptureGroupPresentation.stackSources(of: recordings), [.desktop, .omi, .omi])
    XCTAssertEqual(CaptureGroupPresentation.countLabel(recordings.count), "4 recordings")
    XCTAssertEqual(CaptureGroupPresentation.countLabel(1), "1 recording")
  }

  // MARK: - Opening another recording

  @MainActor
  func testOpeningALoadedMemberUsesTheListRowWithoutFetching() async throws {
    let loaded = [try Self.conversation("pendant-late", members: Self.meeting)]
    var fetched: [String] = []
    let resolved = await CaptureGroupPresentation.resolveMember(
      id: "pendant-late", loaded: loaded,
      fetch: {
        fetched.append($0)
        return nil
      })
    XCTAssertEqual(resolved?.id, "pendant-late")
    XCTAssertEqual(fetched, [])
  }

  @MainActor
  func testOpeningAMemberTheListHasNotLoadedFetchesItById() async throws {
    let remote = try Self.conversation("pendant-late", members: Self.meeting)
    var fetched: [String] = []
    let resolved = await CaptureGroupPresentation.resolveMember(
      id: "pendant-late", loaded: [],
      fetch: {
        fetched.append($0)
        return remote
      })
    XCTAssertEqual(resolved?.id, "pendant-late")
    XCTAssertEqual(fetched, ["pendant-late"])

    let missing = await CaptureGroupPresentation.resolveMember(id: "gone", loaded: [], fetch: { _ in nil })
    XCTAssertNil(missing, "A member that cannot be fetched opens nothing rather than a placeholder")
  }

  // MARK: - Separation

  @MainActor
  func testSuccessfulSeparationReloadsThenReturnsToIdle() async {
    var separated: [String] = []
    let controller = CaptureGroupSeparationController { id in
      separated.append(id)
      return true
    }
    var phaseDuringReload: CaptureGroupSeparationController.Phase?
    let succeeded = await controller.separate(recordingID: "pendant-late") {
      phaseDuringReload = controller.phase
    }

    XCTAssertTrue(succeeded)
    XCTAssertEqual(separated, ["pendant-late"])
    XCTAssertEqual(phaseDuringReload, .separating(recordingID: "pendant-late"))
    XCTAssertEqual(controller.phase, .idle)
  }

  @MainActor
  func testRejectedSeparationReportsFailureAndDoesNotReload() async {
    let controller = CaptureGroupSeparationController { _ in false }
    var reloads = 0
    let succeeded = await controller.separate(recordingID: "desktop") { reloads += 1 }

    XCTAssertFalse(succeeded)
    XCTAssertEqual(reloads, 0)
    XCTAssertEqual(controller.phase, .failed(recordingID: "desktop"))

    controller.reset()
    XCTAssertEqual(controller.phase, .idle)
  }

  @MainActor
  func testSecondSeparationWhileOneIsInFlightIsRefused() async {
    let gate = SeparationGate()
    var separated: [String] = []
    let controller = CaptureGroupSeparationController { id in
      separated.append(id)
      await gate.wait()
      return true
    }

    let first = Task { await controller.separate(recordingID: "pendant-early") {} }
    await gate.waitUntilEntered()
    let second = await controller.separate(recordingID: "pendant-late") {}
    controller.reset()
    XCTAssertEqual(controller.phase, .separating(recordingID: "pendant-early"), "reset must not drop an in-flight one")

    await gate.open()
    let firstResult = await first.value
    XCTAssertTrue(firstResult)
    XCTAssertFalse(second)
    XCTAssertEqual(separated, ["pendant-early"])
  }

  // MARK: - Header facts

  func testParticipantsUseTheNamesTheTranscriptShowsWithTheReaderFirst() {
    func segment(_ speaker: String, isUser: Bool = false, person: String? = nil) -> TranscriptSegment {
      TranscriptSegment(
        id: UUID().uuidString, backendId: nil, text: "x", speaker: speaker, isUser: isUser, personId: person,
        start: 0, end: 1, translations: [])
    }
    let segments = [
      segment("SPEAKER_01"), segment("SPEAKER_00", isUser: true), segment("SPEAKER_02", person: "p-1"),
      segment("SPEAKER_01"),
    ]
    XCTAssertEqual(
      ConversationDetailMeta.participants(in: segments, people: [Person(id: "p-1", name: "Dana")]),
      ["You", "Speaker 1", "Dana"])
    XCTAssertEqual(ConversationDetailMeta.participants(in: [], people: []), [])
  }

  func testPeopleSummaryNamesTheFirstTwoThenCountsTheRest() {
    XCTAssertEqual(ConversationDetailMeta.peopleSummary(["You"]), "You")
    XCTAssertEqual(ConversationDetailMeta.peopleSummary(["You", "Dana"]), "You, Dana")
    XCTAssertEqual(ConversationDetailMeta.peopleSummary(["You", "Dana", "Speaker 2", "Speaker 3"]), "You, Dana +2")
  }

  func testWhenLineOmitsTheYearOnlyForThisYear() {
    let end = Self.base.addingTimeInterval(62 * 60)
    let thisYear = Self.plain(
      ConversationDetailMeta.when(start: Self.base, end: end, now: Self.base, locale: Self.enUS, timeZone: Self.utc))
    XCTAssertTrue(thisYear.hasPrefix("Wed, Sep 23 · 12:58"), thisYear)
    XCTAssertTrue(thisYear.hasSuffix("2:00 PM"), thisYear)

    let lastYear = Self.plain(
      ConversationDetailMeta.when(
        start: Self.base, end: nil, now: Self.base.addingTimeInterval(400 * 86_400), locale: Self.enUS,
        timeZone: Self.utc))
    XCTAssertEqual(lastYear, "Wed, Sep 23, 2026 · 12:58 PM")
  }
}

/// Holds a fake server call open until the test releases it.
private actor SeparationGate {
  private var entered = false
  private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
  private var release: CheckedContinuation<Void, Never>?
  private var isOpen = false

  func wait() async {
    entered = true
    for waiter in enteredWaiters { waiter.resume() }
    enteredWaiters.removeAll()
    guard !isOpen else { return }
    await withCheckedContinuation { release = $0 }
  }

  func waitUntilEntered() async {
    guard !entered else { return }
    await withCheckedContinuation { enteredWaiters.append($0) }
  }

  func open() {
    isOpen = true
    release?.resume()
    release = nil
  }
}

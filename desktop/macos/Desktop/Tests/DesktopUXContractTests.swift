import OmiTheme
import XCTest

@testable import Omi_Computer

/// Behavior of the shared UX components in `docs/ux-contract.md` (INV-UI-2): dates, speakers, the
/// back/close vocabulary, copy, and the icon-button fill ladder.
final class DesktopUXContractTests: XCTestCase {
  private let locale = Locale(identifier: "en_US")
  private var calendar: Calendar = {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "America/Los_Angeles") ?? .gmt
    return calendar
  }()

  private func date(_ year: Int, _ month: Int, _ day: Int, _ hour: Int = 10, _ minute: Int = 17) -> Date {
    calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour, minute: minute))
      ?? .distantPast
  }

  // MARK: - Dates

  func testDayHeaderNamesTodayYesterdayAndOlderDays() {
    let now = date(2026, 9, 23)
    XCTAssertEqual(OmiDateFormat.dayHeader(date(2026, 9, 23, 8), now: now, calendar: calendar, locale: locale), "Today")
    XCTAssertEqual(
      OmiDateFormat.dayHeader(date(2026, 9, 22, 23), now: now, calendar: calendar, locale: locale), "Yesterday")
    let sameYear = OmiDateFormat.dayHeader(date(2026, 9, 21), now: now, calendar: calendar, locale: locale)
    XCTAssertTrue(sameYear.contains("Sep") && sameYear.contains("21"), sameYear)
    XCTAssertFalse(sameYear.contains("2026"), "a date in this year does not repeat the year: \(sameYear)")
    let otherYear = OmiDateFormat.dayHeader(date(2025, 9, 21), now: now, calendar: calendar, locale: locale)
    XCTAssertTrue(otherYear.contains("2025"), otherYear)
  }

  func testTimestampLeansOnTheDayOnlyWhenItIsToday() {
    let now = date(2026, 9, 23)
    let today = OmiDateFormat.timestamp(date(2026, 9, 23, 10, 43), now: now, calendar: calendar, locale: locale)
    XCTAssertFalse(today.contains("Sep"), today)
    XCTAssertTrue(
      OmiDateFormat.timestamp(date(2026, 9, 22, 10, 43), now: now, calendar: calendar, locale: locale)
        .hasPrefix("Yesterday, "))
  }

  func testRangeNamesTheDayOnceAndBothTimes() {
    let range = OmiDateFormat.range(
      date(2026, 9, 23, 10, 17), date(2026, 9, 23, 11, 19), calendar: calendar, locale: locale)
    XCTAssertTrue(range.contains("10:17") && range.contains("11:19"), range)
    XCTAssertEqual(range.components(separatedBy: "Sep").count - 1, 1, "the day appears once: \(range)")
    // A missing or inverted end reads as the start alone rather than a nonsense span.
    let open = OmiDateFormat.range(date(2026, 9, 23, 10, 17), nil, calendar: calendar, locale: locale)
    XCTAssertFalse(open.contains("–"), open)
  }

  func testOffsetGrowsHoursInsteadOfSixtyPlusMinutes() {
    XCTAssertEqual(OmiDateFormat.offset(218), "3:38")
    XCTAssertEqual(OmiDateFormat.offset(3725), "1:02:05")
    XCTAssertEqual(OmiDateFormat.offset(-4), "0:00")
  }

  func testDurationStyles() {
    XCTAssertEqual(OmiDateFormat.duration(8), "8s")
    XCTAssertEqual(OmiDateFormat.duration(42 * 60 + 10), "42m 10s")
    XCTAssertEqual(OmiDateFormat.duration(3900), "1h 5m")
    XCTAssertEqual(OmiDateFormat.duration(7200), "2h")
  }

  // MARK: - Speakers

  private func segment(
    _ speaker: String?, isUser: Bool = false, personId: String? = nil, text: String = "hello"
  ) -> TranscriptSegment {
    TranscriptSegment(
      id: UUID().uuidString, text: text, speaker: speaker, isUser: isUser, personId: personId, start: 0, end: 1)
  }

  func testSpeakerLabelsAreYouThenPersonThenOneBasedNumber() {
    let formatter = SpeakerLabelFormatter(names: ["p1": "Alice"])
    XCTAssertEqual(formatter.label(for: segment("SPEAKER_03", isUser: true)), "You")
    XCTAssertEqual(formatter.label(for: segment("SPEAKER_03", personId: "p1")), "Alice")
    XCTAssertEqual(formatter.label(for: segment("SPEAKER_00")), "Speaker 1", "1-based, matching mobile")
    XCTAssertEqual(formatter.label(for: segment("SPEAKER_01", personId: "unknown")), "Speaker 2")
  }

  func testParticipantsNeverLeakRawDiarizationLabels() {
    let formatter = SpeakerLabelFormatter(names: ["p1": "Alice"])
    let participants = formatter.participants(in: [
      segment("SPEAKER_00", personId: "p1"), segment("SPEAKER_01"), segment("SPEAKER_00", personId: "p1"),
      segment("SPEAKER_02", isUser: true),
    ])
    XCTAssertEqual(participants, ["Alice", "Speaker 2", "You"])
    XCTAssertFalse(participants.contains { $0.contains("SPEAKER_") })
  }

  func testCopiedTranscriptUsesTheSameLabelsAndSkipsBlankTurns() {
    let formatter = SpeakerLabelFormatter(names: ["p1": "Alice"])
    let text = formatter.transcript([
      segment("SPEAKER_00", personId: "p1", text: "Hi"), segment("SPEAKER_01", text: "  "),
      segment("SPEAKER_01", text: "Hey"),
    ])
    XCTAssertEqual(text, "Alice: Hi\n\nSpeaker 2: Hey")
  }

  // MARK: - One conversation, one duration

  /// Activity and the Conversations list must report the same length for the same conversation.
  /// Activity measured the capture window (`finishedAt - startedAt`), which on a live socket is how
  /// long the socket had been open: an 8-second dictation read as 42m45s in Activity and 8s in the
  /// list (FC-capture-session-window-read-as-content-duration).
  func testActivityAndConversationsReportTheSameDuration() {
    let start = date(2026, 9, 23, 10, 0)
    let conversation = ServerConversation(
      id: "c1", createdAt: start, startedAt: start, finishedAt: start.addingTimeInterval(2565),
      structured: Structured(
        title: "Dictation", overview: "", emoji: "", category: "other", actionItems: [], events: []),
      transcriptSegments: [
        TranscriptSegment(
          id: "s1", text: "remind me to call", speaker: "SPEAKER_00", isUser: true, personId: nil, start: 0, end: 8)
      ],
      transcriptSegmentsIncluded: true, geolocation: nil, photos: [], appsResults: [], source: .desktop, language: "en",
      status: .completed, discarded: false, deleted: false, isLocked: false, starred: false, folderId: nil,
      inputDeviceName: nil)
    let activityRow = SpineConversation(conversation: conversation, memoryCount: 0, taskCount: 0, momentCount: 0)

    XCTAssertEqual(activityRow.duration, 8)
    XCTAssertEqual(SpineFormat.duration(activityRow.duration), conversation.formattedDuration)
    XCTAssertTrue(activityRow.emoji.isEmpty, "no 💬 fallback: the row draws the neutral waveform")
    XCTAssertEqual(activityRow.title, conversation.displayTitle)
  }

  // MARK: - Navigation vocabulary

  func testBackChipNamesItsDestinationAndAdvertisesEscape() {
    XCTAssertEqual(BackChip.helpText(for: "Conversations"), "Back to Conversations (Esc)")
    XCTAssertEqual(BackChip.helpText(for: "Back"), "Back (Esc)")
  }

  func testConversationDetailBadgeSaysWhatItCounts() {
    XCTAssertEqual(ConversationDetailView.segmentCountLabel(1), "1 segment")
    XCTAssertEqual(ConversationDetailView.segmentCountLabel(388), "388 segments")
  }

  @MainActor
  func testSettingsBackReturnsToThePageThatOpenedIt() {
    let navigation = ChatFirstShellNavigation(defaults: isolatedDefaults())
    navigation.selectPrimary(.tasks)
    navigation.selectMore(.settings)
    XCTAssertEqual(navigation.moreOrigin, .tasks)
    navigation.closeMorePage()
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertNil(navigation.moreOrigin)
  }

  @MainActor
  func testEscapeOnSettingsAlsoReturnsToItsOrigin() {
    let navigation = ChatFirstShellNavigation(defaults: isolatedDefaults())
    navigation.selectPrimary(.memories)
    navigation.selectMore(.settings)
    XCTAssertTrue(navigation.handleEscapeNavigation())
    XCTAssertEqual(navigation.route, .memories)
  }

  private func isolatedDefaults() -> UserDefaults {
    let suite = "DesktopUXContractTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite) ?? .standard
    defaults.removePersistentDomain(forName: suite)
    return defaults
  }

  // MARK: - Copy

  @MainActor
  func testClipboardRefusesToCopyEmptyText() {
    XCTAssertFalse(OmiClipboard.copy(""))
    XCTAssertFalse(OmiClipboard.copy("   \n"))
  }

  // MARK: - Icon button ladder

  func testRestingFilledIconButtonsStepUpOnHover() {
    let rest = GlassShell.iconButtonFill(isPressed: false, isActive: false, isHovering: false, restsFilled: true)
    let hover = GlassShell.iconButtonFill(isPressed: false, isActive: false, isHovering: true, restsFilled: true)
    XCTAssertEqual(rest, Ink.wash)
    XCTAssertEqual(hover, Ink.rowFillHover)
    // The bar's own buttons still rest clear.
    XCTAssertEqual(GlassShell.iconButtonFill(isPressed: false, isActive: false, isHovering: false), .clear)
  }

  func testIconButtonDiametersAreTheThreeRungs() {
    XCTAssertEqual(
      [OmiIconButtonSize.compact, .regular, .large].map(\.diameter), [22, 28, 32])
  }

  // MARK: - Settings search

  /// Every Settings search result must land on a card. A result whose `settingId` names no card
  /// selects the pane and then scrolls to nothing, which is what "Ask omi" and "Rewind" did.
  func testEverySettingsSearchResultHasACardToScrollTo() throws {
    let sources = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources")
    // Cards take their ID directly or through a row helper (`settingRow(settingId:)`); either way the
    // literal is spelled `settingId: "…"` outside the search index itself.
    let anchorPattern = try NSRegularExpression(pattern: #"settingId: "([^"]+)""#)
    var anchors = Set<String>()
    let files = try XCTUnwrap(FileManager.default.enumerator(at: sources, includingPropertiesForKeys: nil))
    for case let url as URL in files
    where url.pathExtension == "swift" && url.lastPathComponent != "SettingsSidebar.swift" {
      // omi-test-quality: source-inspection -- static contract: search anchors are string IDs spread across view builders with no runtime registry to query
      let text = try String(contentsOf: url, encoding: .utf8)
      for match in anchorPattern.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
        if let range = Range(match.range(at: 1), in: text) { anchors.insert(String(text[range])) }
      }
    }
    let missing = SettingsSearchItem.allSearchableItems.map(\.settingId).filter { !anchors.contains($0) }
    XCTAssertEqual(missing, [], "search results with no card to scroll to")
  }

  /// "Reset Window Size" is a window setting, not a font one: its result lands on its own card.
  func testResetWindowSizeSearchResultLandsOnTheWindowCard() throws {
    let item = try XCTUnwrap(SettingsSearchItem.allSearchableItems.first { $0.name == "Reset Window Size" })
    XCTAssertEqual(item.settingId, "general.window")
  }
}

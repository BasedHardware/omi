import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The query shell's decisions, held where they are arithmetic rather than pixels.
@MainActor
final class QueryShellTests: XCTestCase {

  // MARK: - The two keys

  func testReturnSearchesAndCommandReturnAsks() {
    XCTAssertEqual(QueryShellSubmit.resolve(text: "priya", commandHeld: false), .search)
    XCTAssertEqual(QueryShellSubmit.resolve(text: "priya", commandHeld: true), .ask)
  }

  /// The error path: an empty field must do nothing at all rather than send an empty chat turn,
  /// which `ChatProvider.sendMessage` silently drops — a key that appears to do nothing is worse
  /// than one that is inert on purpose.
  func testAnEmptyOrBlankFieldSubmitsNothingOnEitherKey() {
    for blank in ["", "   ", "\n \t"] {
      XCTAssertEqual(QueryShellSubmit.resolve(text: blank, commandHeld: false), .none)
      XCTAssertEqual(QueryShellSubmit.resolve(text: blank, commandHeld: true), .none)
    }
  }

  // MARK: - The gap

  /// The single most important number on the surface: two panels 12 pt apart read as two objects,
  /// the same two at 0 read as one slab with a rule through it.
  func testTheTwoPanelsKeepRealAirBetweenThemAndShareOneCorner() {
    XCTAssertEqual(QueryShellLayout.panelGap, 12)
    XCTAssertEqual(
      QueryShellLayout.panelGap, RewindSearchLayout.panelGap,
      "one product, one opinion about how far apart its glass sits")
    XCTAssertEqual(QueryShellLayout.panelCornerRadius, InkGlass.cornerRadius)
  }

  /// Both panels sit in the top bar's lane, or the surface reads as three objects that missed
  /// each other.
  func testThePanelsShareTheTopBarsLane() {
    for width in [1_400.0, 800.0, 40.0] {
      XCTAssertEqual(
        QueryShellLayout.laneWidth(for: width),
        TopNavigationLayoutMetrics.contentLaneWidth(for: width))
    }
  }

  // MARK: - The count sentence

  func testTheCountLineSaysTheCorpusAtRestAndTheFractionUnderAFilter() {
    XCTAssertEqual(
      QueryShellCount.sentence(matching: 0, total: 3_741, isFiltering: false),
      "3,741 moments captured")
    XCTAssertEqual(
      QueryShellCount.sentence(matching: 12, total: 3_741, isFiltering: true),
      "12 results · of 3,741 captured")
    XCTAssertEqual(
      QueryShellCount.sentence(matching: 1, total: 3_741, isFiltering: true),
      "1 result · of 3,741 captured")
  }

  /// Typing one letter must not make the surface claim the archive is empty. Collapsing the two
  /// sentences into one is exactly how that happens.
  func testFilteringToNothingStillReportsTheWholeCorpus() {
    let sentence = QueryShellCount.sentence(matching: 0, total: 3_741, isFiltering: true)
    XCTAssertTrue(sentence.contains("3,741"))
    XCTAssertFalse(sentence.hasPrefix("0 moments"))
  }

  // MARK: - The request

  func testARestingRequestIsNotFilteringAndAdmitsEverything() {
    let request = QueryShellRequest()
    XCTAssertFalse(request.isFiltering)
    XCTAssertTrue(request.admits(kind: .rewind, at: .distantPast))
    XCTAssertTrue(request.admits(kind: .memories, at: .distantPast))
  }

  func testEachOfTheThreeControlsCountsAsFiltering() {
    XCTAssertTrue(QueryShellRequest(text: "priya").isFiltering)
    XCTAssertTrue(QueryShellRequest(kind: .memories).isFiltering)
    XCTAssertTrue(QueryShellRequest(range: .today).isFiltering)
  }

  func testTheTypeChipAndTheTimeWindowNarrowIndependently() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let request = QueryShellRequest(kind: .conversations, range: .week)
    XCTAssertTrue(request.admits(kind: .conversations, at: now.addingTimeInterval(-3_600), now: now))
    XCTAssertFalse(
      request.admits(kind: .memories, at: now.addingTimeInterval(-3_600), now: now),
      "the chip must exclude a kind it did not select")
    XCTAssertFalse(
      request.admits(kind: .conversations, at: now.addingTimeInterval(-30 * 86_400), now: now),
      "the time window must exclude a row older than it")
  }

  func testTheTermIsNormalisedOnceSoEveryBodyMatchesTheSameWay() {
    XCTAssertEqual(QueryShellRequest(text: "  Priya  ").term, "priya")
    XCTAssertTrue(QueryShellRequest(text: "   ").term.isEmpty)
  }

  func testAllTimeAdmitsAnythingAndTodayStartsAtMidnight() {
    let calendar = Calendar.current
    let now = Date()
    XCTAssertNil(QueryShellRange.all.earliest(now: now, calendar: calendar))
    XCTAssertEqual(
      QueryShellRange.today.earliest(now: now, calendar: calendar), calendar.startOfDay(for: now))
    XCTAssertFalse(
      QueryShellRange.today.admits(
        calendar.startOfDay(for: now).addingTimeInterval(-1), now: now, calendar: calendar))
  }

  // MARK: - The wordless controls

  /// A control with no label is only legible if its dot is. Three states, three distinguishable
  /// fills, and "off" must never look like "on".
  func testTheStateDotGivesEveryStateItsOwnColour() {
    let fills = [HomeStatusState.active, .inactive, .blocked].map(ShellStatusDot.fill(for:))
    XCTAssertEqual(
      Set(fills.map(\.description)).count, 3,
      "three states must not collapse onto two fills")
    XCTAssertNotEqual(
      ShellStatusDot.fill(for: .inactive).description,
      ShellStatusDot.fill(for: .active).description,
      "off must never render as on")
  }

  // MARK: - The answer thread

  /// The mark is drawn in an overlay offset by exactly this much, so the gutter is
  /// the room the mark needs — its own width plus one gap — and nothing else.
  ///
  /// Pinned relationally rather than to a literal, because the literal is what went
  /// wrong: at `32 + OmiSpacing.md` the gutter was a margin of its own invention,
  /// and on this panel — whose content starts `panelPaddingHorizontal` in — it put
  /// the mark left of every other element's leading edge while pushing the message
  /// column 60 pt off the glass. The measurement that fixed it was the panel's own
  /// inset, so that is what the test compares against.
  func testTheAssistantMarksGutterIsTheRoomTheMarkNeedsAndNoMore() {
    XCTAssertEqual(
      ChatOmiMarkPlacement.markGutter,
      ChatOmiMarkPlacement.markSize + OmiSpacing.sm,
      "the gutter is the mark's width plus one gap")

    // The transcript reserves the gutter itself, so the mark lands on the panel's
    // own content edge — level with the header chip — rather than left of it.
    XCTAssertLessThanOrEqual(
      ChatOmiMarkPlacement.markGutter, QueryShellLayout.panelPaddingHorizontal * 2,
      "a gutter wider than the panel's own margins is chrome, not a gutter")
    XCTAssertGreaterThanOrEqual(
      ChatOmiMarkPlacement.markGutter, ChatOmiMarkPlacement.markSize,
      "the gutter must at least hold the mark it reserves room for")
  }

  /// **The failure this build actually produces must not render as an empty panel.**
  ///
  /// A crashed agent runtime throws something that is not a `BridgeError` with a card, so it lands
  /// on the provider's legacy `errorMessage` with `currentError` nil. Handling only the structured
  /// card left the panel silent for the one failure that has occurred on every turn here.
  func testACrashedAgentRuntimeProducesRetryableUserFacingCopy() {
    let classified = AgentErrorClassifier.classify("pi-mono process exited (code 1)")
    XCTAssertEqual(classified.code, .runtimeCrashed)
    XCTAssertTrue(classified.retryable, "a crashed runtime is worth another attempt")
    XCTAssertFalse(
      classified.userMessage.contains("pi-mono"),
      "the panel must not show a process name to the person holding the keyboard")
    XCTAssertFalse(classified.userMessage.isEmpty)
  }

  /// The chips are the only vocabulary the panel body is filtered by, so their identity is a
  /// contract with whatever occupies the seam.
  ///
  /// It is also the guard against the tempting fifth chip. The Brain Map is a control on this
  /// surface, but it is not a *kind* of row: every chip here narrows the spine in place and leaves
  /// you on the same list, and the map is a second drawing of the whole corpus on a page that owns
  /// it. A chip that looks like its four neighbours and navigates instead teaches the row a rule and
  /// then breaks it — so `Brain Map ›` lives in the panel header beside `Filter ›`, next to the one
  /// other control that leaves the list (`Chat ›`), and `QueryShellKind` stays four.
  func testTheChipsAreTheFourTypesTheSpineMerges() {
    XCTAssertEqual(
      QueryShellKind.allCases.map(\.rawValue), ["all", "conversations", "memories", "rewind"])
    XCTAssertEqual(QueryShellKind.allCases.map(\.title).first, "All")
  }

  // MARK: - Chat capability on the one chat surface

  /// **The regression the deleted chat page left behind.** Clear and copy had their only call sites
  /// on a page that was removed for being an unreachable reduced copy, so from that commit until
  /// this one there was no way to clear or copy the conversation anywhere in the app.
  func testTheConversationMenuOffersCopyAndClearOnceThereIsAConversation() {
    let empty = HomeChatMenu.resolve(messageCount: 0, isSending: false, isClearing: false)
    XCTAssertFalse(empty.canCopy)
    XCTAssertFalse(empty.canClear)
    XCTAssertFalse(empty.isPresentable, "an overflow over nothing is chrome pretending to be a control")

    let settled = HomeChatMenu.resolve(messageCount: 4, isSending: false, isClearing: false)
    XCTAssertTrue(settled.canCopy)
    XCTAssertTrue(settled.canClear)
    XCTAssertTrue(settled.isPresentable)
  }

  /// Clearing races a turn that is about to append to the thing being cleared, so it waits — but
  /// copying what is already on screen never has to.
  func testClearYieldsToALiveTurnWhileCopyDoesNot() {
    let sending = HomeChatMenu.resolve(messageCount: 4, isSending: true, isClearing: false)
    XCTAssertTrue(sending.canCopy)
    XCTAssertFalse(sending.canClear)
    XCTAssertTrue(sending.isPresentable)

    let clearing = HomeChatMenu.resolve(messageCount: 4, isSending: false, isClearing: true)
    XCTAssertFalse(clearing.canClear, "clear must not be re-entrant")
    XCTAssertFalse(clearing.canCopy, "the transcript being torn down is not a transcript to copy")
  }

  /// Copy promises the conversation, not the machinery: an assistant turn contributes its answer
  /// and not its reasoning, which is the same promise the per-message copy button already makes.
  func testCopyingTheConversationWritesTheAnswersAndNotTheReasoning() {
    let messages = [
      ChatMessage(text: "what did priya say about the deadline", sender: .user),
      ChatMessage(
        text: "", sender: .ai,
        contentBlocks: [
          .thinking(id: "t", text: "the user is asking about a person named priya"),
          .text(id: "a", text: "She moved it to Friday."),
        ]),
    ]
    let copied = HomeChatTranscript.plainText(messages)
    XCTAssertEqual(copied, "You: what did priya say about the deadline\n\nomi: She moved it to Friday.")
    XCTAssertFalse(copied.contains("the user is asking"))
  }

  /// A turn that produced nothing copyable — a bare tool row, a send that failed — contributes no
  /// line rather than an attributed blank.
  func testAnEmptyTurnContributesNoLineAndAnEmptyTranscriptCopiesNothing() {
    XCTAssertEqual(HomeChatTranscript.plainText([]), "")
    let messages = [
      ChatMessage(text: "hello", sender: .user),
      ChatMessage(text: "   ", sender: .ai),
    ]
    XCTAssertEqual(HomeChatTranscript.plainText(messages), "You: hello")
  }

  /// **"All of chat is there" is not the same as "chat is reachable".** Asking is a mode, and the
  /// mode is view state, so leaving Home and coming back leaves the transcript on the provider and
  /// nothing on screen admitting it exists. The panel's corner offers the way back — but only once
  /// history has actually loaded, or the chip flickers in during every launch.
  func testTheWayBackIntoTheTranscriptAppearsOnlyForLoadedHistory() {
    XCTAssertFalse(HomeChatReentry.isOffered(messageCount: 0, isLoading: false))
    XCTAssertFalse(
      HomeChatReentry.isOffered(messageCount: 12, isLoading: true),
      "a count that is still being restored is not history yet")
    XCTAssertTrue(HomeChatReentry.isOffered(messageCount: 12, isLoading: false))
  }

  /// It is the same rule Home already had for its resting mode. Two opinions about "is there
  /// history worth showing" is how one of them silently stops matching the other.
  func testReentryReusesHomesOneOpinionAboutExistingHistory() {
    for (count, loading) in [(0, false), (12, true), (12, false), (1, false)] {
      XCTAssertEqual(
        HomeChatReentry.isOffered(messageCount: count, isLoading: loading),
        HomeHistoryPresentationPolicy.restingMode(isLoading: loading, messageCount: count) == .chat)
    }
  }
}

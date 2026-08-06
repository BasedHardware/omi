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

  /// The mark is drawn in an overlay offset by exactly this much. A host that insets the transcript
  /// by less draws it outside the container and the assistant's only identity cue disappears —
  /// which is what left ask mode's replies as bare text beside capsuled user turns.
  func testTheAssistantMarksGutterIsTheOffsetItIsDrawnAt() {
    XCTAssertEqual(ChatOmiMarkPlacement.markGutter, 32 + OmiSpacing.md)
    XCTAssertGreaterThanOrEqual(
      ChatOmiMarkPlacement.markGutter, ChatOmiMarkPlacement.reservedRowHeight,
      "the gutter must be at least as wide as the mark is tall")
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
  func testTheChipsAreTheFourTypesTheSpineMerges() {
    XCTAssertEqual(
      QueryShellKind.allCases.map(\.rawValue), ["all", "conversations", "memories", "rewind"])
    XCTAssertEqual(QueryShellKind.allCases.map(\.title).first, "All")
  }
}

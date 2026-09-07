import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The query shell's decisions, held where they are arithmetic rather than pixels.
@MainActor
final class QueryShellTests: XCTestCase {

  /// **`⏎` sends. There is nothing else for it to mean.**
  ///
  /// The surface used to answer this question with "it depends": `⏎` searched and `⌘⏎` asked, which
  /// is why the bar carried two labelled buttons to explain itself. The reader looked at the running
  /// build and said so — *"No need to separate search and ask. While typing its just search and then
  /// if i press enter its chat."* Searching is not a key, because the list narrows as each character
  /// lands; the only decision left is whether to send.
  func testReturnSendsAndThereIsNoSecondThingItCouldMean() {
    XCTAssertEqual(QueryShellSubmit.resolve(text: "priya"), .ask)
  }

  /// The error path: an empty field must do nothing at all rather than send an empty chat turn,
  /// which `ChatProvider.sendMessage` silently drops — a key that appears to do nothing is worse
  /// than one that is inert on purpose.
  func testAnEmptyOrBlankFieldSubmitsNothing() {
    for blank in ["", "   ", "\n \t"] {
      XCTAssertEqual(QueryShellSubmit.resolve(text: blank), .none)
    }
  }

  // MARK: - What a submit leaves behind

  /// A composer that keeps the message it just sent leaves `Ask a follow-up…` permanently
  /// unreachable, makes a second `⏎` re-send the question verbatim, and forces the reader to empty
  /// the field by hand before they can write the next one.
  func testAskingSendsTheTrimmedQuestionAndEmptiesTheComposer() {
    let submission = QueryShellSubmission.resolve(text: "  what did I ship  ")
    XCTAssertEqual(submission.action, .ask)
    XCTAssertEqual(submission.question, "what did I ship")
    XCTAssertEqual(submission.text, "", "the send consumes the message")
    XCTAssertEqual(submission.mode, .answer)
  }

  /// **A submit from the list is the same submit.** This replaces the assertion that `⏎` on the
  /// hero kept the term and stayed on the results, which was the two-key contract the reader asked
  /// us to drop: typing is what filters, so the only thing left for a key to do is send — and the
  /// send takes the words with it, out of the field and into the conversation.
  func testSubmittingFromTheListSendsRatherThanCommittingAFilter() {
    let submission = QueryShellSubmission.resolve(text: "priya")
    XCTAssertEqual(submission.action, .ask)
    XCTAssertEqual(submission.question, "priya")
    XCTAssertEqual(submission.text, "", "the send consumes the words wherever the bar is standing")
    XCTAssertEqual(submission.mode, .answer)
  }

  /// An inert key must not move the reader. Before this, an empty field was itself read as "go back
  /// to the list", so emptying the bar to type a follow-up ejected you from the conversation.
  func testAnInertSubmitMovesNothingAndKeepsTheReaderInTheirConversation() {
    for blank in ["", "   ", "\n \t"] {
      let submission = QueryShellSubmission.resolve(text: blank)
      XCTAssertEqual(submission.action, .none)
      XCTAssertNil(submission.question)
      XCTAssertNil(submission.mode, "an empty field is not an instruction to leave answer mode")
      XCTAssertEqual(submission.text, blank)
    }
  }

  /// **Opening the app is opening a chat with Omi.** Home lands in the conversation, with the
  /// spine/search surface one `esc` / `‹ Results` away — not the other way round.
  func testHomeOpensInTheConversation() {
    XCTAssertEqual(QueryShellMode.homeDefault, .answer)
    XCTAssertEqual(QueryComposerPlacement.of(QueryShellMode.homeDefault), .panelFooter)
  }

  /// **Every `homeStage*` notification the bridge posts has an observer on the modern surface.**
  /// The `home_close_panel` action posts `.homeStageClose` and reports success to the caller, so an
  /// unobserved notification is a bridge action that silently does nothing — the defect the home
  /// automation entry points exist to avoid (it shipped once: the modern surface dropped its
  /// `.homeStageClose` handler while the registry kept answering "ok").
  /// **A bridge action that promises the conversation leaves no search behind.** Mode is derived
  /// from the search text, so `home_open_chat` / `home_ask` / `home_close_panel` reporting success
  /// while the text survives would leave their effect hidden behind the results panel — the
  /// regression cross-review caught after the close handler landed without covering open/ask.
  func testConversationBridgeIntentsCollapseTheSearchAndAttachDoesNot() {
    for intent in [HomeBridgeIntent.openChat, .ask, .closePanel] {
      XCTAssertEqual(intent.searchTextAfter("standup notes"), "", "\(intent) must land on the conversation")
    }
    XCTAssertEqual(HomeBridgeIntent.attach.searchTextAfter("standup notes"), "standup notes")
    // The transition is total: every intent has an explicit answer for live search text.
    for intent in HomeBridgeIntent.allCases {
      _ = intent.searchTextAfter("x")
    }
  }

  func testEveryBridgeHomeStageNotificationIsObservedByTheModernSurface() throws {
    // omi-test-quality: source-inspection -- static contract: SwiftUI @State/onReceive wiring cannot be driven hermetically without mounting the view; pins the registration sites for the bridge's four homeStage notifications.
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()  // Tests/
        .deletingLastPathComponent()  // Desktop/
        .appendingPathComponent("Sources/MainWindow/QueryShell/QueryShellHome.swift"),
      encoding: .utf8)
    for name in ["homeStageOpenChat", "homeStageClose", "homeStageAsk", "homeStageAttach"] {
      XCTAssertTrue(
        source.contains("publisher(for: .\(name))"),
        "QueryShellHome no longer observes .\(name); its bridge action now succeeds while doing nothing")
    }
    // …and each handler applies the shared search-text transition, so an action cannot succeed
    // while its effect stays hidden behind a live search.
    for intent in ["openChat", "closePanel", "ask", "attach"] {
      XCTAssertTrue(
        source.contains("HomeBridgeIntent.\(intent).searchTextAfter"),
        "the .\(intent) handler no longer applies HomeBridgeIntent.searchTextAfter")
    }
  }

  // MARK: - Where the composer stands

  /// **A chat you have opened is not searching.** The field belongs above the rows it filters and
  /// under the transcript it is replying to, and this is the one function that decides which — so
  /// the chrome the composer draws and the room the panel reserves for it cannot describe two
  /// different arrangements.
  func testSearchingPutsTheComposerAboveThePanelAndChattingPutsItInside() {
    XCTAssertEqual(QueryComposerPlacement.of(.results), .hero)
    XCTAssertEqual(QueryComposerPlacement.of(.answer), .panelFooter)
  }

  /// The two placements rest at different heights on purpose: the hero is a place to type, the
  /// in-panel composer is a chat input. A single resting height for both means one of them is
  /// wearing the other's chrome.
  func testTheTwoPlacementsRestAtTheirOwnHeights() {
    XCTAssertEqual(
      QueryShellLayout.composerContainerMinHeight(placement: .hero), QueryShellLayout.barMinHeight)
    XCTAssertEqual(
      QueryShellLayout.composerContainerMinHeight(placement: .panelFooter),
      QueryShellLayout.panelComposerMinHeight)
    XCTAssertLessThan(
      QueryShellLayout.panelComposerMinHeight, QueryShellLayout.barMinHeight,
      "the composer inside the panel must not be as tall as the hero bar it replaced")
    XCTAssertLessThan(
      QueryShellLayout.panelComposerFontSize, QueryShellLayout.queryFontSize,
      "a query face under a conversation reads as a headline stacked on the end of it")
  }

  // MARK: - The in-panel composer's proportions

  /// **A true capsule, not a large-ish card corner.**
  ///
  /// It shipped wearing the shared `chatComposerShell`: an 18 pt corner on a 52 pt pill, which has
  /// visibly straight sides and reads as a boxy input. At half the pill's own height the two ends
  /// are semicircles — and the send disc, one `panelComposerShellInset` in from a
  /// `panelComposerControlDiameter` frame, comes out concentric with the cap it sits in, which is
  /// what makes the trailing cluster look settled rather than parked.
  func testTheInPanelComposerIsATrueCapsuleRatherThanARoundedBox() {
    XCTAssertEqual(
      QueryShellLayout.panelComposerCornerRadius,
      QueryShellLayout.panelComposerShellHeight / 2,
      "the corner is no longer half the height, so the composer has straight sides again")
    XCTAssertGreaterThan(
      QueryShellLayout.panelComposerCornerRadius, ChatComposerLayout.shellRadius,
      "the composer is back on a card radius that is too small for its own height")
    XCTAssertEqual(
      QueryShellLayout.panelComposerShellInset
        + QueryShellLayout.panelComposerControlDiameter / 2,
      QueryShellLayout.panelComposerCornerRadius,
      "the send disc is no longer concentric with the capsule's cap")
  }

  /// **The height comes from the padding, and one line is exactly one control tall.**
  ///
  /// Both halves matter. A declared row height is how the interior padding silently stops being
  /// symmetric; and if a laid-out line of the chat face is not the same height as the disc beside
  /// it, the reader's own words and the button that sends them sit at permanently different centres
  /// however the row aligns.
  func testTheInPanelComposersHeightIsItsPaddingAndItsRowIsOneHeight() {
    XCTAssertEqual(
      QueryShellLayout.panelComposerShellHeight,
      QueryShellLayout.panelComposerControlDiameter
        + QueryShellLayout.panelComposerShellInset * 2,
      "the pill's height stopped being one control row plus its own margin")
    XCTAssertEqual(
      QueryShellLayout.panelComposerMinEditorHeight,
      QueryShellLayout.panelComposerControlDiameter,
      "one line of the chat face is not a control tall — text and buttons sit at different centres")
  }

  /// **The pill stands inside the panel rather than spanning it corner to corner**, and the reserve
  /// pays for the air under it. Reserving only the pill is how the composer overruns the panel's own
  /// bottom padding the moment the inset is tuned.
  func testTheInPanelComposerStandsInFromThePanelAndIsReservedWholesale() {
    XCTAssertGreaterThan(QueryShellLayout.panelComposerEdgeInset, 0)
    XCTAssertGreaterThan(QueryShellLayout.panelComposerBottomInset, 0)
    XCTAssertEqual(
      QueryShellLayout.panelComposerMinHeight,
      QueryShellLayout.panelComposerShellHeight + QueryShellLayout.panelComposerBottomInset,
      "the panel reserves the pill but not the air under it")
  }

  // MARK: - The gap

  /// The single most important number on the surface: two panels keep a compact real gap,
  /// the same two at 0 read as one slab with a rule through it.
  func testTheTwoPanelsKeepRealAirBetweenThemAndShareOneCorner() {
    XCTAssertEqual(QueryShellLayout.panelGap, 8)
    XCTAssertEqual(
      QueryShellLayout.panelGap, RewindSearchLayout.panelGap,
      "one product, one opinion about how far apart its glass sits")
    XCTAssertEqual(QueryShellLayout.panelCornerRadius, InkGlass.cornerRadius)
  }

  func testSharedSearchAndBrainChromeUseTheCompactDensityContract() {
    XCTAssertEqual(QueryShellLayout.barMinHeight, 48)
    XCTAssertEqual(RewindSearchLayout.barHeight, QueryShellLayout.barMinHeight)
    XCTAssertEqual(RewindSearchMetrics.queryFontSize, QueryShellLayout.queryFontSize)
    XCTAssertEqual(
      PagePanelFirstRowMetrics.topPadding,
      QueryShellLayout.panelPaddingTop,
      "list and catalog toolbars must start where Activity's first row starts")
    XCTAssertEqual(
      BrainSectionPageMetrics.navigationTopPadding,
      PagePanelFirstRowMetrics.topPadding,
      "Brain pills must not sit closer to the panel edge than the other page controls")
    XCTAssertEqual(
      PagePanelFirstRowMetrics.bottomPadding,
      0,
      "the first row must not stack a second gap before its content")
    XCTAssertEqual(
      BrainSectionPageMetrics.navigationBottomPadding,
      PagePanelVerticalRhythm.rowGap,
      "Brain navigation owns the single gap before its refinement row")
    XCTAssertEqual(BrainSectionPageMetrics.navigationHeight, 44)
    XCTAssertGreaterThanOrEqual(QueryShellLayout.chipHeight, 28)
    XCTAssertLessThan(QueryShellLayout.panelHeaderSpacing, 8)
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
      QueryShellCount.sentence(matching: 0, total: 3_741, isFiltering: false, isSettled: true),
      "3,741 moments in everything Omi has kept")
    XCTAssertEqual(
      QueryShellCount.sentence(matching: 12, total: 3_741, isFiltering: true, isSettled: true),
      "12 results · of 3,741 in everything Omi has kept")
    XCTAssertEqual(
      QueryShellCount.sentence(matching: 1, total: 3_741, isFiltering: true, isSettled: true),
      "1 result · of 3,741 in everything Omi has kept")
  }

  /// **Every branch says what it counted.** There is a second counter on this page — the hour rail,
  /// 200 pt to the left, counting *one day* of screen capture — and the reader could not tell which
  /// number covered what: they looked at a large `0` beside `798 so far · still counting` and asked
  /// what each was supposed to show.
  ///
  /// The first fix gave the two counters different nouns. That shipped and did not work, because a
  /// noun is not a scope. So all four states are asserted here, including the one that names no
  /// number worth reading (`still counting`) and the one where the filter matched nothing — the two
  /// most likely to be written without a scope, because in both the number is the interesting part.
  func testEveryStateOfTheCountLineNamesTheScopeItCounted() {
    let states = [
      QueryShellCount.sentence(matching: 0, total: 798, isFiltering: false, isSettled: true),
      QueryShellCount.sentence(matching: 0, total: 798, isFiltering: false, isSettled: false),
      QueryShellCount.sentence(matching: 12, total: 798, isFiltering: true, isSettled: true),
      QueryShellCount.sentence(matching: 0, total: 798, isFiltering: true, isSettled: true),
    ]

    for sentence in states {
      XCTAssertTrue(
        sentence.contains(QueryShellCount.scope),
        "\"\(sentence)\" does not say what it counted, so it only means something next to the rail")
    }
    XCTAssertEqual(
      states[1], "798 so far · still counting everything Omi has kept",
      "the unsettled line named no scope at all — it is the one the reader asked about")
    XCTAssertEqual(states[3], "0 results · of 798 in everything Omi has kept")
  }

  /// **The corner has to say all of that inside the corner.** The count is set on one line
  /// (`.lineLimit(1)`), so a sentence too long for the space is not wrapped — it is truncated from
  /// the end, and the end is exactly the scope clause this line exists to carry. Measured in the
  /// face the corner is actually set in, at the narrowest window the app opens at.
  ///
  /// The budget is half the panel's inner width: the other half belongs to the header's leading
  /// controls (`Filter ›`, `Brain Map ›`, `Chat ›`), which is the widest that cluster ever gets.
  func testEveryCountSentenceFitsTheCornerAtTheNarrowestWindow() {
    let lane = QueryShellLayout.laneWidth(for: DesktopWindowLayoutPolicy.width)
    let inner = lane - QueryShellLayout.panelPaddingHorizontal * 2
    let budget = inner / 2
    let attributes = [NSAttributedString.Key.font: NSFont.systemFont(ofSize: OmiType.caption)]

    for sentence in [
      QueryShellCount.sentence(matching: 0, total: 88_888, isFiltering: false, isSettled: true),
      QueryShellCount.sentence(matching: 0, total: 88_888, isFiltering: false, isSettled: false),
      QueryShellCount.sentence(matching: 88_888, total: 88_888, isFiltering: true, isSettled: true),
      QueryShellCount.sentence(matching: 0, total: 88_888, isFiltering: true, isSettled: true),
    ] {
      let width = (sentence as NSString).size(withAttributes: attributes).width
      XCTAssertLessThanOrEqual(
        width, budget,
        "\"\(sentence)\" is \(width)pt in a \(budget)pt corner — it will truncate, and the first "
          + "thing an ellipsis eats is the scope")
    }
  }

  /// Typing one letter must not make the surface claim the archive is empty. Collapsing the two
  /// sentences into one is exactly how that happens.
  func testFilteringToNothingStillReportsTheWholeCorpus() {
    let sentence = QueryShellCount.sentence(
      matching: 0, total: 3_741, isFiltering: true, isSettled: true)
    XCTAssertTrue(sentence.contains("3,741"))
    XCTAssertFalse(sentence.hasPrefix("0 moments"))
  }

  /// The corner climbed 5,562 → 7,310 → 7,311 while the tester watched it, presented throughout as a
  /// settled total. A number still being assembled has to say so.
  func testAnUnsettledCorpusSaysItIsStillCountingRatherThanNamingATotal() {
    let counting = QueryShellCount.sentence(
      matching: 0, total: 5_562, isFiltering: false, isSettled: false)

    XCTAssertEqual(counting, "5,562 so far · still counting everything Omi has kept")
    XCTAssertTrue(
      counting.contains("so far"),
      "A count that is still climbing must not claim to be the whole account.")

    XCTAssertEqual(
      QueryShellCount.sentence(matching: 0, total: 7_311, isFiltering: false, isSettled: true),
      "7,311 moments in everything Omi has kept",
      "Once hydration finishes the same line settles into a total.")
  }

  /// **The two numbers on this panel count different things and must never wear the same noun.**
  /// The rail counts one day of screen capture; the corner counts the whole account — conversations,
  /// memories and screen together. The tester read "0 screen moments" beside "7,311 moments
  /// captured" as a contradiction, because as written it was one.
  func testTheCornerAndTheRailDoNotShareANoun() {
    let corner = QueryShellCount.sentence(
      matching: 0, total: 7_311, isFiltering: false, isSettled: true)
    let rail = SpineHourRail.headlineCaption(0)

    XCTAssertEqual(rail, "screen moments")
    XCTAssertTrue(
      corner.hasSuffix(QueryShellCount.scope),
      "The corner names its scope out loud: everything, not a day.")
    XCTAssertFalse(
      corner.contains("screen"),
      "Only the rail counts screen capture; the corner counts three kinds of record.")
    XCTAssertFalse(
      corner.contains(rail),
      "\"\(corner)\" and \"\(rail)\" sit 200 pt apart and must not read as the same population.")
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
  /// other control that leaves the list (`Chat ›`), while Tasks remains a filter over the spine.
  func testTheChipsAreTheFiveTypesTheSpineMerges() {
    XCTAssertEqual(
      QueryShellKind.allCases.map(\.rawValue), ["all", "conversations", "memories", "tasks", "rewind"])
    XCTAssertEqual(QueryShellKind.allCases.map(\.title).first, "All")
  }

  // MARK: - Where Home's controls send you

  /// **Home routes; it does not own.** Every row on this surface belongs to an established page, and
  /// INV-NAV-1's rule is that a control here opens that page rather than growing a smaller version of
  /// it in the panel. `QueryShellRoute` is that rule as a value, so this is the check that a control
  /// added to Home later still lands somewhere real.
  ///
  /// `Brain Map ›` in the panel header is the newest of these and the one the rule is easiest to
  /// break on: an atlas is a view, so drawing it inside the panel is a tempting one-line change, and
  /// it would leave Home with a map that has none of the hub's camera, time cursor, evidence
  /// inspector or cohort gate.
  func testEveryWayOutOfHomeLandsOnThePageThatOwnsIt() {
    for route in QueryShellRoute.allCases {
      XCTAssertTrue(
        TopNavigationRoutes.primaryItems.contains { $0.index == route.navItem.rawValue },
        "\(route) leaves Home for a page the top bar has no pill for")
    }

    XCTAssertEqual(QueryShellRoute.conversation.navItem, .conversations)
    XCTAssertEqual(QueryShellRoute.memories.navItem, .conversations)
    XCTAssertEqual(QueryShellRoute.brainMap.navItem, .conversations)
    XCTAssertEqual(QueryShellRoute.rewind.navItem, .conversations)
  }

  /// Each route into Brain must select the peer view that owns its content.
  func testTheBrainRoutesSelectTheirOwnViews() {
    XCTAssertEqual(
      QueryShellRoute.allCases.compactMap(\.memoryDestination),
      [.conversations, .memories, .brainMap, .rewind],
      "Home's Brain routes no longer select their peer views one-for-one")

    for route in QueryShellRoute.allCases {
      guard let hubView = route.memoryDestination else { continue }
      XCTAssertTrue(
        ActivityDestinationChip.reachableHubDestinations.contains(hubView),
        "\(route) selects a hub view Activity's chip row has no chip for")
    }
  }

  /// **The map has exactly one route out of Home.** The panel header's `Brain Map ›` and the spine's
  /// end-of-day card are two controls; two routes would be two maps, and the second one is always the
  /// one that stops matching the hub.
  func testBothOfHomesWaysIntoTheMapAreTheSameRoute() {
    XCTAssertEqual(QueryShellRoute.brainMap.memoryDestination, .brainMap)
    XCTAssertEqual(
      QueryShellRoute.allCases.filter { $0.memoryDestination == .brainMap }, [.brainMap])
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
}

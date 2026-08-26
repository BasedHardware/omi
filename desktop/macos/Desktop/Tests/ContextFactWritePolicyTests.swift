import XCTest

@testable import Omi_Computer

/// Every statement here is real live dogfood data (lightly truncated), not
/// synthetic: the policy was fitted on the pre-2026-08-16T17:33 corpus and
/// these assertions pin its behavior on representatives of each class.
final class ContextFactWritePolicyTests: XCTestCase {
  func testMachineryEchoesAreDropped() {
    for statement in [
      "The destination is unknown/.",
      "A user requests a 150-400 token summary of untrusted screen-derived content.",
      "The user is instructed to fill evidence_refs with supporting wording.",
      "UNTRUSTED SCREEN-DERIVED CONTENT: The user provided quoted data captured from applications.",
      "   ",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .dropMachinery, statement)
    }
  }

  func testSceneryIsCappedNotDropped() {
    for statement in [
      "A Google Sheets document named Combined_Cap_Table is open in a tab within a browser.",
      "A Slack workspace is open in a browser-like window and shows a Yukon Research channel structure.",
      "The user is viewing a usage/settings panel labeled Usage with a Weekly SuperGrok Heavy Limit.",
      "The left sidebar lists multiple color-coded sections such as Wedding Plan, Shop, Retro.",
      "Finder is being used.",
      "There is one new item in the Yukon announcements channel on Slack.",
      "The user is reviewing their Gmail inbox and has multiple promotions emails visible.",
      "The active window is Finder in Recents view.",
      "The Discord window shows a video call with multiple participants in a grid of thumbnails.",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .capScenery, statement)
    }
  }

  func testNamedPersonSpeechActsAreFlooredToArmingEligibility() {
    // nano scored 8 of 9 of these 0.0 in live data while a sidebar description
    // scored 0.7 — the floor exists because the score is blind to this class.
    for statement in [
      "David posted a thread about odd behavior where Boardy recommends something but has context-loss.",
      "Mihir Malde thanked flagging the issue and said the team is looking into fixing it.",
      "Kory Hoang mentions an upcoming first interview for a position and shares a URL.",
      "Ratnam requested a GitHub username or URL from the other party.",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .floorHumanEvent, statement)
    }
    XCTAssertEqual(ContextFactWritePolicy.humanEventWorthinessFloor, 0.6, accuracy: 0.000_001)
  }

  func testScenerySubjectsWithSpeechShapedNounsAreNotHumanEvents() {
    // "Review notes", "Release notes mention", "pull requests" — capitalized
    // scenery subjects followed by noun forms of speech verbs must not be
    // exempted from capping as if a person had spoken.
    XCTAssertFalse(
      ContextFactWritePolicy.isHumanEvent(
        "Review notes reference ticket #11643 and discuss cache reads."))
    XCTAssertFalse(
      ContextFactWritePolicy.isHumanEvent(
        "Release notes mention automated Windows beta build."))
    XCTAssertFalse(
      ContextFactWritePolicy.isHumanEvent(
        "The tab lists 185 Open pull requests and 8,494 Closed pull requests."))
  }

  func testActionableStatementsPassUntouched() {
    // The one measured near-miss is here on purpose: "is present to repair"
    // must not be display language ("is present in" is).
    for statement in [
      "PR #11651 in the BasedHardware/omi repository has been merged.",
      "An email from Slack contains a link to add a workspace (Yukon) and notes the link expires in 24 hours.",
      "A remediation instruction is present to repair the surface or correct its contract row in a text box.",
      "Health monitor script terminated with exit code 1.",
      "The macOS release build v0.12.180 was cut at 11:15 UTC and verification should use git merge-base.",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .pass, statement)
    }
  }

  /// The collision class an earlier revision of this policy silently zeroed.
  ///
  /// Scenery language and work-status language share verbs. "is open",
  /// "is active", "appears in", "is reviewing" and "shows" are how English
  /// states that a pull request is unmerged, a flag is live, a regression
  /// landed, a person is doing something, or a metric breached a threshold.
  /// Matching the verb alone capped every sentence below to worthiness 0,
  /// removing it from arming, pooling, departure evaluation and director
  /// eligibility at once. Scenery is now anchored to an *interface subject*,
  /// matching the predicate the extraction prompt actually states.
  func testWorkStatusLanguageIsNotMistakenForScenery() {
    for statement in [
      "PR #11651 is open and blocked on review.",
      "The feature flag is now active in production.",
      "Legal is reviewing the MSA before Friday.",
      "The regression appears in the latest build after the deploy.",
      "The chart shows error rate above the SLO.",
      "The staging cluster is being used for the load test.",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .pass, statement)
    }
  }

  /// `dropMachinery` skips the INSERT, so a false positive destroys a fact
  /// outright rather than demoting it. These four were deleted by unanchored
  /// substrings (`unknown/`, `^The destination`, `150-400`) before the patterns
  /// were anchored to the echoes they were measured on.
  func testRealStatementsSharingMachineryTokensAreNotDropped() {
    for statement in [
      "Push to unknown/production failed.",
      "The destination branch cannot fast-forward.",
      "The destination folder is missing from the artifact.",
      "Latency is 150-400ms at p99.",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .pass, statement)
    }
  }

  /// The extraction prompt's own examples leak verbatim on this model (~1 in 14
  /// calls). The Good example is a named-person speech-act, which is the class
  /// `floorHumanEvent` raises to arming eligibility — so an unguarded leak
  /// would not just be stored, it would arm a notification built from the
  /// prompt's placeholder text.
  func testPromptExamplesCannotLeakIntoStoredFacts() {
    for statement in [
      "Nik asked for the demo recording before tomorrow's launch video.",
      "The user is viewing a window with a sidebar and a chat panel.",
      "Ambient narrative: the user appears to be coordinating a recording workflow.",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .dropMachinery, statement)
    }
  }

  /// Both engines used here fail silently on an invalid pattern: `try?` leaves
  /// the regex nil and `range(of:options:)` returns nil, so a typo reads
  /// exactly like a rule that never matches.
  func testEveryPatternCompiles() {
    XCTAssertTrue(ContextFactWritePolicy.allPatternsCompile)
  }

  /// Paraphrased instruction echoes from live data (77 of 2,531 corpus facts,
  /// every one verified an echo by reading). The anchored machinery patterns
  /// miss these because the model rewords; the conjunctive frame+vocabulary
  /// detector catches them.
  func testParaphrasedInstructionEchoesAreDropped() {
    for statement in [
      "The designated destination value is set to unknown/.",
      "There is a note indicating a destination should be set to unknown/.",
      "Destination is set to unknown/ per instruction.",
      "If domain confidence is low, the response should be unknown/.",
      "The user requires that each factual record be a plain declarative sentence.",
      "The task requires filling identifiers with names or handles copied from on-screen text.",
      "Instructions require plain declarative sentences without labels or numbering.",
      "The user asks to identify the website page-group this tab belongs to, as destination.",
      "Format requirement: statements must be plain declarative sentences suitable for colleagues.",
    ] {
      XCTAssertEqual(ContextFactWritePolicy.verdict(statement), .dropMachinery, statement)
    }
  }

  /// The negatives the echo detector was tested against before adoption: real
  /// facts that share single ingredients with echoes (the bare `unknown/`
  /// token, an instruction-shaped frame with no prompt vocabulary) must never
  /// be dropped. This is the class the earlier unanchored patterns deleted.
  func testRealFactsSharingEchoIngredientsAreNotDropped() {
    XCTAssertNotEqual(
      ContextFactWritePolicy.verdict("Push to unknown/production failed."), .dropMachinery)
    XCTAssertNotEqual(
      ContextFactWritePolicy.verdict("The destination branch cannot fast-forward."),
      .dropMachinery)
    XCTAssertNotEqual(
      ContextFactWritePolicy.verdict("The response should be sent to the customer before EOD."),
      .dropMachinery)
    XCTAssertNotEqual(
      ContextFactWritePolicy.verdict(
        "The user must re-authenticate before the deploy can continue."),
      .dropMachinery)
    XCTAssertNotEqual(
      ContextFactWritePolicy.verdict(
        "A policy note states that undivisible PRs involve an outside collaborator with repo Admin rights."),
      .dropMachinery)
  }
}

/// The director cites open tasks by the bracketed handle the prompt supplies.
/// Every cited ref is filtered against the tasks actually supplied on that
/// visit: an invented handle would render in chat as a "Task is no longer
/// available" tombstone rather than failing visibly, which is the failure mode
/// already observed on the chat surface.
final class ContextDirectorTaskRefsTests: XCTestCase {
  private let supplied = [
    ContextDirectorTaskContext(id: "abc-123", description: "Send the contract", dueAt: nil),
    ContextDirectorTaskContext(id: "def-456", description: "Review the release", dueAt: nil),
  ]

  func testPromptRefIsNamespacedSoItCannotBeConfusedWithOtherRefKinds() {
    XCTAssertEqual(supplied[0].promptRef, "task:abc-123")
    XCTAssertEqual(ContextDirectorTaskRefs.taskID(from: "task:abc-123"), "abc-123")
    XCTAssertNil(ContextDirectorTaskRefs.taskID(from: "visit:123"))
    XCTAssertNil(ContextDirectorTaskRefs.taskID(from: "task:"))
  }

  func testInventedOrForeignRefsAreDropped() {
    XCTAssertEqual(
      ContextDirectorTaskRefs.resolvable(
        ["task:abc-123", "task:not-a-real-task", "visit:9", "fact:1", ""], supplied: supplied),
      ["task:abc-123"])
  }

  func testUserAuthoredQuestionFloorsToArmingEligibility() {
    // The live fact that kept the answer-delivery path dark: worthiness 0.0.
    XCTAssertEqual(
      ContextFactWritePolicy.verdict(
        "The body of the email currently contains the question: What is the latest omi desktop app download link?"),
      .floorHumanEvent)
    XCTAssertEqual(
      ContextFactWritePolicy.verdict(
        "The user is asking david@scalingforever.com: where can I grab the newest Omi desktop build?"),
      .floorHumanEvent)
    // Displayed questions without an authoring frame never floor.
    XCTAssertNotEqual(
      ContextFactWritePolicy.verdict("The page shows a FAQ question about billing."),
      .floorHumanEvent)
    // A paraphrased question (asking verb + interrogative clause, no "?") floors.
    XCTAssertEqual(
      ContextFactWritePolicy.verdict(
        "The user is asking where to download the latest version of Omi desktop."),
      .floorHumanEvent)
    // A paraphrased REQUEST with a strong asking verb needs no question marker
    // (live extraction: "asking for a link ... to be shared").
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "The user is asking for a link to the latest Omi desktop to be shared with david@scalingforever.com."))
    // A mangled subject with an embedded question mark in a compose frame
    // still floors (live extraction: "Yu is composing a new email ...").
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "Yu is composing a new email to david@scalingforever.com with the body: What is the latest omi desktop link?"))
    // The prompt's Good example is machinery when echoed verbatim.
    XCTAssertEqual(
      ContextFactWritePolicy.verdict(
        "The user is asking alex@example.com: When is the next release shipping?"),
      .dropMachinery)
    // "A user wrote: <question>?" (live extraction phrasing) floors.
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "A user wrote: Yo David, link for the latest Omi desktop please?"))
    // Someone else's question never qualifies.
    XCTAssertFalse(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "David asked when the offsite is scheduled?"))
    // Authoring frames without a question signal never floor via this class.
    XCTAssertFalse(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "The user is composing an email addressed to david@scalingforever.com."))
    // Passive draft-subject phrasings (live 02:22 extraction, both scored 0.0
    // and kept the departure trigger dark) floor.
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "A draft email is addressed to david@scalingforever.com containing a question about the Omi desktop download URL."
      ))
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "A note or message content questions the URL to download Omi for Mac."))
    // A displayed artifact that merely lists questions is not an authored ask.
    XCTAssertFalse(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "The page shows frequently asked questions about billing."))
    // User-subject inclusion phrasing (live 02:44 extraction, scored 0.9 by
    // the model yet unclassified, which kept the forced lookup dark).
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "The user included a question about the latest Omi desktop link in the body of the email."))
    // Compose-anchored artifact-subject asking (live 03:00 extraction, w=1.0
    // yet unclassified — run6's silence).
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "A message is being composed to david@scalingforever.com asking for the latest Omi desktop link."))
    // Received mail is someone else's ask, never the user's.
    XCTAssertFalse(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "An email from David asks when the offsite is scheduled."))
    // Structural catch-all (live 03:36 extraction — sixth distinct paraphrase):
    // an artifact-subject statement quoting a literal question mark is the
    // user's own typed question.
    XCTAssertTrue(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "The message body includes the line: 'Quote probe David: what is the latest Omi desktop link?'"))
    // ...but a received artifact stays excluded even with a quoted question.
    XCTAssertFalse(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "An email from David contains the line: 'when is the offsite?'"))
    // Every artifact-subject branch honors the received marker, including the
    // original contains-the-question shape (review finding).
    XCTAssertFalse(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "An email from David contains the question: when is the offsite scheduled?"))
    XCTAssertFalse(
      ContextFactWritePolicy.isUserAuthoredQuestion(
        "A message received from the sender questions the deployment timeline."))
  }

  func testSuppliedRefsSurviveWhitespaceAndDeduplicate() {
    XCTAssertEqual(
      ContextDirectorTaskRefs.resolvable(
        ["  task:def-456  ", "task:def-456", "task:abc-123"], supplied: supplied),
      ["task:def-456", "task:abc-123"])
  }

  func testEmptySuppliedListAcceptsNothing() {
    XCTAssertTrue(ContextDirectorTaskRefs.resolvable(["task:abc-123"], supplied: []).isEmpty)
  }

  func testCitationCountIsBounded() {
    let many = (0..<20).map {
      ContextDirectorTaskContext(id: "t\($0)", description: "d", dueAt: nil)
    }
    XCTAssertEqual(
      ContextDirectorTaskRefs.resolvable(many.map(\.promptRef), supplied: many).count,
      ContextDirectorTaskRefs.maximumCount)
  }
}

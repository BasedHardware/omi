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
      "Nik asked for the demo recording before tomorrow's launch video.",
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
}

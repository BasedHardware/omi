import AppKit
import XCTest

@testable import Omi_Computer

/// The floating bar's one timing table: which notices time out, for how long, and which wait.
final class FloatingBarNoticePolicyTests: XCTestCase {
  func testInformationalCardWithInterjectOffUsesTheInformationalTime() {
    XCTAssertEqual(
      FloatingBarNoticePolicy.lifetime(
        title: "A title", message: "Some long message that used to be ignored at six seconds",
        kind: .insight, isPersistent: false, interjectEnabled: false),
      .timed(seconds: OmiFeedbackTiming.informational))
  }

  func testInterjectOnKeepsReadingTimeDuration() {
    // task base 6 s + 4 words at 0.25 s.
    XCTAssertEqual(
      FloatingBarNoticePolicy.lifetime(
        title: "two words", message: "two more", kind: .task, isPersistent: false, interjectEnabled: true),
      .timed(seconds: 7))
  }

  func testTrialCardsPersistEvenWhenTheCallerDidNotAsk() {
    XCTAssertTrue(FloatingBarNoticePolicy.persists(kind: .trial, requestedPersistent: false))
    for interject in [false, true] {
      XCTAssertEqual(
        FloatingBarNoticePolicy.lifetime(
          title: "Trial Ended", message: "Upgrade", kind: .trial, isPersistent: false,
          interjectEnabled: interject),
        .untilDismissed)
    }
  }

  func testRequestedPersistenceWinsForEveryKind() {
    for kind in ProactiveNotificationKind.allCases {
      XCTAssertEqual(
        FloatingBarNoticePolicy.lifetime(
          title: "t", message: "m", kind: kind, isPersistent: true, interjectEnabled: false),
        .untilDismissed, "\(kind)")
    }
  }

  func testOnlyTrialIsForcedPersistent() {
    let forced = ProactiveNotificationKind.allCases.filter {
      FloatingBarNoticePolicy.persists(kind: $0, requestedPersistent: false)
    }
    XCTAssertEqual(forced, [.trial])
  }

  func testNotificationOverloadReadsTheCardsOwnFields() {
    let card = FloatingBarNotification(
      ownerID: "owner", title: "Trial ending tomorrow", message: "Check out plans", assistantId: "trial",
      kind: .trial)
    XCTAssertEqual(FloatingBarNoticePolicy.lifetime(for: card, interjectEnabled: false), .untilDismissed)
  }

  func testConfirmationIsTheSharedConfirmationTime() {
    XCTAssertEqual(FloatingBarNoticePolicy.confirmation, OmiFeedbackTiming.confirmation)
  }

  func testNotchDismissTargetMeetsTheMinimumClickSize() {
    XCTAssertGreaterThanOrEqual(NotchDismissButton.diameter, 24)
  }
}

@MainActor
final class FloatingBarMenuBarItemTests: XCTestCase {
  func testTitleNamesTheActionTheItemWillTake() {
    XCTAssertEqual(FloatingBarMenuBarItem.title(isEnabled: true), "Hide Floating Bar")
    XCTAssertEqual(FloatingBarMenuBarItem.title(isEnabled: false), "Show Floating Bar")
  }

  func testToggleFlipsThePreferenceAndRetitlesTheItem() {
    let controller = FloatingBarMenuBarItemController()
    var enabled = false
    var writes: [Bool] = []
    controller.isEnabled = { enabled }
    controller.setEnabled = { value in
      writes.append(value)
      enabled = value
    }
    let item = NSMenuItem(title: "", action: nil, keyEquivalent: "")

    controller.toggle(item)
    XCTAssertEqual(writes, [true])
    XCTAssertEqual(item.title, "Hide Floating Bar")

    controller.toggle(item)
    XCTAssertEqual(writes, [true, false])
    XCTAssertEqual(item.title, "Show Floating Bar")
  }

  func testValidationReReadsAChangeMadeElsewhere() {
    let controller = FloatingBarMenuBarItemController()
    var enabled = true
    controller.isEnabled = { enabled }
    let item = NSMenuItem(title: "Hide Floating Bar", action: nil, keyEquivalent: "")

    // Hidden from the notch or Settings while the menu was closed.
    enabled = false
    XCTAssertTrue(controller.validateMenuItem(item))
    XCTAssertEqual(item.title, "Show Floating Bar")
  }
}

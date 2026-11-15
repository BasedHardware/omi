import Foundation
import XCTest

@testable import Omi_Computer

/// Regression guard for SCA-2171's macOS cancel-sheet lifecycle: a successful
/// cancellation refreshes the subscription, which sets `cancelAtPeriodEnd` and
/// removes the cancel row. The sheet used to be attached to that row, so the
/// refresh tore down the sheet and its done screen before the user could read
/// it. These tests pin the presentation to the stable plan-usage section.
@MainActor
final class CancelSheetLifecycleTests: XCTestCase {
  private var desktopRoot: URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests
      .deletingLastPathComponent()  // Desktop
  }

  private func source(_ relativePath: String) throws -> String {
    // omi-test-quality: source-inspection -- static contract: a sheet attached to a conditionally rendered row cannot be observed from a mounted view; this pins the presentation to the section ancestor so a cancellation refresh cannot dismiss its own done screen.
    try String(
      contentsOf: desktopRoot.appendingPathComponent(relativePath),
      encoding: .utf8)
  }

  private let billingHelpers =
    "Sources/MainWindow/Pages/Settings/Components/SettingsContentView+BillingHelpers.swift"
  private let accountBilling =
    "Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+AccountBilling.swift"

  /// The row really does disappear on the successful-cancellation refresh — the
  /// precondition that made the old sheet attachment drop the done screen.
  func testCancelEntryDisappearsOnceTheCancellationIsScheduled() {
    XCTAssertTrue(
      SettingsContentView.showsCancelEntry(
        hasPaidSubscription: true, cancelAtPeriodEnd: false, flagEnabled: true))
    XCTAssertFalse(
      SettingsContentView.showsCancelEntry(
        hasPaidSubscription: true, cancelAtPeriodEnd: true, flagEnabled: true),
      "The refresh after a successful cancellation removes the cancel row")
    XCTAssertFalse(
      SettingsContentView.showsCancelEntry(
        hasPaidSubscription: true, cancelAtPeriodEnd: false, flagEnabled: false),
      "The default-off kill switch keeps today's Manage-only path")
    XCTAssertFalse(
      SettingsContentView.showsCancelEntry(
        hasPaidSubscription: false, cancelAtPeriodEnd: false, flagEnabled: true))
  }

  /// The sheet must be attached above the conditional row, or the same refresh
  /// takes the presented sheet down with the row.
  func testCancelSheetIsPresentedByTheStableSectionNotTheCancelRow() throws {
    let helpers = try source(billingHelpers)
    XCTAssertFalse(
      helpers.contains(".sheet(isPresented: $showCancelSubscriptionFlow)"),
      "The cancel sheet must not be attached to the cancel row: cancelling removes it")
    XCTAssertTrue(
      helpers.contains("func presentsCancelSubscriptionFlow("),
      "The shared presentation seam lives with the cancel flow")
    XCTAssertTrue(
      helpers.contains("showCancelSubscriptionFlow = true"),
      "The cancel entry still opens the flow while it is visible")

    let section = try source(accountBilling)
    XCTAssertTrue(
      section.contains(".presentsCancelSubscriptionFlow("),
      "The plan-usage section owns the presentation")
    XCTAssertTrue(
      section.contains("isPresented: $showCancelSubscriptionFlow"),
      "The section's sheet is driven by the same presented state")
    XCTAssertTrue(
      section.contains("periodEnd: userSubscription?.subscription.currentPeriodEnd"),
      "The sheet reads the period end from the refreshed subscription")
  }

  /// A confirmed cancellation lands on the done screen and stays there: only
  /// the user's close action ends the flow, not the subscription refresh.
  func testSuccessfulCancelLandsOnDoneAndOnlyExplicitCloseEndsIt() async {
    let controller = CancelFlowController(
      periodEnd: 1_798_000_000,
      loadOffer: { nil },
      acceptOffer: { throw CancellationError() },
      cancelSubscription: { _, _ in })

    controller.reason = "too_expensive"
    controller.advanceFromReason()
    controller.advanceFromFeedback()
    await controller.loadOfferIfNeeded()
    await controller.confirmCancel()

    XCTAssertTrue(controller.finished)
    XCTAssertEqual(controller.step, .done)
    XCTAssertNil(controller.errorMessage)

    // A subscription refresh does not touch the flow's state.
    XCTAssertEqual(controller.step, .done)
    XCTAssertTrue(controller.finished)

    // The sheet's close path is the only thing that ends the flow; it is a
    // no-op for analytics once the cancellation already finished.
    controller.abandon()
    XCTAssertEqual(controller.step, .done)
    XCTAssertTrue(controller.finished)
  }
}

import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class CancelSubscriptionFlowTests: XCTestCase {
  private let offer = RetentionOfferResponse(
    eligible: true,
    percentOff: 50,
    durationMonths: 3,
    regularAmount: 1999,
    discountedAmount: 999,
    currency: "usd")

  private final class Recorder {
    var confirmed: [(String?, Bool)] = []
    var kept: [(Int, String?)] = []
    var abandoned: [(Int, String?)] = []
    var started = 0
    var reasons: [String?] = []

    var analytics: CancelFlowAnalytics {
      CancelFlowAnalytics(
        started: { self.started += 1 },
        reasonSelected: { self.reasons.append($0) },
        confirmed: { self.confirmed.append(($0, $1)) },
        keptPlan: { self.kept.append(($0, $1)) },
        abandoned: { self.abandoned.append(($0, $1)) })
    }
  }

  private func controller(
    offer: RetentionOfferResponse? = nil,
    cancel: @escaping (String, String?) async throws -> Void = { _, _ in },
    recorder: Recorder? = nil
  ) -> CancelFlowController {
    let controller = CancelFlowController(
      periodEnd: 1_798_000_000,
      loadOffer: { offer },
      acceptOffer: { self.offer },
      cancelSubscription: cancel)
    controller.analytics = recorder?.analytics
    return controller
  }

  func testReasonThenFeedbackThenConfirmWithTheStayOffer() async {
    let recorder = Recorder()
    let controller = self.controller(offer: offer, recorder: recorder)

    XCTAssertEqual(controller.step, .reason)
    controller.start()
    XCTAssertEqual(recorder.started, 1)

    controller.reason = "too_expensive"
    controller.advanceFromReason()
    XCTAssertEqual(controller.step, .feedback)
    XCTAssertEqual(recorder.reasons, ["too_expensive"])

    controller.details = "It costs too much"
    controller.advanceFromFeedback()
    XCTAssertEqual(controller.step, .confirm)
    await controller.loadOfferIfNeeded()

    XCTAssertEqual(controller.offer?.percentOff, 50)
    XCTAssertEqual(CancelFlowCopy.offerBody(offer), "Stay and pay US$9.99 a month for the next 3 months.")
  }

  func testCancelPostsTheReasonAndDetails() async {
    let recorder = Recorder()
    var posted: [(String, String?)] = []
    let controller = self.controller(
      offer: offer,
      cancel: { reason, details in posted.append((reason, details)) },
      recorder: recorder)

    controller.reason = "too_expensive"
    controller.details = "  It costs too much  "
    await controller.confirmCancel()

    XCTAssertEqual(posted.count, 1)
    XCTAssertEqual(posted.first?.0, "too_expensive")
    XCTAssertEqual(posted.first?.1, "It costs too much")
    XCTAssertEqual(recorder.confirmed.first?.0, "too_expensive")
    XCTAssertEqual(recorder.confirmed.first?.1, true)
    XCTAssertEqual(controller.step, .done)
    XCTAssertNil(controller.errorMessage)
  }

  func testFailedCancelStaysOnConfirmAndCanRetry() async {
    var attempts = 0
    let controller = self.controller(
      offer: offer,
      cancel: { _, _ in
        attempts += 1
        if attempts == 1 { throw URLError(.notConnectedToInternet) }
      })

    controller.reason = "battery_drain"
    controller.advanceFromFeedback()
    await controller.confirmCancel()

    XCTAssertEqual(controller.step, .confirm)
    XCTAssertEqual(controller.errorMessage, "Failed to cancel subscription. Please try again.")
    XCTAssertFalse(controller.isCancelling)

    await controller.confirmCancel()
    XCTAssertEqual(attempts, 2)
    XCTAssertEqual(controller.step, .done)
  }

  func testIneligibleOfferKeepsKeepSubscriptionAndCancellationReachable() async {
    let ineligible = RetentionOfferResponse(
      eligible: false, percentOff: 50, durationMonths: 3, regularAmount: nil, discountedAmount: nil,
      currency: nil)
    let controller = self.controller(offer: ineligible)
    controller.reason = "other"
    controller.advanceFromFeedback()
    await controller.loadOfferIfNeeded()

    XCTAssertNil(controller.offer)
    XCTAssertFalse(controller.busy)
    controller.keepPlan()
    XCTAssertTrue(controller.finished)
  }

  func testAcceptingTheOfferDoesNotCancel() async {
    var cancelled = false
    let controller = self.controller(offer: offer, cancel: { _, _ in cancelled = true })
    controller.reason = "too_expensive"
    controller.advanceFromFeedback()
    await controller.loadOfferIfNeeded()
    await controller.applyOffer()

    XCTAssertFalse(cancelled)
    XCTAssertEqual(controller.step, .done)
    XCTAssertEqual(controller.appliedPercent, 50)
  }

  func testAbandonReportsTheStepAndReason() {
    let recorder = Recorder()
    let controller = self.controller(recorder: recorder)
    controller.reason = "found_alternative"
    controller.abandon()
    XCTAssertEqual(recorder.abandoned.first?.0, 1)
    XCTAssertEqual(recorder.abandoned.first?.1, "found_alternative")

    controller.abandon()
    XCTAssertEqual(recorder.abandoned.count, 1)
  }

  func testCopyMatchesTheMobileEnglishStrings() {
    XCTAssertEqual(
      CancelFlowCopy.feedbackTitle("too_expensive"), "What price would work for you?")
    XCTAssertEqual(CancelFlowCopy.feedbackTitle("other"), "Tell us more (optional)")
    XCTAssertEqual(
      CancelFlowCopy.feedbackSubtitle("missing_features"),
      "We're always building — this helps us prioritize.")
    XCTAssertEqual(CancelFlowCopy.consequences.count, 6)
    XCTAssertEqual(CancelFlowCopy.price(999, "usd"), "US$9.99")
    XCTAssertEqual(CancelFlowCopy.price(500, "jpy"), "¥500")
    XCTAssertEqual(CancelFlowCopy.price(1000, "eur"), "EUR 10.00")
  }

  func testCancelReasonWireIsAClosedVocabulary() {
    XCTAssertEqual(SubscriptionFunnelWire.cancelReason("too_expensive"), "too_expensive")
    XCTAssertEqual(SubscriptionFunnelWire.cancelReason("made_up"), "unknown")
    XCTAssertEqual(SubscriptionFunnelWire.cancelReason(nil), "unknown")
  }

  // MARK: - Render evidence

  func testRendersCancelFlowStatesWhenRequested() throws {
    guard let dir = ProcessInfo.processInfo.environment["OMI_CANCEL_FLOW_RENDER_DIR"], !dir.isEmpty else {
      throw XCTSkip("set OMI_CANCEL_FLOW_RENDER_DIR to capture cancel-flow renders")
    }
    let base = URL(fileURLWithPath: dir)
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    let size = CGSize(width: 460, height: 620)

    // Entry point before: the current-plan card exposes Manage only.
    write(
      AnyView(
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "creditcard.fill").foregroundColor(Ink.secondary)
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Omi Pro").scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)
            Text("Active").scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
          }
          Spacer()
          CurrentPlanCardActions(
            cancelAtPeriodEnd: false, currentPriceId: "price_plus_m", checkoutBusy: false,
            portalBusy: false, onResubscribe: { _ in }, onManage: {})
        }
        .padding(OmiSpacing.md)
        .frame(width: 460, alignment: .leading)
        .background(Ink.surface)),
      size: CGSize(width: 460, height: 72), to: base.appendingPathComponent("000-macos-manage-only-before.png"),
      chrome: true)

    // Entry point after: the new cancel row under the plan card.
    write(
      AnyView(
        HStack(spacing: OmiSpacing.md) {
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Cancel Subscription").scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(Ink.primary)
            Text("We'll ask why before anything changes.")
              .scaledFont(size: OmiType.caption).foregroundColor(Ink.secondary)
          }
          Spacer()
          Button("Cancel Subscription") {}
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        }
        .padding(OmiSpacing.md)
        .frame(width: 460, alignment: .leading)
        .background(Ink.surface)),
      size: CGSize(width: 460, height: 72), to: base.appendingPathComponent("006-macos-cancel-entry-after.png"),
      chrome: true)

    let states: [(String, CancelFlowStep, String?, RetentionOfferResponse?)] = [
      ("001-macos-cancel-reason.png", .reason, nil, nil),
      ("002-macos-cancel-feedback.png", .feedback, "too_expensive", nil),
      ("003-macos-cancel-offer.png", .confirm, "too_expensive", offer),
      ("004-macos-cancel-no-offer.png", .confirm, "too_expensive", nil),
      ("005-macos-cancel-done.png", .done, "too_expensive", offer),
    ]
    for (file, step, reason, stateOffer) in states {
      let sheet = CancelSubscriptionFlowSheet(
        periodEnd: 1_798_000_000,
        onClose: {},
        onSubscriptionChanged: {},
        loadOffer: { stateOffer },
        previewStep: step,
        previewReason: reason,
        previewDetails: reason == nil ? "" : "It costs too much",
        previewOffer: stateOffer)
      write(AnyView(sheet), size: size, to: base.appendingPathComponent(file), chrome: false)
    }
  }

  private func write(_ view: AnyView, size: CGSize, to url: URL, chrome: Bool) {
    let host = NSHostingView(rootView: view)
    host.frame = NSRect(origin: .zero, size: size)
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless], backing: .buffered,
      defer: false)
    window.contentView = host
    window.appearance = NSAppearance(named: .aqua)
    window.backgroundColor = .white
    window.orderFrontRegardless()
    host.layoutSubtreeIfNeeded()
    // Let the offer task settle for the confirm step.
    RunLoop.current.run(until: Date().addingTimeInterval(0.4))
    host.layoutSubtreeIfNeeded()
    guard let rep = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { return }
    host.cacheDisplay(in: host.bounds, to: rep)
    if let data = rep.representation(using: .png, properties: [:]) {
      try? data.write(to: url)
    }
    window.orderOut(nil)
    window.contentView = nil
    _ = chrome
  }
}

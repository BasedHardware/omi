import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Runs the backend storefront goldens through the desktop decoder and checkout boundary.
/// Mobile and web pin the same files, so a contract change shows up on every client.
final class PlanStorefrontTests: XCTestCase {
  static let goldenDir = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()  // Tests
    .deletingLastPathComponent()  // Desktop
    .deletingLastPathComponent()  // macos
    .deletingLastPathComponent()  // desktop
    .deletingLastPathComponent()  // repo root
    .appendingPathComponent("backend/tests/fixtures/storefront_v2")

  static func raw(_ name: String) throws -> [String: Any] {
    let data = try Data(contentsOf: goldenDir.appendingPathComponent("\(name).json"))
    return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
  }

  static func golden(_ name: String) throws -> PlanStorefront {
    try PlanStorefront.decode(Data(contentsOf: goldenDir.appendingPathComponent("\(name).json")))
  }

  static func decode(_ object: [String: Any]) throws -> PlanStorefront {
    try PlanStorefront.decode(JSONSerialization.data(withJSONObject: object))
  }

  /// Button label each card draws for `interval`, keyed by plan id ("" when none).
  static func buttons(_ data: PlanStorefront, _ interval: PlanStorefront.Interval? = nil) -> [String: String] {
    var out: [String: String] = [:]
    for tier in data.tiers {
      let price = data.offeredPrice(tier, interval: interval ?? data.initialInterval)
      out[tier.planId] = price.flatMap { data.actionLabel(tier: tier, price: $0) } ?? ""
    }
    return out
  }

  func testEveryGoldenDecodesWithoutDroppingTiers() throws {
    let names = try FileManager.default.contentsOfDirectory(atPath: Self.goldenDir.path)
      .filter { $0.hasSuffix(".json") }.map { String($0.dropLast(5)) }
    XCTAssertGreaterThanOrEqual(names.count, 15)
    for name in names {
      let data = try Self.golden(name)
      XCTAssertEqual(data.tiers.count, (try Self.raw(name)["tiers"] as? [Any])?.count, name)
      XCTAssertNotNil(data.header, name)
    }
  }

  func testFreeSeesBackendCTAsOnHigherTiersOnly() throws {
    XCTAssertEqual(
      Self.buttons(try Self.golden("free_settings")),
      ["plus": "Get Plus", "basic": "", "operator": "Get Pro", "architect": "Get Architect"])
  }

  func testMonthlyPlusSwitchesToYearlyOnlyThroughThePriceLabel() throws {
    let data = try Self.golden("plus_monthly_yearly_toggle")
    XCTAssertEqual(
      Self.buttons(data, .month),
      ["operator": "Upgrade to Pro", "plus": "Switch to yearly · save $39.98", "architect": "Upgrade to Architect"])
    let plus = try XCTUnwrap(data.tiers.first(where: \.isCurrent))
    XCTAssertEqual(data.offeredPrice(plus, interval: .month)?.headline, "$19.99/month")
    XCTAssertEqual(
      data.offeredPrice(plus, interval: .month)?.confirmLines.first, "Your monthly plan continues until Nov 1")
  }

  func testAnnualPlusStartsYearlyAndIsNeverOfferedMonthly() throws {
    let data = try Self.golden("plus_annual_current")
    XCTAssertEqual(data.initialInterval, .year)
    XCTAssertEqual(Self.buttons(data)["plus"], "")
  }

  func testProAtFullBudgetUpsellsArchitectAndProSettingsNeverListsIt() throws {
    let capped = try Self.golden("pro_budget_cap")
    XCTAssertTrue(capped.budgetExhausted)
    XCTAssertFalse(capped.showsBudgetNudge)
    XCTAssertEqual(
      Self.buttons(capped, .month),
      ["architect": "Upgrade to Architect", "plus": "", "operator": "Switch to yearly · save $99.98"])
    XCTAssertEqual(capped.partitionedTiers.primary.map(\.planId), ["architect", "operator"])
    XCTAssertFalse(try Self.golden("pro_settings").tiers.map(\.planId).contains("architect"))
    XCTAssertFalse(try Self.golden("pro_budget80").tiers.map(\.planId).contains("architect"))
  }

  func testEightyPercentBudgetShowsTheNudge() throws {
    for name in ["free_budget80", "plus_budget80"] {
      let data = try Self.golden(name)
      XCTAssertEqual(data.showsBudgetNudge, data.usage.nudgeLine != nil, name)
      XCTAssertFalse(data.budgetExhausted, name)
    }
  }

  func testCancelScheduledResubscribesOnlyOnTheCurrentPrice() throws {
    for name in ["cancel_scheduled_plus", "cancel_scheduled_pro"] {
      let data = try Self.golden(name)
      let current = try XCTUnwrap(data.tiers.first(where: \.isCurrent))
      let price = try XCTUnwrap(current.prices.first)
      XCTAssertEqual(data.checkoutDecision(tier: current, price: price), .resubscribe, name)
      for tier in data.tiers where !tier.isCurrent {
        XCTAssertEqual(Self.buttons(data)[tier.planId], "", "\(name):\(tier.planId)")
        XCTAssertEqual(tier.blockedLine, "Resubscribe first to change plans")
      }
      XCTAssertEqual(data.partitionedTiers.primary.first?.isCurrent, true)
      XCTAssertTrue(data.partitionedTiers.primary.map(\.planId).contains("basic"))
      XCTAssertTrue(data.partitionedTiers.rest.isEmpty)
    }
  }

  func testLegacyPlansNeverCheckOut() throws {
    for name in ["legacy_neo", "legacy_unlimited"] {
      let data = try Self.golden(name)
      XCTAssertEqual(data.current?.legacy, true)
      XCTAssertNotNil(data.current?.legacyNote)
      XCTAssertTrue(Self.buttons(data).values.allSatisfy(\.isEmpty), name)
    }
  }

  func testProGatesApplyBelowProOnly() throws {
    let free = try Self.golden("free_pro_gate_proactive")
    XCTAssertEqual(free.shouldGate(.proactiveAgent), free.usage.proGates.contains("proactive_agent"))
    XCTAssertFalse(try Self.golden("pro_budget_cap").shouldGate(.proactiveAgent))
    XCTAssertFalse(try Self.golden("legacy_neo").shouldGate(.proactiveAgent))

    var omiPro = try Self.raw("free_pro_gate_proactive")
    var current = try XCTUnwrap(omiPro["current"] as? [String: Any])
    current["plan_id"] = "unlimited_v2"
    omiPro["current"] = current
    XCTAssertFalse(try Self.decode(omiPro).shouldGate(.proactiveAgent))
    XCTAssertFalse(try Self.decode(omiPro).shouldGate(.screenContext))
  }

  func testOmiProIsPurchasable() throws {
    let data = try Self.golden("single_plan_omi_pro")
    XCTAssertEqual(Self.buttons(data), ["unlimited_v2": "Get Unlimited", "basic": ""])
    XCTAssertEqual(Self.buttons(data, .year)["unlimited_v2"], "Get Unlimited")
  }

  func testRetiredPlanMaySwitchOnlyToOmiPro() throws {
    var payload = try Self.raw("legacy_neo")
    var tiers = try XCTUnwrap(payload["tiers"] as? [[String: Any]])
    let omiPro = try XCTUnwrap((Self.raw("single_plan_omi_pro")["tiers"] as? [[String: Any]])?.first)
    tiers.append(omiPro)
    tiers[1]["action"] = "checkout"
    tiers[1]["cta_label"] = "Get Pro"
    payload["tiers"] = tiers

    let buttons = Self.buttons(try Self.decode(payload))
    XCTAssertEqual(buttons["unlimited_v2"], "Get Unlimited")
    XCTAssertEqual(buttons["operator"], "", "retired plans never sell, even if offered")
  }

  func testRejectsOtherSchemaVersions() throws {
    var payload = try Self.raw("free_settings")
    payload["schema_version"] = 3
    XCTAssertThrowsError(try Self.decode(payload))
  }

  func testUnknownFieldsActionsIntervalsAndKindsDegradeInert() throws {
    var payload = try Self.raw("free_settings")
    var tiers = try XCTUnwrap(payload["tiers"] as? [[String: Any]])
    tiers[0]["action"] = "trial"
    tiers[0]["future_field"] = ["nested": true]
    var prices = try XCTUnwrap(tiers[2]["prices"] as? [[String: Any]])
    prices.append(["interval": "week", "amount_minor": 1, "currency": "usd", "headline": "$1/week"])
    tiers[2]["prices"] = prices
    tiers.append(
      tiers[3].merging(["tier_id": "galaxy:ladder_v2", "plan_id": "galaxy", "name": "Galaxy"]) { $1 })
    payload["tiers"] = tiers
    var usage = try XCTUnwrap(payload["usage"] as? [String: Any])
    usage["kind"] = "tokens"
    payload["usage"] = usage
    payload["brand_new"] = 1

    let data = try Self.decode(payload)
    XCTAssertEqual(data.tiers[0].action, PlanStorefront.Action.none)
    XCTAssertEqual(data.tiers[2].prices.map(\.interval), [.month, .year])
    XCTAssertEqual(data.usage.kind, .unavailable)
    let buttons = Self.buttons(data)
    XCTAssertEqual(buttons["plus"], "")
    XCTAssertEqual(buttons["galaxy"], "", "an unknown plan renders but never sells")
  }

  func testRefusesAMonthlyPriceOnTheAnnualSubscribersOwnTier() throws {
    let data = try Self.golden("plus_annual_current")
    let pro = try XCTUnwrap(data.tiers.first { $0.planId == "operator" })
    let month = try XCTUnwrap(pro.price(for: .month))
    XCTAssertEqual(data.checkoutDecision(tier: pro, price: month), .checkout)
    let plus = try XCTUnwrap(data.tiers.first(where: \.isCurrent))
    let forgedPrice = PlanStorefront.Price(
      id: "price_plus_month", interval: .month, amountMinor: 1999, currency: "usd", headline: "$19.99/month",
      subline: nil, renewalLine: nil, monthsFree: nil, ctaLabel: nil)
    let forged = PlanStorefront.Tier(
      tierId: plus.tierId, planId: plus.planId, name: plus.name, recommended: false, isCurrent: true,
      hoursLine: plus.hoursLine, bullets: [], action: .checkout, ctaLabel: "Get Plus", blockedLine: nil,
      compact: false, prices: [forgedPrice])
    XCTAssertEqual(data.checkoutDecision(tier: forged, price: forgedPrice), .refuse)
  }
}

/// Offscreen renders of the plans section for review. Always renders (so a layout crash
/// fails the suite); writes PNGs only when `OMI_STOREFRONT_RENDER_DIR` is set.
@MainActor
final class StorefrontPlansRenderTests: XCTestCase {
  private func render(_ data: PlanStorefront, name: String, width: CGFloat = 640) throws {
    let view = VStack(spacing: OmiSpacing.lg) {
      StorefrontBudgetBanner(data: data, onOpen: {}, onDismiss: {})
      StorefrontPlansView(
        data: data, startExpanded: true, onRetry: {}, onSelect: { _, _ in }, onManage: {})
    }
    .padding(24)
    .frame(width: width)
    .background(Color(nsColor: .windowBackgroundColor))
    .environment(\.colorScheme, .dark)

    var png: Data?
    let dark = try XCTUnwrap(NSAppearance(named: .darkAqua))
    dark.performAsCurrentDrawingAppearance {
      if name == "plus_yearly_confirmation" {
        // The shared shell contains AppKit material; ImageRenderer cannot capture it.
        // Cache the real hosting view in a hidden test-owned window instead.
        let composed =
          view
          .shellConfirmation(
            isPresented: .constant(name == "plus_yearly_confirmation"),
            title: data.tiers.first(where: \.isCurrent)?.prices.first?.ctaLabel ?? "Plans",
            message: data.tiers.first(where: \.isCurrent)?.prices.first?.confirmLines.joined(separator: "\n") ?? "",
            confirmTitle: data.tiers.first(where: \.isCurrent)?.prices.first?.ctaLabel ?? "Switch to yearly",
            isDestructive: false, onConfirm: {})
        let hosting = NSHostingView(rootView: composed)
        let height = max(hosting.fittingSize.height, 700)
        let window = NSWindow(
          contentRect: NSRect(x: -10000, y: -10000, width: width, height: height), styleMask: .borderless,
          backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = dark
        window.contentView = hosting
        hosting.frame = NSRect(x: 0, y: 0, width: width, height: height)
        hosting.layoutSubtreeIfNeeded()
        if let rep = hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds) {
          hosting.cacheDisplay(in: hosting.bounds, to: rep)
          png = rep.representation(using: .png, properties: [:])
        }
        window.close()
      } else {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        if let image = renderer.cgImage {
          png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])
        }
      }
    }
    let data = try XCTUnwrap(png, name)
    XCTAssertGreaterThan(data.count, 10_000, name)
    if let dir = ProcessInfo.processInfo.environment["OMI_STOREFRONT_RENDER_DIR"] {
      try data.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
    }
  }

  func testRendersReviewStates() throws {
    try render(try PlanStorefrontTests.golden("plus_monthly_yearly_toggle"), name: "plus_yearly_confirmation")
    for name in [
      "free_settings", "plus_monthly_yearly_toggle", "pro_budget_cap", "cancel_scheduled_plus", "legacy_neo",
      "free_budget80", "pro_budget80",
    ] {
      try render(try PlanStorefrontTests.golden(name), name: name)
    }

  }
}

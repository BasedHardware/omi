import Foundation

/// Ladder-v1 plans presentation (`GET /v2/payments/plans`, schema 2).
///
/// The backend owns rank, recommendation, every plan string, prices and entitlements
/// (`backend/docs/storefront-contract.md`). This type decodes the generated wire DTOs
/// defensively and decides whether a rendered price may start a purchase. It mirrors the
/// mobile model (`app/lib/models/plan_storefront.dart`) and the web module
/// (`web/app/src/lib/planStorefront.ts`); all three run the backend goldens.
struct PlanStorefront: Equatable {
  enum Action: String, Equatable { case checkout, current, none }
  enum Interval: String, Equatable { case month, year }
  enum CheckoutDecision: Equatable { case refuse, checkout, resubscribe }
  enum Trigger: String {
    case usageBudget = "usage_budget"
    case proactiveAgent = "proactive_agent"
    case screenContext = "screen_context"
    case mcpDailyCap = "mcp_daily_cap"
  }

  struct Price: Equatable {
    /// Exact checkout price id; never rebuilt from tier or interval. Nil for Free.
    let id: String?
    let interval: Interval
    let amountMinor: Int
    let currency: String
    let headline: String
    let subline: String?
    let renewalLine: String?
    let monthsFree: Int?
    let ctaLabel: String?
    var confirmLines: [String] = []
  }

  struct Tier: Equatable, Identifiable {
    let tierId: String
    let planId: String
    let name: String
    let recommended: Bool
    let isCurrent: Bool
    let hoursLine: String
    let bullets: [String]
    let action: Action
    let ctaLabel: String?
    let blockedLine: String?
    let compact: Bool
    let prices: [Price]
    var id: String { tierId }

    func price(for interval: Interval) -> Price? { prices.first { $0.interval == interval } }
  }

  struct Current: Equatable {
    let planId: String
    let name: String
    let priceId: String?
    let interval: Interval?
    let legacy: Bool
    let cancelAtPeriodEnd: Bool
    let line: String
    let legacyNote: String?
  }

  struct Usage: Equatable {
    enum Kind: String, Equatable {
      case usageBudget = "usage_budget"
      case transcription
      case unavailable
    }
    let kind: Kind
    let percent: Int?
    let periodId: String?
    let resetLabel: String?
    let meterLine: String?
    let nudgeLine: String?
    let proGates: [String]
    var mcpCapReached: Bool = false
  }

  let catalogRevision: Int
  let showSubscriptionUi: Bool
  let header: String?
  let current: Current?
  let usage: Usage
  let tiers: [Tier]
  let yearlyToggleLabel: String?

  enum DecodeError: Error { case unsupportedSchema }

  /// Schema 2 only. Unknown fields are ignored by the wire DTOs; unknown actions,
  /// intervals and usage kinds degrade to their inert value; malformed or duplicate
  /// rows are dropped rather than failing the sheet.
  init(wire: OmiAPI.StorefrontResponse) throws {
    guard wire.schemaVersion == 2 else { throw DecodeError.unsupportedSchema }
    catalogRevision = wire.catalogRevision
    showSubscriptionUi = wire.showSubscriptionUi == true
    header = Self.text(wire.header)
    current = wire.current.flatMap(Self.decodeCurrent)
    usage = Self.decodeUsage(wire.usage)
    var tiers: [Tier] = []
    for row in wire.tiers ?? [] {
      guard let tier = Self.decodeTier(row),
        !tiers.contains(where: { $0.tierId == tier.tierId || $0.planId == tier.planId })
      else { continue }
      tiers.append(tier)
    }
    self.tiers = tiers
    yearlyToggleLabel = Self.text(wire.yearlyToggleLabel)
  }

  static func decode(_ data: Data) throws -> PlanStorefront {
    try PlanStorefront(wire: JSONDecoder().decode(OmiAPI.StorefrontResponse.self, from: data))
  }

  private static func text(_ value: String?) -> String? {
    guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
    return value
  }

  private static func decodePrice(_ row: OmiAPI.StorefrontPrice) -> Price? {
    guard let interval = Interval(rawValue: row.interval), let headline = text(row.headline),
      row.amountMinor >= 0
    else { return nil }
    return Price(
      id: text(row.priceId), interval: interval, amountMinor: row.amountMinor, currency: row.currency,
      headline: headline, subline: text(row.subline), renewalLine: text(row.renewalLine),
      monthsFree: row.monthsFree, ctaLabel: text(row.ctaLabel), confirmLines: (row.confirmLines ?? []).compactMap(text))
  }

  private static func decodeTier(_ row: OmiAPI.StorefrontTier) -> Tier? {
    guard let tierId = text(row.tierId), let planId = text(row.planId), let name = text(row.name) else {
      return nil
    }
    var prices: [Price] = []
    for candidate in row.prices.compactMap(decodePrice)
    where !prices.contains(where: { $0.interval == candidate.interval }) {
      prices.append(candidate)
    }
    return Tier(
      tierId: tierId, planId: planId, name: name, recommended: row.recommended == true,
      isCurrent: row.isCurrent == true, hoursLine: row.hoursLine, bullets: row.bullets.compactMap(text),
      // An action this client does not know is not purchasable.
      action: Action(rawValue: row.action) ?? .none, ctaLabel: text(row.ctaLabel),
      blockedLine: text(row.blockedLine), compact: row.compact == true, prices: prices)
  }

  private static func decodeCurrent(_ row: OmiAPI.StorefrontCurrent) -> Current? {
    guard let planId = text(row.planId), let name = text(row.name), let line = text(row.line) else { return nil }
    return Current(
      planId: planId, name: name, priceId: text(row.priceId),
      interval: row.interval.flatMap(Interval.init(rawValue:)), legacy: row.legacy,
      cancelAtPeriodEnd: row.cancelAtPeriodEnd == true, line: line,
      legacyNote: row.legacy ? text(row.legacyNote) : nil)
  }

  private static func decodeUsage(_ row: OmiAPI.StorefrontUsage?) -> Usage {
    Usage(
      kind: row?.kind.flatMap(Usage.Kind.init(rawValue:)) ?? .unavailable,
      percent: row?.percent.flatMap { $0 >= 0 ? $0 : nil }, periodId: text(row?.periodId),
      resetLabel: text(row?.resetLabel), meterLine: text(row?.meterLine), nudgeLine: text(row?.nudgeLine),
      proGates: (row?.proGates ?? []).compactMap(text), mcpCapReached: row?.mcpCapReached == true)
  }

  // MARK: - Policy

  private static let ladder = ["basic", "plus", "operator", "architect"]

  /// basic < plus < operator < architect; nil off the ladder or unknown. `pro` is the
  /// retained wire alias for Architect.
  static func ladderRank(_ planId: String?) -> Int? {
    guard let planId else { return nil }
    return ladder.firstIndex(of: planId == "pro" ? "architect" : planId)
  }

  /// Neo/Unlimited and ids this client does not recognize.
  private static func offLadder(_ planId: String?) -> Bool { planId != nil && ladderRank(planId) == nil }

  var cancelScheduled: Bool { current?.cancelAtPeriodEnd == true }

  /// The single checkout boundary for rendering and every click. Paid subscribers may move
  /// up the ladder; the only same-tier purchase is monthly to yearly from a monthly price.
  /// Legacy prices, off-ladder plans and unknown plan ids never check out. While a
  /// cancellation is scheduled the only purchase is resubscribing on the current price.
  func checkoutDecision(tier: Tier, price: Price, livePlanId: String? = nil) -> CheckoutDecision {
    if !showSubscriptionUi || usage.kind == .transcription || current?.legacy == true { return .refuse }
    if Self.offLadder(current?.planId) || Self.offLadder(livePlanId) || Self.offLadder(tier.planId) {
      return .refuse
    }
    guard tier.action != .none, tier.prices.contains(price), let priceId = price.id else { return .refuse }
    // `current` is purchasable only through a price-level label (yearly switch).
    if tier.action == .current && price.ctaLabel == nil { return .refuse }
    let sameTier = current.map { Self.ladderRank($0.planId) == Self.ladderRank(tier.planId) } ?? false
    if sameTier && current?.interval == .year && price.interval == .month { return .refuse }
    let held = tier.prices.first { $0.id != nil && $0.id == current?.priceId }
    if held?.interval == .year && price.interval == .month { return .refuse }
    let ranks = [Self.ladderRank(current?.planId), Self.ladderRank(livePlanId)].compactMap { $0 }
    if let target = Self.ladderRank(tier.planId), let effective = ranks.max(), target < effective {
      return .refuse
    }
    if priceId == current?.priceId { return cancelScheduled ? .resubscribe : .refuse }
    if cancelScheduled { return .refuse }
    if sameTier && !(current?.interval == .month && price.interval == .year) { return .refuse }
    return .checkout
  }

  /// The backend's words for one price's button; a price label replaces the tier label.
  func actionLabel(tier: Tier, price: Price, livePlanId: String? = nil) -> String? {
    checkoutDecision(tier: tier, price: price, livePlanId: livePlanId) == .refuse
      ? nil : (price.ctaLabel ?? tier.ctaLabel)
  }

  /// The selected interval's price; a single-price card shows it on either chip.
  func offeredPrice(_ tier: Tier, interval: Interval) -> Price? {
    tier.price(for: interval) ?? (tier.prices.count == 1 ? tier.prices.first : nil)
  }

  /// Monthly by default; yearly only when the current card publishes nothing else.
  var initialInterval: Interval {
    guard current?.interval == .year, let tier = tiers.first(where: { $0.isCurrent }) else { return .month }
    return tier.price(for: .month) == nil && tier.price(for: .year) != nil ? .year : .month
  }

  /// Cards before "See all plans". Cancel-scheduled: current first, then every tier (each
  /// other card carries the backend's blocked line). Otherwise recommended and current.
  var partitionedTiers: (primary: [Tier], rest: [Tier]) {
    if cancelScheduled {
      return (tiers.filter(\.isCurrent) + tiers.filter { !$0.isCurrent }, [])
    }
    let primary = tiers.filter { $0.recommended || $0.isCurrent }
    return (primary, tiers.filter { tier in !primary.contains(tier) })
  }

  private var ladderBudget: Bool {
    showSubscriptionUi && current?.legacy == false && usage.kind == .usageBudget && usage.percent != nil
  }

  /// 80–99% nudge. At 100% the sheet itself is the exhausted surface.
  var showsBudgetNudge: Bool {
    guard ladderBudget, let percent = usage.percent else { return false }
    return percent >= 80 && percent < 100 && usage.nudgeLine != nil
  }

  var budgetExhausted: Bool { ladderBudget && (usage.percent ?? 0) >= 100 }

  /// Pro gates apply only below Pro on the ladder and only when the backend lists them.
  func shouldGate(_ feature: Trigger, livePlanId: String? = nil) -> Bool {
    guard showSubscriptionUi, let current, !current.legacy, usage.proGates.contains(feature.rawValue),
      !Self.offLadder(current.planId), !Self.offLadder(livePlanId)
    else { return false }
    let rank = [Self.ladderRank(current.planId), Self.ladderRank(livePlanId)].compactMap { $0 }.max() ?? 0
    return rank < (Self.ladderRank("operator") ?? 2)
  }
}

/// Client presentation gates for the ladder-v1 plans section. Backend visibility and
/// entitlement decisions win. Lifecycle: rollout; owner: dazheng; review-by: 2026-11-13;
/// default off. Mirrors mobile `PlanStorefrontGate` with the desktop- prefix.
@MainActor
enum PlanStorefrontGate {
  static let enabledFlag = "desktop-plan-storefront"
  static let contextualUpsellsFlag = "desktop-contextual-upsells"

  /// Dev builds never initialize PostHog, so both read off.
  static var sheetEnabled: Bool { PostHogManager.shared.isFeatureEnabled(enabledFlag) }
  static var contextualEnabled: Bool {
    sheetEnabled && PostHogManager.shared.isFeatureEnabled(contextualUpsellsFlag)
  }
}

extension APIClient {
  /// Throws on any failure so the section shows its error state; there is no fallback catalog.
  func getStorefront(source: String, trigger: PlanStorefront.Trigger? = nil) async throws -> PlanStorefront {
    var components = URLComponents()
    components.queryItems =
      [URLQueryItem(name: "source", value: source)]
      + (trigger.map { [URLQueryItem(name: "trigger", value: $0.rawValue)] } ?? [])
      + (Locale.preferredLanguages.first.map { [URLQueryItem(name: "locale", value: $0)] } ?? [])
    let wire: OmiAPI.StorefrontResponse = try await get("v2/payments/plans?\(components.percentEncodedQuery ?? "")")
    return try PlanStorefront(wire: wire)
  }
}

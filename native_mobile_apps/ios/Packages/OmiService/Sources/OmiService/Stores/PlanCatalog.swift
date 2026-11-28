import Foundation
import OmiNetwork

/// One paid plan with its monthly and annual price (Flutter's plans sheet groups
/// `available-plans` by `plan_id` the same way).
public struct PlanTier: Identifiable, Equatable, Sendable {
    /// The plan id ("plus", "unlimited_v2").
    public let id: String
    public let title: String
    public let subtitle: String?
    /// "Most popular": the one plan to point at.
    public let eyebrow: String?
    public let features: [String]
    public let monthly: PlanOffer?
    public let annual: PlanOffer?

    public func offer(_ interval: PlanOffer.Interval) -> PlanOffer? {
        interval == .year ? annual : monthly
    }

    /// Paid now (either price), or scheduled.
    public var isCurrent: Bool {
        monthly?.isActive == true || annual?.isActive == true
    }

    /// Whole percent the annual price saves against twelve monthly ones; nil when it does not.
    public var annualSavingsPercent: Int? {
        PlanCatalog.savingsPercent(monthly: monthly?.unitAmount, annual: annual?.unitAmount)
    }
}

/// What the main button does for the chosen price.
public enum PlanPurchase: Equatable, Sendable {
    /// Free or cancelled: Stripe checkout (or the backend reactivates a cancelled plan in place).
    case checkout(PlanOffer)
    /// A running paid plan: switch to this price (`upgrade-subscription`).
    case change(PlanOffer)
    /// Already paid (or scheduled): nothing to buy.
    case current
    /// Desktop plans are managed on the Mac; this price cannot replace them from the phone.
    case managedElsewhere
}

/// A meter on Plan & usage: what this month used against the plan's limit.
public struct UsageMeter: Identifiable, Equatable, Sendable {
    public enum Kind: String, Sendable {
        case listening, chat, chatSpend, words, insights
    }

    public let kind: Kind
    /// Minutes for listening, questions for chat, US dollars for chat spend, counts otherwise.
    public let used: Double
    /// nil: unlimited.
    public let limit: Double?

    public var id: Kind {
        kind
    }

    /// 0…1 of the limit; nil when unlimited.
    public var fraction: Double? {
        guard let limit, limit > 0 else { return nil }
        return min(1, max(0, used / limit))
    }

    public var isUnlimited: Bool {
        limit == nil
    }

    /// From 80 % of the limit.
    public var isNearLimit: Bool {
        (fraction ?? 0) >= 0.8
    }

    public var isAtLimit: Bool {
        (fraction ?? 0) >= 1
    }
}

/// Plan logic for Plan & usage, kept pure so it is tested without a screen (mirrors Flutter's
/// `plan_pricing.dart`, `plan_display_name.dart` and the plans sheet's button rules).
public enum PlanCatalog {
    /// Cheaper first, as Flutter orders the tiers.
    static let order = ["plus", "unlimited_v2", "unlimited", "operator", "architect"]
    /// Plans that include the Mac app; managed from the desktop, never swapped for a phone plan here.
    static let desktopPlans: Set<String> = ["operator", "architect"]

    /// Prices grouped into plans, cheaper first. `plans` (from the subscription) adds the feature
    /// lines and titles the price list does not carry.
    public static func tiers(offers: [PlanOffer], plans: [Subscription.Plan]) -> [PlanTier] {
        let grouped = Dictionary(grouping: offers, by: \.planID)
        return grouped.keys.sorted { rank($0) == rank($1) ? $0 < $1 : rank($0) < rank($1) }.map { id in
            let prices = grouped[id] ?? []
            let plan = plans.first { $0.id == id }
            let any = prices.first
            return PlanTier(
                id: id,
                title: plan?.title ?? title(fromOffer: any?.title, planID: id),
                subtitle: plan?.subtitle ?? any?.subtitle,
                eyebrow: plan?.eyebrow ?? any?.eyebrow,
                features: plan?.features ?? [],
                monthly: prices.first { $0.interval == .month },
                annual: prices.first { $0.interval == .year }
            )
        }
    }

    /// The prices the subscription lists, as offers: what Plan & usage shows when
    /// `available-plans` cannot be read. Interval from the price's title ("Monthly", "Annual").
    public static func offers(from plans: [Subscription.Plan], currentPriceID: String?) -> [PlanOffer] {
        plans.flatMap { plan in
            plan.prices.compactMap { price -> PlanOffer? in
                let title = price.title.lowercased()
                let interval: PlanOffer.Interval? = title.contains("annual") || title.contains("year") ? .year
                    : title.contains("month") ? .month : nil
                guard let interval else { return nil }
                return PlanOffer(
                    id: price.id, planID: plan.id, title: "\(plan.title) \(price.title)", priceString: price.priceString,
                    description: price.description, subtitle: plan.subtitle, eyebrow: plan.eyebrow, interval: interval,
                    unitAmount: cents(price.priceString), isActive: price.id == currentPriceID
                )
            }
        }
    }

    /// "$17.99/month" → 1799.
    public static func cents(_ priceString: String) -> Int? {
        let number = priceString.drop { !$0.isNumber }.prefix { $0.isNumber || $0 == "." || $0 == "," }
        guard let value = Double(number.replacingOccurrences(of: ",", with: "")) else { return nil }
        return Int((value * 100).rounded())
    }

    /// Whole percent an annual price saves against twelve monthly ones (Flutter
    /// `annualDiscountPercent`); nil when a price is missing or annual is not cheaper.
    public static func savingsPercent(monthly: Int?, annual: Int?) -> Int? {
        guard let monthly, let annual, monthly > 0 else { return nil }
        let percent = Int(((1 - Double(annual) / Double(monthly * 12)) * 100).rounded())
        return percent > 0 ? percent : nil
    }

    /// The largest saving across plans, for the Monthly / Yearly switch.
    public static func bestSavingsPercent(_ tiers: [PlanTier]) -> Int? {
        tiers.compactMap(\.annualSavingsPercent).max()
    }

    /// An annual price as a monthly one ("$13.49"), from cents; nil without an amount.
    public static func monthlyEquivalent(_ offer: PlanOffer, locale: Locale = .current) -> String? {
        guard offer.interval == .year, let amount = offer.unitAmount else { return nil }
        return (Double(amount) / 1200).formatted(.currency(code: "USD").locale(locale))
    }

    /// The plan's name: nil for the free plan (the screen says "Free"), the backend's title when
    /// it lists the plan, else the product name this app knows.
    public static func paidPlanName(_ subscription: Subscription) -> String? {
        let plan = subscription.plan
        guard plan != "basic", !plan.isEmpty else { return nil }
        if let title = subscription.availablePlans.first(where: { $0.id == plan })?.title.trimmingCharacters(in: .whitespaces),
           !title.isEmpty
        {
            return title
        }
        switch plan {
        case "plus": return "Plus"
        case "operator": return "Operator"
        case "architect": return "Architect"
        case "unlimited", "unlimited_v2": return "Unlimited"
        default:
            return plan.split(whereSeparator: { $0 == "_" || $0 == "-" || $0 == " " })
                .map { $0.prefix(1).uppercased() + $0.dropFirst() }
                .joined(separator: " ")
        }
    }

    /// What the main button does for `offer` (Flutter `_handleUpgrade` and
    /// `shouldShowPlanContinueButton`).
    public static func purchase(_ offer: PlanOffer, subscription: Subscription) -> PlanPurchase {
        if offer.isActive { return .current }
        let running = subscription.isPaid && !subscription.cancelAtPeriodEnd
        if running, desktopPlans.contains(subscription.plan), !desktopPlans.contains(offer.planID) { return .managedElsewhere }
        return running ? .change(offer) : .checkout(offer)
    }

    /// This month's meters: listening minutes, chat questions (or spend), words, insights. Limits
    /// of 0 are unlimited (the wire's sentinel). Words and insights only when they are limited.
    public static func meters(_ subscription: Subscription) -> [UsageMeter] {
        let usage = subscription.usage
        var meters = [UsageMeter(
            kind: .listening, used: Double(subscription.secondsUsed / 60),
            limit: subscription.secondsLimit > 0 ? Double(subscription.secondsLimit / 60) : nil
        )]
        if let chatLimit = usage.chatLimit, chatLimit > 0 {
            meters.append(UsageMeter(kind: usage.chatUnit == "cost_usd" ? .chatSpend : .chat, used: usage.chatUsed, limit: chatLimit))
        } else if let percent = subscription.chatQuotaPercent, percent > 0, usage.chatUsed > 0 {
            // No cap in the payload, but a share of it: the cap follows from the two.
            meters.append(UsageMeter(kind: .chat, used: usage.chatUsed, limit: (usage.chatUsed * 100 / percent).rounded()))
        } else if usage.chatUnit != nil {
            meters.append(UsageMeter(kind: .chat, used: usage.chatUsed, limit: nil))
        }
        if usage.wordsLimit > 0 {
            meters.append(UsageMeter(kind: .words, used: Double(usage.wordsUsed), limit: Double(usage.wordsLimit)))
        }
        if usage.insightsLimit > 0 {
            meters.append(UsageMeter(kind: .insights, used: Double(usage.insightsUsed), limit: Double(usage.insightsLimit)))
        }
        return meters
    }

    private static func rank(_ id: String) -> Int {
        order.firstIndex(of: id) ?? order.count
    }

    /// "Plus Monthly" → "Plus"; the plan id when there is no title.
    private static func title(fromOffer title: String?, planID: String) -> String {
        let words = (title ?? "").split(separator: " ").filter { !["Monthly", "Annual", "Yearly"].contains($0) }
        return words.isEmpty ? planID.capitalized : words.joined(separator: " ")
    }
}

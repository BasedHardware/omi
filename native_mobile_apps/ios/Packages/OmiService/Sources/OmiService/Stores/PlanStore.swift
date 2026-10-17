import Foundation
import Observation
import OmiNetwork

/// Plan & usage (Flutter `usage_page` + `plans_sheet`): the plan, this month's meters, the plans
/// to choose from (monthly or yearly), and the one action that buys or switches. Payment itself
/// always happens on Stripe's page; this store only asks the backend for that page.
@MainActor
@Observable
public final class PlanStore {
    /// What the last action did, for one line on the screen.
    public enum Notice: Equatable, Sendable {
        /// Back from checkout and the plan is paid now.
        case upgraded(plan: String)
        /// A cancelled plan runs again (backend message, if it sent one).
        case reactivated(String?)
        /// A running plan was switched (backend message, if it sent one).
        case changed(String?)
        /// The payment service refused, in its words (an expired promo code, a plan it will not sell).
        case refused(String)
        /// The payment service could not be reached.
        case unreachable
    }

    public private(set) var subscription: Subscription?
    public private(set) var tiers: [PlanTier] = []
    public private(set) var isLoading = false
    /// Neither the plan nor its prices could be read.
    public private(set) var failed = false
    /// The plan loaded but no prices: plans cannot be bought from here right now.
    public private(set) var plansUnavailable = false
    public private(set) var isWorking = false
    public private(set) var notice: Notice?
    public var interval: PlanOffer.Interval = .year
    public var selectedTierID: String?
    public var promoCode = ""

    private let api: any APIClientProtocol
    /// The plan before a checkout opened, to tell on return whether it went through.
    private var planBeforeCheckout: String?

    public init(api: any APIClientProtocol) {
        self.api = api
    }

    public var selectedTier: PlanTier? {
        tiers.first { $0.id == selectedTierID } ?? tiers.first
    }

    public var selectedOffer: PlanOffer? {
        selectedTier?.offer(interval) ?? selectedTier?.offer(interval == .year ? .month : .year)
    }

    /// What the main button does now; nil while there is nothing to choose.
    public var purchase: PlanPurchase? {
        guard let subscription, let selectedOffer else { return nil }
        return PlanCatalog.purchase(selectedOffer, subscription: subscription)
    }

    public var meters: [UsageMeter] {
        subscription.map(PlanCatalog.meters) ?? []
    }

    /// Both prices exist for some plan: the Monthly / Yearly switch is worth showing.
    public var offersBothIntervals: Bool {
        tiers.contains { $0.monthly != nil && $0.annual != nil }
    }

    public func load() async {
        isLoading = true
        defer { isLoading = false }
        guard let subscription = try? await api.subscription() else {
            failed = self.subscription == nil
            return
        }
        failed = false
        self.subscription = subscription
        guard subscription.showSubscriptionUI else {
            tiers = []
            plansUnavailable = false
            return
        }
        var offers = (try? await api.planOffers()) ?? []
        var plans = subscription.availablePlans
        if offers.isEmpty { offers = PlanCatalog.offers(from: plans, currentPriceID: subscription.currentPriceID) }
        #if DEBUG
            if offers.isEmpty, UserDefaults.standard.bool(forKey: "omiSamplePlans") {
                (offers, plans) = (PlanCatalog.sampleOffers, PlanCatalog.samplePlans)
            }
        #endif
        tiers = PlanCatalog.tiers(offers: offers, plans: plans)
        plansUnavailable = tiers.isEmpty
        // Start on the plan paid now (and its interval), else the one the backend points at.
        if let current = tiers.first(where: \.isCurrent) {
            selectedTierID = current.id
            interval = current.annual?.isActive == true ? .year : .month
        } else if selectedTierID == nil || !tiers.contains(where: { $0.id == selectedTierID }) {
            selectedTierID = (tiers.first { $0.eyebrow?.lowercased().contains("popular") == true } ?? tiers.first)?.id
        }
    }

    /// The main button. Returns Stripe's checkout page to open; nil when it was handled in place
    /// (a reactivation or a plan switch) or refused (see `notice`).
    public func buy() async -> URL? {
        guard let purchase, !isWorking else { return nil }
        isWorking = true
        notice = nil
        defer { isWorking = false }
        let code = promoCode.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            switch purchase {
            case let .checkout(offer):
                switch try await api.startCheckout(priceID: offer.id, promotionCode: code.isEmpty ? nil : code) {
                case let .checkout(url):
                    planBeforeCheckout = subscription?.plan
                    return url
                case let .reactivated(message):
                    notice = .reactivated(message)
                    await load()
                }
            case let .change(offer):
                notice = try await .changed(api.changePlan(priceID: offer.id, promotionCode: code.isEmpty ? nil : code))
                promoCode = ""
                await load()
            case .current, .managedElsewhere:
                return nil
            }
        } catch {
            notice = Self.notice(for: error)
        }
        return nil
    }

    /// Back from Stripe's checkout: read the plan again and say so when it is paid now.
    public func returnedFromCheckout() async {
        let before = planBeforeCheckout
        planBeforeCheckout = nil
        await load()
        if let subscription, subscription.isPaid, subscription.plan != before {
            notice = .upgraded(plan: PlanCatalog.paidPlanName(subscription) ?? subscription.plan)
            promoCode = ""
        }
    }

    /// Stripe's portal (payment method, invoices, cancel there too); nil with `notice` on failure.
    public func portalURL() async -> URL? {
        notice = nil
        do {
            if let url = try await api.customerPortalURL() { return url }
            notice = .unreachable
        } catch {
            notice = Self.notice(for: error)
        }
        return nil
    }

    public func dismissNotice() {
        notice = nil
    }

    static func notice(for error: any Error) -> Notice {
        if let refusal = PaymentsMapper.refusal(error), (400 ..< 500).contains(refusal.status), let detail = refusal.detail {
            return .refused(detail)
        }
        return .unreachable
    }
}

public extension SettingsStore {
    func makePlanStore() -> PlanStore {
        PlanStore(api: api)
    }
}

#if DEBUG
    extension PlanCatalog {
        /// `-omiSamplePlans YES` (Debug): the mobile catalog with today's prices, for screenshots
        /// against a backend without Stripe. Checkout with these ids fails with a clear notice.
        static let sampleOffers: [PlanOffer] = [
            PlanOffer(
                id: "sample_plus_month", planID: "plus", title: "Plus Monthly", priceString: "$17.99/mo",
                subtitle: "1,500 minutes of transcription per month", eyebrow: "For everyday use", interval: .month, unitAmount: 1799
            ),
            PlanOffer(
                id: "sample_plus_year", planID: "plus", title: "Plus Annual", priceString: "$13/mo",
                subtitle: "1,500 minutes of transcription per month", eyebrow: "For everyday use", interval: .year, unitAmount: 16191
            ),
            PlanOffer(
                id: "sample_unlimited_month", planID: "unlimited_v2", title: "Unlimited Monthly", priceString: "$29.99/mo",
                subtitle: "Unlimited transcription", eyebrow: "Most popular", interval: .month, unitAmount: 2999
            ),
            PlanOffer(
                id: "sample_unlimited_year", planID: "unlimited_v2", title: "Unlimited Annual", priceString: "$22/mo",
                subtitle: "Unlimited transcription", eyebrow: "Most popular", interval: .year, unitAmount: 26991
            ),
        ]

        static let samplePlans: [Subscription.Plan] = [
            .init(
                id: "plus", title: "Plus", subtitle: "1,500 minutes of transcription per month", eyebrow: "For everyday use",
                features: ["1,500 minutes of transcription per month", "200 chat questions per month"], prices: []
            ),
            .init(
                id: "unlimited_v2", title: "Unlimited", subtitle: "Unlimited transcription", eyebrow: "Most popular",
                features: ["Unlimited transcription", "1000 chat questions per month"], prices: []
            ),
        ]
    }
#endif

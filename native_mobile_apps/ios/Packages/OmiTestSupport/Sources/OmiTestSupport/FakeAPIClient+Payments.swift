import Foundation
import OmiNetwork

/// What the fake answers for Plan & usage, and what was asked of it.
public struct FakePayments: Sendable {
    /// What `subscription()` returns; nil: the basic plan with 30 of 300 minutes used.
    public var subscription: Subscription?
    public var offers: [PlanOffer] = []
    /// Checkout and plan-change calls, in order ("checkout:<price>:<promo>", "change:<price>").
    public var log: [String] = []
    /// What `startCheckout` answers; nil: a checkout URL for the price.
    public var checkoutAnswer: CheckoutResult?

    public init() {}
}

public extension FakeAPIClient {
    func subscription() async throws -> Subscription {
        if let subscription = payments.subscription { return subscription }
        return Subscription(
            plan: "basic", status: "active", cancelAtPeriodEnd: false, features: ["300 minutes"], secondsUsed: 1800,
            secondsLimit: 18000, chatQuotaPercent: 10, showSubscriptionUI: true, availablePlans: [],
            transcriptionAllowance: transcriptionAllowance
        )
    }

    func planOffers() async throws -> [PlanOffer] {
        try failIfNeeded()
        return payments.offers
    }

    func startCheckout(priceID: String, promotionCode: String?) async throws -> CheckoutResult {
        try failIfNeeded()
        payments.log.append("checkout:\(priceID):\(promotionCode ?? "")")
        return payments.checkoutAnswer ?? .checkout(URL(string: "https://checkout.example/\(priceID)")!)
    }

    func changePlan(priceID: String, promotionCode _: String?) async throws -> String? {
        try failIfNeeded()
        payments.log.append("change:\(priceID)")
        return "Plan changed"
    }

    func customerPortalURL() async throws -> URL? {
        URL(string: "https://portal.example")
    }
}

import Foundation
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Plan & usage: grouping prices into plans, what the main button does, the meters (Flutter
/// `plan_pricing.dart`, `plans_sheet.dart`, `usage_page.dart`).
@MainActor
struct PlanTests {
    static let plusMonth = PlanOffer(
        id: "pm", planID: "plus", title: "Plus Monthly", priceString: "$17.99/mo", interval: .month, unitAmount: 1799
    )
    static let plusYear = PlanOffer(
        id: "py", planID: "plus", title: "Plus Annual", priceString: "$13/mo", interval: .year, unitAmount: 16191
    )
    static let unlimitedMonth = PlanOffer(
        id: "um", planID: "unlimited_v2", title: "Unlimited Monthly", priceString: "$29.99/mo", eyebrow: "Most popular",
        interval: .month, unitAmount: 2999
    )
    static let unlimitedYear = PlanOffer(
        id: "uy", planID: "unlimited_v2", title: "Unlimited Annual", priceString: "$22/mo", eyebrow: "Most popular",
        interval: .year, unitAmount: 26991
    )

    static func subscription(plan: String = "basic", cancelled: Bool = false, plans: [Subscription.Plan] = []) -> Subscription {
        Subscription(
            plan: plan, status: "active", cancelAtPeriodEnd: cancelled, features: [], secondsUsed: 1800, secondsLimit: 18000,
            chatQuotaPercent: 80, showSubscriptionUI: true, availablePlans: plans
        )
    }

    @Test func tiersGroupCheaperFirstWithFeatures() {
        let plans = [Subscription.Plan(id: "plus", title: "Plus", subtitle: "1,500 minutes", features: ["A", "B"], prices: [])]
        let tiers = PlanCatalog.tiers(offers: [Self.unlimitedYear, Self.plusMonth, Self.unlimitedMonth, Self.plusYear], plans: plans)
        #expect(tiers.map(\.id) == ["plus", "unlimited_v2"])
        #expect(tiers[0].title == "Plus" && tiers[0].features == ["A", "B"] && tiers[0].subtitle == "1,500 minutes")
        // No plan in the subscription: the title comes from the price's ("Unlimited Monthly" → "Unlimited").
        #expect(tiers[1].title == "Unlimited" && tiers[1].eyebrow == "Most popular")
        #expect(tiers[1].offer(.year)?.id == "uy" && tiers[1].offer(.month)?.id == "um")
    }

    @Test func annualSavingsFromThePrices() {
        // Plus and Unlimited bill 9 of 12 months: 25 %, never a hardcoded number.
        #expect(PlanCatalog.savingsPercent(monthly: 1799, annual: 16191) == 25)
        #expect(PlanCatalog.savingsPercent(monthly: 1999, annual: 19999) == 17)
        #expect(PlanCatalog.savingsPercent(monthly: 1000, annual: 12000) == nil)
        #expect(PlanCatalog.savingsPercent(monthly: nil, annual: 16191) == nil)
        let tiers = PlanCatalog.tiers(offers: [Self.plusMonth, Self.plusYear, Self.unlimitedMonth], plans: [])
        #expect(PlanCatalog.bestSavingsPercent(tiers) == 25)
    }

    @Test func offersFromTheSubscriptionWhenTheListFails() {
        let plans = [Subscription.Plan(id: "plus", title: "Plus", features: [], prices: [
            .init(id: "pm", title: "Monthly", priceString: "$17.99/month"),
            .init(id: "py", title: "Annual", priceString: "$1,161.91/year"),
            .init(id: "odd", title: "Lifetime", priceString: "$99"),
        ])]
        let offers = PlanCatalog.offers(from: plans, currentPriceID: "py")
        #expect(offers.map(\.interval) == [.month, .year])
        #expect(offers.map(\.unitAmount) == [1799, 116_191])
        #expect(offers.map(\.isActive) == [false, true])
    }

    @Test func purchaseRules() {
        let free = Self.subscription()
        #expect(PlanCatalog.purchase(Self.plusMonth, subscription: free) == .checkout(Self.plusMonth))
        let paid = Self.subscription(plan: "plus")
        #expect(PlanCatalog.purchase(Self.unlimitedYear, subscription: paid) == .change(Self.unlimitedYear))
        let current = PlanOffer(id: "pm", planID: "plus", title: "", priceString: "", interval: .month, unitAmount: 1799, isActive: true)
        #expect(PlanCatalog.purchase(current, subscription: paid) == .current)
        // Cancelled but not ended: checkout, which the backend turns into a reactivation.
        let cancelled = Self.subscription(plan: "plus", cancelled: true)
        #expect(PlanCatalog.purchase(Self.plusYear, subscription: cancelled) == .checkout(Self.plusYear))
        // Desktop plans are not swapped for a phone plan here.
        #expect(PlanCatalog.purchase(Self.plusMonth, subscription: Self.subscription(plan: "operator")) == .managedElsewhere)
    }

    @Test func metersUseLimitsOrTheChatShare() {
        var subscription = Self.subscription()
        subscription.usage.chatUsed = 24
        subscription.usage.chatUnit = "questions"
        subscription.usage.chatLimit = 30
        let meters = PlanCatalog.meters(subscription)
        #expect(meters.map(\.kind) == [.listening, .chat])
        #expect(meters[0].used == 30 && meters[0].limit == 300 && meters[0].fraction == 0.1)
        #expect(meters[1].isNearLimit && !meters[1].isAtLimit)

        // No cap in the payload: derived from the share (24 is 80 % of 30).
        subscription.usage.chatLimit = nil
        #expect(PlanCatalog.meters(subscription)[1].limit == 30)

        // Unlimited listening (limit 0), words limited.
        let unlimited = Subscription(
            plan: "unlimited_v2", status: "active", cancelAtPeriodEnd: false, features: [], secondsUsed: 7200, secondsLimit: 0,
            chatQuotaPercent: nil, showSubscriptionUI: true, availablePlans: []
        )
        var limitedWords = unlimited
        limitedWords.usage.wordsUsed = 10
        limitedWords.usage.wordsLimit = 100
        #expect(PlanCatalog.meters(unlimited).map(\.isUnlimited) == [true])
        #expect(PlanCatalog.meters(limitedWords).map(\.kind) == [.listening, .words])
    }

    @Test func planNames() {
        #expect(PlanCatalog.paidPlanName(Self.subscription()) == nil)
        #expect(PlanCatalog.paidPlanName(Self.subscription(plan: "unlimited_v2")) == "Unlimited")
        let titled = Self.subscription(plan: "plus", plans: [.init(id: "plus", title: "Plus+", features: [], prices: [])])
        #expect(PlanCatalog.paidPlanName(titled) == "Plus+")
        #expect(PlanCatalog.paidPlanName(Self.subscription(plan: "team_pro")) == "Team Pro")
    }

    @Test func storeCheckoutAndReturn() async {
        let api = FakeAPIClient()
        api.payments.offers = [Self.plusMonth, Self.plusYear, Self.unlimitedMonth, Self.unlimitedYear]
        let store = PlanStore(api: api)
        await store.load()
        // Starts on the plan the backend points at, yearly.
        #expect(store.selectedTier?.id == "unlimited_v2" && store.interval == .year)
        #expect(store.purchase == .checkout(Self.unlimitedYear))
        store.promoCode = " SPRING "
        let url = await store.buy()
        #expect(url == URL(string: "https://checkout.example/uy"))
        #expect(api.payments.log == ["checkout:uy:SPRING"])

        // Paid on Stripe's page: back on the screen the plan reads as paid.
        api.payments.subscription = Self.subscription(plan: "unlimited_v2")
        await store.returnedFromCheckout()
        #expect(store.notice == .upgraded(plan: "Unlimited"))
        #expect(store.promoCode.isEmpty)
    }

    @Test func storeReactivationChangeAndRefusal() async {
        let api = FakeAPIClient()
        api.payments.offers = [Self.plusMonth, Self.plusYear]
        api.payments.checkoutAnswer = .reactivated(message: "Welcome back")
        let store = PlanStore(api: api)
        await store.load()
        #expect(await store.buy() == nil)
        #expect(store.notice == .reactivated("Welcome back"))

        api.payments.subscription = Self.subscription(plan: "plus")
        await store.load()
        store.interval = .month
        #expect(await store.buy() == nil)
        #expect(store.notice == .changed("Plan changed"))
        #expect(api.payments.log.last == "change:pm")

        api.fail(with: .http(status: 400, body: #"{"detail":"Invalid or expired promotion code."}"#))
        _ = await store.buy()
        #expect(store.notice == .refused("Invalid or expired promotion code."))
        api.fail(with: .transport("offline"))
        _ = await store.buy()
        #expect(store.notice == .unreachable)
    }

    @Test func storeWithoutPricesSaysSo() async {
        let api = FakeAPIClient()
        let store = PlanStore(api: api)
        await store.load()
        #expect(store.subscription != nil && store.plansUnavailable && store.purchase == nil)
    }
}

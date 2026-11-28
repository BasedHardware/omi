import Foundation

/// Plan & usage (`GET v1/users/me/subscription`).
public struct Subscription: Sendable, Equatable {
    public struct Plan: Sendable, Equatable, Identifiable {
        public struct Price: Sendable, Equatable, Identifiable {
            public let id: String
            /// "Monthly" or "Annual" (the backend's words).
            public let title: String
            /// "$17.99/month".
            public let priceString: String
            public let description: String?

            public init(id: String, title: String, priceString: String, description: String? = nil) {
                self.id = id
                self.title = title
                self.priceString = priceString
                self.description = description
            }
        }

        /// The plan id ("plus", "unlimited_v2").
        public let id: String
        public let title: String
        /// "1,500 minutes of listening per month", under the title.
        public let subtitle: String?
        /// "Most popular", above the title.
        public let eyebrow: String?
        public let features: [String]
        public let prices: [Price]

        public init(
            id: String, title: String, subtitle: String? = nil, eyebrow: String? = nil, features: [String], prices: [Price]
        ) {
            self.id = id
            self.title = title
            self.subtitle = subtitle
            self.eyebrow = eyebrow
            self.features = features
            self.prices = prices
        }
    }

    /// This month's use against the plan's limits; a limit of 0 means unlimited (the wire's sentinel).
    public struct Usage: Sendable, Equatable {
        public var wordsUsed = 0
        public var wordsLimit = 0
        public var insightsUsed = 0
        public var insightsLimit = 0
        /// Chat questions (or US dollars on cost-capped plans) used this month.
        public var chatUsed: Double = 0
        /// "questions" or "cost_usd"; nil from a backend that does not say.
        public var chatUnit: String?
        /// The plan's chat cap in `chatUnit` (`limits.chat_questions_per_month` or `…cost_usd…`).
        public var chatLimit: Double?
        public var chatAllowed = true
        /// When chat (and the month's minutes) start again.
        public var resetsAt: Date?

        public init() {}
    }

    public let plan: String
    public let status: String
    public let cancelAtPeriodEnd: Bool
    public let features: [String]
    public let secondsUsed: Int
    public let secondsLimit: Int
    public let chatQuotaPercent: Double?
    public let showSubscriptionUI: Bool
    public let availablePlans: [Plan]
    /// How the backend lets this account transcribe now (`transcription_allowance.mode`); nil from
    /// a backend that does not say.
    public let transcriptionAllowance: TranscriptionAllowance?
    /// When the paid period renews (or ends, when cancelled).
    public var currentPeriodEnd: Date?
    /// The Stripe price paid now ("price_…"), to tell monthly from annual.
    public var currentPriceID: String?
    /// The account has a Stripe subscription (paid now or before): the payment portal can open.
    public var hasStripeSubscription = false
    public var usage = Usage()

    public var isPaid: Bool {
        plan != "basic" && status == "active"
    }

    /// The plan's minutes are used up (Flutter `UsageProvider.isOutOfCredits`; 0 is unlimited).
    public var isOutOfMinutes: Bool {
        secondsLimit > 0 && secondsUsed >= secondsLimit
    }

    public init(
        plan: String, status: String, cancelAtPeriodEnd: Bool, features: [String], secondsUsed: Int,
        secondsLimit: Int, chatQuotaPercent: Double?, showSubscriptionUI: Bool, availablePlans: [Plan],
        transcriptionAllowance: TranscriptionAllowance? = nil
    ) {
        self.transcriptionAllowance = transcriptionAllowance
        self.plan = plan
        self.status = status
        self.cancelAtPeriodEnd = cancelAtPeriodEnd
        self.features = features
        self.secondsUsed = secondsUsed
        self.secondsLimit = secondsLimit
        self.chatQuotaPercent = chatQuotaPercent
        self.showSubscriptionUI = showSubscriptionUI
        self.availablePlans = availablePlans
    }
}

/// Backend `resolve_transcription_allowance` modes (`utils/subscription.py`): Omi transcribes
/// (`managed`), the phone must (`on_device`, no managed minutes left), or nothing may (`blocked`).
public enum TranscriptionAllowance: String, Sendable, Equatable {
    case managed
    case onDevice = "on_device"
    case blocked
}

/// One price of a paid plan, as `GET v1/payments/available-plans` lists them (Flutter's plans
/// sheet reads this list: it says which price is the one paid now).
public struct PlanOffer: Sendable, Equatable, Identifiable {
    public enum Interval: String, Sendable {
        case month, year
    }

    /// The Stripe price id, what checkout takes.
    public let id: String
    /// The plan this price belongs to ("plus", "unlimited_v2").
    public let planID: String
    /// "Plus Monthly".
    public let title: String
    /// "$17.99/mo"; for annual prices the monthly equivalent ("$13/mo").
    public let priceString: String
    public let description: String?
    public let subtitle: String?
    public let eyebrow: String?
    public let interval: Interval
    /// In cents, for the whole interval.
    public let unitAmount: Int?
    /// Paid now, or scheduled to start when the current period ends.
    public let isActive: Bool

    public init(
        id: String, planID: String, title: String, priceString: String, description: String? = nil, subtitle: String? = nil,
        eyebrow: String? = nil, interval: Interval, unitAmount: Int?, isActive: Bool = false
    ) {
        self.id = id
        self.planID = planID
        self.title = title
        self.priceString = priceString
        self.description = description
        self.subtitle = subtitle
        self.eyebrow = eyebrow
        self.interval = interval
        self.unitAmount = unitAmount
        self.isActive = isActive
    }
}

/// What starting a checkout gave back.
public enum CheckoutResult: Sendable, Equatable {
    /// Pay on Stripe's page.
    case checkout(URL)
    /// A cancelled plan that had not ended yet is running again; no charge now.
    case reactivated(message: String?)
}

/// The payment service said no, in its own words (`{"detail": "…"}`), e.g. an expired promo code.
public struct PaymentRefusal: Error, Sendable, Equatable {
    public let status: Int
    public let detail: String?
}

/// Plan & usage calls (part of `APIClientProtocol`).
public protocol PaymentsAPI: Sendable {
    func subscription() async throws -> Subscription
    func planOffers() async throws -> [PlanOffer]
    func startCheckout(priceID: String, promotionCode: String?) async throws -> CheckoutResult
    func changePlan(priceID: String, promotionCode: String?) async throws -> String?
    func customerPortalURL() async throws -> URL?
}

/// Wire → model for the plan endpoints. Pure, so the payloads are tested as the backend sends them.
public enum PaymentsMapper {
    public static func subscription(_ root: [String: Any]) -> Subscription {
        let sub = root["subscription"] as? [String: Any] ?? [:]
        let limits = sub["limits"] as? [String: Any] ?? [:]
        let plans = (root["available_plans"] as? [[String: Any]] ?? []).compactMap(plan)
        var subscription = Subscription(
            plan: sub["plan"] as? String ?? "basic",
            status: sub["status"] as? String ?? "active",
            cancelAtPeriodEnd: sub["cancel_at_period_end"] as? Bool ?? false,
            features: sub["features"] as? [String] ?? [],
            secondsUsed: int(root["transcription_seconds_used"]) ?? 0,
            secondsLimit: int(root["transcription_seconds_limit"]) ?? 0,
            chatQuotaPercent: double(root["chat_quota_percent"]),
            showSubscriptionUI: root["show_subscription_ui"] as? Bool ?? true,
            availablePlans: plans,
            transcriptionAllowance: ((root["transcription_allowance"] as? [String: Any])?["mode"] as? String)
                .flatMap(TranscriptionAllowance.init(rawValue:))
        )
        subscription.currentPeriodEnd = double(sub["current_period_end"]).map { Date(timeIntervalSince1970: $0) }
        subscription.currentPriceID = sub["current_price_id"] as? String
        subscription.hasStripeSubscription = !((sub["stripe_subscription_id"] as? String) ?? "").isEmpty
        var usage = Subscription.Usage()
        usage.wordsUsed = int(root["words_transcribed_used"]) ?? 0
        usage.wordsLimit = int(root["words_transcribed_limit"]) ?? 0
        usage.insightsUsed = int(root["insights_gained_used"]) ?? 0
        usage.insightsLimit = int(root["insights_gained_limit"]) ?? 0
        usage.chatUsed = double(root["chat_quota_used"]) ?? 0
        usage.chatUnit = root["chat_quota_unit"] as? String
        usage.chatLimit = usage.chatUnit == "cost_usd"
            ? double(limits["chat_cost_usd_per_month"])
            : double(limits["chat_questions_per_month"])
        usage.chatAllowed = root["chat_quota_allowed"] as? Bool ?? true
        usage.resetsAt = double(root["chat_quota_reset_at"]).map { Date(timeIntervalSince1970: $0) }
        subscription.usage = usage
        return subscription
    }

    static func plan(_ object: [String: Any]) -> Subscription.Plan? {
        guard let id = object["id"] as? String else { return nil }
        let prices = (object["prices"] as? [[String: Any]] ?? []).compactMap { price -> Subscription.Plan.Price? in
            guard let id = price["id"] as? String else { return nil }
            return .init(
                id: id, title: price["title"] as? String ?? "", priceString: price["price_string"] as? String ?? "",
                description: price["description"] as? String
            )
        }
        return .init(
            id: id, title: object["title"] as? String ?? id, subtitle: object["subtitle"] as? String,
            eyebrow: object["eyebrow"] as? String, features: object["features"] as? [String] ?? [], prices: prices
        )
    }

    /// `GET v1/payments/available-plans` → `{"plans": [PricingOption…]}`.
    public static func offers(_ root: [String: Any]) -> [PlanOffer] {
        (root["plans"] as? [[String: Any]] ?? []).compactMap { item in
            guard let id = item["id"] as? String,
                  let interval = (item["interval"] as? String).flatMap(PlanOffer.Interval.init(rawValue:)) else { return nil }
            return PlanOffer(
                id: id, planID: item["plan_id"] as? String ?? "", title: item["title"] as? String ?? "",
                priceString: item["price_string"] as? String ?? "", description: item["description"] as? String,
                subtitle: item["subtitle"] as? String, eyebrow: item["eyebrow"] as? String, interval: interval,
                unitAmount: int(item["unit_amount"]), isActive: item["is_active"] as? Bool ?? false
            )
        }
    }

    /// `POST v1/payments/checkout-session`: a checkout URL, or `status: reactivated`.
    public static func checkout(_ root: [String: Any]) -> CheckoutResult? {
        if root["status"] as? String == "reactivated" { return .reactivated(message: root["message"] as? String) }
        return (root["url"] as? String).flatMap(URL.init(string:)).map(CheckoutResult.checkout)
    }

    /// The `detail` of a refused payment call; nil when the body says nothing a person can read.
    public static func refusal(_ error: any Error) -> PaymentRefusal? {
        guard case let APIError.http(status, body) = error else { return nil }
        let object = body.data(using: .utf8).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
        let detail = (object?["detail"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return PaymentRefusal(status: status, detail: detail?.isEmpty == false ? detail : nil)
    }

    private static func int(_ value: Any?) -> Int? {
        (value as? Int) ?? (value as? Double).map { Int($0) } ?? (value as? NSNumber)?.intValue
    }

    private static func double(_ value: Any?) -> Double? {
        (value as? Double) ?? (value as? Int).map(Double.init) ?? (value as? NSNumber)?.doubleValue
    }
}

public extension APIClient {
    private func paymentsObject(
        _ method: Method, _ path: String, json: [String: Any]? = nil
    ) async throws -> [String: Any] {
        let body: Body = try json.map { try .json(JSONSerialization.data(withJSONObject: $0)) } ?? .none
        let data = try await data(method, path, body: body)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func subscription() async throws -> Subscription {
        try await PaymentsMapper.subscription(paymentsObject(.get, "v1/users/me/subscription"))
    }

    /// `GET v1/payments/available-plans`: every purchasable price, which one is paid now.
    func planOffers() async throws -> [PlanOffer] {
        try await PaymentsMapper.offers(paymentsObject(.get, "v1/payments/available-plans"))
    }

    /// `POST v1/payments/checkout-session` → Stripe checkout, or a reactivated plan. Never pays by
    /// itself: the person pays on Stripe's page.
    func startCheckout(priceID: String, promotionCode: String?) async throws -> CheckoutResult {
        var body: [String: Any] = ["price_id": priceID]
        if let promotionCode, !promotionCode.isEmpty { body["promotion_code"] = promotionCode }
        let object = try await paymentsObject(.post, "v1/payments/checkout-session", json: body)
        guard let result = PaymentsMapper.checkout(object) else { throw APIError.decoding("checkout-session") }
        return result
    }

    /// `POST v1/payments/upgrade-subscription`: switch a running paid plan (another plan now,
    /// prorated; monthly to annual at the end of the period). Returns the backend's message.
    func changePlan(priceID: String, promotionCode: String?) async throws -> String? {
        var body: [String: Any] = ["price_id": priceID]
        if let promotionCode, !promotionCode.isEmpty { body["promotion_code"] = promotionCode }
        return try await paymentsObject(.post, "v1/payments/upgrade-subscription", json: body)["message"] as? String
    }

    /// `POST v1/payments/customer-portal` → Stripe portal URL.
    func customerPortalURL() async throws -> URL? {
        try await (paymentsObject(.post, "v1/payments/customer-portal")["url"] as? String).flatMap(URL.init(string:))
    }
}

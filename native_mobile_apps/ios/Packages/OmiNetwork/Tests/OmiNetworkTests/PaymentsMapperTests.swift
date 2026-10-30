import Foundation
@testable import OmiNetwork
import Testing

/// Payloads shaped as the backend sends them (`routers/users.py`, `routers/payment.py`, 2026-10-08).
struct PaymentsMapperTests {
    @Test func freePlanWithChatQuotaAndAllowance() {
        let subscription = PaymentsMapper.subscription([
            "subscription": [
                "plan": "basic", "status": "active", "current_period_end": NSNull(), "stripe_subscription_id": NSNull(),
                "features": ["300 minutes of listening per month"], "cancel_at_period_end": false,
                "limits": ["transcription_seconds": 18000, "chat_questions_per_month": 30, "chat_cost_usd_per_month": NSNull()],
            ],
            "transcription_seconds_used": 600, "transcription_seconds_limit": 18000,
            "words_transcribed_used": 1200, "words_transcribed_limit": 0,
            "insights_gained_used": 3, "insights_gained_limit": 0,
            "available_plans": [],
            "show_subscription_ui": true,
            "chat_quota_used": 24.0, "chat_quota_unit": "questions", "chat_quota_percent": 80.0,
            "chat_quota_allowed": true, "chat_quota_reset_at": 1_793_491_200,
            "transcription_allowance": ["mode": "managed", "remaining_seconds": 17400],
        ])
        #expect(subscription.plan == "basic" && !subscription.isPaid && !subscription.hasStripeSubscription)
        #expect(subscription.secondsUsed == 600 && subscription.secondsLimit == 18000)
        #expect(subscription.usage.chatUsed == 24 && subscription.usage.chatLimit == 30 && subscription.usage.chatUnit == "questions")
        #expect(subscription.usage.resetsAt == Date(timeIntervalSince1970: 1_793_491_200))
        #expect(subscription.usage.wordsUsed == 1200 && subscription.usage.wordsLimit == 0)
        #expect(subscription.transcriptionAllowance == .managed)
        #expect(subscription.currentPeriodEnd == nil)
    }

    @Test func paidPlanWithPeriodPriceAndPlans() {
        let subscription = PaymentsMapper.subscription([
            "subscription": [
                "plan": "plus", "status": "active", "current_period_end": 1_795_000_000, "cancel_at_period_end": true,
                "stripe_subscription_id": "sub_1", "current_price_id": "price_plus_m",
                "limits": ["chat_questions_per_month": 200],
            ],
            "transcription_seconds_used": 0, "transcription_seconds_limit": 90000,
            "available_plans": [[
                "id": "plus", "title": "Plus", "subtitle": "1,500 minutes of transcription per month", "eyebrow": "For everyday use",
                "features": ["1,500 minutes of transcription per month"],
                "prices": [
                    ["id": "price_plus_m", "title": "Monthly", "price_string": "$17.99/month", "description": "Billed monthly."],
                    ["id": "price_plus_y", "title": "Annual", "price_string": "$161.91/year"],
                ],
            ]],
        ])
        #expect(subscription.isPaid && subscription.cancelAtPeriodEnd && subscription.hasStripeSubscription)
        #expect(subscription.currentPeriodEnd == Date(timeIntervalSince1970: 1_795_000_000))
        #expect(subscription.currentPriceID == "price_plus_m")
        #expect(subscription.availablePlans.first?.eyebrow == "For everyday use")
        #expect(subscription.availablePlans.first?.prices.map(\.priceString) == ["$17.99/month", "$161.91/year"])
        #expect(subscription.usage.chatLimit == 200)
    }

    @Test func costCappedChatReadsTheDollarLimit() {
        let subscription = PaymentsMapper.subscription([
            "subscription": ["plan": "architect", "limits": ["chat_cost_usd_per_month": 400.0]],
            "chat_quota_used": 12.5, "chat_quota_unit": "cost_usd",
        ])
        #expect(subscription.usage.chatLimit == 400 && subscription.usage.chatUsed == 12.5)
    }

    @Test func availablePlansOffers() {
        let offers = PaymentsMapper.offers(["plans": [
            [
                "id": "price_plus_m", "plan_id": "plus", "title": "Plus Monthly", "price_string": "$17.99/mo",
                "interval": "month", "unit_amount": 1799, "is_active": true, "eyebrow": "For everyday use",
            ],
            [
                "id": "price_plus_y", "plan_id": "plus", "title": "Plus Annual", "price_string": "$13/mo",
                "interval": "year", "unit_amount": 16191,
            ],
            ["id": "price_odd", "plan_id": "plus", "title": "Weekly", "price_string": "$1", "interval": "week"],
        ]])
        #expect(offers.map(\.id) == ["price_plus_m", "price_plus_y"])
        #expect(offers.first?.isActive == true && offers.first?.unitAmount == 1799 && offers.first?.interval == .month)
        #expect(offers.last?.isActive == false && offers.last?.interval == .year)
    }

    @Test func checkoutOrReactivation() {
        #expect(PaymentsMapper.checkout(["url": "https://checkout.stripe.com/c/1", "session_id": "cs_1"])
            == .checkout(URL(string: "https://checkout.stripe.com/c/1")!))
        #expect(PaymentsMapper.checkout(["status": "reactivated", "message": "Welcome back", "next_billing_date": 1])
            == .reactivated(message: "Welcome back"))
        #expect(PaymentsMapper.checkout([:]) == nil)
    }

    @Test func refusalDetail() {
        let refusal = PaymentsMapper.refusal(APIError.http(status: 400, body: #"{"detail": "Invalid or expired promotion code."}"#))
        #expect(refusal == PaymentRefusal(status: 400, detail: "Invalid or expired promotion code."))
        #expect(PaymentsMapper.refusal(APIError.http(status: 500, body: "oops"))?.detail == nil)
        #expect(PaymentsMapper.refusal(APIError.transport("offline")) == nil)
    }
}

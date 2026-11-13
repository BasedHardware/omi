package com.friend.ios.network.endpoints

import com.friend.ios.core.models.CheckoutResult
import com.friend.ios.core.models.PaymentRefusal
import com.friend.ios.core.models.PlanOffer
import com.friend.ios.core.models.Subscription
import com.friend.ios.core.models.TranscriptionAllowance
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant

/** Port of `APIClient+Payments.swift`: Plan & usage calls. */
interface PaymentsAPI {
    suspend fun subscription(): Subscription
    /** `GET v1/payments/available-plans`: every purchasable price, which one is paid now. */
    suspend fun planOffers(): List<PlanOffer>
    /** `POST v1/payments/checkout-session`: a Stripe checkout URL, or a reactivated plan. Never pays by itself. */
    suspend fun startCheckout(priceID: String, promotionCode: String?): CheckoutResult
    /** `POST v1/payments/upgrade-subscription`; returns the backend's message. */
    suspend fun changePlan(priceID: String, promotionCode: String?): String?
    /** `POST v1/payments/customer-portal` → Stripe portal URL. */
    suspend fun customerPortalURL(): String?
}

internal class PaymentsEndpoints(private val http: HttpCore) : PaymentsAPI {
    override suspend fun subscription(): Subscription = PaymentsMapper.subscription(http.jsonObject(Method.GET, "v1/users/me/subscription"))

    override suspend fun planOffers(): List<PlanOffer> = PaymentsMapper.offers(http.jsonObject(Method.GET, "v1/payments/available-plans"))

    override suspend fun startCheckout(priceID: String, promotionCode: String?): CheckoutResult {
        val body = buildJsonObject {
            put("price_id", priceID)
            if (!promotionCode.isNullOrEmpty()) put("promotion_code", promotionCode)
        }
        return PaymentsMapper.checkout(http.jsonObject(Method.POST, "v1/payments/checkout-session", json = body))
            ?: throw APIError.Decoding("checkout-session")
    }

    override suspend fun changePlan(priceID: String, promotionCode: String?): String? {
        val body = buildJsonObject {
            put("price_id", priceID)
            if (!promotionCode.isNullOrEmpty()) put("promotion_code", promotionCode)
        }
        return http.jsonObject(Method.POST, "v1/payments/upgrade-subscription", json = body).string("message")
    }

    override suspend fun customerPortalURL(): String? = http.jsonObject(Method.POST, "v1/payments/customer-portal").string("url")
}

/** Wire → model for the plan endpoints. Pure, so the payloads are tested as the backend sends them. */
object PaymentsMapper {
    fun subscription(root: JsonObject): Subscription {
        val sub = root.obj("subscription") ?: JsonObject(emptyMap())
        val limits = sub.obj("limits") ?: JsonObject(emptyMap())
        val chatUnit = root.string("chat_quota_unit")
        return Subscription(
            plan = sub.string("plan") ?: "basic",
            status = sub.string("status") ?: "active",
            cancelAtPeriodEnd = sub.bool("cancel_at_period_end") ?: false,
            features = sub.strings("features"),
            secondsUsed = root.int("transcription_seconds_used") ?: 0,
            secondsLimit = root.int("transcription_seconds_limit") ?: 0,
            chatQuotaPercent = root.double("chat_quota_percent"),
            showSubscriptionUI = root.bool("show_subscription_ui") ?: true,
            availablePlans = root.objects("available_plans").mapNotNull(::plan),
            transcriptionAllowance = TranscriptionAllowance.from(root.obj("transcription_allowance")?.string("mode")),
            currentPeriodEnd = sub.double("current_period_end")?.let { Instant.ofEpochMilli((it * 1000).toLong()) },
            currentPriceID = sub.string("current_price_id"),
            hasStripeSubscription = !sub.string("stripe_subscription_id").isNullOrEmpty(),
            usage = Subscription.Usage(
                wordsUsed = root.int("words_transcribed_used") ?: 0,
                wordsLimit = root.int("words_transcribed_limit") ?: 0,
                insightsUsed = root.int("insights_gained_used") ?: 0,
                insightsLimit = root.int("insights_gained_limit") ?: 0,
                chatUsed = root.double("chat_quota_used") ?: 0.0,
                chatUnit = chatUnit,
                chatLimit = if (chatUnit == "cost_usd") limits.double("chat_cost_usd_per_month") else limits.double("chat_questions_per_month"),
                chatAllowed = root.bool("chat_quota_allowed") ?: true,
                resetsAt = root.double("chat_quota_reset_at")?.let { Instant.ofEpochMilli((it * 1000).toLong()) },
            ),
        )
    }

    fun plan(item: JsonObject): Subscription.Plan? {
        val id = item.string("id") ?: return null
        val prices = item.objects("prices").mapNotNull { price ->
            val priceID = price.string("id") ?: return@mapNotNull null
            Subscription.Plan.Price(priceID, price.string("title").orEmpty(), price.string("price_string").orEmpty(), price.string("description"))
        }
        return Subscription.Plan(
            id = id, title = item.string("title") ?: id, subtitle = item.string("subtitle"), eyebrow = item.string("eyebrow"),
            features = item.strings("features"), prices = prices,
        )
    }

    /** `GET v1/payments/available-plans` → `{"plans": [PricingOption...]}`. */
    fun offers(root: JsonObject): List<PlanOffer> = root.objects("plans").mapNotNull { item ->
        val id = item.string("id") ?: return@mapNotNull null
        val interval = PlanOffer.Interval.from(item.string("interval")) ?: return@mapNotNull null
        PlanOffer(
            id = id, planID = item.string("plan_id").orEmpty(), title = item.string("title").orEmpty(),
            priceString = item.string("price_string").orEmpty(), description = item.string("description"),
            subtitle = item.string("subtitle"), eyebrow = item.string("eyebrow"), interval = interval,
            unitAmount = item.int("unit_amount"), isActive = item.bool("is_active") ?: false,
        )
    }

    /** `POST v1/payments/checkout-session`: a checkout URL, or `status: reactivated`. */
    fun checkout(root: JsonObject): CheckoutResult? {
        if (root.string("status") == "reactivated") return CheckoutResult.Reactivated(root.string("message"))
        return root.string("url")?.let(CheckoutResult::Checkout)
    }

    /** The `detail` of a refused payment call; nil when the body says nothing a person can read. */
    fun refusal(error: Throwable): PaymentRefusal? {
        val http = error as? APIError.Http ?: return null
        val detail = JsonAccess.obj(http.body).string("detail")?.trim()
        return PaymentRefusal(http.status, detail?.takeIf { it.isNotEmpty() })
    }
}

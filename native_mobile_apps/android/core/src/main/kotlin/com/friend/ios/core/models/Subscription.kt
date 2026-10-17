package com.friend.ios.core.models

import java.time.Instant

/** Port of the models in `APIClient+Payments.swift`: Plan & usage (`GET v1/users/me/subscription`). */
data class Subscription(
    val plan: String,
    val status: String,
    val cancelAtPeriodEnd: Boolean,
    val features: List<String>,
    val secondsUsed: Int,
    val secondsLimit: Int,
    val chatQuotaPercent: Double?,
    val showSubscriptionUI: Boolean,
    val availablePlans: List<Plan>,
    /** How the backend lets this account transcribe now; nil from a backend that does not say. */
    val transcriptionAllowance: TranscriptionAllowance? = null,
    /** When the paid period renews (or ends, when cancelled). */
    val currentPeriodEnd: Instant? = null,
    /** The Stripe price paid now ("price_..."), to tell monthly from annual. */
    val currentPriceID: String? = null,
    /** The account has a Stripe subscription (paid now or before): the payment portal can open. */
    val hasStripeSubscription: Boolean = false,
    val usage: Usage = Usage(),
) {
    data class Plan(
        /** The plan id ("plus", "unlimited_v2"). */
        val id: String,
        val title: String,
        /** "1,500 minutes of listening per month", under the title. */
        val subtitle: String? = null,
        /** "Most popular", above the title. */
        val eyebrow: String? = null,
        val features: List<String>,
        val prices: List<Price>,
    ) {
        data class Price(
            val id: String,
            /** "Monthly" or "Annual" (the backend's words). */
            val title: String,
            /** "$17.99/month". */
            val priceString: String,
            val description: String? = null,
        )
    }

    /** This month's use against the plan's limits; a limit of 0 means unlimited (the wire's sentinel). */
    data class Usage(
        val wordsUsed: Int = 0,
        val wordsLimit: Int = 0,
        val insightsUsed: Int = 0,
        val insightsLimit: Int = 0,
        /** Chat questions (or US dollars on cost-capped plans) used this month. */
        val chatUsed: Double = 0.0,
        /** "questions" or "cost_usd"; nil from a backend that does not say. */
        val chatUnit: String? = null,
        val chatLimit: Double? = null,
        val chatAllowed: Boolean = true,
        /** When chat (and the month's minutes) start again. */
        val resetsAt: Instant? = null,
    )

    val isPaid: Boolean get() = plan != "basic" && status == "active"

    /** The plan's minutes are used up (Flutter `UsageProvider.isOutOfCredits`; 0 is unlimited). */
    val isOutOfMinutes: Boolean get() = secondsLimit > 0 && secondsUsed >= secondsLimit
}

/** Backend `resolve_transcription_allowance` modes. */
enum class TranscriptionAllowance(val rawValue: String) {
    Managed("managed"), OnDevice("on_device"), Blocked("blocked");

    companion object {
        fun from(raw: String?): TranscriptionAllowance? = entries.firstOrNull { it.rawValue == raw }
    }
}

/** One price of a paid plan, as `GET v1/payments/available-plans` lists them. */
data class PlanOffer(
    /** The Stripe price id, what checkout takes. */
    val id: String,
    val planID: String,
    val title: String,
    /** "$17.99/mo"; for annual prices the monthly equivalent ("$13/mo"). */
    val priceString: String,
    val description: String? = null,
    val subtitle: String? = null,
    val eyebrow: String? = null,
    val interval: Interval,
    /** In cents, for the whole interval. */
    val unitAmount: Int?,
    /** Paid now, or scheduled to start when the current period ends. */
    val isActive: Boolean = false,
) {
    enum class Interval(val rawValue: String) {
        Month("month"), Year("year");

        companion object {
            fun from(raw: String?): Interval? = entries.firstOrNull { it.rawValue == raw }
        }
    }
}

/** What starting a checkout gave back. */
sealed interface CheckoutResult {
    /** Pay on Stripe's page. */
    data class Checkout(val url: String) : CheckoutResult
    /** A cancelled plan that had not ended yet is running again; no charge now. */
    data class Reactivated(val message: String?) : CheckoutResult
}

/** The payment service said no, in its own words (`{"detail": "..."}`). */
data class PaymentRefusal(val status: Int, val detail: String?) : Exception(detail ?: "HTTP $status")

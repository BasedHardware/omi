package com.friend.ios.service.stores

import com.friend.ios.core.models.PlanOffer
import com.friend.ios.core.models.Subscription
import java.text.NumberFormat
import java.util.Currency
import java.util.Locale
import kotlin.math.roundToInt

/** Port of `PlanCatalog.swift`: one paid plan with its monthly and annual price. */
data class PlanTier(
    /** The plan id ("plus", "unlimited_v2"). */
    val id: String,
    val title: String,
    val subtitle: String?,
    /** "Most popular": the one plan to point at. */
    val eyebrow: String?,
    val features: List<String>,
    val monthly: PlanOffer?,
    val annual: PlanOffer?,
) {
    fun offer(interval: PlanOffer.Interval): PlanOffer? = if (interval == PlanOffer.Interval.Year) annual else monthly

    /** Paid now (either price), or scheduled. */
    val isCurrent: Boolean get() = monthly?.isActive == true || annual?.isActive == true

    /** Whole percent the annual price saves against twelve monthly ones; nil when it does not. */
    val annualSavingsPercent: Int? get() = PlanCatalog.savingsPercent(monthly?.unitAmount, annual?.unitAmount)
}

/** What the main button does for the chosen price. */
sealed interface PlanPurchase {
    /** Free or cancelled: Stripe checkout (or the backend reactivates a cancelled plan in place). */
    data class Checkout(val offer: PlanOffer) : PlanPurchase
    /** A running paid plan: switch to this price (`upgrade-subscription`). */
    data class Change(val offer: PlanOffer) : PlanPurchase
    /** Already paid (or scheduled): nothing to buy. */
    data object Current : PlanPurchase
    /** Desktop plans are managed on the Mac; this price cannot replace them from the phone. */
    data object ManagedElsewhere : PlanPurchase
}

/** A meter on Plan & usage: what this month used against the plan's limit. */
data class UsageMeter(
    val kind: Kind,
    /** Minutes for listening, questions for chat, US dollars for chat spend, counts otherwise. */
    val used: Double,
    /** null: unlimited. */
    val limit: Double?,
) {
    enum class Kind(val rawValue: String) { Listening("listening"), Chat("chat"), ChatSpend("chatSpend"), Words("words"), Insights("insights") }

    val id: Kind get() = kind

    /** 0...1 of the limit; null when unlimited. */
    val fraction: Double?
        get() {
            val limit = limit ?: return null
            if (limit <= 0) return null
            return (used / limit).coerceIn(0.0, 1.0)
        }

    val isUnlimited: Boolean get() = limit == null

    /** From 80 % of the limit. */
    val isNearLimit: Boolean get() = (fraction ?: 0.0) >= 0.8

    val isAtLimit: Boolean get() = (fraction ?: 0.0) >= 1
}

/**
 * Plan logic for Plan & usage, kept pure so it is tested without a screen (mirrors Flutter's
 * `plan_pricing.dart`, `plan_display_name.dart` and the plans sheet's button rules).
 */
object PlanCatalog {
    /** Cheaper first, as Flutter orders the tiers. */
    internal val order = listOf("plus", "unlimited_v2", "unlimited", "operator", "architect")

    /** Plans that include the Mac app; managed from the desktop, never swapped for a phone plan here. */
    internal val desktopPlans = setOf("operator", "architect")

    /** Prices grouped into plans, cheaper first. `plans` adds the feature lines and titles the price list does not carry. */
    fun tiers(offers: List<PlanOffer>, plans: List<Subscription.Plan>): List<PlanTier> {
        val grouped = offers.groupBy { it.planID }
        return grouped.keys.sortedWith(compareBy<String> { rank(it) }.thenBy { it }).map { id ->
            val prices = grouped[id].orEmpty()
            val plan = plans.firstOrNull { it.id == id }
            val any = prices.firstOrNull()
            PlanTier(
                id = id,
                title = plan?.title ?: title(any?.title, id),
                subtitle = plan?.subtitle ?: any?.subtitle,
                eyebrow = plan?.eyebrow ?: any?.eyebrow,
                features = plan?.features.orEmpty(),
                monthly = prices.firstOrNull { it.interval == PlanOffer.Interval.Month },
                annual = prices.firstOrNull { it.interval == PlanOffer.Interval.Year },
            )
        }
    }

    /** The prices the subscription lists, as offers: what Plan & usage shows when `available-plans` cannot be read. */
    fun offers(plans: List<Subscription.Plan>, currentPriceID: String?): List<PlanOffer> = plans.flatMap { plan ->
        plan.prices.mapNotNull { price ->
            val title = price.title.lowercase()
            val interval = when {
                "annual" in title || "year" in title -> PlanOffer.Interval.Year
                "month" in title -> PlanOffer.Interval.Month
                else -> return@mapNotNull null
            }
            PlanOffer(
                id = price.id, planID = plan.id, title = "${plan.title} ${price.title}", priceString = price.priceString,
                description = price.description, subtitle = plan.subtitle, eyebrow = plan.eyebrow, interval = interval,
                unitAmount = cents(price.priceString), isActive = price.id == currentPriceID,
            )
        }
    }

    /** "$17.99/month" -> 1799. */
    fun cents(priceString: String): Int? {
        val number = priceString.dropWhile { !it.isDigit() }.takeWhile { it.isDigit() || it == '.' || it == ',' }
        val value = number.replace(",", "").toDoubleOrNull() ?: return null
        return (value * 100).roundToInt()
    }

    /** Whole percent an annual price saves against twelve monthly ones; nil when a price is missing or annual is not cheaper. */
    fun savingsPercent(monthly: Int?, annual: Int?): Int? {
        if (monthly == null || annual == null || monthly <= 0) return null
        val percent = ((1 - annual.toDouble() / (monthly * 12).toDouble()) * 100).roundToInt()
        return percent.takeIf { it > 0 }
    }

    /** The largest saving across plans, for the Monthly / Yearly switch. */
    fun bestSavingsPercent(tiers: List<PlanTier>): Int? = tiers.mapNotNull { it.annualSavingsPercent }.maxOrNull()

    /** An annual price as a monthly one ("$13.49"), from cents; null without an amount. */
    fun monthlyEquivalent(offer: PlanOffer, locale: Locale = Locale.getDefault()): String? {
        if (offer.interval != PlanOffer.Interval.Year) return null
        val amount = offer.unitAmount ?: return null
        val format = NumberFormat.getCurrencyInstance(locale).apply { currency = Currency.getInstance("USD") }
        return format.format(amount / 1200.0)
    }

    /** The plan's name: null for the free plan (the screen says "Free"), the backend's title when it lists the plan, else the product name. */
    fun paidPlanName(subscription: Subscription): String? {
        val plan = subscription.plan
        if (plan == "basic" || plan.isEmpty()) return null
        subscription.availablePlans.firstOrNull { it.id == plan }?.title?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        return when (plan) {
            "plus" -> "Plus"
            "operator" -> "Operator"
            "architect" -> "Architect"
            "unlimited", "unlimited_v2" -> "Unlimited"
            else -> plan.split('_', '-', ' ').filter { it.isNotEmpty() }.joinToString(" ") { it.take(1).uppercase() + it.drop(1) }
        }
    }

    /** What the main button does for [offer] (Flutter `_handleUpgrade` and `shouldShowPlanContinueButton`). */
    fun purchase(offer: PlanOffer, subscription: Subscription): PlanPurchase {
        if (offer.isActive) return PlanPurchase.Current
        val running = subscription.isPaid && !subscription.cancelAtPeriodEnd
        if (running && subscription.plan in desktopPlans && offer.planID !in desktopPlans) return PlanPurchase.ManagedElsewhere
        return if (running) PlanPurchase.Change(offer) else PlanPurchase.Checkout(offer)
    }

    /**
     * This month's meters: listening minutes, chat questions (or spend), words, insights. Limits of 0
     * are unlimited (the wire's sentinel). Words and insights only when they are limited.
     */
    fun meters(subscription: Subscription): List<UsageMeter> {
        val usage = subscription.usage
        val meters = mutableListOf(
            UsageMeter(
                UsageMeter.Kind.Listening, (subscription.secondsUsed / 60).toDouble(),
                if (subscription.secondsLimit > 0) (subscription.secondsLimit / 60).toDouble() else null,
            ),
        )
        val chatLimit = usage.chatLimit
        val percent = subscription.chatQuotaPercent
        when {
            chatLimit != null && chatLimit > 0 ->
                meters += UsageMeter(if (usage.chatUnit == "cost_usd") UsageMeter.Kind.ChatSpend else UsageMeter.Kind.Chat, usage.chatUsed, chatLimit)
            // No cap in the payload, but a share of it: the cap follows from the two.
            percent != null && percent > 0 && usage.chatUsed > 0 ->
                meters += UsageMeter(UsageMeter.Kind.Chat, usage.chatUsed, Math.round(usage.chatUsed * 100 / percent).toDouble())
            usage.chatUnit != null -> meters += UsageMeter(UsageMeter.Kind.Chat, usage.chatUsed, null)
        }
        if (usage.wordsLimit > 0) meters += UsageMeter(UsageMeter.Kind.Words, usage.wordsUsed.toDouble(), usage.wordsLimit.toDouble())
        if (usage.insightsLimit > 0) meters += UsageMeter(UsageMeter.Kind.Insights, usage.insightsUsed.toDouble(), usage.insightsLimit.toDouble())
        return meters
    }

    private fun rank(id: String): Int = order.indexOf(id).let { if (it < 0) order.size else it }

    /** "Plus Monthly" -> "Plus"; the plan id when there is no title. */
    private fun title(offerTitle: String?, planID: String): String {
        val words = offerTitle.orEmpty().split(" ").filter { it.isNotEmpty() && it !in listOf("Monthly", "Annual", "Yearly") }
        return if (words.isEmpty()) planID.replaceFirstChar { it.uppercase() } else words.joinToString(" ")
    }
}

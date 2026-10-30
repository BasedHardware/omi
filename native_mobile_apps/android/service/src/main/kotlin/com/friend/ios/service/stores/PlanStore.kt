package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.CheckoutResult
import com.friend.ios.core.models.PlanOffer
import com.friend.ios.core.models.Subscription
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.endpoints.PaymentsMapper
import kotlinx.coroutines.CancellationException

/**
 * Port of `PlanStore.swift`: Plan & usage (Flutter `usage_page` + `plans_sheet`): the plan, this
 * month's meters, the plans to choose from (monthly or yearly), and the one action that buys or
 * switches. Payment itself always happens on Stripe's page; this store only asks the backend for
 * that page.
 */
class PlanStore(private val api: APIClientProtocol) {
    /** What the last action did, for one line on the screen. */
    sealed interface Notice {
        /** Back from checkout and the plan is paid now. */
        data class Upgraded(val plan: String) : Notice
        /** A cancelled plan runs again (backend message, if it sent one). */
        data class Reactivated(val message: String?) : Notice
        /** A running plan was switched (backend message, if it sent one). */
        data class Changed(val message: String?) : Notice
        /** The payment service refused, in its words (an expired promo code, a plan it will not sell). */
        data class Refused(val reason: String) : Notice
        /** The payment service could not be reached. */
        data object Unreachable : Notice
    }

    var subscription: Subscription? by mutableStateOf(null)
        private set
    var tiers: List<PlanTier> by mutableStateOf(emptyList())
        private set
    var isLoading: Boolean by mutableStateOf(false)
        private set
    /** Neither the plan nor its prices could be read. */
    var failed: Boolean by mutableStateOf(false)
        private set
    /** The plan loaded but no prices: plans cannot be bought from here right now. */
    var plansUnavailable: Boolean by mutableStateOf(false)
        private set
    var isWorking: Boolean by mutableStateOf(false)
        private set
    var notice: Notice? by mutableStateOf(null)
        private set
    var interval: PlanOffer.Interval by mutableStateOf(PlanOffer.Interval.Year)
    var selectedTierID: String? by mutableStateOf(null)
    var promoCode: String by mutableStateOf("")

    /** The plan before a checkout opened, to tell on return whether it went through. */
    private var planBeforeCheckout: String? = null

    val selectedTier: PlanTier? get() = tiers.firstOrNull { it.id == selectedTierID } ?: tiers.firstOrNull()

    val selectedOffer: PlanOffer?
        get() = selectedTier?.offer(interval) ?: selectedTier?.offer(if (interval == PlanOffer.Interval.Year) PlanOffer.Interval.Month else PlanOffer.Interval.Year)

    /** What the main button does now; null while there is nothing to choose. */
    val purchase: PlanPurchase?
        get() {
            val subscription = subscription ?: return null
            val offer = selectedOffer ?: return null
            return PlanCatalog.purchase(offer, subscription)
        }

    val meters: List<UsageMeter> get() = subscription?.let(PlanCatalog::meters).orEmpty()

    /** Both prices exist for some plan: the Monthly / Yearly switch is worth showing. */
    val offersBothIntervals: Boolean get() = tiers.any { it.monthly != null && it.annual != null }

    suspend fun load() {
        isLoading = true
        try {
            val loaded = try {
                api.subscription()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                null
            }
            if (loaded == null) {
                failed = subscription == null
                return
            }
            failed = false
            subscription = loaded
            if (!loaded.showSubscriptionUI) {
                tiers = emptyList()
                plansUnavailable = false
                return
            }
            var offers = try {
                api.planOffers()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                emptyList()
            }
            if (offers.isEmpty()) offers = PlanCatalog.offers(loaded.availablePlans, loaded.currentPriceID)
            tiers = PlanCatalog.tiers(offers, loaded.availablePlans)
            plansUnavailable = tiers.isEmpty()
            // Start on the plan paid now (and its interval), else the one the backend points at.
            val current = tiers.firstOrNull { it.isCurrent }
            if (current != null) {
                selectedTierID = current.id
                interval = if (current.annual?.isActive == true) PlanOffer.Interval.Year else PlanOffer.Interval.Month
            } else if (selectedTierID == null || tiers.none { it.id == selectedTierID }) {
                selectedTierID = (tiers.firstOrNull { it.eyebrow?.lowercase()?.contains("popular") == true } ?: tiers.firstOrNull())?.id
            }
        } finally {
            isLoading = false
        }
    }

    /**
     * The main button. Returns Stripe's checkout page to open; null when it was handled in place
     * (a reactivation or a plan switch) or refused (see [notice]).
     */
    suspend fun buy(): String? {
        val purchase = purchase ?: return null
        if (isWorking) return null
        isWorking = true
        notice = null
        val code = promoCode.trim().takeIf { it.isNotEmpty() }
        try {
            when (purchase) {
                is PlanPurchase.Checkout -> when (val result = api.startCheckout(purchase.offer.id, code)) {
                    is CheckoutResult.Checkout -> {
                        planBeforeCheckout = subscription?.plan
                        return result.url
                    }
                    is CheckoutResult.Reactivated -> {
                        notice = Notice.Reactivated(result.message)
                        load()
                    }
                }
                is PlanPurchase.Change -> {
                    notice = Notice.Changed(api.changePlan(purchase.offer.id, code))
                    promoCode = ""
                    load()
                }
                PlanPurchase.Current, PlanPurchase.ManagedElsewhere -> return null
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            notice = notice(e)
        } finally {
            isWorking = false
        }
        return null
    }

    /** Back from Stripe's checkout: read the plan again and say so when it is paid now. */
    suspend fun returnedFromCheckout() {
        val before = planBeforeCheckout
        planBeforeCheckout = null
        load()
        val subscription = subscription ?: return
        if (subscription.isPaid && subscription.plan != before) {
            notice = Notice.Upgraded(PlanCatalog.paidPlanName(subscription) ?: subscription.plan)
            promoCode = ""
        }
    }

    /** Stripe's portal (payment method, invoices, cancel there too); null with [notice] on failure. */
    suspend fun portalURL(): String? {
        notice = null
        try {
            api.customerPortalURL()?.let { return it }
            notice = Notice.Unreachable
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            notice = notice(e)
        }
        return null
    }

    fun dismissNotice() {
        notice = null
    }

    companion object {
        fun notice(error: Throwable): Notice {
            val refusal = PaymentsMapper.refusal(error)
            val detail = refusal?.detail
            if (refusal != null && refusal.status in 400 until 500 && detail != null) return Notice.Refused(detail)
            return Notice.Unreachable
        }
    }
}

fun SettingsStore.makePlanStore(): PlanStore = PlanStore(api)

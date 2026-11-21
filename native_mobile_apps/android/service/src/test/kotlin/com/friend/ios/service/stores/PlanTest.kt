package com.friend.ios.service.stores

import com.friend.ios.core.models.CheckoutResult
import com.friend.ios.core.models.PlanOffer
import com.friend.ios.core.models.Subscription
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.PaymentsMapper
import com.friend.ios.service.fakeAPI
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `PlanTests.swift`: PlanCatalog, PaymentsMapper and PlanStore. */
class PlanTest {
    private fun json(text: String) = Json.parseToJsonElement(text) as JsonObject

    private fun sub(
        plan: String = "basic",
        status: String = "active",
        cancel: Boolean = false,
        secondsUsed: Int = 0,
        secondsLimit: Int = 18_000,
        usage: Subscription.Usage = Subscription.Usage(),
        plans: List<Subscription.Plan> = emptyList(),
        showUI: Boolean = true,
    ) = Subscription(plan, status, cancel, emptyList(), secondsUsed, secondsLimit, null, showUI, plans, usage = usage)

    private fun offer(id: String, plan: String, interval: PlanOffer.Interval, cents: Int, active: Boolean = false, eyebrow: String? = null) =
        PlanOffer(id, plan, "$plan ${interval.rawValue}", "$${cents / 100}", eyebrow = eyebrow, interval = interval, unitAmount = cents, isActive = active)

    @Test
    fun mapperReadsTheSubscriptionPayload() {
        val root = json(
            """
            {"subscription": {"plan": "unlimited_v2", "status": "active", "cancel_at_period_end": true,
              "current_period_end": 1790000000, "current_price_id": "price_1", "stripe_subscription_id": "sub_1",
              "limits": {"chat_questions_per_month": 1000}},
             "transcription_seconds_used": 600.0, "transcription_seconds_limit": 0, "chat_quota_used": 31,
             "chat_quota_unit": "questions", "show_subscription_ui": false,
             "transcription_allowance": {"mode": "on_device"},
             "available_plans": [{"id": "unlimited_v2", "title": "Unlimited", "features": ["a"], "prices": [{"id": "p", "title": "Monthly", "price_string": "${'$'}29.99/mo"}]}]}
            """.trimIndent(),
        )
        val s = PaymentsMapper.subscription(root)
        assertEquals("unlimited_v2", s.plan)
        assertTrue(s.isPaid)
        assertTrue(s.cancelAtPeriodEnd)
        assertEquals(600, s.secondsUsed)
        assertEquals(1000.0, s.usage.chatLimit)
        assertEquals(31.0, s.usage.chatUsed, 0.0)
        assertFalse(s.showSubscriptionUI)
        assertTrue(s.hasStripeSubscription)
        assertEquals("price_1", s.currentPriceID)
        assertEquals(1_790_000_000_000L, s.currentPeriodEnd?.toEpochMilli())
        assertEquals(com.friend.ios.core.models.TranscriptionAllowance.OnDevice, s.transcriptionAllowance)
        assertEquals("Unlimited", PlanCatalog.paidPlanName(s))
        assertEquals("p", s.availablePlans.single().prices.single().id)
    }

    @Test
    fun mapperReadsOffersCheckoutAndRefusals() {
        val offers = PaymentsMapper.offers(json("""{"plans": [{"id": "a", "plan_id": "plus", "interval": "year", "unit_amount": 16191, "is_active": true}, {"id": "b", "interval": "week"}]}"""))
        assertEquals(1, offers.size)
        assertEquals(PlanOffer.Interval.Year, offers[0].interval)
        assertTrue(offers[0].isActive)
        assertEquals(CheckoutResult.Reactivated("back"), PaymentsMapper.checkout(json("""{"status": "reactivated", "message": "back"}""")))
        assertEquals(CheckoutResult.Checkout("https://pay"), PaymentsMapper.checkout(json("""{"url": "https://pay"}""")))
        assertEquals("Expired", PaymentsMapper.refusal(APIError.Http(400, """{"detail": " Expired "}"""))?.detail)
        assertNull(PaymentsMapper.refusal(APIError.Http(500, "oops"))?.detail)
        assertNull(PaymentsMapper.refusal(IllegalStateException()))
    }

    @Test
    fun catalogGroupsPricesIntoTiersCheaperFirst() {
        val offers = listOf(
            offer("u_m", "unlimited_v2", PlanOffer.Interval.Month, 2999),
            offer("p_y", "plus", PlanOffer.Interval.Year, 16191),
            offer("p_m", "plus", PlanOffer.Interval.Month, 1799),
        )
        val tiers = PlanCatalog.tiers(offers, listOf(Subscription.Plan("plus", "Plus", features = listOf("x"), prices = emptyList())))
        assertEquals(listOf("plus", "unlimited_v2"), tiers.map { it.id })
        assertEquals("Plus", tiers[0].title)
        assertEquals(25, tiers[0].annualSavingsPercent)
        assertEquals(25, PlanCatalog.bestSavingsPercent(tiers))
    }

    @Test
    fun catalogPricesAndNames() {
        assertEquals(1799, PlanCatalog.cents("$17.99/month"))
        assertEquals(161_91, PlanCatalog.cents("$161.91"))
        assertNull(PlanCatalog.cents("free"))
        assertNull(PlanCatalog.savingsPercent(1000, 12_000))
        assertNull(PlanCatalog.paidPlanName(sub()))
        assertEquals("Operator", PlanCatalog.paidPlanName(sub(plan = "operator")))
        assertEquals("Team Pro", PlanCatalog.paidPlanName(sub(plan = "team_pro")))
        val offers = PlanCatalog.offers(
            listOf(Subscription.Plan("plus", "Plus", features = emptyList(), prices = listOf(Subscription.Plan.Price("y", "Annual", "$161.91"), Subscription.Plan.Price("z", "Lifetime", "$1")))),
            currentPriceID = "y",
        )
        assertEquals(1, offers.size)
        assertTrue(offers[0].isActive)
        assertEquals(PlanOffer.Interval.Year, offers[0].interval)
    }

    @Test
    fun purchaseRules() {
        val plus = offer("p", "plus", PlanOffer.Interval.Month, 1799)
        assertEquals(PlanPurchase.Checkout(plus), PlanCatalog.purchase(plus, sub()))
        assertEquals(PlanPurchase.Change(plus), PlanCatalog.purchase(plus, sub(plan = "unlimited_v2")))
        assertEquals(PlanPurchase.Checkout(plus), PlanCatalog.purchase(plus, sub(plan = "unlimited_v2", cancel = true)))
        assertEquals(PlanPurchase.ManagedElsewhere, PlanCatalog.purchase(plus, sub(plan = "operator")))
        assertEquals(PlanPurchase.Current, PlanCatalog.purchase(plus.copy(isActive = true), sub(plan = "plus")))
    }

    @Test
    fun metersSkipUnlimitedWordsAndDeriveTheChatCap() {
        val meters = PlanCatalog.meters(sub(secondsUsed = 600, secondsLimit = 18_000, usage = Subscription.Usage(chatUsed = 30.0, chatUnit = "questions", chatLimit = 30.0)))
        assertEquals(listOf(UsageMeter.Kind.Listening, UsageMeter.Kind.Chat), meters.map { it.kind })
        assertEquals(10.0, meters[0].used, 0.0)
        assertEquals(300.0, meters[0].limit)
        assertTrue(meters[1].isAtLimit)
        val derived = PlanCatalog.meters(sub(secondsLimit = 0).copy(chatQuotaPercent = 25.0, usage = Subscription.Usage(chatUsed = 10.0)))
        assertNull(derived[0].limit)
        assertEquals(40.0, derived[1].limit)
        val spend = PlanCatalog.meters(sub(usage = Subscription.Usage(chatUnit = "cost_usd", chatLimit = 5.0, wordsLimit = 100, wordsUsed = 85)))
        assertEquals(listOf(UsageMeter.Kind.Listening, UsageMeter.Kind.ChatSpend, UsageMeter.Kind.Words), spend.map { it.kind })
        assertTrue(spend[2].isNearLimit)
    }

    @Test
    fun storeLoadsTiersAndStartsOnThePopularOne() = runTest {
        val api = fakeAPI {
            "subscription" returns sub()
            "planOffers" returns listOf(
                offer("p_m", "plus", PlanOffer.Interval.Month, 1799),
                offer("p_y", "plus", PlanOffer.Interval.Year, 16191),
                offer("u_m", "unlimited_v2", PlanOffer.Interval.Month, 2999, eyebrow = "Most popular"),
            )
        }
        val store = PlanStore(api.client)
        store.load()
        assertFalse(store.failed)
        assertFalse(store.plansUnavailable)
        assertEquals("unlimited_v2", store.selectedTier?.id)
        assertTrue(store.offersBothIntervals)
        // Unlimited has no yearly price: the monthly one stands in.
        assertEquals("u_m", store.selectedOffer?.id)
        assertEquals(PlanPurchase.Checkout(store.selectedOffer!!), store.purchase)
    }

    @Test
    fun storeStartsOnThePlanPaidNow() = runTest {
        val api = fakeAPI {
            "subscription" returns sub(plan = "plus")
            "planOffers" returns listOf(offer("p_m", "plus", PlanOffer.Interval.Month, 1799, active = true), offer("p_y", "plus", PlanOffer.Interval.Year, 16191))
        }
        val store = PlanStore(api.client)
        store.load()
        assertEquals("plus", store.selectedTierID)
        assertEquals(PlanOffer.Interval.Month, store.interval)
        assertEquals(PlanPurchase.Current, store.purchase)
    }

    @Test
    fun storeFallsBackToTheSubscriptionsPricesAndSaysWhenThereAreNone() = runTest {
        val api = fakeAPI {
            "subscription" returns sub()
            "planOffers" throws APIError.Transport("offline")
        }
        val store = PlanStore(api.client)
        store.load()
        assertTrue(store.plansUnavailable)
        val failing = PlanStore(fakeAPI { "subscription" throws APIError.Transport("offline") }.client)
        failing.load()
        assertTrue(failing.failed)
    }

    @Test
    fun buyOpensCheckoutReactivatesOrSaysWhyNot() = runTest {
        val api = fakeAPI {
            "subscription" returns sub()
            "planOffers" returns listOf(offer("p_m", "plus", PlanOffer.Interval.Month, 1799))
            "startCheckout" does { args -> if (args[1] == "BAD") throw APIError.Http(400, """{"detail": "Code expired"}""") else CheckoutResult.Checkout("https://stripe/${args[0]}") }
        }
        val store = PlanStore(api.client)
        store.load()
        store.promoCode = " "
        assertEquals("https://stripe/p_m", store.buy())
        assertNull(api.called("startCheckout").last()[1])
        store.promoCode = "BAD"
        assertNull(store.buy())
        assertEquals(PlanStore.Notice.Refused("Code expired"), store.notice)
        assertFalse(store.isWorking)
        // Back from checkout and paid now: say so.
        with(api) { "subscription" returns sub(plan = "plus") }
        store.promoCode = ""
        store.buy()
        store.returnedFromCheckout()
        assertEquals(PlanStore.Notice.Upgraded("Plus"), store.notice)
    }

    @Test
    fun changeAndPortal() = runTest {
        val api = fakeAPI {
            "subscription" returns sub(plan = "plus")
            "planOffers" returns listOf(offer("p_m", "plus", PlanOffer.Interval.Month, 1799, active = true), offer("u_m", "unlimited_v2", PlanOffer.Interval.Month, 2999))
            "changePlan" returns "Switched"
            "customerPortalURL" returns null
        }
        val store = PlanStore(api.client)
        store.load()
        store.selectedTierID = "unlimited_v2"
        assertNull(store.buy())
        assertEquals(PlanStore.Notice.Changed("Switched"), store.notice)
        assertNull(store.portalURL())
        assertEquals(PlanStore.Notice.Unreachable, store.notice)
        store.dismissNotice()
        assertNull(store.notice)
    }
}

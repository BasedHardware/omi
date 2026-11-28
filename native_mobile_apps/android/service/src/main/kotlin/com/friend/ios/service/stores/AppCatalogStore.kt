package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.AppCategory
import com.friend.ios.core.models.AppDetail
import com.friend.ios.core.models.AppQuery
import com.friend.ios.core.models.AppSubscription
import com.friend.ios.core.models.OmiApp
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import java.net.URI
import java.net.URLEncoder

/**
 * Port of `AppCatalogStore.swift`: the app store (Flutter `pages/apps/...`): browse with category,
 * kind and sort, an app's page with setup, reviews and payment. Turning apps on and off stays in
 * [CapabilitiesStore].
 */
class AppCatalogStore(
    internal val api: APIClientProtocol,
    private val capabilities: CapabilitiesStore,
    private val userID: () -> String?,
    private val purchasePollMillis: Long = 5_000,
) {
    var query: AppQuery by mutableStateOf(AppQuery())
    var results: List<OmiApp> by mutableStateOf(emptyList())
        private set
    var hasMore: Boolean by mutableStateOf(false)
        private set
    var isLoading: Boolean by mutableStateOf(false)
        private set
    /** The last first-page search failed (offline, server error); the browse screen offers Try again. */
    var searchFailed: Boolean by mutableStateOf(false)
        private set
    var categories: List<AppCategory> by mutableStateOf(emptyList())
        private set
    var details: Map<String, AppDetail> by mutableStateOf(emptyMap())
        private set
    var subscriptions: Map<String, AppSubscription> by mutableStateOf(emptyMap())
        private set
    /** Apps whose purchase is being waited for (the payment page is open). */
    var awaitingPurchase: Set<String> by mutableStateOf(emptySet())
        private set
    var lastError: String? by mutableStateOf(null)
        internal set
    private var searchGeneration = 0

    suspend fun loadCategories() {
        if (categories.isNotEmpty()) return
        categories = attempt { api.appCategories() } ?: emptyList()
    }

    /** The first page for [query]; an older search finishing late never overwrites a newer one. */
    suspend fun search() {
        searchGeneration += 1
        val generation = searchGeneration
        isLoading = true
        try {
            val page = try {
                api.browseApps(query, 0)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (generation == searchGeneration) searchFailed = true
                return
            }
            if (generation != searchGeneration) return
            searchFailed = false
            results = page.first
            hasMore = page.second
        } finally {
            if (generation == searchGeneration) isLoading = false
        }
    }

    suspend fun loadMore() {
        if (!hasMore || isLoading) return
        val generation = searchGeneration
        isLoading = true
        try {
            val page = attempt { api.browseApps(query, results.size) } ?: return
            if (generation != searchGeneration) return
            val known = results.map { it.id }.toSet()
            results = results + page.first.filter { it.id !in known }
            hasMore = page.second
        } finally {
            isLoading = false
        }
    }

    // MARK: One app

    suspend fun loadDetail(id: String) {
        try {
            val detail = api.appDetail(id, userID())
            details = details + (id to detail)
            if (detail.app.isPaid) attempt { api.appSubscription(id) }?.let { subscriptions = subscriptions + (id to it) }
            replace(detail.app)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            lastError = e.toString()
        }
    }

    /**
     * Turns the app on or off; returns the backend's reason when it refuses (setup not finished,
     * payment required ...), [COULD_NOT_CHANGE] without one.
     */
    suspend fun setEnabled(app: OmiApp, enabled: Boolean): String? {
        lastError = null
        try {
            api.setApp(app.id, enabled)
        } catch (e: CancellationException) {
            throw e
        } catch (e: APIError.Http) {
            return SettingsStore.detail(e.body) ?: COULD_NOT_CHANGE
        } catch (e: Exception) {
            return COULD_NOT_CHANGE
        }
        val updated = (details[app.id]?.app ?: app).copy(isEnabled = enabled)
        details[app.id]?.let { details = details + (app.id to it.copy(app = updated)) }
        replace(updated)
        capabilities.loadApps()
        return null
    }

    /** Writes (or changes) the user's own rating; the page reloads to show it. */
    suspend fun review(id: String, score: Int, text: String): Boolean {
        val updating = details[id]?.userReview != null
        try {
            api.reviewApp(id, score.coerceIn(1, 5), text.trim(), updating)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            lastError = e.toString()
            return false
        }
        loadDetail(id)
        return true
    }

    /**
     * After the payment page opened: checks every few seconds (for up to five minutes, like
     * Flutter) until the backend reports the app paid, then turns it on.
     */
    suspend fun awaitPurchase(id: String, attempts: Int = 60) {
        if (id in awaitingPurchase) return
        awaitingPurchase = awaitingPurchase + id
        try {
            repeat(attempts) {
                delay(purchasePollMillis)
                if (!currentCoroutineContext().isActive) return
                loadDetail(id)
                val detail = details[id]
                if (detail != null && detail.isUserPaid) {
                    if (!detail.app.isEnabled) setEnabled(detail.app, true)
                    return
                }
            }
        } finally {
            awaitingPurchase = awaitingPurchase - id
        }
    }

    /** Cancels at the end of the paid period. */
    suspend fun cancelSubscription(id: String): Boolean {
        try {
            api.cancelAppSubscription(id)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            lastError = e.toString()
            return false
        }
        attempt { api.appSubscription(id) }?.let { subscriptions = subscriptions + (id to it) }
        return true
    }

    /** A setup link with the user's id (Flutter sets `uid=` on auth steps and the setup check). */
    fun signedSetupURL(url: String): String {
        val uid = userID() ?: return url
        val parsed = runCatching { URI(url) }.getOrNull() ?: return url
        val kept = parsed.rawQuery.orEmpty().split("&").filter { it.isNotEmpty() && it.substringBefore("=") != "uid" }
        val query = (kept + ("uid=" + URLEncoder.encode(uid, "UTF-8"))).joinToString("&")
        val fragment = parsed.rawFragment?.let { "#" + it }.orEmpty()
        return URI(parsed.scheme, parsed.rawAuthority, parsed.rawPath, null, null).toString() + "?" + query + fragment
    }

    private fun replace(app: OmiApp) {
        results = results.map { if (it.id == app.id) app else it }
    }

    private suspend fun <T> attempt(block: suspend () -> T): T? = try {
        block()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }

    companion object {
        /** The kinds of app the browse list filters by (backend capability ids). */
        val capabilityKinds = listOf("chat", "memories", "external_integration", "proactive_notification", "tasks")

        /** Used when the backend gives no reason; the screen words it (`L10nFallback.couldNotChange`). */
        const val COULD_NOT_CHANGE = "could_not_change"
    }
}

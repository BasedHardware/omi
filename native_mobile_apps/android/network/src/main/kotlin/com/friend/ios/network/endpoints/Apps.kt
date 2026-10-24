package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.AppCategory
import com.friend.ios.core.models.AppDetail
import com.friend.ios.core.models.AppQuery
import com.friend.ios.core.models.AppReview
import com.friend.ios.core.models.AppSubscription
import com.friend.ios.core.models.Integration
import com.friend.ios.core.models.OmiApp
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant

/**
 * Port of `APIClient+Integrations.swift` (connections), `APIClient+Apps.swift` and
 * `APIClient+AppStore.swift` (Omi apps).
 */
interface AppsAPI {
    /** `GET v1/integrations/{key}` → connected (google_calendar, gmail, apple_health). */
    suspend fun integrationConnected(key: String): Boolean
    /** `GET v1/integrations/{key}/oauth-url` or `v1/task-integrations/{key}/oauth-url` → URL to open. */
    suspend fun integrationOAuthURL(integration: Integration): String
    /** `DELETE v1/integrations/{key}` / `v1/task-integrations/{key}`. */
    suspend fun disconnectIntegration(integration: Integration)
    /** `GET v1/task-integrations` → connected task apps. */
    suspend fun connectedTaskApps(): Set<String>
    /** `GET v2/apps/search` (query, installed-only, paging). */
    suspend fun searchApps(query: String, installedOnly: Boolean, offset: Int): List<OmiApp>
    /** `POST v1/apps/enable|disable?app_id=`. */
    suspend fun setApp(id: String, enabled: Boolean)
    /** `GET v1/apps/{id}`: the app with its reviews, setup and payment state. */
    suspend fun appDetail(id: String, uid: String?): AppDetail
    suspend fun appCategories(): List<AppCategory>
    /** `GET v2/apps/search` with filters and sort; `hasMore` from `pagination.hasNext`. */
    suspend fun browseApps(query: AppQuery, offset: Int): Pair<List<OmiApp>, Boolean>
    /** `POST v1/apps/review?app_id=` (first review) or `PATCH v1/apps/{id}/review` (changing it). */
    suspend fun reviewApp(id: String, score: Int, text: String, updating: Boolean)
    suspend fun appSubscription(id: String): AppSubscription?
    /** `DELETE v1/apps/{id}/subscription`: ends at the close of the paid period. */
    suspend fun cancelAppSubscription(id: String)
}

internal class AppsEndpoints(private val http: HttpCore) : AppsAPI {
    override suspend fun integrationConnected(key: String): Boolean = http.jsonObject(Method.GET, "v1/integrations/$key").bool("connected") ?: false

    override suspend fun integrationOAuthURL(integration: Integration): String {
        val base = if (integration.kind == Integration.Kind.TaskApp) "v1/task-integrations" else "v1/integrations"
        // Gmail shares Google's OAuth client with the calendar (Flutter gmail_service.dart).
        val key = if (integration.id == "gmail") "google_calendar" else integration.id
        return http.jsonObject(Method.GET, "$base/$key/oauth-url").string("auth_url") ?: throw APIError.Decoding("no auth_url")
    }

    override suspend fun disconnectIntegration(integration: Integration) {
        val base = if (integration.kind == Integration.Kind.TaskApp) "v1/task-integrations" else "v1/integrations"
        http.data(Method.DELETE, "$base/${integration.id}")
    }

    override suspend fun connectedTaskApps(): Set<String> {
        val integrations = http.jsonObject(Method.GET, "v1/task-integrations").obj("integrations") ?: return emptySet()
        return integrations.keys.filter { key -> (integrations[key] as? JsonObject)?.bool("connected") ?: true }.toSet()
    }

    override suspend fun searchApps(query: String, installedOnly: Boolean, offset: Int): List<OmiApp> {
        val items = mutableListOf("offset" to "$offset", "limit" to "30")
        if (query.isNotEmpty()) items += "q" to query
        if (installedOnly) items += "installed_apps" to "true"
        return http.jsonObject(Method.GET, "v2/apps/search", query = items).objects("data").mapNotNull(AppsMapper::app)
    }

    override suspend fun setApp(id: String, enabled: Boolean) {
        http.data(Method.POST, if (enabled) "v1/apps/enable" else "v1/apps/disable", query = listOf("app_id" to id))
    }

    override suspend fun appDetail(id: String, uid: String?): AppDetail =
        AppsMapper.detail(http.jsonObject(Method.GET, "v1/apps/$id"), uid) ?: throw APIError.Decoding("app without id")

    override suspend fun appCategories(): List<AppCategory> = JsonAccess.array(http.data(Method.GET, "v1/app-categories")).mapNotNull { item ->
        val o = item as? JsonObject ?: return@mapNotNull null
        val id = o.string("id") ?: return@mapNotNull null
        AppCategory(id, o.string("title") ?: id)
    }

    override suspend fun browseApps(query: AppQuery, offset: Int): Pair<List<OmiApp>, Boolean> {
        val items = mutableListOf("offset" to "$offset", "limit" to "30", "sort" to query.sort.rawValue)
        val text = query.text.trim()
        if (text.isNotEmpty()) items += "q" to text
        query.category?.let { items += "category" to it }
        query.capability?.let { items += "capability" to it }
        query.minimumRating?.let { items += "rating" to "$it" }
        val root = http.jsonObject(Method.GET, "v2/apps/search", query = items)
        return root.objects("data").mapNotNull(AppsMapper::app) to (root.obj("pagination")?.bool("hasNext") ?: false)
    }

    override suspend fun reviewApp(id: String, score: Int, text: String, updating: Boolean) {
        val body = Body.Json(buildJsonObject { put("score", score); put("review", text) }.toString())
        if (updating) http.data(Method.PATCH, "v1/apps/$id/review", body = body)
        else http.data(Method.POST, "v1/apps/review", query = listOf("app_id" to id), body = body)
    }

    override suspend fun appSubscription(id: String): AppSubscription? {
        val subscription = http.jsonObject(Method.GET, "v1/apps/$id/subscription").obj("subscription") ?: return null
        return AppSubscription(
            subscription.string("status").orEmpty(), subscription.bool("cancel_at_period_end") ?: false,
            subscription.double("current_period_end")?.let { Instant.ofEpochMilli((it * 1000).toLong()) },
        )
    }

    override suspend fun cancelAppSubscription(id: String) {
        http.data(Method.DELETE, "v1/apps/$id/subscription")
    }
}

/** `OmiApp.from`, `AppReview.from`, `AppDetail.from`: the backend `App` schema to models. */
object AppsMapper {
    fun app(item: JsonObject): OmiApp? {
        val id = item.string("id") ?: return null
        val name = item.string("name") ?: return null
        return OmiApp(
            id = id, name = name, description = item.string("description").orEmpty(), author = item.string("author"),
            imageURL = item.string("image"), category = item.string("category"), rating = item.double("rating_avg"),
            installs = item.int("installs") ?: 0, isEnabled = item.bool("enabled") ?: false,
            capabilities = item.strings("capabilities").toSet(), ratingCount = item.int("rating_count") ?: 0,
            isPaid = item.bool("is_paid") ?: false, price = item.double("price"),
        )
    }

    fun review(o: JsonObject): AppReview? {
        val uid = o.string("uid") ?: return null
        return AppReview(
            uid = uid, score = o.double("score") ?: 0.0, text = o.string("review").orEmpty(),
            username = o.string("username")?.takeIf { it.isNotEmpty() }, ratedAt = BackendDate.parse(o.string("rated_at")),
            response = o.string("response")?.takeIf { it.isNotEmpty() },
        )
    }

    fun detail(o: JsonObject, uid: String?): AppDetail? {
        val app = app(o) ?: return null
        val integration = o.obj("external_integration")
        val steps = integration?.objects("auth_steps").orEmpty().mapNotNull { step ->
            val name = step.string("name") ?: return@mapNotNull null
            val url = step.string("url") ?: return@mapNotNull null
            AppDetail.SetupStep(name, url)
        }
        val instructions = integration?.string("setup_instructions_file_path")?.takeIf { it.isNotEmpty() }
        val isURL = integration?.bool("is_instructions_url") ?: (instructions?.startsWith("http") ?: false)
        fun text(key: String) = o.string(key)?.takeIf { it.isNotBlank() }
        return AppDetail(
            app = app,
            reviews = o.objects("reviews").mapNotNull(::review).filter { it.text.isNotEmpty() },
            userReview = o.obj("user_review")?.let(::review),
            setupSteps = steps,
            setupInstructionsURL = if (isURL) instructions else null,
            setupInstructionsText = if (isURL) null else instructions,
            homeURL = integration?.string("app_home_url"),
            chatPrompt = text("chat_prompt"), conversationPrompt = text("memory_prompt"),
            paymentLink = o.string("payment_link"), paymentPlan = text("payment_plan"),
            isUserPaid = o.bool("is_user_paid") ?: false, isPrivate = o.bool("private") ?: false,
            isOwn = uid != null && o.string("uid") == uid,
        )
    }
}

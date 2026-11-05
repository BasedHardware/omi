package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.OmiApp
import com.friend.ios.core.models.SummaryTemplateDraft
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import java.text.Collator

/**
 * Port of `SummaryTemplatesStore.swift`: "Summary template" for one conversation (Flutter
 * `summarized_apps_sheet`): the apps Omi suggests, the user's summary apps (default and last used
 * first), summarizing again with one, setting the default, and writing a new template.
 */
class SummaryTemplatesStore(private val api: APIClientProtocol, private val preferences: Preferences?) {
    enum class Phase { Loading, Loaded }

    sealed interface Failure {
        data class Install(val name: String) : Failure
        data object SaveDefault : Failure
        data object Create : Failure
        data object Reprocess : Failure
    }

    enum class CreationStep { Describing, Creating, Installing }

    var phase by mutableStateOf(Phase.Loading)
        private set
    /** Suggested apps not already among the user's apps. */
    var suggested: List<OmiApp> by mutableStateOf(emptyList())
        private set
    /** The user's enabled summary apps: default, last used, then by name. */
    var apps: List<OmiApp> by mutableStateOf(emptyList())
        private set
    var defaultAppID: String? by mutableStateOf(preferences?.string(Preferences.Key.PreferredSummarizationAppId))
        private set
    var lastUsedAppID: String? by mutableStateOf(preferences?.string(Preferences.Key.LastUsedSummarizationAppId))
        private set
    /** The app being installed or summarizing with. */
    var working: String? by mutableStateOf(null)
        private set
    var creationStep: CreationStep? by mutableStateOf(null)
        private set
    var failure: Failure? by mutableStateOf(null)

    suspend fun load(conversationID: String) {
        val (suggestions, enabled) = coroutineScope {
            val suggestedApps = async { attempt { api.suggestedSummaryApps(conversationID) } }
            val enabledApps = async { attempt { api.summaryApps() } }
            (suggestedApps.await() ?: emptyList()) to (enabledApps.await() ?: emptyList())
        }
        val mine = enabled.map { it.id }.toSet()
        suggested = suggestions.filter { it.id !in mine }
        apps = order(enabled)
        phase = Phase.Loaded
    }

    /** Every known app by id (the detail page names the app that wrote the summary). */
    fun app(id: String?): OmiApp? {
        id ?: return null
        return apps.firstOrNull { it.id == id } ?: suggested.firstOrNull { it.id == id }
    }

    /** Summarizes the conversation again with [app], installing it first when it is a suggestion. */
    suspend fun summarize(detail: ConversationDetailStore, app: OmiApp, list: ConversationsStore): Boolean {
        if (working != null) return false
        working = app.id
        try {
            if (apps.none { it.id == app.id }) {
                try {
                    api.setApp(app.id, true)
                } catch (e: Exception) {
                    if (e is CancellationException) throw e
                    failure = Failure.Install(app.name)
                    return false
                }
                val installed = app.copy(isEnabled = true)
                suggested = suggested.filter { it.id != app.id }
                apps = order(apps + installed)
            }
            lastUsedAppID = app.id
            preferences?.set(Preferences.Key.LastUsedSummarizationAppId, app.id)
            if (!detail.reprocess(list, app.id)) {
                failure = Failure.Reprocess
                return false
            }
            return true
        } finally {
            working = null
        }
    }

    /** Future conversations are summarized with [app] (nothing is summarized again now). */
    suspend fun setDefault(app: OmiApp): Boolean {
        try {
            api.setPreferredSummaryApp(app.id)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            failure = Failure.SaveDefault
            return false
        }
        defaultAppID = app.id
        preferences?.set(Preferences.Key.PreferredSummarizationAppId, app.id)
        apps = order(apps)
        return true
    }

    /**
     * Writes a summary app from a name and prompt, installs it, and returns it (Flutter
     * `create_template_bottom_sheet`). [icon] draws the emoji Omi picked as a PNG.
     */
    suspend fun create(draft: SummaryTemplateDraft, icon: (String) -> ByteArray?): OmiApp? {
        if (draft.problem != null || creationStep != null) return null
        try {
            val name = draft.name.trim()
            creationStep = CreationStep.Describing
            val generated = attempt { api.generateAppDescription(name, draft.prompt) } ?: ("A custom app that ${draft.prompt}" to "✨")
            creationStep = CreationStep.Creating
            val png = icon(generated.second)
            val id = png?.let { attempt { api.createSummaryApp(draft, generated.first, it) } }
            if (id == null) {
                failure = Failure.Create
                return null
            }
            creationStep = CreationStep.Installing
            try {
                api.setApp(id, true)
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                failure = Failure.Install(name)
                return null
            }
            val app = OmiApp(
                id = id, name = name, description = generated.first, author = null, imageURL = null, category = "conversation-analysis",
                rating = null, installs = 0, isEnabled = true, capabilities = setOf("memories"),
            )
            apps = order(apps.filter { it.id != id } + app)
            return app
        } finally {
            creationStep = null
        }
    }

    /** Default first, then last used, then by name. */
    private fun order(list: List<OmiApp>): List<OmiApp> {
        fun rank(app: OmiApp): Int = when (app.id) {
            defaultAppID -> 0
            lastUsedAppID -> 1
            else -> 2
        }
        val collator = Collator.getInstance().apply { strength = Collator.SECONDARY }
        return list.sortedWith { lhs, rhs ->
            if (rank(lhs) != rank(rhs)) rank(lhs).compareTo(rank(rhs)) else collator.compare(lhs.name, rhs.name)
        }
    }

    private suspend fun <T> attempt(block: suspend () -> T): T? = try {
        block()
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        null
    }
}

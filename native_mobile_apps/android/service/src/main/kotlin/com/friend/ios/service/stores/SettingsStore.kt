package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.AssistantVoice
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.PhoneNumber
import com.friend.ios.core.models.SpokenLanguage
import com.friend.ios.core.models.Subscription
import com.friend.ios.core.models.UserProfile
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.PaymentsMapper
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import java.io.File

/**
 * Port of `SettingsStore.swift`: server-backed settings (Flutter `pages/settings/...`). Each area
 * loads on demand; changes apply immediately and roll back if the backend refuses them.
 */
class SettingsStore(
    internal val api: APIClientProtocol,
    internal val preferences: Preferences,
    /** Where short-lived stores made here run their background work (export). */
    internal val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
    /** The app's cache directory, for exports. */
    internal val cacheDirectory: File = File(System.getProperty("java.io.tmpdir") ?: "/tmp"),
) {
    var subscription: Subscription? by mutableStateOf(null)
        private set
    var dailySummaryEnabled: Boolean by mutableStateOf(true)
        private set
    var dailySummaryHour: Int by mutableIntStateOf(22)
        private set
    var notificationFrequency: Int by mutableIntStateOf(0)
        private set
    var storesRecordings: Boolean by mutableStateOf(false)
        private set
    var voices: List<AssistantVoice> by mutableStateOf(emptyList())
        private set
    var selectedVoice: String? by mutableStateOf(null)
        private set
    var vocabulary: List<String> by mutableStateOf(emptyList())
        private set
    var people: List<Person> by mutableStateOf(emptyList())
        internal set
    var phoneNumbers: List<PhoneNumber> by mutableStateOf(emptyList())
        private set
    var phoneUnavailableReason: String? by mutableStateOf(null)
        private set
    var lastError: String? by mutableStateOf(null)
        internal set

    // MARK: Account

    /**
     * The account as the backend knows it ([loadProfile]); its name wins over the one saved on
     * this phone (Flutter's prefs, the sign-in), which may be an old or a placeholder name.
     */
    var profile: UserProfile? by mutableStateOf(null)
        private set

    /** Bumped when this phone's saved name or email changes, so readers of [displayName] recompose. */
    private var localRevision by mutableIntStateOf(0)

    val displayName: String?
        get() {
            localRevision
            return profile?.name ?: preferences.displayName
        }

    val email: String?
        get() {
            localRevision
            return preferences.string(Key.Email) ?: profile?.email
        }

    suspend fun loadProfile() {
        runCatching { api.userProfile() }.getOrNull()?.let { profile = it }
    }

    /** Account > Name was saved: show it right away (the backend's copy follows on its own). */
    fun nameChanged(name: String) {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return
        profile = UserProfile(trimmed, profile?.email)
        localRevision++
    }

    suspend fun loadSubscription() {
        subscription = try {
            api.subscription()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            null
        }
    }

    suspend fun portalURL(): String? = runCatching { api.customerPortalURL() }.getOrNull()

    /** 0 off, 1 headphones only, 2 always (Flutter `voiceResponseMode`, kept on sign-out). */
    var voiceResponseMode: Int
        get() {
            localRevision
            return preferences.integer(Key.VoiceResponseMode, 1)
        }
        set(value) {
            preferences.set(Key.VoiceResponseMode, value)
            localRevision++
        }

    /**
     * `@AppStorage("flutter.appearanceMode")`: light, dark or system (dark by default). Snapshot
     * state so the app theme (`MainActivity`) and the Appearance row follow a change live.
     */
    private var appearance by mutableStateOf(preferences.string(Key.AppearanceMode) ?: "dark")

    var appearanceMode: String
        get() = appearance
        set(value) {
            appearance = value
            preferences.set(Key.AppearanceMode, value)
        }

    // MARK: Notifications

    suspend fun loadNotifications() {
        runCatching { api.dailySummary() }.getOrNull()?.let { (enabled, hour) ->
            dailySummaryEnabled = enabled
            dailySummaryHour = hour
        }
        runCatching { api.notificationFrequency() }.getOrNull()?.let { notificationFrequency = it }
    }

    suspend fun setDailySummary(enabled: Boolean, hour: Int) {
        val previous = dailySummaryEnabled to dailySummaryHour
        dailySummaryEnabled = enabled
        dailySummaryHour = hour
        attempt({ api.setDailySummary(enabled, hour) }) {
            dailySummaryEnabled = previous.first
            dailySummaryHour = previous.second
        }
    }

    suspend fun setNotificationFrequency(value: Int) {
        val previous = notificationFrequency
        notificationFrequency = value
        attempt({ api.setNotificationFrequency(value) }) { notificationFrequency = previous }
    }

    // MARK: Privacy

    suspend fun loadPrivacy() {
        runCatching { api.storesRecordings() }.getOrNull()?.let { storesRecordings = it }
    }

    suspend fun setStoresRecordings(value: Boolean) {
        storesRecordings = value
        attempt({ api.setStoresRecordings(value) }) { storesRecordings = !value }
    }

    // MARK: Assistant

    suspend fun loadVoices() {
        runCatching { api.assistantVoices() }.getOrNull()?.let { (list, selected) ->
            voices = list
            selectedVoice = selected
        }
    }

    suspend fun selectVoice(id: String) {
        val previous = selectedVoice
        selectedVoice = id
        attempt({ api.setAssistantVoice(id) }) { selectedVoice = previous }
    }

    // MARK: Spoken language

    var languages: List<SpokenLanguage> by mutableStateOf(emptyList())
        private set

    val spokenLanguage: String?
        get() {
            localRevision
            return preferences.string(Key.UserPrimaryLanguage)
        }

    suspend fun loadLanguages() {
        if (languages.isEmpty()) languages = runCatching { api.availableLanguages() }.getOrNull().orEmpty()
    }

    suspend fun setSpokenLanguage(code: String) {
        val previous = spokenLanguage
        preferences.set(Key.UserPrimaryLanguage, code)
        localRevision++
        attempt({ api.setPrimaryLanguage(code) }) {
            preferences.set(Key.UserPrimaryLanguage, previous)
            localRevision++
        }
    }

    // MARK: Vocabulary

    suspend fun loadVocabulary() {
        runCatching { api.vocabulary() }.getOrNull()?.let { vocabulary = it }
    }

    suspend fun addWord(word: String) {
        val trimmed = word.trim()
        if (trimmed.isEmpty() || trimmed in vocabulary) return
        val previous = vocabulary
        vocabulary = vocabulary + trimmed
        attempt({ api.setVocabulary(vocabulary) }) { vocabulary = previous }
    }

    suspend fun removeWords(offsets: Set<Int>) {
        val previous = vocabulary
        vocabulary = vocabulary.filterIndexed { index, _ -> index !in offsets }
        attempt({ api.setVocabulary(vocabulary) }) { vocabulary = previous }
    }

    // MARK: People

    suspend fun loadPeople() {
        runCatching { api.people() }.getOrNull()?.let { list -> people = list.sortedBy { it.name } }
    }

    suspend fun addPerson(name: String) {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return
        attempt({ api.addPerson(trimmed) }) {}
        loadPeople()
    }

    suspend fun renamePerson(id: String, name: String) {
        attempt({ api.renamePerson(id, name) }) {}
        loadPeople()
    }

    suspend fun deletePerson(id: String) {
        val previous = people
        people = people.filter { it.id != id }
        attempt({ api.deletePerson(id) }) { people = previous }
    }

    // MARK: Phone

    suspend fun loadPhoneNumbers() {
        try {
            phoneNumbers = api.phoneNumbers()
            phoneUnavailableReason = null
        } catch (e: CancellationException) {
            throw e
        } catch (e: APIError.Http) {
            // e.g. "Phone calls require a paid subscription"
            phoneUnavailableReason = if (e.status == 402 || e.status == 403) detail(e.body) ?: "HTTP ${e.status}" else e.toString()
        } catch (e: Exception) {
            phoneUnavailableReason = e.toString()
        }
    }

    // MARK: Helpers

    internal suspend fun attempt(operation: suspend () -> Unit, rollback: () -> Unit) {
        lastError = null
        try {
            operation()
        } catch (e: CancellationException) {
            rollback()
            throw e
        } catch (e: Exception) {
            rollback()
            lastError = e.toString()
        }
    }

    companion object {
        fun detail(body: String): String? = PaymentsMapper.refusal(APIError.Http(0, body))?.detail
    }
}

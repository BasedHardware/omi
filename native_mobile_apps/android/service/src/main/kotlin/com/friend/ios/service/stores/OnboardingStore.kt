package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.util.Locale

/** Port of `OnboardingStore.swift`: the first-run flow (Flutter `pages/onboarding/wrapper.dart`, reordered per PLAN.md 4.6). */
class OnboardingStore(
    private val api: APIClientProtocol,
    private val preferences: Preferences,
    private val scope: CoroutineScope,
    /** Hears the user on `hello` and `voice`. */
    val voice: VoiceIntroStore? = null,
    /** The Omi button lessons (`askOmi`, `doublePress`); without it those steps pass straight on. */
    val buttonTutorial: ButtonTutorialStore? = null,
    /** Spoken replies (`voiceReply`) and their preview. */
    val playback: VoicePlaybackStore? = null,
    /** The paired watch (`watch` step); null or unpaired leaves the step out. */
    val watch: com.friend.ios.service.watch.WatchStore? = null,
    private val watchPaired: () -> Boolean = { watch?.link?.isWatchPaired ?: false },
    private val updateDisplayName: suspend (String) -> Unit,
    /** The phone's language (`Locale.current`), a parameter so tests can pin it. */
    private val phoneLanguage: () -> String = { Locale.getDefault().language },
) {
    /**
     * With an Omi: pair it, learn its light, whisper to it, train the voice through it, then
     * learn its button (ask with one press, hear the answer, pick what a double press does).
     * Without one the phone microphone stands in and the Omi steps are left out.
     */
    enum class Step {
        Name, Language, FoundOmi, HasOmi, Pair, Lights, Hello, Voice, AskOmi, VoiceReply, DoublePress, Watch,
        /**
         * Connecting calendar, mail and task apps is left to Settings > Connections (it was a long
         * list of its own here).
         */
        Permissions, Setup,
        /** "You're ready", then a short introduction to the app. */
        Ready;

        val needsOmi: Boolean get() = this in setOf(Pair, Lights, AskOmi, VoiceReply, DoublePress)

        /** The iOS case name (`-omiOnboardingStep askOmi`). */
        val rawName: String get() = name.replaceFirstChar { it.lowercase() }

        companion object {
            fun from(raw: String): Step? = entries.firstOrNull { it.rawName == raw || it.name.equals(raw, ignoreCase = true) }
        }
    }

    data class Language(val name: String, val code: String)

    var step: Step by mutableStateOf(Step.Name)
    /** Answered on `hasOmi`; null until then. */
    var hasOmi: Boolean? by mutableStateOf(null)
    var givenName: String by mutableStateOf(preferences.displayName ?: "")

    /** Picked in order of importance; the first is the main language. */
    var spokenLanguages: List<String> by mutableStateOf(emptyList())
        private set
    private val fallbackLanguage: String = preferences.string(Key.UserPrimaryLanguage) ?: phoneLanguage().ifEmpty { "en" }
    var languages: List<Language> by mutableStateOf(emptyList())
        private set
    var errorMessage: String? by mutableStateOf(null)
        private set
    /** Spoken replies as picked on `voiceReply`; null until the step was shown. */
    var voiceReplyMode: VoicePlaybackStore.ReplyMode? by mutableStateOf(null)
        private set

    /** The main language: the first one picked. */
    val language: String get() = spokenLanguages.firstOrNull() ?: fallbackLanguage

    /** The steps this user walks through. */
    val path: List<Step>
        get() {
            val watchPaired = watchPaired()
            return Step.entries.filter { (!it.needsOmi || hasOmi == true) && (it != Step.Watch || watchPaired) }
        }

    val progress: Double
        get() {
            val path = path
            return (path.indexOf(step).coerceAtLeast(0) + 1).toDouble() / path.size
        }

    val voiceSource: VoiceIntroStore.Source
        get() = if (hasOmi == true) VoiceIntroStore.Source.Device else VoiceIntroStore.Source.Phone

    suspend fun loadLanguages() {
        if (languages.isEmpty()) languages = runCatching { api.availableLanguages() }.getOrNull().orEmpty().map { Language(it.name, it.code) }
    }

    fun next() {
        val path = path
        val index = path.indexOf(step)
        if (index >= 0 && index + 1 < path.size) step = path[index + 1]
    }

    fun back() {
        val path = path
        val index = path.indexOf(step)
        if (index > 0) step = path[index - 1]
    }

    fun chooseOmi(has: Boolean) {
        hasOmi = has
        next()
    }

    /** Gave up pairing: carry on with the phone microphone. */
    fun continueWithoutOmi() {
        hasOmi = false
        step = Step.Hello
    }

    /** Name: first word given, the rest family (like Flutter's name step). */
    suspend fun saveName() {
        val trimmed = givenName.trim()
        if (trimmed.isEmpty()) return
        val parts = trimmed.split(" ", limit = 2)
        preferences.set(Key.GivenName, parts[0])
        preferences.set(Key.FamilyName, parts.getOrNull(1))
        updateDisplayName(trimmed)
        next()
    }

    /**
     * Tapping picks a language (after the ones already picked: the order of the taps is the order
     * of importance) or takes it out again.
     */
    fun toggleLanguage(code: String) {
        spokenLanguages = if (code in spokenLanguages) spokenLanguages - code else spokenLanguages + code
    }

    /** 1 for the main language, 2, 3 ... in the order picked; null when not picked. */
    fun rank(code: String): Int? = spokenLanguages.indexOf(code).takeIf { it >= 0 }?.plus(1)

    /**
     * The picked languages with their names in the phone's language, in order. A code the catalog
     * does not list (an older saved choice) still shows: a pick never drops out of sight.
     */
    val pickedLanguages: List<Language>
        get() = spokenLanguages.map { code -> Language(displayName(code, languages.firstOrNull { it.code == code }?.name), code) }

    /**
     * The short list shown before searching: the phone's language and the most spoken ones, in
     * the catalog, six in all (they fit the screen with the search field).
     */
    val commonLanguages: List<Language>
        get() {
            val codes = (listOf(phoneLanguage()).filter { it.isNotEmpty() } + COMMON_CODES).distinct()
            // Shown right away: the server's catalog only confirms the codes once it has loaded.
            return codes.mapNotNull { code ->
                if (languages.isNotEmpty() && languages.none { it.code == code }) return@mapNotNull null
                Language(displayName(code, languages.firstOrNull { it.code == code }?.name), code)
            }.take(COMMON_COUNT)
        }

    /**
     * The list on the language step. Without a query: picks from outside the short list first
     * (so a searched pick stays visible), then the short list. With one: every catalog language
     * whose name (in the phone's language or English) or code matches.
     */
    fun languageRows(matching: String = ""): List<Language> {
        val needle = matching.trim().lowercase()
        if (needle.isEmpty()) {
            val common = commonLanguages
            return pickedLanguages.filter { picked -> common.none { it.code == picked.code } } + common
        }
        return languages.mapNotNull { language ->
            val name = displayName(language.code, language.name)
            val matches = name.lowercase().contains(needle) || language.name.lowercase().contains(needle) ||
                language.code.lowercase().startsWith(needle)
            if (matches) Language(name, language.code) else null
        }
    }

    /**
     * `PATCH v1/users/language` with the main language; the server also tunes transcription for
     * it. The full list stays on the phone and decides whether capture mixes languages.
     */
    suspend fun saveLanguage() {
        errorMessage = null
        if (spokenLanguages.isEmpty()) return
        try {
            api.setPrimaryLanguage(language)
            preferences.set(Key.UserPrimaryLanguage, language)
            preferences.set(NativeKey.SpokenLanguages, spokenLanguages)
            preferences.set(Key.HasSetPrimaryLanguage, true)
            next()
        } catch (e: Exception) {
            errorMessage = e.message ?: e.toString()
        }
    }

    /**
     * The first run starts spoken replies at Off until the user picks one (Flutter
     * `initializeVoiceResponseMode`); a replay from Settings shows the saved choice.
     */
    fun showVoiceReply() {
        if (voiceReplyMode != null) return
        if (preferences.bool(Key.OnboardingCompleted)) {
            voiceReplyMode = VoicePlaybackStore.ReplyMode.from(preferences.integer(Key.VoiceResponseMode, 1))
                ?: VoicePlaybackStore.ReplyMode.HeadphonesOnly
        } else {
            chooseVoiceReply(VoicePlaybackStore.ReplyMode.Off)
        }
    }

    /** The same setting as Settings > Assistant > Spoken replies. */
    fun chooseVoiceReply(mode: VoicePlaybackStore.ReplyMode) {
        voiceReplyMode = mode
        preferences.set(Key.VoiceResponseMode, mode.rawValue)
    }

    /** Fire-and-forget like Flutter; skipping sends nothing. */
    fun saveSource(source: String?) {
        if (source != null) {
            preferences.set(Key.FoundOmiSource, source)
            scope.launch { runCatching { api.updateOnboarding(completed = null, acquisitionSource = source) } }
        }
        next()
    }

    companion object {
        /** The most spoken languages, the phone's own first; base codes only ("en", not "en-GB"). */
        val COMMON_CODES = listOf("en", "es", "de", "fr", "pt", "it", "hi", "zh")
        const val COMMON_COUNT = 6

        /**
         * "Deutsch", "Englisch (Vereinigte Staaten)" on a German phone; the catalog's English name
         * when the phone does not know the code.
         */
        fun displayName(code: String, catalogName: String?): String {
            val locale = Locale.forLanguageTag(code.replace('_', '-'))
            val name = locale.getDisplayName(Locale.getDefault())
            if (name.isEmpty() || name.equals(code, ignoreCase = true) || locale.language.isEmpty()) return catalogName ?: code
            return name.replaceFirstChar { it.uppercase() }
        }
    }
}

package com.friend.ios.persistence

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

/**
 * Port of `Preferences.swift`: typed user preferences under the Flutter app's own keys (ADR 0002
 * of omi-native). On Android, Flutter's `shared_preferences` writes the `FlutterSharedPreferences`
 * file with a `flutter.` prefix, ints as Long and string lists behind a marker prefix. Reading and
 * writing the same file and encodings means an update from the Flutter build keeps every setting
 * with no copy step (and a rollback to Flutter still reads ours). Key names come from
 * `app/lib/backend/preferences.dart`.
 */
class Preferences(private val prefs: SharedPreferences) {
    constructor(context: Context) : this(context.getSharedPreferences(FILE, Context.MODE_PRIVATE))

    enum class Key(val rawValue: String) {
        Uid("uid"),
        Email("email"),
        GivenName("givenName"),
        FamilyName("familyName"),
        OnboardingCompleted("onboardingCompleted"),
        PermissionsCompleted("permissionsCompleted"),
        UserPrimaryLanguage("userPrimaryLanguage"),
        AppLocale("app_locale"),
        AppearanceMode("appearanceMode"),
        HasSpeakerProfile("hasSpeakerProfile"),
        BtDevice("btDevice"),
        DeviceName("deviceName"),
        AiConsentGiven("aiConsentGiven"),
        HasSetPrimaryLanguage("hasSetPrimaryLanguage"),
        FoundOmiSource("foundOmiSource"),
        /** 0 off, 1 headphones only (default), 2 always. */
        VoiceResponseMode("voiceResponseMode"),
        /** What a double tap on the Omi does: 0 end the conversation (default), 1 mute/unmute, 2 star. */
        DoubleTapAction("doubleTapAction"),
        OmiButtonActionsEnabled("omiButtonActionsEnabled"),
        /** Seconds of silence that end a conversation; -1 is four hours. */
        ConversationSilenceDuration("conversationSilenceDuration"),
        BatchModeEnabled("batchModeEnabled"),
        VadGateEnabled("vadGateEnabled"),
        TranscriptionModel("transcriptionModel3"),
        DevModeEnabled("devModeEnabled"),
        DevLogsToFileEnabled("devLogsToFileEnabled"),
        CachedSingleLanguageMode("cachedSingleLanguageMode"),
        ShowDiscardedMemories("showDiscardedMemories"),
        ShowShortConversations("showShortConversations"),
        ShortConversationThreshold("v2/shortConversationThreshold"),
        PreferredSummarizationAppId("preferredSummarizationAppId"),
        LastUsedSummarizationAppId("lastUsedSummarizationAppId"),
        CustomSttConfig("customSttConfig"),
        UnlimitedLocalStorageEnabled("unlimitedLocalStorageEnabled"),
        TranscriptionAllowanceLastKnown("transcriptionAllowanceLastKnown"),
        /** Hash of this install (Flutter `ClientDeviceService`), as in `android_<hash>`. */
        DeviceIdHash("deviceIdHash"),
        /** The app version that ran last (`X.Y.Z+build`); what's new shows after an update. */
        LastKnownAppVersion("lastKnownAppVersion"),
    }

    /** Native-only values, never under the `flutter.` prefix (ADR 0002). */
    enum class NativeKey(val rawValue: String) {
        MainChatSessionID("omi.chat.mainSessionID"),
        AgentChatSessionIDs("omi.agent.chatSessionIDs"),
        OpenedAgentRuns("omi.agent.openedRuns"),
        OnDeviceTranscription("omi.capture.onDeviceTranscription"),
        SpokenLanguages("omi.capture.spokenLanguages"),
        LowBatteryAlerted("omi.device.lowBatteryAlerted"),
        FirmwareCheck("omi.device.firmwareCheck"),
        DeviceDiagnostics("omi.device.diagnostics"),
        DeviceMuted("omi.capture.deviceMuted"),
        DeveloperMode("omi.developer.mode"),
        SelectedChatAppID("omi.chat.selectedAppID"),
        TaskAppSelections("omi.tasks.appSelections"),
        CaptureActiveSince("omi.capture.activeSince"),
        CaptureOpenConversation("omi.capture.openConversation"),
        HealthLastSync("omi.health.lastSync"),
        FeedbackPromptLastShown("omi.feedback.promptLastShown"),
        FeedbackPromptDone("omi.feedback.promptDone"),
        HiddenChatMessages("omi.chat.hiddenMessages"),
    }

    fun string(key: Key): String? = (prefs.all[PREFIX + key.rawValue] as? String)?.takeIf { it.isNotEmpty() }

    fun bool(key: Key, default: Boolean = false): Boolean = prefs.all[PREFIX + key.rawValue] as? Boolean ?: default

    /** Flutter stores Dart ints as Long. */
    fun integer(key: Key, default: Int): Int = (prefs.all[PREFIX + key.rawValue] as? Number)?.toInt() ?: default

    fun set(key: Key, value: String?) = prefs.edit { if (value == null) remove(PREFIX + key.rawValue) else putString(PREFIX + key.rawValue, value) }

    fun set(key: Key, value: Boolean) = prefs.edit { putBoolean(PREFIX + key.rawValue, value) }

    fun set(key: Key, value: Int) = prefs.edit { putLong(PREFIX + key.rawValue, value.toLong()) }

    fun string(key: NativeKey): String? = prefs.getString(key.rawValue, null)

    fun set(key: NativeKey, value: String?) = prefs.edit { if (value == null) remove(key.rawValue) else putString(key.rawValue, value) }

    fun bool(key: NativeKey, default: Boolean): Boolean = prefs.all[key.rawValue] as? Boolean ?: default

    fun set(key: NativeKey, value: Boolean) = prefs.edit { putBoolean(key.rawValue, value) }

    fun strings(key: NativeKey): List<String> = decodeList(prefs.getString(key.rawValue, null))

    fun set(key: NativeKey, values: List<String>) = prefs.edit { putString(key.rawValue, encodeList(values)) }

    fun append(value: String, key: NativeKey) = set(key, (strings(key) + value).takeLast(200))

    /** True when a Flutter build ran on this install before (any `flutter.` key exists). */
    val hasLegacyFlutterState: Boolean get() = prefs.all.keys.any { it.startsWith(PREFIX) }

    val displayName: String?
        get() = listOfNotNull(string(Key.GivenName), string(Key.FamilyName)).joinToString(" ").ifEmpty { null }

    val deviceIdHash: String? get() = string(Key.DeviceIdHash)

    /** Sign-out: clears every `flutter.` key except [keptOnSignOut], plus native account state. */
    fun clearUser() = prefs.edit {
        prefs.all.keys.filter { it.startsWith(PREFIX) && it.removePrefix(PREFIX) !in keptOnSignOut }.forEach { remove(it) }
        listOf(
            NativeKey.MainChatSessionID, NativeKey.AgentChatSessionIDs, NativeKey.SelectedChatAppID, NativeKey.TaskAppSelections,
            NativeKey.CaptureActiveSince, NativeKey.CaptureOpenConversation, NativeKey.HealthLastSync, NativeKey.OpenedAgentRuns,
        ).forEach { remove(it.rawValue) }
    }

    companion object {
        const val FILE = "FlutterSharedPreferences"
        const val PREFIX = "flutter."

        /** `LegacySharedPreferencesPlugin`'s marker for a JSON-encoded List<String>. */
        const val LIST_PREFIX = "VGhpcyBpcyB0aGUgcHJlZml4IGZvciBhIGxpc3Qu!"

        /** Survive sign-out, exactly the Flutter app's `kPreferencesKeptOnSignOut`. */
        val keptOnSignOut = setOf(
            "btDevice", "btDevices", "deviceName", "deviceIsV2", "deviceSupportsMultiFileSync",
            "deviceOnboardingCompleted", "lastKnownFirmwareVersion", "doubleTapAction", "omiButtonActionsEnabled",
            "companionAssociationPrompted", "autoSyncOfflineRecordings", "appearanceDefaultMigration", "appearanceMode",
            "showShortConversations", "showDiscardedMemories", "voiceResponseMode", "devLogsToFileEnabled",
            "lastKnownAppVersion", "lastAnnouncementCheckTime",
        )

        internal fun encodeList(values: List<String>): String =
            LIST_PREFIX + kotlinx.serialization.json.JsonArray(values.map { kotlinx.serialization.json.JsonPrimitive(it) }).toString()

        internal fun decodeList(raw: String?): List<String> {
            if (raw == null || !raw.startsWith(LIST_PREFIX)) return emptyList()
            return runCatching {
                kotlinx.serialization.json.Json.parseToJsonElement(raw.removePrefix(LIST_PREFIX))
                    .let { it as kotlinx.serialization.json.JsonArray }
                    .map { (it as kotlinx.serialization.json.JsonPrimitive).content }
            }.getOrDefault(emptyList())
        }
    }
}

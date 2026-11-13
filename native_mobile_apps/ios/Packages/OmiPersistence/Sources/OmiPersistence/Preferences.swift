import Foundation

/// Typed user preferences, stored under the Flutter app's own keys (ADR 0002).
///
/// Flutter's `shared_preferences` writes `UserDefaults.standard` with a `flutter.` prefix. Reading
/// and writing the same keys means a user updating from the Flutter build keeps every setting with
/// no copy step, and the key names stay identical to the Android (Flutter) app.
/// Key names come from `app/lib/backend/preferences.dart`.
public final class Preferences: @unchecked Sendable {
    public enum Key: String, CaseIterable, Sendable {
        case uid
        case email
        case givenName
        case familyName
        case onboardingCompleted
        case permissionsCompleted
        case userPrimaryLanguage
        case appLocale = "app_locale"
        case appearanceMode
        case hasSpeakerProfile
        case btDevice
        case deviceName
        case aiConsentGiven
        case hasSetPrimaryLanguage
        case foundOmiSource
        /// 0 off, 1 headphones only (default), 2 always.
        case voiceResponseMode
        /// What a double tap on the Omi does: 0 end the conversation (default), 1 mute/unmute, 2 star.
        case doubleTapAction
        /// Single press asks Omi, double tap runs `doubleTapAction`; on by default.
        case omiButtonActionsEnabled
        /// Seconds of silence that end a conversation (`conversation_timeout`); -1 is four hours.
        case conversationSilenceDuration
        /// Transcribe later: the phone records to a file, uploaded when the user asks.
        case batchModeEnabled
        /// `vad_gate=enabled` on `/v4/listen` (developer setting).
        case vadGateEnabled
        /// The server's speech model; `parakeet` is sent as `stt_service`, anything else lets the backend choose.
        case transcriptionModel = "transcriptionModel3"
        /// Conversation developer tools (copy ID); Flutter's "devModeEnabled".
        case devModeEnabled
        /// Debug log written to a file (kept on sign-out).
        case devLogsToFileEnabled
        /// The backend's `single_language_mode` as last seen (off: languages are detected).
        case cachedSingleLanguageMode
        /// Home lists discarded conversations too (Flutter's name kept).
        case showDiscardedMemories
        /// Home lists conversations shorter than `shortConversationThreshold` (seconds; 0 hides none).
        case showShortConversations
        case shortConversationThreshold = "v2/shortConversationThreshold"
        /// The summary app set as default, and the one picked last (the backend has no getter).
        case preferredSummarizationAppId
        case lastUsedSummarizationAppId
        /// Custom STT provider (JSON, Flutter `CustomSttConfig.toJson`). Native writes it without
        /// the key, which lives in the Keychain (`CustomSTTSettings`).
        case customSttConfig
        /// Store audio on phone: every recording also stays on the phone (Settings › Privacy).
        case unlimitedLocalStorageEnabled
        /// The backend's last `transcription_allowance` (JSON `{"mode": …}`, Flutter's cache key).
        case transcriptionAllowanceLastKnown
    }

    public func bool(_ key: Key, default fallback: Bool) -> Bool {
        defaults.object(forKey: Self.prefix + key.rawValue) as? Bool ?? fallback
    }

    public func integer(_ key: Key, default fallback: Int) -> Int {
        defaults.object(forKey: Self.prefix + key.rawValue) as? Int ?? fallback
    }

    public func set(_ value: Int, for key: Key) {
        defaults.set(value, forKey: Self.prefix + key.rawValue)
    }

    /// Survive sign-out, exactly the Flutter app's `kPreferencesKeptOnSignOut`
    /// (`app/lib/pages/settings/sign_out.dart`): device pairing, device behaviour, display.
    static let keptOnSignOut: Set<String> = [
        "btDevice", "btDevices", "deviceName", "deviceIsV2", "deviceSupportsMultiFileSync",
        "deviceOnboardingCompleted", "lastKnownFirmwareVersion", "doubleTapAction", "omiButtonActionsEnabled",
        "companionAssociationPrompted", "autoSyncOfflineRecordings", "appearanceDefaultMigration", "appearanceMode",
        "showShortConversations", "showDiscardedMemories", "voiceResponseMode", "devLogsToFileEnabled",
        "lastKnownAppVersion", "lastAnnouncementCheckTime",
    ]

    static let prefix = "flutter."
    private let defaults: UserDefaults

    /// `UserDefaults` is thread-safe; this type only wraps it.
    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    public func string(_ key: Key) -> String? {
        defaults.string(forKey: Self.prefix + key.rawValue).flatMap { $0.isEmpty ? nil : $0 }
    }

    public func bool(_ key: Key) -> Bool {
        defaults.bool(forKey: Self.prefix + key.rawValue)
    }

    public func set(_ value: String?, for key: Key) {
        if let value {
            defaults.set(value, forKey: Self.prefix + key.rawValue)
        } else {
            defaults.removeObject(forKey: Self.prefix + key.rawValue)
        }
    }

    public func set(_ value: Bool, for key: Key) {
        defaults.set(value, forKey: Self.prefix + key.rawValue)
    }

    /// Native-only values, never under the `flutter.` prefix (ADR 0002).
    public enum NativeKey: String, Sendable {
        case mainChatSessionID = "omi.chat.mainSessionID"
        case agentChatSessionIDs = "omi.agent.chatSessionIDs"
        /// Tasks whose finished agent run the user has opened (Home stops pointing at them).
        case openedAgentRuns = "omi.agent.openedRuns"
        case onDeviceTranscription = "omi.capture.onDeviceTranscription"
        /// The languages the user speaks, main first (the backend keeps only the main one).
        case spokenLanguages = "omi.capture.spokenLanguages"
        /// The low-battery notification went out and waits for a charge to re-arm.
        case lowBatteryAlerted = "omi.device.lowBatteryAlerted"
        /// The last firmware check (JSON `FirmwareStore.Check`), at most one a day.
        case firmwareCheck = "omi.device.firmwareCheck"
        /// The Omi's link history for My Devices › Diagnostics (JSON `DeviceDiagnosticsLog`), 7 days.
        case deviceDiagnostics = "omi.device.diagnostics"
        /// The Omi's audio is muted (kept across launches, like the Flutter capture policy).
        case deviceMuted = "omi.capture.deviceMuted"
        /// Settings › Developer is shown (switched on in Help & Feedback).
        case developerMode = "omi.developer.mode"
        /// The chat app the chat talks to; none is Omi itself.
        case selectedChatAppID = "omi.chat.selectedAppID"
        /// Where each task app files new tasks (JSON): the backend does not return the choice.
        case taskAppSelections = "omi.tasks.appSelections"
        /// Epoch seconds a capture started; still set at launch means it ended unexpectedly.
        case captureActiveSince = "omi.capture.activeSince"
        /// The conversation the live socket records into; still set at the next capture start means
        /// it was left open (app closed, Omi or socket gone) and is finalized first.
        case captureOpenConversation = "omi.capture.openConversation"
        /// The last Apple Health sync (seconds since 1970), shown in Settings › Apple Health.
        case healthLastSync = "omi.health.lastSync"
        /// When "Was this helpful?" last showed (seconds since 1970), and conversations already answered.
        case feedbackPromptLastShown = "omi.feedback.promptLastShown"
        case feedbackPromptDone = "omi.feedback.promptDone"
        /// Chat messages deleted on this iPhone (the backend keeps them; the thread hides them).
        case hiddenChatMessages = "omi.chat.hiddenMessages"
    }

    public func string(_ key: NativeKey) -> String? {
        defaults.string(forKey: key.rawValue)
    }

    public func set(_ value: String?, for key: NativeKey) {
        defaults.set(value, forKey: key.rawValue)
    }

    public func bool(_ key: NativeKey, default fallback: Bool) -> Bool {
        defaults.object(forKey: key.rawValue) as? Bool ?? fallback
    }

    public func set(_ value: Bool, for key: NativeKey) {
        defaults.set(value, forKey: key.rawValue)
    }

    public func strings(_ key: NativeKey) -> [String] {
        defaults.stringArray(forKey: key.rawValue) ?? []
    }

    public func set(_ values: [String], for key: NativeKey) {
        defaults.set(values, forKey: key.rawValue)
    }

    public func append(_ value: String, to key: NativeKey) {
        defaults.set(Array((strings(key) + [value]).suffix(200)), forKey: key.rawValue)
    }

    /// True when a Flutter build ran on this install before (any `flutter.` key exists).
    public var hasLegacyFlutterState: Bool {
        defaults.dictionaryRepresentation().keys.contains { $0.hasPrefix(Self.prefix) }
    }

    /// Convenience accessors used across the app.
    public var displayName: String? {
        let given = string(.givenName)
        let family = string(.familyName)
        let joined = [given, family].compactMap(\.self).joined(separator: " ")
        return joined.isEmpty ? nil : joined
    }

    /// Sign-out: clears every `flutter.` key except `keptOnSignOut`, plus native account state.
    public func clearUser() {
        for key in defaults.dictionaryRepresentation().keys where key.hasPrefix(Self.prefix) {
            if !Self.keptOnSignOut.contains(String(key.dropFirst(Self.prefix.count))) {
                defaults.removeObject(forKey: key)
            }
        }
        defaults.removeObject(forKey: NativeKey.mainChatSessionID.rawValue)
        defaults.removeObject(forKey: NativeKey.agentChatSessionIDs.rawValue)
        for key in [NativeKey.selectedChatAppID, .taskAppSelections, .captureActiveSince, .captureOpenConversation, .healthLastSync] {
            defaults.removeObject(forKey: key.rawValue)
        }
        defaults.removeObject(forKey: NativeKey.openedAgentRuns.rawValue)
    }
}

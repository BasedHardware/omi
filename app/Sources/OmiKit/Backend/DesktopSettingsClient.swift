import Foundation

// Port of `react-native/src/desktopSettingsClient.ts` — the 17 desktop
// preference keys, the typed preference snapshot, and the tolerant parsers.
// The native defaults store is reached through the `SettingsStoring` facade
// in Services.swift; this file owns keys, defaults, and value parsing.

public let SOFTWARE_PLANE_DEFAULTS_KEY = "omi.backend.softwarePlane"

/// Every JS preference key, with its native defaults mapping. Keep in sync
/// with the `OmiDesktopDefaultsKey` whitelist (17 entries).
public enum desktopPreferenceKeys {
    public static let softwarePlane = SOFTWARE_PLANE_DEFAULTS_KEY
    public static let screenCapture = "screenAnalysisEnabled"
    public static let audioMode = "audioRecordingMode"
    public static let interfaceSounds = "omi.sound.effectsEnabled"
    public static let fontScale = "fontScale"
    public static let notificationsEnabled = "notifications_enabled"
    public static let rewindRetentionDays = "rewindRetentionDays"
    public static let meetingNoteScreenshots = "meetingNoteScreenshotsEnabled"
    public static let floatingBar = "askOmiBarEnabled"
    public static let transcriptionAutoDetect = "transcriptionAutoDetect"
    public static let vadGate = "vadGateEnabled"
    public static let openOmiShortcut = "shortcut_askOmiEnabled"
    public static let pushToTalk = "shortcut_pttEnabled"
    public static let liveVoiceProvider = "omi.live.voiceProvider"
    public static let appearance = "omi.appearance"
    public static let uiVersion = "omi.uiVersion"
    public static let exploreProgress = "omi.onboarding.exploreProgress"

    /// Onboarding-completed marker — a native-only key outside the 17-entry
    /// JS whitelist (`omi.onboarding.setupRevision == "1"`), mirroring the
    /// upstream `OmiAuthModule` / `omiNative.web` storage. `exploreProgress`
    /// stays a pure CSV of check ids.
    public static let onboardingSetupRevision = "omi.onboarding.setupRevision"

    public static let all: [String] = [
        softwarePlane, screenCapture, audioMode, interfaceSounds, fontScale,
        notificationsEnabled, rewindRetentionDays, meetingNoteScreenshots,
        floatingBar, transcriptionAutoDetect, vadGate, openOmiShortcut,
        pushToTalk, liveVoiceProvider, appearance, uiVersion, exploreProgress,
    ]

    /// JS record names for the snapshot record, in `all` order. The native
    /// defaults store translates its keys to these names when composing the
    /// record (`OmiDesktopCommandsModule.mm` upstream).
    public static let recordNames: [String] = [
        "softwarePlane", "screenCapture", "audioMode", "interfaceSounds",
        "fontScale", "notificationsEnabled", "rewindRetentionDays",
        "meetingNoteScreenshots", "floatingBar", "transcriptionAutoDetect",
        "vadGate", "openOmiShortcut", "pushToTalk", "liveVoiceProvider",
        "appearance", "uiVersion", "exploreProgress",
    ]
}

public enum AudioRecordingMode: String, Sendable, Equatable {
    case off
    case always
    case meetings
}

public enum DesktopAppearance: String, Sendable, Equatable {
    case dark
    case light
}

/// Major interface revisions: v5 (pages IA) and v5.1 (Activity IA).
public enum DesktopUiVersion: String, Sendable, Equatable {
    case v5 = "v5"
    case v51 = "v5.1"
}

public enum LiveVoiceProvider: String, Sendable, Equatable {
    case gptLive = "gpt_live"
    case geminiLive = "gemini_live"
}

public enum PermissionKind: String, Sendable, Equatable {
    case screen
    case microphone
    case notifications
}

public enum PermissionState: String, Sendable, Equatable {
    case unknown
    case granted
    case denied
}

public struct DesktopPreferences: Sendable, Equatable {
    public var softwarePlane: SoftwarePlane
    public var screenCapture: Bool
    public var audioMode: AudioRecordingMode
    public var interfaceSounds: Bool
    public var fontScale: Int
    public var notificationsEnabled: Bool
    public var rewindRetentionDays: Int
    public var meetingNoteScreenshots: Bool
    public var floatingBar: Bool
    public var transcriptionAutoDetect: Bool
    public var vadGate: Bool
    public var openOmiShortcut: Bool
    public var pushToTalk: Bool
    public var liveVoiceProvider: LiveVoiceProvider
    public var appearance: DesktopAppearance
    public var uiVersion: DesktopUiVersion
    public var exploreProgress: String
    public var stampedV5Origin: String?
    /// `omi.onboarding.setupRevision == "1"` — onboarding completed.
    public var onboardingSetupCompleted: Bool

    public init(
        softwarePlane: SoftwarePlane = .old, screenCapture: Bool = false,
        audioMode: AudioRecordingMode = .off, interfaceSounds: Bool = true,
        fontScale: Int = 100, notificationsEnabled: Bool = false,
        rewindRetentionDays: Int = 14, meetingNoteScreenshots: Bool = true,
        floatingBar: Bool = true, transcriptionAutoDetect: Bool = true,
        vadGate: Bool = true, openOmiShortcut: Bool = true,
        pushToTalk: Bool = true, liveVoiceProvider: LiveVoiceProvider = .gptLive,
        appearance: DesktopAppearance = .dark, uiVersion: DesktopUiVersion = .v51,
        exploreProgress: String = "", stampedV5Origin: String? = nil,
        onboardingSetupCompleted: Bool = false
    ) {
        self.softwarePlane = softwarePlane
        self.screenCapture = screenCapture
        self.audioMode = audioMode
        self.interfaceSounds = interfaceSounds
        self.fontScale = fontScale
        self.notificationsEnabled = notificationsEnabled
        self.rewindRetentionDays = rewindRetentionDays
        self.meetingNoteScreenshots = meetingNoteScreenshots
        self.floatingBar = floatingBar
        self.transcriptionAutoDetect = transcriptionAutoDetect
        self.vadGate = vadGate
        self.openOmiShortcut = openOmiShortcut
        self.pushToTalk = pushToTalk
        self.liveVoiceProvider = liveVoiceProvider
        self.appearance = appearance
        self.uiVersion = uiVersion
        self.exploreProgress = exploreProgress
        self.stampedV5Origin = stampedV5Origin
        self.onboardingSetupCompleted = onboardingSetupCompleted
    }
}

public func parseSoftwarePlane(_ value: JSONValue?) -> SoftwarePlane {
    value?.stringValue == "new" ? .new : .old
}

public func parseAudioRecordingMode(_ value: JSONValue?) -> AudioRecordingMode {
    let text = value?.stringValue
    if text == "always" { return .always }
    if text == "meetings" { return .meetings }
    return .off
}

public func parseDesktopAppearance(_ value: JSONValue?) -> DesktopAppearance {
    value?.stringValue == "light" ? .light : .dark
}

public func parseDesktopUiVersion(_ value: JSONValue?) -> DesktopUiVersion {
    value?.stringValue == "v5" ? .v5 : .v51
}

public func parseLiveVoiceProvider(_ value: JSONValue?) -> LiveVoiceProvider {
    value?.stringValue == "gemini_live" ? .geminiLive : .gptLive
}

public func parseStampedV5Origin(_ value: JSONValue?) -> String? {
    guard let text = value?.stringValue, !text.isEmpty else { return nil }
    return parseOrigin(text)?.origin
}

public func defaultDesktopPreferences() -> DesktopPreferences {
    DesktopPreferences()
}

/// Port of `snapshotFromRecord` — tolerant record → typed snapshot.
public func snapshotFromRecord(_ record: JSONValue) -> DesktopPreferences {
    let stampedV5Origin = parseStampedV5Origin(record["stampedV5Origin"])
    let planeValue =
        record["softwarePlane"] != nil
        ? record["softwarePlane"]
        : (record["plane"] != nil
            ? record["plane"]
            : JSONValue.string(stampedV5Origin == nil ? "old" : "new"))
    let fontScaleRaw = record["fontScale"]?.numberValue
    let retentionRaw = record["rewindRetentionDays"]?.numberValue
    return DesktopPreferences(
        softwarePlane: parseSoftwarePlane(planeValue),
        screenCapture: record["screenCapture"]?.boolValue == true,
        audioMode: parseAudioRecordingMode(record["audioMode"]),
        interfaceSounds: record["interfaceSounds"]?.boolValue != false,
        fontScale:
            fontScaleRaw != nil && fontScaleRaw! >= 50
            ? Int(min(fontScaleRaw!, 200)) : 100,
        notificationsEnabled: record["notificationsEnabled"]?.boolValue == true,
        rewindRetentionDays: retentionRaw != nil ? Int(retentionRaw!) : 14,
        meetingNoteScreenshots: record["meetingNoteScreenshots"]?.boolValue != false,
        floatingBar: record["floatingBar"]?.boolValue != false,
        transcriptionAutoDetect: record["transcriptionAutoDetect"]?.boolValue != false,
        vadGate: record["vadGate"]?.boolValue != false,
        openOmiShortcut: record["openOmiShortcut"]?.boolValue != false,
        pushToTalk: record["pushToTalk"]?.boolValue != false,
        liveVoiceProvider: parseLiveVoiceProvider(record["liveVoiceProvider"]),
        appearance: parseDesktopAppearance(record["appearance"]),
        uiVersion: parseDesktopUiVersion(record["uiVersion"]),
        exploreProgress: record["exploreProgress"]?.stringValue ?? "",
        stampedV5Origin: stampedV5Origin,
        onboardingSetupCompleted:
            record["onboardingSetupRevision"]?.stringValue == "1"
    )
}

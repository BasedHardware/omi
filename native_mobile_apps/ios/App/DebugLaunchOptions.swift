import Foundation
import OmiService

/// CLI-driven QA without tapping the simulator (Debug builds only; compiled out of Release).
/// Example: `xcrun simctl launch <sim> <bundle> -omiAutoSignIn local-dev-user -omiSkipOnboarding YES -omiTab conversations`
struct DebugLaunchOptions {
    var autoSignInUserID: String?
    var initialTab: String?
    var showsSettings = false
    var showsAgent = false
    var skipsOnboarding = false
    var openConversationID: String?
    var resetsSession = false
    var handOverTaskID: String?
    var chatMessage: String?
    var showsDevice = false
    var startsPhoneCapture = false
    var captureSeconds: Int?
    var captureAudioFile: URL?
    var captureTranscript: String?
    /// `-omiAskAudioFile <wav>`: a question "said into the Omi" when the press-once lesson (or,
    /// with `-omiAskNow YES`, Home) is up: a press, the file as the Omi's audio, a press if needed.
    var askAudioFile: URL?
    /// `-omiAskTranscript "…"`: scripted words for that question where Apple speech cannot run.
    var askTranscript: String?
    var asksNow = false
    var givesConsent = false
    var onboardingStep: String?
    /// With -omiOnboardingStep past the Omi question: walk the Omi path (YES) or the iPhone one.
    var onboardingHasOmi: Bool?
    /// `-omiWatchPaired YES|NO`: onboarding behaves as if an Apple Watch is (not) paired.
    var watchPaired: Bool?
    var settingsTopic: String?
    /// `-omiDeepLink "omi://conversation/demo-1"` opens the link through `DeepLinkRouter`.
    var deepLink: String?
    /// `-omiFakeDevice nearby|connected`: a pretend Omi instead of Bluetooth (DebugDeviceDriver).
    var fakeDevice: String?
    /// `-omiShowRecordWith YES`, `-omiShowSiriTip YES`, `-omiShowNewTask YES`: open that sheet.
    var showsRecordWith = false
    var showsSiriTip = false
    var showsNewTask = false

    static let current: DebugLaunchOptions = {
        #if DEBUG
            let defaults = UserDefaults.standard
            return DebugLaunchOptions(
                autoSignInUserID: defaults.string(forKey: "omiAutoSignIn"),
                initialTab: defaults.string(forKey: "omiTab"),
                showsSettings: defaults.bool(forKey: "omiShowSettings") || defaults.string(forKey: "omiSettingsTopic") != nil,
                showsAgent: defaults.bool(forKey: "omiShowAgent"),
                skipsOnboarding: defaults.bool(forKey: "omiSkipOnboarding"),
                openConversationID: defaults.string(forKey: "omiOpenConversation"),
                resetsSession: defaults.bool(forKey: "omiResetSession"),
                handOverTaskID: defaults.string(forKey: "omiHandOver"),
                chatMessage: defaults.string(forKey: "omiChat"),
                showsDevice: defaults.bool(forKey: "omiShowDevice"),
                startsPhoneCapture: defaults.bool(forKey: "omiStartCapture"),
                // Launch arguments arrive as strings; integer(forKey:) parses them.
                captureSeconds: defaults.integer(forKey: "omiCaptureSeconds") > 0 ? defaults.integer(forKey: "omiCaptureSeconds") : nil,
                captureAudioFile: defaults.string(forKey: "omiCaptureAudioFile").map { URL(fileURLWithPath: $0) },
                captureTranscript: defaults.string(forKey: "omiCaptureTranscript"),
                askAudioFile: defaults.string(forKey: "omiAskAudioFile").map { URL(fileURLWithPath: $0) },
                askTranscript: defaults.string(forKey: "omiAskTranscript"),
                asksNow: defaults.bool(forKey: "omiAskNow"),
                givesConsent: defaults.bool(forKey: "omiGiveConsent"),
                onboardingStep: defaults.string(forKey: "omiOnboardingStep"),
                onboardingHasOmi: defaults.object(forKey: "omiOnboardingHasOmi").map { _ in defaults.bool(forKey: "omiOnboardingHasOmi") },
                watchPaired: defaults.object(forKey: "omiWatchPaired").map { _ in defaults.bool(forKey: "omiWatchPaired") },
                settingsTopic: defaults.string(forKey: "omiSettingsTopic"),
                deepLink: defaults.string(forKey: "omiDeepLink"),
                fakeDevice: defaults.string(forKey: "omiFakeDevice"),
                showsRecordWith: defaults.bool(forKey: "omiShowRecordWith"),
                showsSiriTip: defaults.bool(forKey: "omiShowSiriTip"),
                showsNewTask: defaults.bool(forKey: "omiShowNewTask")
            )
        #else
            return DebugLaunchOptions()
        #endif
    }()

    /// Writes the current root phase for scripted checks (Tools/dev/migration-e2e.sh). Debug only.
    static func recordPhase(_ phase: SessionStore.Phase) {
        #if DEBUG
            let value = switch phase {
            case .launching: "launching"
            case .signedOut: "signedOut"
            case let .consent(userID): "consent:\(userID)"
            case let .onboarding(userID): "onboarding:\(userID)"
            case let .ready(userID): "ready:\(userID)"
            }
            UserDefaults.standard.set(value, forKey: "omi.debug.phase")
        #endif
    }
}

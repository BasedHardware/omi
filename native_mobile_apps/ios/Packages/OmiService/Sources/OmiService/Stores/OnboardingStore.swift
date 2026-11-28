import Foundation
import Observation
import OmiNetwork
import OmiPersistence

/// The first-run flow (Flutter `pages/onboarding/wrapper.dart`, reordered per PLAN.md §4.6).
@MainActor
@Observable
public final class OnboardingStore {
    /// With an Omi: pair it, learn its light, whisper to it, train the voice through it, then
    /// learn its button (ask with one press, hear the answer, pick what a double press does).
    /// Without one the iPhone microphone stands in and the Omi steps are left out. With a paired
    /// Apple Watch, the watch is set up as a recording source too.
    public enum Step: Int, CaseIterable, Sendable {
        case name, language, foundOmi, hasOmi, pair, lights, hello, voice, askOmi, voiceReply, doublePress, watch
        /// Connecting calendar, mail and task apps is left to Settings › Connections (it was a long
        /// list of its own here).
        case permissions, setup
        /// "You're ready", then a short introduction to the app.
        case ready

        var needsOmi: Bool {
            [.pair, .lights, .askOmi, .voiceReply, .doublePress].contains(self)
        }
    }

    public var step: Step = .name
    /// Answered on `hasOmi`; nil until then.
    public var hasOmi: Bool?
    /// Hears the user on `hello` and `voice`.
    public let voice: VoiceIntroStore?
    /// The Omi button lessons (`askOmi`, `doublePress`); without it those steps pass straight on.
    public let buttonTutorial: ButtonTutorialStore?
    /// The paired Apple Watch (`watch` step); nil or unpaired leaves the step out.
    public let watch: WatchStore?
    public var givenName: String
    /// The main language: the first one picked.
    public var language: String {
        spokenLanguages.first ?? fallbackLanguage
    }

    /// Picked in order of importance; the first is the main language.
    public private(set) var spokenLanguages: [String]
    private let fallbackLanguage: String
    public private(set) var languages: [(name: String, code: String)] = []
    public private(set) var errorMessage: String?
    /// Spoken replies as picked on `voiceReply`; nil until the step was shown.
    public private(set) var voiceReplyMode: VoicePlaybackStore.ReplyMode?

    private let api: any APIClientProtocol
    private let preferences: Preferences
    private let updateDisplayName: (String) async -> Void
    private let watchPaired: () -> Bool

    public init(
        api: any APIClientProtocol,
        preferences: Preferences,
        voice: VoiceIntroStore? = nil,
        buttonTutorial: ButtonTutorialStore? = nil,
        watch: WatchStore? = nil,
        watchPaired: (() -> Bool)? = nil,
        updateDisplayName: @escaping (String) async -> Void
    ) {
        self.api = api
        self.preferences = preferences
        self.voice = voice
        self.buttonTutorial = buttonTutorial
        self.watch = watch
        self.watchPaired = watchPaired ?? { watch?.isWatchPaired ?? false }
        self.updateDisplayName = updateDisplayName
        givenName = preferences.displayName ?? ""
        let main = preferences.string(.userPrimaryLanguage) ?? Locale.current.language.languageCode?.identifier ?? "en"
        fallbackLanguage = main
        // Nothing preselected: the phone's language is often not the one people speak.
        spokenLanguages = []
    }

    /// The steps this user walks through.
    public var path: [Step] {
        let watchPaired = watchPaired()
        return Step.allCases.filter { step in
            (!step.needsOmi || hasOmi == true) && (step != .watch || watchPaired)
        }
    }

    public var progress: Double {
        let path = path
        return Double((path.firstIndex(of: step) ?? 0) + 1) / Double(path.count)
    }

    public var voiceSource: VoiceIntroStore.Source {
        hasOmi == true ? .device : .phone
    }

    public func loadLanguages() async {
        if languages.isEmpty { languages = await (try? api.availableLanguages()) ?? [] }
    }

    public func next() {
        let path = path
        if let index = path.firstIndex(of: step), index + 1 < path.count { step = path[index + 1] }
    }

    public func back() {
        let path = path
        if let index = path.firstIndex(of: step), index > 0 { step = path[index - 1] }
    }

    public func chooseOmi(_ has: Bool) {
        hasOmi = has
        next()
    }

    /// Gave up pairing: carry on with the iPhone microphone.
    public func continueWithoutOmi() {
        hasOmi = false
        step = .hello
    }

    /// Name: first word given, the rest family (like Flutter's name step).
    public func saveName() async {
        let trimmed = givenName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        let parts = trimmed.split(separator: " ", maxSplits: 1).map(String.init)
        preferences.set(parts[0], for: .givenName)
        preferences.set(parts.count > 1 ? parts[1] : nil, for: .familyName)
        await updateDisplayName(trimmed)
        next()
    }

    /// Tapping picks a language (after the ones already picked: the order of the taps is the order
    /// of importance) or takes it out again.
    public func toggleLanguage(_ code: String) {
        if let index = spokenLanguages.firstIndex(of: code) {
            spokenLanguages.remove(at: index)
        } else {
            spokenLanguages.append(code)
        }
    }

    /// 1 for the main language, 2, 3 … in the order picked; nil when not picked.
    public func rank(of code: String) -> Int? {
        spokenLanguages.firstIndex(of: code).map { $0 + 1 }
    }

    /// The picked languages with their names in the phone's language, in order. A code the catalog
    /// does not list (an older saved choice) still shows: a pick never drops out of sight.
    public var pickedLanguages: [(name: String, code: String)] {
        spokenLanguages.map { code in (Self.displayName(code, catalogName: languages.first { $0.code == code }?.name), code) }
    }

    /// The most spoken languages, the phone's own first; base codes only ("en", not "en-GB").
    static let commonCodes = ["en", "es", "de", "fr", "pt", "it", "hi", "zh"]
    static let commonCount = 6

    /// The short list shown before searching: the phone's language and the most spoken ones, in
    /// the catalog, six in all (they fit the screen with the search field).
    public var commonLanguages: [(name: String, code: String)] {
        let phone = Locale.current.language.languageCode?.identifier
        let codes = ([phone].compactMap(\.self) + Self.commonCodes).reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
        // Shown right away: the server's catalog only confirms the codes once it has loaded.
        return codes.compactMap { code in
            guard languages.isEmpty || languages.contains(where: { $0.code == code }) else { return nil }
            let catalogName = languages.first { $0.code == code }?.name
            return (Self.displayName(code, catalogName: catalogName), code)
        }
        .prefix(Self.commonCount)
        .map(\.self)
    }

    /// The list on the language step. Without a query: picks from outside the short list first
    /// (so a searched pick stays visible), then the short list. With one: every catalog language
    /// whose name (in the phone's language or English) or code matches.
    public func languageRows(matching query: String = "") -> [(name: String, code: String)] {
        let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !needle.isEmpty else {
            let common = commonLanguages
            return pickedLanguages.filter { picked in !common.contains { $0.code == picked.code } } + common
        }
        return languages.compactMap { language in
            let name = Self.displayName(language.code, catalogName: language.name)
            let matches = name.lowercased().contains(needle) || language.name.lowercased().contains(needle)
                || language.code.lowercased().hasPrefix(needle)
            return matches ? (name, language.code) : nil
        }
    }

    /// "Deutsch", "Englisch (Vereinigte Staaten)" on a German phone; the catalog's English name
    /// when the phone does not know the code.
    static func displayName(_ code: String, catalogName: String?) -> String {
        guard let name = Locale.current.localizedString(forIdentifier: code) else { return catalogName ?? code }
        return name.prefix(1).uppercased() + name.dropFirst()
    }

    /// `PATCH v1/users/language` with the main language; the server also tunes transcription for
    /// it. The full list stays on the phone and decides whether capture mixes languages.
    public func saveLanguage() async {
        errorMessage = nil
        guard !spokenLanguages.isEmpty else { return }
        do {
            try await api.setPrimaryLanguage(language)
            preferences.set(language, for: .userPrimaryLanguage)
            preferences.set(spokenLanguages, for: .spokenLanguages)
            preferences.set(true, for: .hasSetPrimaryLanguage)
            next()
        } catch {
            errorMessage = String(describing: error)
        }
    }

    /// The first run starts spoken replies at Off until the user picks one (Flutter
    /// `initializeVoiceResponseMode`); a replay from Settings shows the saved choice.
    public func showVoiceReply() {
        guard voiceReplyMode == nil else { return }
        if preferences.bool(.onboardingCompleted) {
            voiceReplyMode = VoicePlaybackStore.ReplyMode(rawValue: preferences.integer(.voiceResponseMode, default: 1)) ?? .headphonesOnly
        } else {
            chooseVoiceReply(.off)
        }
    }

    /// The same setting as Settings › Assistant › Spoken replies.
    public func chooseVoiceReply(_ mode: VoicePlaybackStore.ReplyMode) {
        voiceReplyMode = mode
        preferences.set(mode.rawValue, for: .voiceResponseMode)
    }

    /// Fire-and-forget like Flutter; skipping sends nothing.
    public func saveSource(_ source: String?) {
        if let source {
            preferences.set(source, for: .foundOmiSource)
            Task { try? await api.updateOnboarding(completed: nil, acquisitionSource: source) }
        }
        next()
    }
}

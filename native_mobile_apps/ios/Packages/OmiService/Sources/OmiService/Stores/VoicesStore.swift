import Foundation
import Observation
import OmiNetwork

/// Recognizing other people's voices: Home's "Who is this?" prompts, the voice-learning switches
/// and the voices marked Not a Person (Flutter `speaker_tag_prompts_provider`,
/// `voice_profile_settings_section`, `ignored_voices_sheet`). Changes apply at once and roll back.
@MainActor
@Observable
public final class VoicesStore {
    /// Voices to confirm from recent conversations, the next one first.
    public private(set) var prompts: [SpeakerPrompt] = []
    public private(set) var settings: VoiceProfileSettings?
    public private(set) var ignored: [IgnoredVoice] = []
    public private(set) var ignoredLoaded = false
    public private(set) var lastError: String?
    private var shownIDs: Set<String> = []

    private let api: any APIClientProtocol

    public init(api: any APIClientProtocol) {
        self.api = api
    }

    public var currentPrompt: SpeakerPrompt? {
        prompts.first
    }

    // MARK: Prompts

    public func loadPrompts() async {
        if let list = try? await api.speakerPrompts() { prompts = list }
    }

    /// The card is on screen: tells the backend once per set (starts its daily cooldown).
    public func promptsShown() async {
        let fresh = prompts.map(\.id).filter { !shownIDs.contains($0) }
        guard !fresh.isEmpty else { return }
        shownIDs.formUnion(fresh)
        try? await api.markSpeakerPromptsShown(fresh)
    }

    public func answer(_ prompt: SpeakerPrompt, _ answer: SpeakerPromptAnswer) async {
        let previous = prompts
        prompts.removeAll { $0.id == prompt.id }
        await attempt {
            try await self.api.answerSpeakerPrompt(prompt, answer: answer)
        } rollback: {
            self.prompts = previous
        }
    }

    /// Closed without answering: the card goes away and Omi asks less often.
    public func dismissPrompts() async {
        let previous = prompts
        prompts = []
        await attempt {
            try await self.api.dismissSpeakerPrompts()
        } rollback: {
            self.prompts = previous
        }
    }

    public func clip(for prompt: SpeakerPrompt) async -> Data? {
        try? await api.speakerClip(conversationID: prompt.conversationID, start: prompt.clipStart, end: prompt.clipEnd)
    }

    // MARK: Settings

    public func loadSettings() async {
        if let value = try? await api.voiceProfileSettings() { settings = value }
    }

    public func setAsksToTag(_ value: Bool) async {
        await update { $0.asksToTag = value } send: {
            try await self.api.updateVoiceProfileSettings(asksToTag: value, savesOtherVoices: nil)
        }
        if !value { prompts = [] }
    }

    public func setSavesOtherVoices(_ value: Bool) async {
        await update { $0.savesOtherVoices = value } send: {
            try await self.api.updateVoiceProfileSettings(asksToTag: nil, savesOtherVoices: value)
        }
    }

    // MARK: Ignored voices

    public func loadIgnored() async {
        if let list = try? await api.ignoredVoices() { ignored = list }
        ignoredLoaded = true
    }

    /// Undo Not a Person: Omi may ask about this voice again.
    public func restore(_ voice: IgnoredVoice) async {
        let previous = ignored
        ignored.removeAll { $0.id == voice.id }
        await attempt {
            try await self.api.restoreIgnoredVoice(conversationID: voice.conversationID, speakerID: voice.speakerID)
        } rollback: {
            self.ignored = previous
        }
    }

    // MARK: Helpers

    private func update(
        _ change: (inout VoiceProfileSettings) -> Void,
        send: @escaping () async throws -> VoiceProfileSettings
    ) async {
        guard var next = settings else { return }
        let previous = next
        change(&next)
        settings = next
        lastError = nil
        do {
            settings = try await send()
        } catch {
            settings = previous
            lastError = String(describing: error)
        }
    }

    private func attempt(_ operation: @escaping () async throws -> Void, rollback: @escaping () -> Void) async {
        lastError = nil
        do {
            try await operation()
        } catch {
            rollback()
            lastError = String(describing: error)
        }
    }
}

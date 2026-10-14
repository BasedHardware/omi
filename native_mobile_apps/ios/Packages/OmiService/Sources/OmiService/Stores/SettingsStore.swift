import Foundation
import Observation
import OmiNetwork
import OmiPersistence

/// Server-backed settings (Flutter `pages/settings/*`). Each area loads on demand; changes apply
/// immediately and roll back if the backend refuses them.
@MainActor
@Observable
public final class SettingsStore {
    public private(set) var subscription: Subscription?
    public private(set) var dailySummaryEnabled = true
    public private(set) var dailySummaryHour = 22
    public private(set) var notificationFrequency = 0
    public private(set) var storesRecordings = false
    public private(set) var voices: [(id: String, name: String)] = []
    public private(set) var selectedVoice: String?
    public private(set) var vocabulary: [String] = []
    public internal(set) var people: [Person] = []
    public private(set) var phoneNumbers: [PhoneNumber] = []
    public private(set) var phoneUnavailableReason: String?
    public internal(set) var lastError: String?

    let api: any APIClientProtocol
    let preferences: Preferences

    public init(api: any APIClientProtocol, preferences: Preferences) {
        self.api = api
        self.preferences = preferences
    }

    // MARK: Account

    /// The account as the backend knows it (`loadProfile`); its name wins over the one saved on
    /// this iPhone (Flutter's prefs, the sign-in), which may be an old or a placeholder name.
    public private(set) var profile: UserProfile?

    public var displayName: String? {
        profile?.name ?? preferences.displayName
    }

    public var email: String? {
        preferences.string(.email) ?? profile?.email
    }

    public func loadProfile() async {
        if let loaded = try? await api.userProfile() { profile = loaded }
    }

    /// Account › Name was saved: show it right away (the backend's copy follows on its own).
    public func nameChanged(to name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        profile = UserProfile(name: trimmed, email: profile?.email)
    }

    public func loadSubscription() async {
        subscription = try? await api.subscription()
    }

    public func portalURL() async -> URL? {
        try? await api.customerPortalURL()
    }

    /// 0 off, 1 headphones only, 2 always (Flutter `voiceResponseMode`, kept on sign-out).
    public var voiceResponseMode: Int {
        get { preferences.integer(.voiceResponseMode, default: 1) }
        set { preferences.set(newValue, for: .voiceResponseMode) }
    }

    // MARK: Notifications

    public func loadNotifications() async {
        if let daily = try? await api.dailySummary() {
            dailySummaryEnabled = daily.enabled
            dailySummaryHour = daily.hour
        }
        if let frequency = try? await api.notificationFrequency() { notificationFrequency = frequency }
    }

    public func setDailySummary(enabled: Bool, hour: Int) async {
        let previous = (dailySummaryEnabled, dailySummaryHour)
        dailySummaryEnabled = enabled
        dailySummaryHour = hour
        await attempt {
            try await self.api.setDailySummary(enabled: enabled, hour: hour)
        } rollback: {
            (self.dailySummaryEnabled, self.dailySummaryHour) = previous
        }
    }

    public func setNotificationFrequency(_ value: Int) async {
        let previous = notificationFrequency
        notificationFrequency = value
        await attempt {
            try await self.api.setNotificationFrequency(value)
        } rollback: {
            self.notificationFrequency = previous
        }
    }

    // MARK: Privacy

    public func loadPrivacy() async {
        if let value = try? await api.storesRecordings() { storesRecordings = value }
    }

    public func setStoresRecordings(_ value: Bool) async {
        storesRecordings = value
        await attempt {
            try await self.api.setStoresRecordings(value)
        } rollback: {
            self.storesRecordings = !value
        }
    }

    // MARK: Assistant

    public func loadVoices() async {
        if let result = try? await api.assistantVoices() {
            voices = result.voices
            selectedVoice = result.selected
        }
    }

    public func selectVoice(_ id: String) async {
        let previous = selectedVoice
        selectedVoice = id
        await attempt {
            try await self.api.setAssistantVoice(id)
        } rollback: {
            self.selectedVoice = previous
        }
    }

    // MARK: Spoken language

    public private(set) var languages: [(name: String, code: String)] = []
    public var spokenLanguage: String? {
        preferences.string(.userPrimaryLanguage)
    }

    public func loadLanguages() async {
        if languages.isEmpty { languages = await (try? api.availableLanguages()) ?? [] }
    }

    public func setSpokenLanguage(_ code: String) async {
        let previous = spokenLanguage
        preferences.set(code, for: .userPrimaryLanguage)
        await attempt {
            try await self.api.setPrimaryLanguage(code)
        }
        rollback: {
            self.preferences.set(previous, for: .userPrimaryLanguage)
        }
    }

    // MARK: Vocabulary

    public func loadVocabulary() async {
        if let words = try? await api.vocabulary() { vocabulary = words }
    }

    public func addWord(_ word: String) async {
        let trimmed = word.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !vocabulary.contains(trimmed) else { return }
        let previous = vocabulary
        vocabulary.append(trimmed)
        await attempt {
            try await self.api.setVocabulary(self.vocabulary)
        } rollback: {
            self.vocabulary = previous
        }
    }

    public func removeWords(at offsets: IndexSet) async {
        let previous = vocabulary
        vocabulary = vocabulary.enumerated().filter { !offsets.contains($0.offset) }.map(\.element)
        await attempt {
            try await self.api.setVocabulary(self.vocabulary)
        } rollback: {
            self.vocabulary = previous
        }
    }

    // MARK: People

    public func loadPeople() async {
        if let list = try? await api.people() { people = list.sorted { $0.name < $1.name } }
    }

    public func addPerson(_ name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        await attempt {
            try await self.api.addPerson(trimmed)
        } rollback: {}
        await loadPeople()
    }

    public func renamePerson(_ id: String, to name: String) async {
        await attempt {
            try await self.api.renamePerson(id, to: name)
        } rollback: {}
        await loadPeople()
    }

    public func deletePerson(_ id: String) async {
        let previous = people
        people.removeAll { $0.id == id }
        await attempt {
            try await self.api.deletePerson(id)
        } rollback: {
            self.people = previous
        }
    }

    // MARK: Phone

    public func loadPhoneNumbers() async {
        do {
            phoneNumbers = try await api.phoneNumbers()
            phoneUnavailableReason = nil
        } catch let APIError.http(status, body) where status == 402 || status == 403 {
            // e.g. "Phone calls require a paid subscription"
            phoneUnavailableReason = Self.detail(from: body) ?? "HTTP \(status)"
        } catch {
            phoneUnavailableReason = String(describing: error)
        }
    }

    // MARK: Helpers

    func attempt(_ operation: @escaping () async throws -> Void, rollback: @escaping () -> Void) async {
        lastError = nil
        do {
            try await operation()
        } catch {
            rollback()
            lastError = String(describing: error)
        }
    }

    static func detail(from body: String) -> String? {
        guard let data = body.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return object["detail"] as? String
    }
}

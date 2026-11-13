import Foundation
import OmiNetwork

/// Screens create their own short-lived stores from the long-lived ones, so the app shell does not
/// have to build and inject each of them.
public extension SettingsStore {
    func makeUsageStore() -> UsageStore {
        UsageStore(api: api)
    }

    func makeProfileStore() -> ProfileStore {
        ProfileStore(api: api)
    }

    func makeImportStore() -> ImportStore {
        ImportStore(api: api)
    }

    func makeAnnouncementsStore() -> AnnouncementsStore {
        AnnouncementsStore(api: api)
    }
}

public extension MemoriesStore {
    func makeGraphStore(userName: String?) -> KnowledgeGraphStore {
        KnowledgeGraphStore(api: api, userName: userName)
    }
}

public extension ConversationsStore {
    func makeForYouStore() -> ForYouStore {
        ForYouStore(api: api)
    }
}

public extension SessionStore {
    /// Profile › Name: first word given, the rest family, as at sign-up; the identity provider's
    /// display name follows (best effort, like Flutter's `updateGivenName`).
    func changeName(_ name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let parts = trimmed.split(separator: " ", maxSplits: 1).map(String.init)
        preferences.set(parts[0], for: .givenName)
        preferences.set(parts.count > 1 ? parts[1].trimmingCharacters(in: .whitespaces) : nil, for: .familyName)
        try? await auth.updateDisplayName(trimmed)
    }
}

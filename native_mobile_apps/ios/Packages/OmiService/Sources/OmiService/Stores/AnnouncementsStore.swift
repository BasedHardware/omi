import Foundation
import Observation
import OmiNetwork

/// What's new (Flutter `announcement_service`, `changelog_sheet`, `feature_screen`,
/// `announcement_dialog`). After an update the changes since the last version show once; pending
/// feature tours and messages follow, one at a time.
@MainActor
@Observable
public final class AnnouncementsStore {
    /// What is on screen now; the rest waits in line.
    public private(set) var current: Announcement?
    /// Settings › What's new: the latest versions.
    public private(set) var recent: [Announcement] = []
    public private(set) var recentFailed = false

    private var queue: [Announcement] = []
    private let api: any APIClientProtocol
    private let defaults: UserDefaults
    private var checked = false
    /// Flutter's key; a Flutter → native update sees the version it ran before.
    static let lastVersionKey = "flutter.lastKnownAppVersion"

    public init(api: any APIClientProtocol, defaults: UserDefaults = .standard) {
        self.api = api
        self.defaults = defaults
    }

    /// Once per launch. `appVersion` is `X.Y.Z+build`. A fresh install shows nothing (there is no
    /// "before"); an update shows the changes in between, then anything pending.
    public func checkAfterLaunch(appVersion: String) async {
        guard !checked else { return }
        checked = true
        let last = defaults.string(forKey: Self.lastVersionKey)
        if last != appVersion { defaults.set(appVersion, forKey: Self.lastVersionKey) }
        guard let last, !last.isEmpty else { return }
        let upgraded = last != appVersion
        if upgraded, let changes = try? await api.changelogs(fromVersion: last, toVersion: appVersion, limit: 5), !changes.isEmpty {
            enqueue(changes)
        }
        let pending = (try? await api.pendingAnnouncements(appVersion: appVersion, versionUpgrade: upgraded)) ?? []
        for item in pending {
            if case .changelog = item.kind { continue }
            enqueue([item])
        }
    }

    /// Settings › What's new.
    public func loadRecent() async {
        do {
            recent = try await api.changelogs(fromVersion: nil, toVersion: nil, limit: 5)
            recentFailed = false
        } catch {
            recentFailed = true
        }
    }

    /// Answered (button, close, "Got it"): the backend stops offering it. Changelogs are not tracked.
    public func dismiss(buttonTapped: Bool = false) async {
        guard let item = current else { return }
        advance()
        if case .changelog = item.kind { return }
        try? await api.dismissAnnouncement(id: item.id, buttonTapped: buttonTapped)
    }

    /// "Not now": it comes back on the next launch.
    public func later() {
        advance()
    }

    private func enqueue(_ items: [Announcement]) {
        queue += items
        if current == nil { advance() }
    }

    private func advance() {
        current = queue.isEmpty ? nil : queue.removeFirst()
    }
}

/// Home "For you" (Flutter `home_for_you`): short nudges from the proactivity feed with
/// Helpful / Not helpful / Dismiss / Stop these.
@MainActor
@Observable
public final class ForYouStore {
    public private(set) var items: [ForYouItem] = []
    public private(set) var lastError: String?

    private let api: any APIClientProtocol
    private let defaults: UserDefaults
    private var shown: Set<String> = []
    static let stoppedKey = "omi.forYou.stoppedProducers"

    public init(api: any APIClientProtocol, defaults: UserDefaults = .standard) {
        self.api = api
        self.defaults = defaults
    }

    /// Hidden when the feed is off, fails, or is empty.
    public func load() async {
        let stopped = Set(defaults.stringArray(forKey: Self.stoppedKey) ?? [])
        guard let feed = try? await api.forYouFeed() else {
            items = []
            return
        }
        items = feed.filter { !stopped.contains($0.producer) }
    }

    /// Once per card per launch.
    public func markShown(_ item: ForYouItem) {
        guard shown.insert(item.id).inserted else { return }
        let id = item.id
        Task { [api] in try? await api.sendForYouFeedback(itemID: id, .shown) }
    }

    public func send(_ feedback: ForYouItem.Feedback, for item: ForYouItem) async {
        guard let index = items.firstIndex(where: { $0.id == item.id }) else { return }
        let previous = items
        switch feedback {
        case .helpful, .notHelpful:
            guard items[index].feedback != feedback.rawValue else { return }
            items[index].feedback = feedback.rawValue
        case .dismissed:
            items.remove(at: index)
        case .stopThese:
            items.removeAll { $0.producer == item.producer }
            defaults.set(Array(Set((defaults.stringArray(forKey: Self.stoppedKey) ?? []) + [item.producer])), forKey: Self.stoppedKey)
        case .shown, .opened:
            break
        }
        lastError = nil
        do {
            try await api.sendForYouFeedback(itemID: item.id, feedback)
        } catch {
            lastError = String(describing: error)
            // A thumb that did not reach the backend is shown as not given; hiding stays.
            if feedback == .helpful || feedback == .notHelpful { items = previous }
        }
    }
}

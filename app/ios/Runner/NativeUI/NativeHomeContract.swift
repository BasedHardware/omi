import Foundation

/// Versioned presentation values, not backend wire models or stored account data.
struct NativeConversation: Decodable, Equatable, Identifiable {
    struct Segment: Decodable, Equatable, Identifiable {
        let id: String
        let speaker: String
        let text: String
    }

    let id: String
    let title: String
    let timestamp: String
    let locked: Bool
    let starred: Bool
    let status: String
    let summary: String?
    let transcript: [Segment]?
    let externalText: String?
}

struct NativeHomeSnapshot: Decodable, Equatable {
    struct Chrome: Decodable, Equatable {
        struct Action: Decodable, Equatable, Identifiable {
            let id: String
            let title: String
            let symbol: String
            let enabled: Bool
        }
        struct Recap: Decodable, Equatable, Identifiable {
            let id: String
            let title: String
            let date: String
            let emoji: String
        }
        struct Capture: Decodable, Equatable {
            let status: String
            let detail: String
            let elapsed: String
            let source: String
            let lastLine: String
            let explanation: String
            let actions: [Action]
        }
        let home: String
        let tasks: String
        let ask: String
        let recapsTitle: String
        let header: [Action]
        let footer: [Action]
        let alerts: [Action]
        let recaps: [Recap]
        let capture: Capture?
    }
    struct Group: Decodable, Equatable, Identifiable {
        let id: String
        let title: String
        let conversations: [NativeConversation]
    }

    struct Copy: Decodable, Equatable {
        let conversations: String
        let summary: String
        let transcript: String
        let loading: String
        let empty: String
        let error: String
        let retry: String
        let more: String
        let viewAll: String
        let loadMore: String
        let recordings: String
        let noSummary: String
        let noTranscript: String
        let starred: String
        let lockedHint: String
    }

    let version: Int
    let nativeDetail: Bool?
    let revision: Int
    let appearance: String
    let locale: String
    let direction: String
    let loading: Bool
    let failed: Bool
    let hasMore: Bool
    let localRecordingCount: Int
    let groups: [Group]
    let copy: Copy
    let chrome: Chrome?

    func conversation(id: String) -> NativeConversation? {
        groups.lazy.flatMap(\.conversations).first { $0.id == id }
    }

    func withoutContent() -> NativeHomeSnapshot {
        NativeHomeSnapshot(version: version, nativeDetail: nativeDetail, revision: revision, appearance: appearance,
                           locale: locale, direction: direction, loading: false, failed: false,
                           hasMore: false, localRecordingCount: 0, groups: [], copy: copy, chrome: nil)
    }

    static func decode(_ value: Any) throws -> NativeHomeSnapshot {
        let data = try SafeJSON.data(withJSONObject: value)
        let snapshot = try JSONDecoder().decode(Self.self, from: data)
        guard snapshot.version == 1, snapshot.revision >= 0, snapshot.localRecordingCount >= 0,
              ["system", "light", "dark"].contains(snapshot.appearance),
              ["ltr", "rtl"].contains(snapshot.direction), !snapshot.locale.isEmpty,
              Set(snapshot.groups.map(\.id)).count == snapshot.groups.count else {
            throw ContractError.invalidSnapshot
        }
        let ids = snapshot.groups.flatMap(\.conversations).map(\.id)
        guard Set(ids).count == ids.count, !ids.contains("") else {
            throw ContractError.invalidSnapshot
        }
        if let chrome = snapshot.chrome {
            let controls = chrome.header + chrome.footer + chrome.alerts + (chrome.capture?.actions ?? [])
            let controlsIDs = controls.map(\.id)
            let recapIDs = chrome.recaps.map(\.id)
            guard Set(controlsIDs).count == controlsIDs.count, !controlsIDs.contains(""),
                  Set(recapIDs).count == recapIDs.count, !recapIDs.contains("") else {
                throw ContractError.invalidSnapshot
            }
        }
        for conversation in snapshot.groups.flatMap(\.conversations) {
            if conversation.locked,
               conversation.summary?.isEmpty == false || conversation.transcript?.isEmpty == false
                || conversation.externalText?.isEmpty == false {
                throw ContractError.invalidSnapshot
            }
        }
        return snapshot
    }

    enum ContractError: Error { case invalidSnapshot }
}

/// Old channel callbacks cannot roll the renderer back after a newer projection.
struct NativeSnapshotRevision {
    private(set) var value = -1

    mutating func accept(_ revision: Int) -> Bool {
        guard revision > value else { return false }
        value = revision
        return true
    }
}

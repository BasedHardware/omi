import Foundation

/// A folder conversations are sorted into (`v1/folders`). System folders (Work, Personal, …)
/// are created by the backend and cannot be deleted.
public struct Folder: Identifiable, Hashable, Sendable {
    public let id: String
    public var name: String
    public var icon: String
    /// `#RRGGBB`.
    public var color: String
    public var description: String
    public let isSystem: Bool
    public let order: Int
    public let conversationCount: Int

    public init(
        id: String, name: String, icon: String, color: String, isSystem: Bool, order: Int, conversationCount: Int,
        description: String = ""
    ) {
        self.id = id
        self.name = name
        self.icon = icon
        self.color = color
        self.isSystem = isSystem
        self.order = order
        self.conversationCount = conversationCount
        self.description = description
    }

    /// What the folder editor starts from.
    public var draft: FolderDraft {
        FolderDraft(name: name, icon: icon, color: color, description: description)
    }
}

/// Which conversations the list shows. Filtering happens on the backend (`starred=`, `folder_id=`).
public enum ConversationFilter: Hashable, Sendable {
    case all
    case starred
    case folder(String)
}

/// Where a conversation's recording can be played (`v1/sync/audio/{id}/urls`).
public enum ConversationAudio: Hashable, Sendable {
    /// A signed URL, playable without auth headers.
    case ready(URL, duration: TimeInterval?)
    /// The backend is still building the playback file; ask again after this long.
    case pending(retryAfter: TimeInterval)
    /// No single file: these cached parts, played (and shared) one after another.
    case parts([AudioPart])
    case unavailable
}

public extension Conversation {
    /// The public page for a shared conversation, tagged like the Flutter app's `conversationShareUrl`
    /// (`s` = platform, `sid` = a random per-share id, never derived from the sender).
    static func shareURL(id: String, base: String = "https://h.omi.me", source: String = "ios") -> URL {
        let sid = (0 ..< 16).map { _ in String(format: "%02x", UInt8.random(in: 0 ... 255)) }.joined()
        var components = URLComponents(string: base) ?? URLComponents()
        components.path = "/conversations/\(id)"
        components.queryItems = [URLQueryItem(name: "s", value: source), URLQueryItem(name: "sid", value: sid)]
        return components.url ?? URL(fileURLWithPath: "/")
    }
}

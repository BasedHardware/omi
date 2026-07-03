import Foundation

enum MainChatRuntimeSessionStore {
    private static let defaultsKey = "mainChatRuntimeSessionIdsByOwnerAndChat"
    static let defaultChatId = "default"

    static func sessionId(ownerId: String, chatId: String) -> String? {
        guard !ownerId.isEmpty else { return nil }
        return storedMap()[key(ownerId: ownerId, chatId: chatId)]
    }

    static func save(sessionId: String, ownerId: String, chatId: String) {
        guard !ownerId.isEmpty, !sessionId.isEmpty else { return }
        var map = storedMap()
        map[key(ownerId: ownerId, chatId: chatId)] = sessionId
        UserDefaults.standard.set(map, forKey: defaultsKey)
    }

    static func clear(ownerId: String, chatId: String) {
        guard !ownerId.isEmpty else { return }
        var map = storedMap()
        map.removeValue(forKey: key(ownerId: ownerId, chatId: chatId))
        UserDefaults.standard.set(map, forKey: defaultsKey)
    }

    static func clearAll() {
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }

    private static func storedMap() -> [String: String] {
        UserDefaults.standard.dictionary(forKey: defaultsKey) as? [String: String] ?? [:]
    }

    private static func key(ownerId: String, chatId: String) -> String {
        "\(ownerId)|\(chatId.isEmpty ? defaultChatId : chatId)"
    }
}

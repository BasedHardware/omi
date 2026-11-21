import Foundation
import OmiCore
import OmiNetwork

public extension FakeAPIClient {
    /// Matches titles and overviews, newest first. A delay in `searchDelays` answers late even when
    /// cancelled, like a server that already started working.
    func searchConversations(query: String, page _: Int, perPage: Int) async throws -> [Conversation] {
        let delay = lock.withLock {
            searchRequests.append(query)
            return searchDelays[query]
        }
        if let delay { await Self.wait(delay) }
        return try lock.withLock {
            if let _error { throw _error }
            return Array(
                _conversations
                    .filter { $0.title.localizedStandardContains(query) || $0.overview.localizedStandardContains(query) }
                    .sorted { $0.date > $1.date }
                    .prefix(perPage)
            )
        }
    }

    func chatHistory(limit: Int, offset: Int, sessionID: String?) async throws -> [ChatMessage] {
        devApps.lock.withLock { devApps.historySessions.append(sessionID) }
        return try lock.withLock {
            if let _error { throw _error }
            chatOffsets.append(offset)
            guard let chatArchive else {
                return offset == 0 ? [ChatMessage(id: "h1", text: "Hi! How can I help?", sender: .omi, createdAt: Fixtures.now)] : []
            }
            return Array(chatArchive.reversed().dropFirst(offset).prefix(limit).reversed())
        }
    }

    private static func wait(_ delay: Duration) async {
        // Not cancellable on purpose: the answer still arrives, the store has to ignore it.
        await withCheckedContinuation { continuation in
            DispatchQueue.global().asyncAfter(deadline: .now() + delay.timeInterval) { continuation.resume() }
        }
    }
}

private extension Duration {
    var timeInterval: TimeInterval {
        let (seconds, attoseconds) = components
        return TimeInterval(seconds) + TimeInterval(attoseconds) / 1e18
    }
}

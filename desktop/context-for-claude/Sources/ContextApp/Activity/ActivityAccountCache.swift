//
//  ActivityAccountCache.swift — the account's last answer, on disk, for the paint before the network.
//
//  **The spine's account half was network-only, and it looked it.** A cold launch composed the local
//  sessions `context.db` holds and nothing else — every one of them drawn as
//  `ActivityConversation.untitled`, because a title is written by the backend when a transcript is
//  uploaded and a session that has not been uploaded has none — and stayed that way until three HTTP
//  round trips came back. What the user saw was a column of `Untitled conversation` that turned into
//  real titles a second or two later, every single launch.
//
//  The shipping Omi app has never looked like that over the same data, and not because it is faster
//  on the wire: `ConversationRepository.load` reads its SQLite cache, emits it, and *then* fetches,
//  so `structured.title` is on screen in milliseconds and the server answer replaces it in place.
//  `ActivityLocalMemories` already brought half of that arrangement to this app for the memory
//  column. This is the other half, for all three sources, and it is this app's own store rather than
//  a read of somebody else's — Context for Claude ships standalone and cannot assume Omi is
//  installed beside it.
//
//  ## What it is allowed to claim
//
//  **Nothing.** A cached feed is not an answer and must never be presented as one: it does not set
//  `answered`, it does not make the account `reachable`, and it does not settle the corpus. It is
//  pixels that were true a moment ago, standing in until pixels that are true now arrive.
//  `ActivityStore.seed(cached:)` is the only way in, and it deliberately does not go through
//  `absorb(account:)` for exactly that reason — that path draws conclusions about the account, and
//  this has no standing to draw any.
//
//  **Replaced, never merged.** When a source answers, its rows here are rewritten from that answer.
//  A conversation deleted on the phone therefore survives one paint and no longer, which is the same
//  bargain main makes and the reason a stale row is harmless rather than a bug that compounds.
//
//  ## Bounds
//
//  `OmiActivityFeed.maxPerSource` rows per source, which is one page — the page a first paint draws
//  from. A cache that could hold more rows than one answer is allowed to contain would grow past the
//  thing it is a copy of, one 503 at a time, inside a database whose reason for existing is screen
//  capture.
//

import ContextCore
import Foundation

/// Reads and writes the spine's account rows to `context.db`.
///
/// **An actor, and the serialisation is load-bearing.** Saves are spawned detached off a read that
/// has already been absorbed, so at sign-out there can be one in flight with the previous account's
/// rows in it. A struct would let that save's `replace` commit *after* `clear()` had emptied the
/// table, and the next account's first paint would then be somebody else's conversations — the one
/// outcome this cache must never produce. Serialising every write through one actor makes the two
/// orderable; `epoch` is what decides which of the two orders wins.
///
/// The store is still a provider rather than a held handle, for the reason every boundary in this
/// package is one: it opens lazily on the engine's queue, so anything that captured it at build
/// time would hold the `nil` of the first instant forever.
actor ActivityAccountCache {

    /// Bumped by `clear()`. A save carrying an older epoch was minted for an account that has since
    /// been signed out of, and is dropped rather than written.
    ///
    /// Ordering alone is not enough even with the actor: the save may simply *arrive* second and be
    /// perfectly serialised, and still be wrong. What makes it wrong is not when it ran but which
    /// account it describes, so that is what is checked. Same reasoning as
    /// `ConversationCacheWriteScope` in the main app, which fences its cache writes on a generation
    /// for this exact failure.
    private var epoch = 0

    /// The epoch a caller must quote to have its write accepted. Read when the work that will
    /// produce the rows *starts*, not when it finishes.
    func currentEpoch() -> Int { epoch }

    /// How many rows of one source are kept. One page — see the note at the top of the file.
    static let ceiling = OmiActivityFeed.maxPerSource

    private static let category = "activity"

    /// `async` because the engine's store is main-actor state and this runs off it: the reads and
    /// writes below belong on a background task — they are SQLite, on the launch path — and the one
    /// hop to ask for the handle is cheaper than doing the work where the UI is drawn. Same shape
    /// `ActivityDetail` already uses to reach the same property.
    private let store: @Sendable () async -> ContextStore?

    init(store: @escaping @Sendable () async -> ContextStore?) {
        self.store = store
    }

    // MARK: - Reading

    /// Everything cached, as the rows the composer takes.
    ///
    /// Returns an empty triple rather than throwing or reporting failure, and the caller treats an
    /// empty one as "nothing to paint yet". A cache that cannot be read is exactly as interesting as
    /// a cache that is empty: both mean the network answer is the first thing on screen, which is
    /// where this surface was before this file existed.
    func load() async -> (
        conversations: [ActivityAccountConversation], memories: [ActivityAccountMemory],
        tasks: [ActivityAccountTask]
    ) {
        guard let store = await store() else { return ([], [], []) }
        let conversations: [CachedConversation] = read(store, .conversations)
        let memories: [CachedMemory] = read(store, .memories)
        let tasks: [CachedTask] = read(store, .tasks)
        return (
            conversations.map(\.row), memories.map(\.row), tasks.map(\.row)
        )
    }

    private func read<Payload: Decodable>(
        _ store: ContextStore, _ source: ActivityAccountSource
    ) -> [Payload] {
        do {
            return try AccountCacheQueries.recent(
                store, source: source.rawValue, limit: Self.ceiling
            ).compactMap { cached in
                guard let data = cached.payload.data(using: .utf8) else { return nil }
                // A row whose shape this binary no longer understands is dropped, not thrown on.
                // The cache is disposable by construction and the next write repairs it; refusing
                // to paint anything because one row is from an older format would make a schema
                // change cost the very launch this file exists to speed up.
                return try? JSONDecoder().decode(Payload.self, from: data)
            }
        } catch {
            ContextLog.error("Account cache unreadable (\(type(of: error)))", Self.category)
            return []
        }
    }

    // MARK: - Writing

    /// Writes back every source the feed actually answered for.
    ///
    /// **Only answered sources.** A feed carries whatever the reader has gathered, including rows
    /// from a source that has since started failing; rewriting the cache from those would be a copy
    /// of a copy. A source absent from `answered` keeps whatever it had, which is the last thing it
    /// really said.
    ///
    /// **And never a locally-sourced one.** `ActivityLocalMemories` merges this Mac's own memories
    /// into the column, and those rows already live in the Omi app's database. Caching them here
    /// would mean a second copy of somebody else's table, and — worse — a later launch would read
    /// them back as *the account's* answer, which is a claim this app has no business making on
    /// their behalf.
    /// - Parameter epoch: the value `currentEpoch()` gave when the read behind `feed` began. A save
    ///   quoting a stale one is dropped: the account it describes has been signed out of.
    func save(_ feed: ActivityAccountFeed, epoch: Int) async {
        // **The store is acquired first, and the epoch is checked after it.** The order is the whole
        // of the fence, because **actors are reentrant**: `await store()` is a suspension point
        // inside this actor, so a `clear()` arriving while this call is parked there runs to
        // completion and this one then resumes past a check it had already passed. Checking first
        // reads as the careful thing to do and is exactly the hole — the previous revision of this
        // file had it that way and was still racy.
        //
        // Acquiring the handle first means the only suspension is behind us: everything from the
        // check to the last write below is synchronous, so nothing can interleave between them.
        guard let store = await store() else { return }
        guard epoch == self.epoch else {
            ContextLog.info(
                "Account cache: dropping a write from a signed-out session", Self.category)
            return
        }
        let cacheable = feed.answered.subtracting(feed.locallySourced)
        guard !cacheable.isEmpty else { return }

        for source in cacheable {
            let rows: [CachedAccountRow]
            switch source {
            case .conversations:
                rows = newest(feed.conversations.map(CachedConversation.init)) { $0.startedAt }
            case .memories:
                rows = newest(feed.memories.map(CachedMemory.init)) { $0.at }
            case .tasks:
                rows = newest(feed.tasks.map(CachedTask.init)) { $0.at }
            }
            do {
                try AccountCacheQueries.replace(
                    store, source: source.rawValue, rows: rows, keeping: Self.ceiling)
            } catch {
                // A cache that could not be written costs the *next* launch a slower paint and
                // costs this one nothing at all. Never worth failing a read over.
                ContextLog.error(
                    "Account cache unwritable for \(source.rawValue) (\(type(of: error)))",
                    Self.category)
            }
        }
    }

    /// The newest `ceiling` of one source, already encoded.
    ///
    /// Bounded here as well as in the trim: the feed reaching this can be the whole hydrated corpus —
    /// thousands of rows — and handing all of them to an upsert loop that will immediately delete
    /// most of them again is the trim paying for work nobody asked for.
    private func newest<Payload: Encodable & CachedPayload>(
        _ payloads: [Payload], _ instant: (Payload) -> Double
    ) -> [CachedAccountRow] {
        payloads
            .sorted { instant($0) > instant($1) }
            .prefix(Self.ceiling)
            .compactMap { payload in
                guard let data = try? JSONEncoder().encode(payload),
                    let text = String(data: data, encoding: .utf8)
                else { return nil }
                return CachedAccountRow(
                    source: payload.source.rawValue, id: payload.id, at: instant(payload),
                    payload: text)
            }
    }

    /// Empties it. Signing out is the caller — one account's rows must never be the first thing the
    /// next account sees.
    func clear() async {
        // **Before its own suspension point, not merely before the delete.** Same reentrancy as
        // `save`: bumping after `await store()` would leave a window in which a save parked on that
        // await resumes still believing it is current. Unconditional for a second reason — a clear
        // that cannot reach the database must still invalidate the writes behind it, or a failed
        // delete becomes the previous account's rows written back a moment later.
        epoch &+= 1
        guard let store = await store() else { return }
        try? AccountCacheQueries.clear(store)
    }
}

// MARK: - What is written

/// The two things every cached payload has to be able to say about itself for the row to be keyed.
private protocol CachedPayload {
    var id: String { get }
    var source: ActivityAccountSource { get }
}

// The seam types are deliberately *not* made `Codable` and cached directly. A cache is a wire format
// with a version skew problem — this binary reads rows an older one wrote — and conforming the live
// types would mean every field added to a row for the sake of what it draws silently becomes a
// schema change. These mirrors are the format, and they change only when someone changes them.

private struct CachedConversation: Codable, CachedPayload {
    let id: String
    let title: String
    let emoji: String
    let startedAt: Double
    let finishedAt: Double
    let overview: String?

    var source: ActivityAccountSource { .conversations }

    init(_ row: ActivityAccountConversation) {
        id = row.id
        title = row.title
        emoji = row.emoji
        startedAt = row.startedAt
        finishedAt = row.finishedAt
        overview = row.overview
    }

    var row: ActivityAccountConversation {
        ActivityAccountConversation(
            id: id, title: title, emoji: emoji, startedAt: startedAt, finishedAt: finishedAt,
            overview: overview)
    }
}

private struct CachedMemory: Codable, CachedPayload {
    let id: String
    let content: String
    let at: Double
    let conversationID: String?

    var source: ActivityAccountSource { .memories }

    init(_ row: ActivityAccountMemory) {
        id = row.id
        content = row.content
        at = row.at
        conversationID = row.conversationID
    }

    var row: ActivityAccountMemory {
        ActivityAccountMemory(id: id, content: content, at: at, conversationID: conversationID)
    }
}

private struct CachedTask: Codable, CachedPayload {
    let id: String
    let text: String
    let completed: Bool
    let at: Double

    var source: ActivityAccountSource { .tasks }

    init(_ row: ActivityAccountTask) {
        id = row.id
        text = row.text
        completed = row.completed
        at = row.at
    }

    var row: ActivityAccountTask {
        ActivityAccountTask(id: id, text: text, completed: completed, at: at)
    }
}

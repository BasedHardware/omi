//
//  ActivityAccount.swift — the account half of the spine, as a seam.
//
//  Three of the five things the spine can show do not live on this Mac. Conversations carry the
//  titles and emoji the account gave them, memories are durable facts, and tasks are commitments;
//  all three are the user's Omi account answering, not `context.db`. Only screen moments are local.
//
//  **A protocol rather than a call into the network client**, for the reason every other boundary in
//  this package is one: a store that reaches for `OmiAPI` cannot be composed in a test or a preview
//  without a signed-in account and a live backend. The reading side takes this; the implementation
//  over the real API lives in `Backend/`.
//
//  Every read returns a value, never a throw. **An unreachable account is an ordinary state here**,
//  not an error — the user may be signed out, offline, or have never connected one — and the spine's
//  job in that case is to show the screen moments it does have rather than to fail whole. What it
//  must never do is render "nothing happened" when the truth is "nobody answered", which is why the
//  result carries `reachable` instead of collapsing an empty account into an empty array.
//

import Foundation

/// One conversation as the account tells it — the shape the mockup shows, with a real title and the
/// emoji the account chose, which a local speech session has no way to know.
struct ActivityAccountConversation: Sendable, Equatable, Identifiable {
    let id: String
    let title: String
    let emoji: String
    let startedAt: Double
    let finishedAt: Double
    /// What the account calls it, when it says anything — shown under the title.
    let overview: String?
}

/// A durable fact the account is keeping.
struct ActivityAccountMemory: Sendable, Equatable, Identifiable {
    let id: String
    let content: String
    /// When it was captured, falling back to when it was created. Unix epoch seconds.
    let at: Double
}

/// A commitment the account extracted or the user wrote down.
struct ActivityAccountTask: Sendable, Equatable, Identifiable {
    let id: String
    let text: String
    let completed: Bool
    let at: Double
}

/// What one read of the account returned.
///
/// `reachable` is the whole point: `ActivityAccountFeed(reachable: false)` and an account that
/// genuinely holds nothing are different claims, and the spine's empty copy says different things
/// about them.
struct ActivityAccountFeed: Sendable, Equatable {
    var conversations: [ActivityAccountConversation] = []
    var memories: [ActivityAccountMemory] = []
    var tasks: [ActivityAccountTask] = []
    /// False when no account is connected, the network refused, or the read failed.
    var reachable: Bool = true

    static let unreachable = ActivityAccountFeed(reachable: false)
    static let empty = ActivityAccountFeed()

    var isEmpty: Bool { conversations.isEmpty && memories.isEmpty && tasks.isEmpty }
}

/// The account, as the spine needs to see it.
protocol ActivityAccountReading: Sendable {
    /// One read of everything the spine can show from the account, over a time window.
    ///
    /// `since`/`until` are Unix epoch seconds and may be nil, meaning "no bound" — the same
    /// vocabulary `SearchTimeFilter.range` speaks, so the window the chips choose reaches every
    /// source unchanged. Tasks are deliberately not windowed by the caller: an open commitment
    /// matters today whenever it was written.
    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed
}

/// The account nobody connected. Used by previews, the render harness, and every test that is about
/// composition rather than about the network.
struct ActivityAccountAbsent: ActivityAccountReading {
    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed { .unreachable }
}

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
    /// The conversation this fact was extracted from, when the account recorded one.
    ///
    /// **This is what decides the day a memory is shown on**, which is why it is carried across the
    /// seam rather than left on the wire. A memory extracted from a conversation is timestamped when
    /// the extractor got to it, and that is routinely hours — or a day — after the conversation it
    /// came out of; filing it on its own instant puts the fact on a day the user did not live it.
    /// `ActivityComposer` files a memory naming a conversation it holds under *that conversation's*
    /// day. Nil for a fact the user wrote down themselves, and for one whose conversation the
    /// account no longer names.
    let conversationID: String?

    init(id: String, content: String, at: Double, conversationID: String? = nil) {
        self.id = id
        self.content = content
        self.at = at
        self.conversationID = conversationID
    }
}

/// A commitment the account extracted or the user wrote down.
struct ActivityAccountTask: Sendable, Equatable, Identifiable {
    let id: String
    let text: String
    let completed: Bool
    let at: Double
}

/// Which of the three things the spine reads from the account a claim is about.
///
/// **The account is not one source and has never behaved like one.** `OmiActivityFeed` reads three
/// independent endpoints in parallel, and the state this type exists for is the one that was
/// observed live: `GET /v1/conversations` answering normally while `GET /v3/memories` returned
/// `503 Canonical memory unavailable` — for eight hours and counting, on every request shape,
/// because the account is on the canonical memory path and the backend fails it closed. A feed that
/// can only say *reachable* collapses that into one bit, which is both too coarse to tell the reader
/// what is missing and too coarse to *substitute* for: `ActivityLocalMemories` fills the memory
/// column from the Omi app's own database precisely when memories did not answer, and it can only
/// know that if the answer is recorded per source.
enum ActivityAccountSource: String, Sendable, Hashable, CaseIterable, Codable {
    case conversations
    case memories
    case tasks

    /// The chip this source feeds. The words a reader sees live in `ActivityKind.title` and are
    /// borrowed rather than restated, so a source can never be named one thing on a chip and another
    /// in a sentence six points above it.
    var kind: ActivityKind {
        switch self {
        case .conversations: return .conversations
        case .memories: return .memories
        case .tasks: return .tasks
        }
    }
}

/// What one read of the account returned.
///
/// `reachable` is the whole point: `ActivityAccountFeed(reachable: false)` and an account that
/// genuinely holds nothing are different claims, and the spine's empty copy says different things
/// about them.
///
/// **`answered` is the premise and `reachable` is the conclusion**, in that order and never the
/// other way round. `reachable` answers "did the account answer at all", which is exactly
/// `!answered.isEmpty` — so it is derived in the initialiser a real read uses rather than passed
/// beside it, for the same reason `CaptureState.capturing` is: a conclusion nobody may edit is a
/// conclusion that cannot disagree with its premises.
struct ActivityAccountFeed: Sendable, Equatable {
    var conversations: [ActivityAccountConversation] = []
    var memories: [ActivityAccountMemory] = []
    var tasks: [ActivityAccountTask] = []
    /// False when no account is connected, the network refused, or every read failed.
    let reachable: Bool
    /// Which sources answered *this* read. A source that is absent said nothing — which is not the
    /// same as having said "nothing", and is the distinction `ActivityLocalMemories` is built on.
    let answered: Set<ActivityAccountSource>
    /// Sources whose rows below were read from this Mac rather than from the account.
    ///
    /// **Nothing in this feed may present a locally-read row as an account row**, and this is the
    /// only thing standing between the two: the rows are indistinguishable once composed, because
    /// they are the same memories — the Omi app on this Mac holds the account's own copy. See
    /// `ActivityAccountLocalNote` for what the reader is shown, and `ActivityLocalMemories`, which is
    /// the only thing that ever sets this.
    ///
    /// A source can be in both this and `answered`: the local database also holds memories that have
    /// not synced yet, so a perfectly healthy read still merges some local rows in. The state the
    /// note is about is the other one — in here and *not* in `answered`.
    let locallySourced: Set<ActivityAccountSource>
    /// True when the memory page had to start *past* its newest row to be served at all.
    ///
    /// `GET /v3/memories` at `offset: 0` runs a Firestore keyset scan that is currently failing for
    /// real accounts, while any non-zero offset takes a different implementation that works — so a
    /// first page that 503s is re-asked from the second row. The page that comes back is then
    /// complete except at the head, and the difference matters exactly once: `ActivityLocalMemories`
    /// treats a synced row the account did not return as *deleted elsewhere* and refuses to
    /// resurrect it, which is right for a whole page and wrong for a page missing its first row by
    /// construction. This is the flag that tells the two apart.
    let memoriesBeginPastHead: Bool

    /// **The initialiser a real read uses.** `reachable` is not a parameter — see the note above.
    init(
        conversations: [ActivityAccountConversation] = [],
        memories: [ActivityAccountMemory] = [],
        tasks: [ActivityAccountTask] = [],
        answered: Set<ActivityAccountSource>,
        locallySourced: Set<ActivityAccountSource> = [],
        memoriesBeginPastHead: Bool = false
    ) {
        self.conversations = conversations
        self.memories = memories
        self.tasks = tasks
        self.reachable = !answered.isEmpty
        self.answered = answered
        self.locallySourced = locallySourced
        self.memoriesBeginPastHead = memoriesBeginPastHead
    }

    /// The initialiser every preview, fake and composition test uses, where the interesting axis is
    /// the one bit and not which of three endpoints was up. `answered` is derived the other way —
    /// a reachable feed answered everything, an unreachable one answered nothing — so a feed built
    /// this way still carries a premise its conclusion agrees with.
    init(
        conversations: [ActivityAccountConversation] = [],
        memories: [ActivityAccountMemory] = [],
        tasks: [ActivityAccountTask] = [],
        reachable: Bool = true,
        locallySourced: Set<ActivityAccountSource> = []
    ) {
        self.init(
            conversations: conversations,
            memories: memories,
            tasks: tasks,
            answered: reachable ? Set(ActivityAccountSource.allCases) : [],
            locallySourced: locallySourced)
    }

    static let unreachable = ActivityAccountFeed(reachable: false)
    static let empty = ActivityAccountFeed()

    var isEmpty: Bool { conversations.isEmpty && memories.isEmpty && tasks.isEmpty }

    /// How many rows this feed carries, over every source.
    ///
    /// **The hydrator's only progress signal**, and the reference's too: a reader that pages answers
    /// with everything it has gathered so far, so an answer that is no bigger than the last one is
    /// how a caller learns the account has run out of pages — or that the page it just asked for did
    /// not arrive. Neither is worth another request, and the difference between them is `answered`.
    var rowCount: Int { conversations.count + memories.count + tasks.count }
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

/// An account reader whose walk through the account can be moved by the caller.
///
/// **Separate from `ActivityAccountReading` for the reason `ActivityAccountDiagnosing` is**: a
/// preview's account, a test's account and `ActivityAccountAbsent` have no cursor and nothing to
/// move, and making every one of them implement two no-ops would be a protocol demanding a promise
/// only one implementation can keep.
///
/// It exists because a reader that pages is a reader that only ever moves *away* from the newest
/// row, and holds everything it has passed. Both facts are right while a corpus is filling and both
/// are wrong later: what changed since the reader left is at offset zero, which a forward-only
/// cursor never asks for twice, and what it is holding belongs to whichever account was signed in
/// when it read it.
///
/// Neither method fetches. They move the cursor; the next `read` is what spends a request, which is
/// what keeps one read path through the decorators instead of two.
protocol ActivityAccountCursor: Sendable {
    /// Reopen the newest page of every source, so the next `read` asks the account for it again.
    /// Everything already gathered is kept, and rows that come back changed replace their copies.
    func refreshHead() async

    /// Drop everything gathered and every cursor. The account that answered has been signed out of,
    /// and not one row of what it said may reach whoever signs in next.
    func forget() async
}

/// The account nobody connected. Used by previews, the render harness, and every test that is about
/// composition rather than about the network.
struct ActivityAccountAbsent: ActivityAccountReading {
    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed { .unreachable }
}

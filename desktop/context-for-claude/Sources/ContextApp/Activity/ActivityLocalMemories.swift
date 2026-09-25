//
//  ActivityLocalMemories.swift — the memory column, read the way the shipping app reads it.
//
//  The Activity spine used to draw its memories from one live `GET /v3/memories` per window and from
//  nothing else, so an account that would not answer produced an empty column indistinguishable from
//  an account with no memories in it. That is not a hypothetical failure mode. Measured on this
//  machine, from the app's own log and from four probe requests including the shipping client's
//  byte-identical one:
//
//      GET  /v3/memories  → 503: Canonical memory unavailable   (every shape, every attempt)
//      POST /v3/memories  → 503: Memory writes are globally paused
//
//  — while the shipping Omi app, on the same Mac and the same account, showed the user **6,598
//  memories** throughout. Its last successful read of that endpoint was eight hours earlier and it
//  never noticed, because `MemoriesPage.loadMemories()` is cache-first by construction: it renders
//  its local SQLite first and *then* fetches, and a failed fetch leaves the rendered list alone.
//
//  **So the memories are already on this Mac, and this app already knows how to read them.**
//  `OmiMemoryStore` is a read-only WAL pool over the main app's `omi.db`, and `ContextMCPKit`'s
//  `recall` and `get_memories` tools have folded those rows in all along — advertising to Claude that
//  they are available "even when the API key is missing". The Activity panel was the one memory
//  surface in this app that did not use it. This file is that omission closed.
//
//  ## What it does, and what it refuses to do
//
//  - **Local rows always contribute; the account supersedes them by id.** This is main's rule, not a
//    fallback bolted on for outages. The local table holds memories that have not synced yet — 27 of
//    them on the measured machine — and those exist nowhere else, so a healthy account read still
//    merges. Reconciliation is on `backendId`, which `LocalMemory.id` already is once a row has
//    synced, so a memory cannot appear twice.
//  - **The account wins every collision.** It is the authority on its own memories: an edit made on
//    the phone reaches the backend before it reaches this Mac's copy.
//  - **A source that answered is never topped up on its own terms.** If `/v3/memories` returns an
//    empty list, that is the account saying it holds nothing, and only the *unsynced* local rows are
//    added — never the synced ones, which the account has just told us are gone.
//  - **It says so.** A memory column drawn entirely from this Mac because the account would not
//    answer is a different claim from a live one, and `ActivityAccountLocalNote` is what makes the
//    difference visible. Main's register here is silence; this app's whole character is the
//    opposite, so it gets one quiet accurate line where main would say nothing at all.
//
//  ## Airgap Mode
//
//  Reading a SQLite file on this Mac is not egress, so nothing here consults `NetworkEgress` and
//  nothing here needs to: no `Client` case covers it because there is no connection to suppress. The
//  upstream reader still refuses to touch the network under the switch, and an airgapped user now
//  gets the *better* answer rather than a worse one — their own memories, read locally, labelled.
//
//  ## The user's data
//
//  The database belongs to another application and this package opens it **read-only**, through the
//  same configuration `ContextStore`'s reader uses. Nothing in this file writes, and nothing in it
//  logs a memory: the one log line counts rows.
//

import ContextCore
import Foundation

/// The main app's local memories, as the spine needs to see them.
///
/// A protocol for the reason every boundary in this package is one: the real implementation opens a
/// database at a path that only exists on a machine with Omi installed, and every test of the merge
/// rules would otherwise need one.
protocol ActivityLocalMemoryReading: Sendable {
    /// The newest memories this Mac holds, newest first, or an empty array when there is no local
    /// database to read. **Never a throw** — the same bargain `ActivityAccountReading` makes, and for
    /// the same reason: a missing Omi install is an ordinary state, not an error.
    func recent(limit: Int) -> [ActivityAccountMemory]

    /// Whether there is a local database at all. Distinct from "it returned nothing", which is what
    /// an install with no memories yet looks like — and the note may only speak when this is true.
    var isAvailable: Bool { get }
}

/// The real one, over the Omi desktop app's `omi.db`.
struct ActivityLocalMemorySource: ActivityLocalMemoryReading {
    private let store: OmiMemoryStore

    init(store: OmiMemoryStore = .shared) {
        self.store = store
    }

    var isAvailable: Bool { store.isAvailable }

    func recent(limit: Int) -> [ActivityAccountMemory] {
        store.recentMemories(limit: limit).compactMap { local in
            let content = local.content.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !content.isEmpty else { return nil }
            return ActivityAccountMemory(
                id: local.id,
                content: content,
                // A row whose stamp would not decode is placed at zero rather than dropped. It is
                // still a fact the user has; it simply sorts to the bottom of the spine instead of
                // claiming a day it cannot support.
                at: local.createdAt ?? 0,
                conversationID: local.conversationId)
        }
    }
}

/// A reader with no local database behind it. Previews, the render harness, and every test that is
/// about composition rather than about the Omi app being installed.
struct ActivityLocalMemoriesAbsent: ActivityLocalMemoryReading {
    var isAvailable: Bool { false }
    func recent(limit: Int) -> [ActivityAccountMemory] { [] }
}

// MARK: - The merge

/// An account reader whose memory column is drawn from this Mac first and reconciled with the
/// account second — the shape `MemoriesPage` has always had, in this app's seam.
///
/// A decorator rather than a branch inside `OmiActivityFeed`, so that the merge rules can be driven
/// over readers that fail on command, and so the app's decision to use one lives at a single call
/// site.
///
/// `ActivityAccountDiagnosing` is forwarded rather than reimplemented: *why* the account did not
/// answer is still the network reader's to say, and this changes only what is drawn.
struct ActivityLocalMemories: ActivityAccountReading, ActivityAccountDiagnosing,
    ActivityAccountCursor
{
    private let upstream: ActivityAccountReading
    private let local: ActivityLocalMemoryReading

    private static let category = "activity"

    init(
        _ upstream: ActivityAccountReading,
        local: ActivityLocalMemoryReading = ActivityLocalMemorySource()
    ) {
        self.upstream = upstream
        self.local = local
    }

    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        let account = await upstream.read(since: since, until: until, limit: limit)
        guard local.isAvailable else { return account }

        let bounded = min(max(limit, 1), OmiActivityFeed.maxPerSource)
        let rows = local.recent(limit: bounded)
        guard !rows.isEmpty else { return account }

        let answeredMemories = account.answered.contains(.memories)
        let merged = Self.merge(
            account: account.memories, local: rows, accountAnswered: answeredMemories,
            beginsPastHead: account.memoriesBeginPastHead)
        guard merged.count > account.memories.count else { return account }

        // Counts only. The content of a memory is the user's own words and never reaches a log line.
        ContextLog.info(
            "Memory column: \(account.memories.count) from the account, "
                + "\(merged.count - account.memories.count) from this Mac"
                + (answeredMemories ? "" : " (the account did not answer)"), Self.category)

        return ActivityAccountFeed(
            conversations: account.conversations,
            memories: merged,
            tasks: account.tasks,
            // **Untouched.** Whether the account answered is a fact about the account, and filling
            // the column from a local database must not turn an outage into a clean bill of health.
            // What is on screen is described by `locallySourced` and by the note that renders it.
            answered: account.answered,
            locallySourced: account.locallySourced.union([.memories]))
    }

    /// The account's memories, plus the local ones it did not already account for.
    ///
    /// - Parameter accountAnswered: whether `account` is an answer or a silence, and it changes which
    ///   local rows may be added.
    ///
    ///   **When the account answered, only rows it has never seen are added.** A synced local row
    ///   absent from a successful read is a memory the account no longer has — deleted on the phone,
    ///   perhaps minutes ago — and re-adding it from a copy that has not caught up would resurrect
    ///   something the user threw away. `backendId` is exactly the evidence needed: a row that has
    ///   one has synced, so its absence from the account's answer is meaningful, and a row without
    ///   one has never left this Mac and cannot have been deleted anywhere else.
    ///
    ///   **When it did not answer, every local row is added**, because there is no answer for an
    ///   absence to be meaningful against.
    ///
    /// - Parameter beginsPastHead: whether the account's page had to start past its own newest row.
    ///
    ///   The `/v3/memories` first page is currently unservable for real accounts, so a 503 there is
    ///   answered by re-asking from `offset: 1` — see `OmiActivityFeed.attemptMemories`. That page is
    ///   complete *except at the head*, which breaks the reasoning above for exactly the rows above
    ///   it: they are absent because they were never asked for, not because they were deleted. So a
    ///   synced local row newer than everything the account returned is added back, and a synced row
    ///   inside the returned range is still refused. The bound is what keeps this narrow — without
    ///   it, "the page is incomplete" would readmit every deletion the account has ever made.
    static func merge(
        account: [ActivityAccountMemory],
        local: [ActivityAccountMemory],
        accountAnswered: Bool,
        beginsPastHead: Bool = false
    ) -> [ActivityAccountMemory] {
        let known = Set(account.map(\.id))
        // Nil when the account returned nothing at all, in which case there is no head to be past
        // and no range for a row to be inside — every synced row is above an empty page.
        let newestReturned = account.map(\.at).max()
        let additions = local.filter { row in
            guard !known.contains(row.id) else { return false }
            guard accountAnswered else { return true }
            if isUnsynced(row.id) { return true }
            guard beginsPastHead else { return false }
            guard let newestReturned else { return true }
            return row.at > newestReturned
        }
        return account + additions
    }

    /// Whether this id is the main app's stand-in for a memory that has never reached the backend.
    ///
    /// The convention is that app's, mirrored in `LocalMemoryRow.toMemory()`: a synced row is known
    /// by its `backendId`, and an unsynced one by `local_<rowid>`. Nothing else in Omi mints an id of
    /// that shape, and a backend id is a UUID, so the prefix cannot collide with one.
    static func isUnsynced(_ id: String) -> Bool { id.hasPrefix("local_") }

    func unreachableReason() async -> ActivityAccountUnreachableReason? {
        await (upstream as? ActivityAccountDiagnosing)?.unreachableReason()
    }

    /// Forwarded for the reason `unreachableReason` is: the cursor being rewound belongs to the
    /// network reader, and this decorator has none of its own. The local half needs no rewinding —
    /// `recent(limit:)` reads the newest rows out of SQLite on every call and has never been paged.
    func refreshHead() async {
        await (upstream as? ActivityAccountCursor)?.refreshHead()
    }

    /// Forwarded for the same reason. Nothing of the previous account is held here — the local rows
    /// are re-read from SQLite on every call and belong to whoever is signed into the Omi app — so
    /// there is nothing of this decorator's own to forget.
    func forget() async {
        await (upstream as? ActivityAccountCursor)?.forget()
    }
}

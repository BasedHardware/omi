//
//  ActivityComposer.swift — what attaches to what, and what a day header counts.
//
//  **Composition and filtering are deliberately two steps.** Composing is the expensive half — it
//  groups every conversation, attaches every frame, and sorts each day — and it does not depend on
//  the chips or on what has been typed. Filtering is a scan. Recomposing on every keystroke would
//  make the query field feel like the list is thinking; this way the store composes when the *data*
//  changes and filters when the *question* does.
//
//  It also keeps the day header honest: `filter(_:kind:query:earliest:)` never touches the counts,
//  so a filtered stream still says how big the day really was.
//

import ContextCore
import Foundation

/// How many captured frames one sampled frame stands for, and the one place a run of the sample is
/// turned back into a count of the day.
///
/// A value rather than a division written out three times, because the three call sites — the
/// conversation's `N screen moments`, its attached strip's `8 of N`, and a loose run's — have to
/// agree or a conversation says six where the strip under it says two hundred.
struct MomentScale: Equatable {
    /// How many of the day's frames the composer was actually handed.
    let sampled: Int
    /// How many the day really holds, from `ActivityDayScreen.total`.
    let captured: Int

    /// What a run of `count` sampled frames stands for.
    ///
    /// Never fewer than the frames themselves: a `captured` smaller than `sampled` is not a state
    /// the store can produce, and a strip that said "8 of 3" would be worse than one that said
    /// nothing. Below the sampling ceiling the sample *is* the day and this is the identity.
    func forRun(of count: Int) -> Int {
        guard sampled > 0, captured > sampled else { return count }
        return max(count, Int((Double(count) * Double(captured) / Double(sampled)).rounded()))
    }
}

enum ActivityComposer {
    /// How many frames a single strip draws. Eight is what fits a strip at the panel's narrowest
    /// before it starts scrolling, and a strip is a glance, not a gallery.
    static let momentsPerStrip = 8

    /// A gap this long ends a run of unattached screen moments and starts the next one. Forty-five
    /// minutes is long enough that a coffee break does not split a work session in two, and short
    /// enough that morning and evening are never one row.
    ///
    /// It ends a run of memories and a run of tasks on the same terms: the question "did these come
    /// out of the same stretch of the day" is the same question, and two answers to it would put a
    /// memory and the frame beside it in different rows for no reason a reader could see.
    static let momentClusterGap: TimeInterval = 45 * 60

    /// Compose the whole stream, unfiltered.
    ///
    /// - Parameters:
    ///   - sessions: every spoken session read so far, any order.
    ///   - uploads: what the queue holds for each session it is answerable for — the Omi
    ///     conversation ids that session became, or an empty list while it is still owed to an
    ///     account (`UploadQueue.conversationLinks`, keyed by session id). Empty when the caller has
    ///     not read the queue; see `merge`, which then has only the clock to go on.
    ///   - account: what the account answered. `.unreachable` contributes nothing and suppresses
    ///     nothing, which is what leaves a signed-out Mac showing the screen moments it does have.
    ///   - screen: per-day screen capture, keyed by the local start of the day.
    ///   - isAirgapped: whether the upload queue is allowed to drain at all. Injected rather than
    ///     read here so both answers are drivable in a test, exactly as `OmiActivityFeed` and
    ///     `ActivityDetail` take it. See `merge` for what it decides.
    static func compose(
        sessions rawSessions: [SessionSummary],
        uploads: [Int64: [String]] = [:],
        account: ActivityAccountFeed = .unreachable,
        screen: [Date: ActivityDayScreen],
        calendar: Calendar = .current,
        isAirgapped: () -> Bool = { NetworkEgress.isSuppressed(.conversationUpload) }
    ) -> [ActivityDay] {
        // **Every row id below is derived from a record id, so a repeated record is a repeated
        // SwiftUI identity** — which in a `ForEach` is not a cosmetic duplicate but undefined
        // behaviour in the list's own diffing. Days are read independently and their bounds are
        // half-open at one end only, so a frame or a session landing on a boundary can reach the
        // composer twice; that is a matter of timing rather than of correctness. The composer holds
        // no authority over the reads, but it does own its own row identities, so it keeps the
        // first sighting of each and drops the rest here rather than rendering the same row twice.
        let sessions = uniqued(rawSessions, by: \.id)
        let conversations = merge(
            account: uniqued(account.conversations, by: \.id), sessions: sessions,
            uploads: uploads, isAirgapped: isAirgapped)

        var conversationsByDay: [Date: [ActivityConversation]] = [:]
        for conversation in conversations {
            conversationsByDay[calendar.startOfDay(for: conversation.startedAt), default: []]
                .append(conversation)
        }

        // **A memory naming a conversation we are actually holding attaches to it; everything else
        // stands on its own at the time it was made.** The conversation is the thing that happened
        // and the memory is what was learned from it, so they belong on the same day — and they
        // routinely are not on the same day by the clock. Extraction runs after the fact, so a
        // conversation at eleven at night leaves a memory timestamped the following morning, and
        // filing that on its own instant puts the fact on a day the user did not live it. This is
        // the one attachment the account can *state*; the composer never infers one from a
        // timestamp, which is why tasks — whose seam carries no conversation id — do not attach.
        //
        // A memory pointing at a conversation on a page we have not loaded must not vanish: it falls
        // through to `looseMemories` and gets a row of its own rather than being filed against a
        // conversation that is not on screen to hold it.
        let conversationIDs = Set(conversations.map(\.id))
        var attachedMemories: [String: [ActivityMemory]] = [:]
        var looseMemories: [ActivityMemory] = []
        for memory in uniqued(account.memories, by: \.id).map(ActivityMemory.init(memory:)) {
            if let conversationID = memory.conversationID, conversationIDs.contains(conversationID) {
                attachedMemories[conversationID, default: []].append(memory)
            } else {
                looseMemories.append(memory)
            }
        }

        // Only the loose ones can put a day on the stream. An attached memory is shown on its
        // conversation's day, so counting its own day here would open a header over a day whose
        // only row had been re-seated onto another one.
        var memoriesByDay: [Date: [ActivityMemory]] = [:]
        for memory in looseMemories {
            memoriesByDay[calendar.startOfDay(for: memory.timestamp), default: []].append(memory)
        }

        var tasksByDay: [Date: [ActivityTask]] = [:]
        for task in uniqued(account.tasks, by: \.id).map(ActivityTask.init(task:)) {
            tasksByDay[calendar.startOfDay(for: task.timestamp), default: []].append(task)
        }

        let days = Set(conversationsByDay.keys)
            .union(memoriesByDay.keys)
            .union(tasksByDay.keys)
            .union(screen.keys)
            .sorted(by: >)

        return days.map { day in
            composeDay(
                day: day,
                conversations: conversationsByDay[day] ?? [],
                memories: memoriesByDay[day] ?? [],
                attachedMemories: attachedMemories,
                tasks: tasksByDay[day] ?? [],
                screen: screen[day] ?? .empty,
                calendar: calendar
            )
        }
    }

    /// The account's conversations, plus the local sessions the account did not already know about.
    ///
    /// **One conversation, one row.** A session this Mac heard and the account conversation it was
    /// uploaded into are the same conversation described twice — the Mac heard the speech, the
    /// account summarised it — so the local telling is dropped and the account's stands, carrying the
    /// title and the emoji somebody actually wrote. Showing both prints the day as a column of pairs,
    /// each real title shadowed by an untitled duplicate of itself.
    ///
    /// **The link is the queue's, not the clock's.** `ConversationUploader` records the conversation
    /// ids the backend handed back for a session (`UploadQueue.Entry.conversationIds`), and that is a
    /// statement that these two records are the same conversation rather than an inference about
    /// them. A session that split into several parts became several account conversations, and any
    /// one of them being on a loaded page is enough: the session is accounted for.
    ///
    /// **Overlap is the fallback, for sessions the queue says nothing about.** A row can predate the
    /// queue, and reconciliation can miss one; for those there is only the clock, and overlap rather
    /// than equality because the two clocks are not the same clock — the account timestamps a
    /// conversation from the recording it received and this Mac from the first line it heard, so they
    /// agree about the stretch of the day and not about the second. It is the weaker rule of the two
    /// and it is used only where the stronger one has nothing to say.
    ///
    /// **A session whose account counterpart is not on a loaded page keeps its row.** Same rule as a
    /// memory naming a conversation we do not hold: it must not vanish because paging has not reached
    /// it. It merges the moment the page lands.
    ///
    /// **A local session with no counterpart at all survives too.** It is a real thing that happened
    /// on this Mac — the whole reason the store still reads `Queries.sessions` — and dropping it
    /// would make a signed-out user's day claim they had not spoken.
    ///
    /// **A session the queue is still holding for an account draws no row at all, and that is the
    /// one place this differs from "no counterpart".** A local session has no title of its own —
    /// titles are written by the account when the transcript is uploaded — so it draws
    /// `ActivityConversation.untitled`, the same string an account conversation nobody named gets.
    /// For a queued session that string is simply false: it is not untitled, it is *not yet
    /// uploaded*, and on a Mac whose queue is blocked (a paused backend, a long backlog) the day
    /// fills with placeholders that bury the conversations that do have titles — fifteen rows where
    /// the shipping app shows nine, the top of the list all `Untitled conversation`. Each of those
    /// rows is about to *become* the account conversation underneath it, so drawing it now is
    /// drawing the same talk twice, once as a placeholder. Its screen moments still draw, on their
    /// own run, so the stretch of day it happened in is not blank — and the menu bar keeps saying
    /// "N conversations waiting to upload" (`ConversationUploader.pendingCount`), which is where a
    /// backlog belongs.
    ///
    /// **Only while the queue can actually deliver it**, which is what `isAirgapped` decides. In
    /// Airgap Mode nothing is ever going to be uploaded, and the account feed is suppressed too, so
    /// suppressing these rows as well would leave that user an Activity panel with no conversations
    /// on it whatsoever. Same reasoning as the unowned rows `UploadQueue.conversationLinks` declines
    /// to report as owed: a session nothing is going to upload is local, and local sessions draw.
    static func merge(
        account: [ActivityAccountConversation],
        sessions: [SessionSummary],
        uploads: [Int64: [String]] = [:],
        isAirgapped: () -> Bool = { NetworkEgress.isSuppressed(.conversationUpload) }
    ) -> [ActivityConversation] {
        let known = account.map(ActivityConversation.init(account:))
        let accountIDs = Set(known.map(\.id))
        let windows = known.map { $0.startedAt...max($0.startedAt, $0.finishedAt) }
        let queueCanDeliver = !isAirgapped()
        let unmatched = sessions.filter { session in
            if let links = uploads[session.id] {
                if !links.isEmpty { return !links.contains(where: accountIDs.contains) }
                // Owed to an account and nothing has landed yet: no row of its own.
                if queueCanDeliver { return false }
            }
            let local = ActivityConversation(session: session)
            let window = local.startedAt...max(local.startedAt, local.finishedAt)
            return !windows.contains { $0.overlaps(window) }
        }
        return known + unmatched.map(ActivityConversation.init(session:))
    }

    /// Narrows a composed stream to one kind, one query and one time window.
    ///
    /// A day with nothing left is dropped whole — header and all — because a sticky day header over
    /// no rows is a heading for content that is not there.
    ///
    /// - Parameter query: already trimmed and case-folded by the caller, so there is one
    ///   normalisation on this surface rather than one per call site.
    /// - Parameter latest: the top of the window, and **not decoration on `earliest`**. Tasks are
    ///   read unwindowed on purpose (`OmiActivityFeed.read` — an open commitment matters whenever it
    ///   was written) and are placed on their *due* date, which can be days either side of what the
    ///   time chips asked for. With no upper bound here, picking `Yesterday` composed a `TODAY`
    ///   header above it out of tasks due today; a task due next Friday put a day in the future at
    ///   the top of a stream whose whole claim is that it is a record of the past.
    static func filter(
        _ days: [ActivityDay],
        kind: ActivityKind,
        query: String,
        earliest: Date? = nil,
        latest: Date? = nil
    ) -> [ActivityDay] {
        let needle = query
        guard kind != .all || !needle.isEmpty || earliest != nil || latest != nil else { return days }

        return days.compactMap { day in
            var rows = day.rows.filter { row in
                guard kind == .all || row.kind == kind else { return false }
                if let earliest, row.anchor < earliest { return false }
                if let latest, row.anchor > latest { return false }
                guard !needle.isEmpty else { return true }
                return row.searchText.contains(needle)
            }
            guard !rows.isEmpty else { return nil }

            if kind != .all {
                // Soloed: nothing is a child of anything, so every row earns its own place on the
                // clock.
                rows = rows.map {
                    ActivityRow(
                        id: $0.id, anchor: $0.anchor, kind: $0.kind, isAttached: false,
                        content: $0.content, searchText: $0.searchText)
                }
            }

            return ActivityDay(
                id: day.id,
                title: day.title,
                momentCount: day.momentCount,
                conversationCount: day.conversationCount,
                memoryCount: day.memoryCount,
                taskCount: day.taskCount,
                rows: rows
            )
        }
    }

    /// - Parameter memories: the day's *loose* memories — the ones filed on their own timestamp.
    /// - Parameter attachedMemories: every attached memory in the whole stream, keyed by the
    ///   conversation that produced it. Not narrowed to this day on purpose: an attached memory is
    ///   shown on its conversation's day, and its own timestamp routinely falls on another one.
    private static func composeDay(
        day: Date,
        conversations: [ActivityConversation],
        memories: [ActivityMemory],
        attachedMemories: [String: [ActivityMemory]],
        tasks: [ActivityTask],
        screen: ActivityDayScreen,
        calendar: Calendar
    ) -> ActivityDay {
        let ordered = conversations.sorted { $0.startedAt > $1.startedAt }
        let moments = uniqued(screen.sampled, by: \.id).sorted { $0.timestamp > $1.timestamp }

        // Attach each sampled frame to the conversation whose window contains it. Newest-first over
        // newest-first, so this is a single pass rather than a lookup per frame.
        //
        // The cursor advances only past conversations that **start after** this frame — those are
        // in the frame's future and, because both runs descend, in every later frame's future too,
        // so skipping them is permanent and safe. Advancing on `finishedAt` instead looks
        // equivalent and is not: one frame newer than the newest conversation would walk the cursor
        // off the end and every older frame after it would be orphaned.
        var momentsByConversation: [String: [ActivityMoment]] = [:]
        var looseMoments: [ActivityMoment] = []
        var cursor = 0
        for moment in moments {
            while cursor < ordered.count, ordered[cursor].startedAt > moment.timestamp {
                cursor += 1
            }
            if cursor < ordered.count, moment.timestamp <= ordered[cursor].finishedAt {
                momentsByConversation[ordered[cursor].id, default: []].append(moment)
            } else {
                looseMoments.append(moment)
            }
        }

        // **What one sampled frame stands for.** `ActivityStore.project` keeps at most
        // `sampleCeiling` frames of a day, spread evenly (`evenlySampled`), and a day of screen
        // capture at three-second intervals is thousands — so every number derived from the sample
        // is short by the sampling ratio unless it is scaled back. Counting the sample instead was
        // visible on screen: a conversation said "6 screen moments" for a stretch that held two
        // hundred, and the corner reported a chip that excluded nothing as "51 results · of 2,954".
        //
        // Even sampling is exactly the claim "these N stand for those M evenly", so the scale is a
        // reading of the sample rather than an estimate laid over it.
        //
        // Denominated in the sample **as the store delivered it**, not in `moments` — which is that
        // sample after `uniqued`. A frame that reached the composer twice was still counted once by
        // the day's own read, so dividing by the deduped count would inflate every run by exactly
        // the duplicates it had just removed.
        let stands = MomentScale(sampled: screen.sampled.count, captured: screen.total)

        var rows: [ActivityRow] = []
        // How many memories this day is showing because a conversation on it produced them. They
        // are the day's memories as far as the reader is concerned, so the header counts them — and
        // it cannot get them from `memories`, which is only the loose half.
        var attachedMemoryCount = 0

        for summary in ordered {
            let attached = momentsByConversation[summary.id] ?? []
            let remembered = (attachedMemories[summary.id] ?? []).sorted {
                $0.timestamp > $1.timestamp
            }
            attachedMemoryCount += remembered.count
            let counted = summary.counted(
                memoryCount: remembered.count, momentCount: stands.forRun(of: attached.count))
            rows.append(
                ActivityRow(
                    id: "conv:\(summary.id)",
                    anchor: counted.startedAt,
                    kind: .conversations,
                    isAttached: false,
                    content: .conversation(counted),
                    searchText: counted.searchText
                ))
            // What was learned before what was on screen: the memory is the conversation's own
            // residue and the strip is context around it.
            if !remembered.isEmpty {
                rows.append(memoryRow(remembered, id: "conv-mem:\(summary.id)", isAttached: true))
            }
            if !attached.isEmpty {
                rows.append(
                    momentRow(
                        attached, total: stands.forRun(of: attached.count),
                        id: "conv-shot:\(summary.id)", isAttached: true))
            }
        }

        for cluster in clusters(of: looseMoments) {
            guard let first = cluster.first else { continue }
            rows.append(
                momentRow(
                    cluster, total: stands.forRun(of: cluster.count), id: "shot:\(first.id)",
                    isAttached: false))
        }

        // What is left stands on the clock in its own right, grouped by the run it came out of.
        for cluster in runs(of: memories, at: \.timestamp) {
            guard let first = cluster.first else { continue }
            rows.append(memoryRow(cluster, id: "mem:\(first.id)", isAttached: false))
        }

        // **Tasks never attach, and that is not an oversight.** The seam carries no conversation id
        // for a task, so claiming one as the child of the conversation it happens to fall inside
        // would be an attachment invented from a timestamp. A frame can be attached because being on
        // screen *during* a conversation is exactly what the window means, and a memory because the
        // account says which conversation it came out of; a task landing in the same minute is a
        // coincidence until something states otherwise.
        for cluster in runs(of: tasks, at: \.timestamp) {
            guard let first = cluster.first else { continue }
            rows.append(
                ActivityRow(
                    id: "task:\(first.id)",
                    anchor: cluster.map(\.timestamp).max() ?? first.timestamp,
                    kind: .tasks,
                    isAttached: false,
                    content: .tasks(cluster),
                    searchText: cluster.map(\.text).joined(separator: " ").lowercased()
                ))
        }

        rows.sort { lhs, rhs in
            if lhs.anchor != rhs.anchor { return lhs.anchor > rhs.anchor }
            // A conversation's own row must stay above the rows it produced even when the first
            // frame was captured at exactly the conversation's start time.
            return lhs.kind == .conversations && rhs.kind != .conversations
        }

        // Re-seat every attached row directly under its conversation. Sorting by anchor alone would
        // interleave them with anything that happened mid-conversation, which is the exact reading
        // failure the indent exists to prevent.
        rows = reseatAttachments(rows)

        return ActivityDay(
            id: day,
            title: ActivityFormat.day(day, calendar: calendar),
            momentCount: screen.total,
            conversationCount: conversations.count,
            memoryCount: memories.count + attachedMemoryCount,
            taskCount: tasks.count,
            rows: rows
        )
    }

    /// First sighting of each id wins, in the order given. Order is what the stream sorts by, so a
    /// stable filter rather than a set round-trip.
    static func uniqued<Element, Key: Hashable>(
        _ elements: [Element], by key: KeyPath<Element, Key>
    ) -> [Element] {
        var seen = Set<Key>()
        seen.reserveCapacity(elements.count)
        return elements.filter { seen.insert($0[keyPath: key]).inserted }
    }

    /// Moves each attached row to sit immediately under its own conversation.
    private static func reseatAttachments(_ rows: [ActivityRow]) -> [ActivityRow] {
        var attachments: [String: [ActivityRow]] = [:]
        var spine: [ActivityRow] = []
        for row in rows {
            guard row.isAttached else {
                spine.append(row)
                continue
            }
            // "conv-shot:<id>" / "conv-mem:<id>" — the owner is everything after the *first* colon,
            // because a local session's id carries one of its own
            // (`ActivityConversation.localID`).
            let owner = String(row.id.drop(while: { $0 != ":" }).dropFirst())
            attachments[owner, default: []].append(row)
        }
        return spine.flatMap { row -> [ActivityRow] in
            guard case .conversation(let summary) = row.content else { return [row] }
            return [row] + (attachments["\(summary.id)"] ?? [])
        }
    }

    private static func memoryRow(
        _ memories: [ActivityMemory], id: String, isAttached: Bool
    ) -> ActivityRow {
        ActivityRow(
            id: id,
            anchor: memories.map(\.timestamp).max() ?? Date(),
            kind: .memories,
            isAttached: isAttached,
            content: .memories(memories),
            searchText: memories.map(\.text).joined(separator: " ").lowercased()
        )
    }

    private static func momentRow(
        _ moments: [ActivityMoment], total: Int, id: String, isAttached: Bool
    ) -> ActivityRow {
        let shown = Array(moments.prefix(momentsPerStrip))
        return ActivityRow(
            id: id,
            anchor: moments.map(\.timestamp).max() ?? Date(),
            kind: .rewind,
            isAttached: isAttached,
            content: .moments(shown: shown, total: total),
            searchText: moments.map { "\($0.appName) \($0.windowTitle ?? "")" }
                .joined(separator: " ")
                .lowercased()
        )
    }

    /// Splits a run of moments wherever the gap between two of them exceeds `momentClusterGap`,
    /// newest first.
    static func clusters(of moments: [ActivityMoment]) -> [[ActivityMoment]] {
        runs(of: moments, at: \.timestamp)
    }

    /// The same split, for anything that happened at a time.
    ///
    /// One function rather than three copies of the same six lines: memories, tasks and frames are
    /// grouped by the same question — *did these come out of one stretch of the day* — and three
    /// implementations of it is three places for the answer to drift.
    static func runs<Element>(
        of elements: [Element], at timestamp: KeyPath<Element, Date>
    ) -> [[Element]] {
        let ordered = elements.sorted { $0[keyPath: timestamp] > $1[keyPath: timestamp] }
        var result: [[Element]] = []
        var current: [Element] = []
        for element in ordered {
            if let previous = current.last,
                previous[keyPath: timestamp].timeIntervalSince(element[keyPath: timestamp])
                    > momentClusterGap
            {
                result.append(current)
                current = []
            }
            current.append(element)
        }
        if !current.isEmpty { result.append(current) }
        return result
    }

    /// Keeps at most `ceiling` frames, spread evenly across the run rather than taken off the front.
    ///
    /// Taking the first N would show a busy day as its last twenty minutes and nothing else — the
    /// strips would all cluster at the top of the day and the rest of it would look empty.
    static func evenlySampled(_ moments: [ActivityMoment], ceiling: Int) -> [ActivityMoment] {
        guard ceiling > 0 else { return [] }
        guard moments.count > ceiling else { return moments }
        let step = Double(moments.count) / Double(ceiling)
        var sampled: [ActivityMoment] = []
        sampled.reserveCapacity(ceiling)
        var cursor = 0.0
        while sampled.count < ceiling {
            let index = Int(cursor)
            guard index < moments.count else { break }
            sampled.append(moments[index])
            cursor += step
        }
        return sampled
    }
}

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
    ///   - account: what the account answered. `.unreachable` contributes nothing and suppresses
    ///     nothing, which is what leaves a signed-out Mac showing the screen moments it does have.
    ///   - screen: per-day screen capture, keyed by the local start of the day.
    static func compose(
        sessions rawSessions: [SessionSummary],
        account: ActivityAccountFeed = .unreachable,
        screen: [Date: ActivityDayScreen],
        calendar: Calendar = .current
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
            account: uniqued(account.conversations, by: \.id), sessions: sessions)

        var conversationsByDay: [Date: [ActivityConversation]] = [:]
        for conversation in conversations {
            conversationsByDay[calendar.startOfDay(for: conversation.startedAt), default: []]
                .append(conversation)
        }

        var memoriesByDay: [Date: [ActivityMemory]] = [:]
        for memory in uniqued(account.memories, by: \.id).map(ActivityMemory.init(memory:)) {
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
                tasks: tasksByDay[day] ?? [],
                screen: screen[day] ?? .empty,
                calendar: calendar
            )
        }
    }

    /// The account's conversations, plus the local sessions the account did not already know about.
    ///
    /// **A local session whose window overlaps an account conversation is dropped, and the account's
    /// telling wins.** They are one conversation described twice — this Mac heard the speech, the
    /// account summarised it — and showing both would print every conversation on the spine as a pair
    /// the moment somebody signs in, with the honest-looking untitled one directly under the titled
    /// one. Overlap and not equality, because the two clocks are not the same clock: the account
    /// timestamps a conversation from the recording it received and this Mac from the first line it
    /// heard, so they agree about the stretch of the day and not about the second.
    ///
    /// **A local session with no counterpart survives.** It is a real thing that happened on this
    /// Mac — the whole reason the store still reads `Queries.sessions` — and dropping it would make a
    /// signed-out user's spine claim they had not spoken all day. What it cannot have is a title or
    /// an emoji: this database stores speech, not summaries, so the row says which app the sound came
    /// through and draws the speech mark rather than inventing either.
    static func merge(
        account: [ActivityAccountConversation], sessions: [SessionSummary]
    ) -> [ActivityConversation] {
        let known = account.map(ActivityConversation.init(account:))
        let windows = known.map { $0.startedAt...max($0.startedAt, $0.finishedAt) }
        let unmatched = sessions.map(ActivityConversation.init(session:)).filter { local in
            let window = local.startedAt...max(local.startedAt, local.finishedAt)
            return !windows.contains { $0.overlaps(window) }
        }
        return known + unmatched
    }

    /// Narrows a composed stream to one kind, one query and one time window.
    ///
    /// A day with nothing left is dropped whole — header and all — because a sticky day header over
    /// no rows is a heading for content that is not there.
    ///
    /// - Parameter query: already trimmed and case-folded by the caller, so there is one
    ///   normalisation on this surface rather than one per call site.
    static func filter(
        _ days: [ActivityDay],
        kind: ActivityKind,
        query: String,
        earliest: Date? = nil
    ) -> [ActivityDay] {
        let needle = query
        guard kind != .all || !needle.isEmpty || earliest != nil else { return days }

        return days.compactMap { day in
            var rows = day.rows.filter { row in
                guard kind == .all || row.kind == kind else { return false }
                if let earliest, row.anchor < earliest { return false }
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

    private static func composeDay(
        day: Date,
        conversations: [ActivityConversation],
        memories: [ActivityMemory],
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

        var rows: [ActivityRow] = []

        for summary in ordered {
            let attached = momentsByConversation[summary.id] ?? []
            let counted = summary.counted(momentCount: attached.count)
            rows.append(
                ActivityRow(
                    id: "conv:\(summary.id)",
                    anchor: counted.startedAt,
                    kind: .conversations,
                    isAttached: false,
                    content: .conversation(counted),
                    searchText: counted.searchText
                ))
            if !attached.isEmpty {
                rows.append(
                    momentRow(
                        attached, total: attached.count, id: "conv-shot:\(summary.id)",
                        isAttached: true))
            }
        }

        for cluster in clusters(of: looseMoments) {
            guard let first = cluster.first else { continue }
            rows.append(
                momentRow(cluster, total: cluster.count, id: "shot:\(first.id)", isAttached: false))
        }

        // **Memories and tasks stand on the clock in their own right — they never attach.** The seam
        // carries no conversation id for either (see `ActivityAccountMemory`), so claiming a memory
        // as the child of the conversation it happens to fall inside would be an attachment invented
        // from a timestamp. A frame can be attached because being on screen *during* a conversation
        // is exactly what the window means; a memory landing in the same minute is a coincidence
        // until the account says otherwise.
        for cluster in runs(of: memories, at: \.timestamp) {
            guard let first = cluster.first else { continue }
            rows.append(
                ActivityRow(
                    id: "mem:\(first.id)",
                    anchor: cluster.map(\.timestamp).max() ?? first.timestamp,
                    kind: .memories,
                    isAttached: false,
                    content: .memories(cluster),
                    searchText: cluster.map(\.text).joined(separator: " ").lowercased()
                ))
        }

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
            memoryCount: memories.count,
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
            // "conv-shot:<id>" — the owner is everything after the *first* colon, because a local
            // session's id carries one of its own (`ActivityConversation.localID`).
            let owner = String(row.id.drop(while: { $0 != ":" }).dropFirst())
            attachments[owner, default: []].append(row)
        }
        return spine.flatMap { row -> [ActivityRow] in
            guard case .conversation(let summary) = row.content else { return [row] }
            return [row] + (attachments["\(summary.id)"] ?? [])
        }
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

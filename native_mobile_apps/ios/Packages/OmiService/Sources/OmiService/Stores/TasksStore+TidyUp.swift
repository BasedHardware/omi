import Foundation
import OmiCore
import OmiNetwork

/// The daily tidy-up: once a day (the first Home visit after 6:00), the chat agent proposes
/// merges, done and "not a task" in its own session; Home shows it as one suggestion card and the
/// user applies what they keep. Never applied on its own.
public extension TasksStore {
    static let tidyUpLastRunKey = "omi.tidyUp.lastRun"
    static let tidyUpProposalKey = "omi.tidyUp.proposal"
    static let tidyUpSessionKey = "omi.tidyUp.session"
    /// The hour from which a day's tidy-up may run (local time).
    static let tidyUpHour = 6
    /// The tidy-up's own thread: an app id that is no app, so it never becomes the main chat (the
    /// backend's main thread is the newest session without one), and the ✦ title the chat skips.
    static let tidyUpSessionAppID = AgentStore.runSessionAppID
    static let tidyUpSessionTitle = AgentStore.sessionTitlePrefix + "Tidy up tasks"

    /// The first visit after `tidyUpHour` on a day that has not had one.
    func tidyUpIsDue(now: Date = .now) -> Bool {
        guard let start = calendar.date(bySettingHour: Self.tidyUpHour, minute: 0, second: 0, of: now), now >= start else {
            return false
        }
        let last = defaults?.double(forKey: Self.tidyUpLastRunKey) ?? lastTidyUpInMemory
        return last < start.timeIntervalSince1970
    }

    /// Asks the agent when the day's tidy-up is due (or `force`); the suggestion lands in `tidyUp`.
    /// `source` names a task's conversation for the prompt.
    func tidyUpIfDue(
        source: (ActionItem) -> String?, quote: (ActionItem) -> String? = { _ in nil }, now: Date = .now, force: Bool = false
    ) async {
        guard !isTidyingUp, force || tidyUpIsDue(now: now), phase == .loaded else { return }
        // Marked first: a failure waits for tomorrow instead of asking again on every visit.
        markTidyUpRun(now)
        // Newest first; ties keep the list's order.
        let open = tasks.filter { $0.isOpen && $0.owner != .other }.enumerated()
            .sorted { lhs, rhs in
                let (left, right) = (lhs.element.createdAt ?? .distantPast, rhs.element.createdAt ?? .distantPast)
                return left != right ? left > right : lhs.offset < rhs.offset
            }
            .map(\.element)
            .prefix(TaskTidyUp.maxTasks)
        guard open.count >= 2 else {
            log?.add(.info, "tidyup", "skipped: \(open.count) open tasks")
            return
        }
        isTidyingUp = true
        defer { isTidyingUp = false }
        let list = Array(open)
        let keys = TaskTidyUp.keys(for: list)
        let prompt = TaskTidyUp.prompt(list, source: source, quote: quote, now: now, calendar: calendar)
        guard let answer = await askTidyUp(prompt) else { return }
        log?.add(.info, "tidyup", "raw answer: \(String(answer.prefix(4000)))")
        guard let proposal = TaskTidyUp.parse(answer, keys: keys) else {
            log?.add(.warning, "tidyup", "no JSON in the answer")
            return
        }
        log?.add(.info, "tidyup", "merge \(proposal.mergedCount), done \(proposal.done.count), not a task \(proposal.notTask.count)")
        setTidyUp(proposal)
    }

    /// Today's suggestion, without changes to tasks that were closed since.
    var currentTidyUp: TaskTidyUp.Proposal? {
        guard let tidyUp else { return nil }
        let open = Set(tasks.filter(\.isOpen).map(\.id))
        let current = tidyUp.restricted(to: open)
        return current.isEmpty ? nil : current
    }

    /// "Not now": the card goes until tomorrow's tidy-up.
    func dismissTidyUp() {
        setTidyUp(nil)
    }

    /// Applies the changes the user kept, one PATCH each; the card goes. Returns how many were saved.
    @discardableResult
    func applyTidyUp(_ edits: [TaskTidyUp.Edit]) async -> Int {
        var saved = 0
        for edit in edits {
            let into: String? = if case let .merge(keep) = edit.kind { keep } else { nil }
            if await setStatus(edit.taskID, edit.status, supersededBy: into) { saved += 1 }
        }
        log?.add(.info, "tidyup", "applied \(saved) of \(edits.count)")
        setTidyUp(nil)
        return saved
    }

    // MARK: Private

    private func askTidyUp(_ prompt: String) async -> String? {
        guard let session = await tidyUpSession() else {
            log?.add(.warning, "tidyup", "no chat session")
            return nil
        }
        var text = ""
        do {
            for try await event in api.sendMessage(prompt, context: nil, sessionID: session) {
                switch event {
                case let .delta(delta): text += delta
                case let .done(message): if !message.text.isEmpty { text = message.text }
                case let .failed(reason):
                    log?.add(.warning, "tidyup", "agent failed: \(reason)")
                    return nil
                case .step, .memorySaved, .deviceTool: break
                }
            }
        } catch {
            // A session that is gone: a new one tomorrow.
            defaults?.removeObject(forKey: Self.tidyUpSessionKey)
            log?.add(.warning, "tidyup", "request failed: \(error)")
            return nil
        }
        return text
    }

    private func tidyUpSession() async -> String? {
        // The stored thread only if it is this account's (another account may have signed in since).
        if let stored = defaults?.string(forKey: Self.tidyUpSessionKey),
           let mine = try? await api.chatSessions(appID: Self.tidyUpSessionAppID), mine.contains(where: { $0.id == stored })
        {
            return stored
        }
        // Without the app id the ✦ title still keeps it out of the chat's list.
        var created = try? await api.createChatSession(title: Self.tidyUpSessionTitle, appID: Self.tidyUpSessionAppID)
        if created == nil { created = try? await api.createChatSession(title: Self.tidyUpSessionTitle) }
        guard let created else { return nil }
        defaults?.set(created, forKey: Self.tidyUpSessionKey)
        return created
    }

    private func markTidyUpRun(_ now: Date) {
        lastTidyUpInMemory = now.timeIntervalSince1970
        defaults?.set(now.timeIntervalSince1970, forKey: Self.tidyUpLastRunKey)
    }

    private func setTidyUp(_ proposal: TaskTidyUp.Proposal?) {
        tidyUp = proposal
        if let proposal, let data = try? JSONEncoder().encode(proposal) {
            defaults?.set(data, forKey: Self.tidyUpProposalKey)
        } else {
            defaults?.removeObject(forKey: Self.tidyUpProposalKey)
        }
    }

    internal func restoreTidyUp() {
        guard let data = defaults?.data(forKey: Self.tidyUpProposalKey) else { return }
        tidyUp = try? JSONDecoder().decode(TaskTidyUp.Proposal.self, from: data)
    }
}

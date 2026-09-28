import Foundation
import OmiKit

// AppStore orchestration, continued: cloud reads + pagination
// (useDesktopReads.ts), chat (AppOrchestrator.tsx send/older/cancel), task
// mutations (useTaskMutations.ts), and devices (useNativeDevices.ts).

// MARK: - Pure helpers (unit-tested)

/// Port of the TS `send()` transcript settle: replaces the optimistic local
/// + pending rows with the canonical pair, preserving the echo position.
public func settleChatTranscript(
    current: [ChatMessage],
    echoId: String,
    pendingId: String,
    human: ChatMessage,
    assistant: ChatMessage?
) -> [ChatMessage] {
    let echoIndex = current.firstIndex { $0.id == echoId }
    let withoutCanonical = current.filter { message in
        message.id != echoId
            && message.id != human.id
            && message.id != assistant?.id
            && message.id != pendingId
    }
    let canonical = assistant == nil ? [human] : [human, assistant!]
    guard let echoIndex else {
        return withoutCanonical + canonical
    }
    let insertAt = min(echoIndex, withoutCanonical.count)
    return
        Array(withoutCanonical[..<insertAt])
        + canonical
        + Array(withoutCanonical[insertAt...])
}

/// Local capture groups → timeline capture summaries. Today the only source
/// of `rewindGroups` is the host capture engine (not yet bridged into this
/// store), so the feed is honestly empty until frames arrive.
public func captureSummaries(
    from groups: [RewindCaptureGroup]
) -> [CaptureGroupSummary] {
    groups.map { group in
        CaptureGroupSummary(
            id: group.id,
            title: group.windowTitle.isEmpty ? group.appName : group.windowTitle,
            appName: group.appName,
            capturedAtMs: group.capturedAtMs,
            count: group.count
        )
    }
}

extension AppStore {
    // MARK: - Reads refresh (useDesktopReads.ts)

    public func refreshReads() async {
        await refreshReads(initial: false)
    }

    /// Port of `refreshReads(initial:options:)`. Cloud reads only run for a
    /// ready session; signed-out and probing Macs never hit the projections.
    func refreshReads(initial: Bool) async {
        guard sessionReady else {
            resetReads()
            return
        }
        guard let reads = services.reads else {
            refreshSeqBump()
            var unavailable = outcomes
            unavailable = DesktopReadOutcomes(
                conversations: .error(desktopBackendConfigurationCopy),
                memories: .error(desktopBackendConfigurationCopy),
                tasks: .error(desktopBackendConfigurationCopy))
            outcomes = unavailable
            readsPhase = .unavailable
            syncPostSetupCue()
            return
        }
        let sequence = refreshSeqBump()
        let stillCurrent = { sequence == self.runtime.refreshSeq }
        runtime.conversationPagePending = false
        runtime.taskPagePending = false
        runtime.memoryPagePending = false
        tasksLoadingMore = false
        taskNotice = nil
        conversationsLoadingMore = false
        conversationNotice = nil
        memoriesLoadingMore = false
        memoriesNotice = nil
        runtime.refreshPending = true
        defer {
            if stillCurrent() {
                runtime.refreshPending = false
            }
        }
        readsPhase =
            initial && outcomes == nil
            ? .initialLoading : .refreshing
        do {
            var fresh = await reads.loadDesktopReads()
            guard stillCurrent() else { return }
            // Sessions that loaded extra pages re-validate their whole window
            // so a refresh never silently truncates what the user can see.
            if runtime.conversationsExtended,
                case .success(let previousConversations) = outcomes?.conversations,
                case .success = fresh.conversations
            {
                guard
                    let revalidated = try await revalidateLoadedWindow(
                        { cursor in try await reads.loadConversations(cursor: cursor) },
                        idOf: { $0.id }, previousCount: previousConversations.items.count,
                        stillCurrent: stillCurrent)
                else { return }
                fresh.conversations = .success(revalidated)
            }
            guard stillCurrent() else { return }
            if runtime.tasksExtended,
                case .success(let previousTasks) = outcomes?.tasks,
                case .success = fresh.tasks
            {
                guard
                    let revalidated = try await revalidateTasksWindow(
                        reads, previousCount: previousTasks.items.count,
                        stillCurrent: stillCurrent)
                else { return }
                fresh.tasks = .success(revalidated)
            }
            guard stillCurrent() else { return }
            // Merge first, then judge the phase from what the shell will
            // actually show. Transient service failures keep prior rows.
            let next: DesktopReadOutcomes
            if let previous = outcomes {
                next = DesktopReadOutcomes(
                    conversations: mergedOutcome(
                        previous.conversations, fresh.conversations),
                    memories: mergedOutcome(previous.memories, fresh.memories),
                    tasks: mergedTaskOutcome(previous.tasks, fresh.tasks))
            } else {
                next = fresh
            }
            outcomes = next
            if case .success(let tasksValue) = next.tasks {
                tasksRead = tasksValue
            } else {
                tasksRead = nil
            }
            let showingSavedRows =
                outcomeHasRows(next.conversations)
                || outcomeHasRowsMemory(next.memories)
                || outcomeHasRowsTask(next.tasks)
            // A projection the backend legitimately cannot serve yet is not a
            // Home-level "history failed" nag: only hard failures degrade.
            let hardFailed =
                outcomeHardFailed(next.conversations)
                || outcomeHardFailedMemory(next.memories)
                || outcomeHardFailedTask(next.tasks)
            readsPhase = deriveReadsPhase(
                showingSavedRows: showingSavedRows, hardFailed: hardFailed)
            syncPostSetupCue()
        } catch {
            guard stillCurrent() else { return }
            let retained = outcomes
            let showingSavedRows =
                retained != nil
                && (outcomeHasRows(retained!.conversations)
                    || outcomeHasRowsMemory(retained!.memories)
                    || outcomeHasRowsTask(retained!.tasks))
            readsPhase = deriveReadsPhase(
                showingSavedRows: showingSavedRows, hardFailed: true)
            syncPostSetupCue()
        }
    }

    private func refreshSeqBump() -> Int {
        runtime.refreshSeq += 1
        return runtime.refreshSeq
    }

    private func outcomeHasRows(_ outcome: ReadOutcome<DomainRead<ConversationProjection>>) -> Bool {
        if case .success(let value) = outcome { return !value.items.isEmpty }
        return false
    }

    private func outcomeHasRowsMemory(_ outcome: ReadOutcome<DomainRead<MemoryProjection>>) -> Bool {
        if case .success(let value) = outcome { return !value.items.isEmpty }
        return false
    }

    private func outcomeHasRowsTask(_ outcome: ReadOutcome<TaskRead>) -> Bool {
        if case .success(let value) = outcome { return !value.items.isEmpty }
        return false
    }

    private func outcomeHardFailed(
        _ outcome: ReadOutcome<DomainRead<ConversationProjection>>
    ) -> Bool {
        if case .error(let message) = outcome {
            return message != desktopProjectionUnavailableCopy
        }
        return false
    }

    private func outcomeHardFailedMemory(
        _ outcome: ReadOutcome<DomainRead<MemoryProjection>>
    ) -> Bool {
        if case .error(let message) = outcome {
            return message != desktopProjectionUnavailableCopy
        }
        return false
    }

    private func outcomeHardFailedTask(_ outcome: ReadOutcome<TaskRead>) -> Bool {
        if case .error(let message) = outcome {
            return message != desktopProjectionUnavailableCopy
        }
        return false
    }

    /// Port of `mergeOutcome`: a transient service failure never replaces
    /// loaded rows.
    private func mergedOutcome(
        _ current: ReadOutcome<DomainRead<ConversationProjection>>,
        _ next: ReadOutcome<DomainRead<ConversationProjection>>
    ) -> ReadOutcome<DomainRead<ConversationProjection>> {
        mergeOutcomeRows(current, next) { !($0?.items.isEmpty ?? true) }
    }

    private func mergedOutcome(
        _ current: ReadOutcome<DomainRead<MemoryProjection>>,
        _ next: ReadOutcome<DomainRead<MemoryProjection>>
    ) -> ReadOutcome<DomainRead<MemoryProjection>> {
        mergeOutcomeRows(current, next) { !($0?.items.isEmpty ?? true) }
    }

    private func mergedTaskOutcome(
        _ current: ReadOutcome<TaskRead>, _ next: ReadOutcome<TaskRead>
    ) -> ReadOutcome<TaskRead> {
        mergeOutcomeRows(current, next) { !($0?.items.isEmpty ?? true) }
    }

    private func mergeOutcomeRows<Value>(
        _ current: ReadOutcome<Value>, _ next: ReadOutcome<Value>,
        hasRows: (Value?) -> Bool
    ) -> ReadOutcome<Value> {
        let transientFailure: Bool
        if case .error(let message) = next {
            transientFailure =
                message == desktopBackendServiceCopy
                || message == desktopLocalBackendServiceCopy
        } else {
            transientFailure = false
        }
        let currentHasRows: Bool
        if case .success(let value) = current {
            currentHasRows = hasRows(value)
        } else {
            currentHasRows = false
        }
        return currentHasRows && transientFailure ? current : next
    }

    /// Port of `revalidateLoadedWindow` for the canonical projections.
    private func revalidateLoadedWindow<T: Sendable>(
        _ load: (String?) async throws -> DomainRead<T>,
        idOf: (T) -> String,
        previousCount: Int,
        stillCurrent: () -> Bool
    ) async throws -> DomainRead<T>? {
        var items: [T] = []
        var ids = Set<String>()
        var cursor: String?
        var latest: DomainRead<T>?
        while items.count < 10_000 {
            if !stillCurrent() { return nil }
            let page = try await load(cursor)
            if !stillCurrent() { return nil }
            for item in page.items {
                let itemId = idOf(item)
                if ids.contains(itemId) {
                    throw ReadCopyError("Loaded page did not advance")
                }
                ids.insert(itemId)
                items.append(item)
            }
            latest = page
            cursor = page.page.nextCursor
            if items.count >= previousCount || !page.page.hasMore || cursor == nil {
                break
            }
        }
        guard let latest, stillCurrent() else { return nil }
        return DomainRead(items: items, page: latest.page)
    }

    private func revalidateTasksWindow(
        _ reads: ReadsServicing,
        previousCount: Int,
        stillCurrent: () -> Bool
    ) async throws -> TaskRead? {
        var items: [TaskProjection] = []
        var ids = Set<String>()
        var cursor: String?
        var latest: TaskRead?
        while items.count < 10_000 {
            if !stillCurrent() { return nil }
            let page = try await reads.loadTasks(cursor: cursor)
            if !stillCurrent() { return nil }
            for item in page.items {
                if ids.contains(item.id) {
                    throw ReadCopyError("Loaded page did not advance")
                }
                ids.insert(item.id)
                items.append(item)
            }
            latest = page
            cursor = page.page.nextCursor
            if items.count >= previousCount || !page.page.hasMore || cursor == nil {
                break
            }
        }
        guard let latest, stillCurrent() else { return nil }
        return TaskRead(
            apiContract: latest.apiContract, items: items, page: latest.page,
            accountEpoch: latest.accountEpoch)
    }

    /// Drops every saved row and phase so the next session starts at a
    /// truthful initial-loading (port of `resetReads`).
    func resetReads() {
        runtime.refreshSeq += 1
        runtime.refreshPending = false
        runtime.conversationPagePending = false
        runtime.taskPagePending = false
        runtime.memoryPagePending = false
        tasksLoadingMore = false
        taskNotice = nil
        conversationsLoadingMore = false
        conversationNotice = nil
        memoriesLoadingMore = false
        memoriesNotice = nil
        outcomes = nil
        tasksRead = nil
        runtime.conversationsExtended = false
        runtime.tasksExtended = false
        conversationsExtended = false
        readsPhase = .initialLoading
        syncPostSetupCue()
    }

    // MARK: - Pagination (loadMore in useDesktopReads.ts)

    public func loadOlderConversations() async {
        await loadMoreConversationsOrMemories(kind: .conversations)
    }

    public func loadOlderMemories() async {
        await loadMoreConversationsOrMemories(kind: .memories)
    }

    private enum OlderReadKind {
        case conversations
        case memories
    }

    private func loadMoreConversationsOrMemories(kind: OlderReadKind) async {
        guard sessionReady, let reads = services.reads else { return }
        let pending: Bool
        let refreshPending: Bool
        switch kind {
        case .conversations:
            pending = runtime.conversationPagePending
            refreshPending = runtime.refreshPending
        case .memories:
            pending = runtime.memoryPagePending
            refreshPending = runtime.refreshPending
        }
        guard !pending, !refreshPending else { return }
        guard let current = outcomes else { return }
        let previousOutcome: ReadOutcome<DomainRead<ConversationProjection>>?
        let previousMemoryOutcome: ReadOutcome<DomainRead<MemoryProjection>>?
        switch kind {
        case .conversations:
            previousOutcome = current.conversations
            previousMemoryOutcome = nil
        case .memories:
            previousOutcome = nil
            previousMemoryOutcome = current.memories
        }
        let previousPage: ReadPageState?
        let previousItems: Int
        if kind == .conversations {
            guard case .success(let value) = previousOutcome! else { return }
            previousPage = value.page
            previousItems = value.items.count
        } else {
            guard case .success(let value) = previousMemoryOutcome! else { return }
            previousPage = value.page
            previousItems = value.items.count
        }
        guard let page = previousPage, page.hasMore, let cursor = page.nextCursor else {
            return
        }
        let sequence = runtime.refreshSeq
        switch kind {
        case .conversations:
            runtime.conversationPagePending = true
            conversationsLoadingMore = true
            conversationNotice = nil
        case .memories:
            runtime.memoryPagePending = true
            memoriesLoadingMore = true
            memoriesNotice = nil
        }
        defer {
            if sequence == runtime.refreshSeq {
                switch kind {
                case .conversations:
                    runtime.conversationPagePending = false
                    conversationsLoadingMore = false
                case .memories:
                    runtime.memoryPagePending = false
                    memoriesLoadingMore = false
                }
            }
        }
        do {
            var replace = false
            var next: DomainRead<ConversationProjection>?
            var nextMemory: DomainRead<MemoryProjection>?
            do {
                if kind == .conversations {
                    next = try await reads.loadConversations(cursor: cursor)
                } else {
                    nextMemory = try await reads.loadMemories(cursor: cursor)
                }
            } catch {
                let expired: Bool
                if kind == .conversations {
                    expired = isConversationCursorExpired(error)
                } else {
                    expired = isTaskCursorExpiredShaped(error)
                }
                guard expired, sequence == runtime.refreshSeq else { throw error }
                replace = true
                if kind == .conversations {
                    next = try await reads.loadConversations(cursor: nil)
                } else {
                    nextMemory = try await reads.loadMemories(cursor: nil)
                }
            }
            guard sequence == runtime.refreshSeq, let live = outcomes else { return }
            if kind == .conversations {
                guard case .success(let currentValue) = live.conversations else { return }
                let mergedItems = replace
                    ? next!.items
                    : currentValue.items + next!.items
                if mergedItems.count > 10_000 {
                    throw ReadCopyError("Conversation list is too large")
                }
                try validatePageAppend(
                    mergedItems.map { $0.id }, appended: next!.items.count,
                    replace: replace, nextPage: next!.page, cursor: cursor)
                let merged = DomainRead(items: mergedItems, page: next!.page)
                outcomes = DesktopReadOutcomes(
                    conversations: .success(merged),
                    memories: live.memories, tasks: live.tasks)
                runtime.conversationsExtended = !replace && mergedItems.count > next!.items.count
                conversationsExtended = runtime.conversationsExtended
                if replace {
                    conversationNotice = "Conversations changed. The list has been refreshed."
                }
            } else {
                guard case .success(let currentValue) = live.memories else { return }
                let mergedItems = replace
                    ? nextMemory!.items
                    : currentValue.items + nextMemory!.items
                if mergedItems.count > 10_000 {
                    throw ReadCopyError("Memory list is too large")
                }
                try validatePageAppend(
                    mergedItems.map { $0.id }, appended: nextMemory!.items.count,
                    replace: replace, nextPage: nextMemory!.page, cursor: cursor)
                let merged = DomainRead(items: mergedItems, page: nextMemory!.page)
                outcomes = DesktopReadOutcomes(
                    conversations: live.conversations,
                    memories: .success(merged), tasks: live.tasks)
                if replace {
                    memoriesNotice = "Memories changed. The list has been refreshed."
                }
            }
            _ = previousItems
        } catch {
            if sequence == runtime.refreshSeq {
                switch kind {
                case .conversations:
                    conversationNotice = "More conversations could not be loaded. Try again."
                case .memories:
                    memoriesNotice = "More memories could not be loaded. Try again."
                }
            }
        }
    }

    public func loadOlderTasks() async {
        guard sessionReady, let reads = services.reads else { return }
        guard !runtime.taskPagePending, !runtime.refreshPending else { return }
        guard let current = outcomes,
            case .success(let value) = current.tasks,
            value.page.hasMore, let cursor = value.page.nextCursor
        else { return }
        let sequence = runtime.refreshSeq
        runtime.taskPagePending = true
        tasksLoadingMore = true
        taskNotice = nil
        defer {
            if sequence == runtime.refreshSeq {
                runtime.taskPagePending = false
                tasksLoadingMore = false
            }
        }
        do {
            var replace = false
            var next: TaskRead
            do {
                next = try await reads.loadTasks(cursor: cursor)
            } catch {
                guard isTaskCursorExpiredShaped(error), sequence == runtime.refreshSeq
                else { throw error }
                replace = true
                next = try await reads.loadTasks(cursor: nil)
            }
            guard sequence == runtime.refreshSeq, let live = outcomes,
                case .success(let currentValue) = live.tasks
            else { return }
            if !replace, next.accountEpoch != currentValue.accountEpoch {
                // An appended page from a different account epoch must never
                // merge into the visible list.
                throw ReadCopyError("Task account epoch changed")
            }
            let items = replace ? next.items : currentValue.items + next.items
            if items.count > 10_000 {
                throw ReadCopyError("Task list is too large")
            }
            try validatePageAppend(
                items.map { $0.id }, appended: next.items.count, replace: replace,
                nextPage: next.page, cursor: cursor)
            let merged = TaskRead(
                apiContract: next.apiContract, items: items, page: next.page,
                accountEpoch: next.accountEpoch)
            outcomes = DesktopReadOutcomes(
                conversations: live.conversations, memories: live.memories,
                tasks: .success(merged))
            tasksRead = merged
            runtime.tasksExtended = !replace && items.count > next.items.count
            if replace {
                taskNotice = "Tasks changed. The list has been refreshed."
            }
        } catch {
            if sequence == runtime.refreshSeq {
                taskNotice = "More tasks could not be loaded. Try again."
            }
        }
    }

    /// Post-cursor-expiry replacement uses the fresh read directly, so the
    /// cursor check only guards an append that claims more pages.
    private func validatePageAppend(
        _ mergedIds: [String], appended: Int, replace: Bool,
        nextPage: ReadPageState, cursor: String
    ) throws {
        if Set(mergedIds).count != mergedIds.count {
            throw ReadCopyError("Page did not advance")
        }
        if !replace, nextPage.hasMore, nextPage.nextCursor == cursor {
            throw ReadCopyError("Page did not advance")
        }
        _ = appended
    }

    private func isConversationCursorExpired(_ error: Error) -> Bool {
        if let cursorError = error as? ReadCursorError {
            if case ReadCursorError.conversationExpired = cursorError { return true }
            return false
        }
        return false
    }

    /// The legacy Omi plane reports cursor expiry through the same 400 shape
    /// for tasks and memories; the typed error only exists for canonical.
    private func isTaskCursorExpiredShaped(_ error: Error) -> Bool {
        if let cursorError = error as? ReadCursorError {
            if case ReadCursorError.taskExpired = cursorError { return true }
            return false
        }
        return false
    }

    /// Port of `refreshTasks` — the post-mutation acknowledgement read.
    /// Returns nil when the read failed or was retired.
    func refreshTasks() async -> TaskRead? {
        guard sessionReady, let reads = services.reads else { return nil }
        let sequence = refreshSeqBump()
        let stillCurrent = { sequence == self.runtime.refreshSeq }
        runtime.conversationPagePending = false
        runtime.taskPagePending = false
        runtime.memoryPagePending = false
        tasksLoadingMore = false
        taskNotice = nil
        conversationsLoadingMore = false
        runtime.refreshPending = true
        defer {
            if stillCurrent() {
                runtime.refreshPending = false
            }
        }
        do {
            let tasks = try await reads.loadTasks(cursor: nil)
            guard stillCurrent(), let previous = outcomes else { return nil }
            var mergedTasks = tasks
            if runtime.tasksExtended,
                case .success(let previousTasks) = previous.tasks
            {
                guard
                    let revalidated = try await revalidateTasksWindow(
                        reads, previousCount: previousTasks.items.count,
                        stillCurrent: stillCurrent)
                else { return nil }
                mergedTasks = revalidated
            }
            guard stillCurrent() else { return nil }
            let next = DesktopReadOutcomes(
                conversations: previous.conversations, memories: previous.memories,
                tasks: .success(mergedTasks))
            outcomes = next
            tasksRead = mergedTasks
            let homeFailed =
                isErrorConversations(next.conversations) || isErrorMemories(next.memories)
            readsPhase = homeFailed ? .savedButRefreshFailed : .ready
            syncPostSetupCue()
            return mergedTasks
        } catch {
            return nil
        }
    }

    private func isErrorConversations(_ outcome: ReadOutcome<DomainRead<ConversationProjection>>) -> Bool {
        if case .error = outcome { return true }
        return false
    }

    private func isErrorMemories(_ outcome: ReadOutcome<DomainRead<MemoryProjection>>) -> Bool {
        if case .error = outcome { return true }
        return false
    }

    // MARK: - Remote glance line (useRemoteGlanceLine.ts)

    /// Asks the canonical worker for a composed glance line, throttled to one
    /// fetch per `glanceRefreshMs` (upstream fetchedAtRef). Failures leave
    /// the previous line — and nil — untouched, so the local line stays up.
    public func refreshGlance(context: DesktopGlanceContext) async {
        // Upstream returns before stamping when there is no backend at all;
        // the throttle only gates real fetch attempts.
        guard let transport = services.transport else { return }
        let now = appNowMilliseconds()
        guard now - runtime.glanceFetchedAtMs >= glanceRefreshMs else { return }
        // Upstream stamps the ref before the request so a hang can't loop.
        runtime.glanceFetchedAtMs = now
        if let line = await loadDesktopGlance(transport, context: context) {
            glanceLine = line
        }
    }
}

/// 5-minute remote-glance throttle (GLANCE_REFRESH_MS).
public let glanceRefreshMs: Int64 = 5 * 60 * 1000


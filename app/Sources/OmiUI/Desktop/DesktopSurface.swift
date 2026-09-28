import OmiKit
import SwiftUI

// The desktop root (`DesktopApp.tsx`): session gate, the 12/44 window-inset
// padding, chrome rows, stage with page transition (`ShippingStage`), the
// chat overlay + inline ask card, and the post-setup overlay. Both interface
// versions render here: v5.1 (Activity IA, default) and v5 (pages IA,
// selected via the `omi.uiVersion` preference).

public struct DesktopSurface: View {
    @EnvironmentObject var store: AppStore

    @Environment(\.desktopTokens) private var tokens
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    // v5.1 Activity state (chrome-owned: filters are not routes).
    @State private var desktopRoute: DesktopRoute = DesktopRoute.home
    @State private var mode: OmnibarMode = OmnibarMode.ask
    @State private var filter: TimelineFilter = TimelineFilter.all
    @State private var groupBy: TimelineGrouping = TimelineGrouping.date
    @State private var chatOpen = false
    @State private var inlineAnswerOpen = false
    @State private var focusCaptureId: String?
    @State private var guideTarget: ExploreCheck?

    // v5 pages IA rail selection ("Home" | "Chat" | "Conversations" |
    // "Rewind" | "Tasks" | "Settings").
    @State private var v5Selection: String = "Home"

    @State private var searchCommandObserver: (any NSObjectProtocol)?
    @State private var proveItDismissed = false

    public init() {}

    // MARK: Session gate (DesktopApp.tsx)

    private var session: DesktopSessionPhase {
        switch store.authState {
        case AuthUiState.signedOut, AuthUiState.onboarding: return DesktopSessionPhase.signedOut
        case AuthUiState.signingIn: return DesktopSessionPhase.probing
        case AuthUiState.signedIn: return DesktopSessionPhase.ready
        }
    }
    public var body: some View {
        let palette = DesktopPalettes.tokens(
            store.preferences.appearance == DesktopAppearance.light ? DesktopThemeName.light : DesktopThemeName.dark
        )
        DesktopRootSurface(tokens: palette) {
            content
                .padding(DesktopLayout.windowInset)
                .environment(\.desktopTokens, palette)
        }
        .onAppear {
            if session != DesktopSessionPhase.ready {
                desktopRoute = DesktopRoute.home
            }
            Task { await store.refreshReads() }
        }
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name(DesktopWindowSignals.searchCommand))) { _ in
            // Edit → Search (Cmd+K): Search mode, Home, all filter, focus.
            mode = OmnibarMode.search
            chatOpen = false
            desktopRoute = DesktopRoute.home
            filter = TimelineFilter.all
        }
    }

    @ViewBuilder
    private var content: some View {
        switch session {
        case DesktopSessionPhase.probing:
            DesktopSessionProbe()
        case DesktopSessionPhase.signedOut:
            DesktopOnboardingPage(returning: store.returningUser)
        case DesktopSessionPhase.ready:
            readySurface
        }
    }

    // MARK: Ready surface

    @ViewBuilder
    private var readySurface: some View {
        if store.preferences.uiVersion == DesktopUiVersion.v5 {
            v5Shell
        } else {
            v51Shell
        }
    }

    // MARK: v5.1 Activity IA (DesktopApp.tsx)

    private var v51Shell: some View {
        VStack(alignment: .leading, spacing: 10) {
            DesktopOmnibarRow(
                store: store,
                mode: mode,
                onModeChange: { next in
                    mode = next
                    if next == OmnibarMode.search {
                        chatOpen = false
                        inlineAnswerOpen = false
                        desktopRoute = DesktopRoute.rewind
                    } else if desktopRoute == DesktopRoute.rewind {
                        desktopRoute = DesktopRoute.home
                        filter = TimelineFilter.all
                    }
                },
                onSend: {
                    if mode == OmnibarMode.ask {
                        inlineAnswerOpen = true
                        let text = store.searchQuery
                        Task {
                            await store.sendChat(text)
                        }
                    } else {
                        desktopRoute = DesktopRoute.rewind
                    }
                },
                onStop: {
                    Task { await store.cancelChatGeneration() }
                },
                route: desktopRoute,
                onNavigate: { next in
                    chatOpen = false
                    desktopRoute = next
                    if next == DesktopRoute.rewind {
                        mode = OmnibarMode.search
                    } else if mode == OmnibarMode.search {
                        mode = OmnibarMode.ask
                    }
                },
                chatBusy: store.chatBusy || store.activeGenerationId != nil,
                captureActive: captureActive,
                captureAvailable: captureAvailable,
                onToggleCapture: captureAvailable
                    ? {
                        Task {
                            await store.setPreference(
                                desktopPreferenceKeys.screenCapture,
                                PreferenceValue.bool(!captureActive)
                            )
                            if !captureActive {
                                await store.requestPermission(PermissionKind.screen)
                            }
                        }
                    }
                    : nil
            )

            DesktopFilterRow(
                filter: filter,
                onFilterChange: { next in
                    chatOpen = false
                    if mode == OmnibarMode.search {
                        mode = OmnibarMode.ask
                    }
                    filter = next
                    desktopRoute = DesktopRoute.home
                },
                groupBy: groupBy,
                onGroupByChange: { groupBy = $0 }
            )

            // Stage with the page transition (ShippingStage variant "page").
            ZStack {
                switch desktopRoute {
                case DesktopRoute.home:
                    stagePage(key: "Home") {
                        DesktopActivityPage(
                            filter: filter,
                            groupBy: groupBy,
                            exploreDone: exploreDone,
                            onExploreItem: startExploreGuide,
                            onOpenCapture: { capture in
                                focusCaptureId = capture.id
                                mode = OmnibarMode.search
                                desktopRoute = DesktopRoute.rewind
                            }
                        )
                    }
                case DesktopRoute.rewind:
                    stagePage(key: "Rewind") {
                        DesktopRewindPage(
                            query: mode == OmnibarMode.search ? store.searchQuery : "",
                            focusGroupId: focusCaptureId
                        )
                    }
                case DesktopRoute.settings:
                    stagePage(key: "Settings") {
                        DesktopSettingsPage()
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .overlay(alignment: .top) {
            if inlineAnswerOpen && !chatOpen {
                InlineAskCard(
                    busy: store.chatBusy || store.activeGenerationId != nil,
                    notice: visibleChatError(session, store.chatErrorCopy),
                    onClose: { inlineAnswerOpen = false },
                    onOpenChat: openChat
                )
                .padding(.top, DesktopLayout.omnibarHeight + 40)
                .frame(maxWidth: 560)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .overlay {
            if chatOpen {
                DesktopChatOverlay(
                    notice: visibleChatError(session, store.chatErrorCopy),
                    onClose: { chatOpen = false },
                    onSuggest: { prompt in
                        mode = OmnibarMode.ask
                        store.searchQuery = prompt
                    }
                )
                .zIndex(3)
            }
        }
        .animation(
            DesktopMotion.searchExpandAnimation(reduceMotion),
            value: inlineAnswerOpen
        )
        .overlay {
            if store.postSetupHomeCue == PostSetupHomeCue.proven && store.readsPhase == ReadsPhase.ready
                && !proveItDismissed
            {
                DesktopPostSetupOverlay {
                    proveItDismissed = true
                }
                .zIndex(4)
            }
        }
        .task(id: mode) {
            markArrival()
        }
        .task(id: desktopRoute) {
            markArrival()
            // Arriving at Rewind from Search keeps the query live.
            if desktopRoute == DesktopRoute.home {
                focusCaptureId = nil
            }
        }
    }

    // MARK: v5 pages IA (DesktopShellV5.tsx)

    private var v5Shell: some View {
        VStack(alignment: .leading, spacing: 14) {
            DesktopOmnibarRow(
                store: store,
                mode: mode,
                onModeChange: { next in
                    mode = next
                    if next == OmnibarMode.search {
                        v5Selection = "Rewind"
                    } else if v5Selection == "Rewind" {
                        v5Selection = "Home"
                    }
                },
                onSend: {
                    if mode == OmnibarMode.ask {
                        chatOpen = true
                        let text = store.searchQuery
                        Task {
                            await store.sendChat(text)
                        }
                    } else {
                        v5Selection = "Rewind"
                    }
                },
                onStop: {
                    Task { await store.cancelChatGeneration() }
                },
                route: v5Selection == "Settings" ? DesktopRoute.settings : DesktopRoute.home,
                onNavigate: { _ in
                    // The gear always lands on Settings in the pages IA.
                    withAnimation(DesktopMotion.navAnimation(reduceMotion)) {
                        v5Selection = "Settings"
                    }
                },
                chatBusy: store.chatBusy || store.activeGenerationId != nil,
                captureActive: captureActive,
                captureAvailable: captureAvailable,
                onToggleCapture: captureAvailable
                    ? {
                        Task {
                            await store.setPreference(
                                desktopPreferenceKeys.screenCapture,
                                PreferenceValue.bool(!captureActive)
                            )
                        }
                    }
                    : nil
            )

            ZStack {
                switch v5Selection {
                case "Chat":
                    stagePage(key: "Chat") {
                        DesktopChatTranscript(onSuggest: { prompt in
                            mode = OmnibarMode.ask
                            store.searchQuery = prompt
                        })
                    }
                case "Conversations":
                    stagePage(key: "Conversations") {
                        DesktopLibraryPage()
                    }
                case "Rewind":
                    stagePage(key: "Rewind") {
                        DesktopRewindPage(query: mode == OmnibarMode.search ? store.searchQuery : "")
                    }
                case "Tasks":
                    stagePage(key: "Tasks") {
                        DesktopTasksPage()
                    }
                case "Settings":
                    stagePage(key: "Settings") {
                        DesktopSettingsPage()
                    }
                default:
                    stagePage(key: "Home") {
                        DesktopActivityPage(
                            filter: filter,
                            groupBy: groupBy,
                            exploreDone: exploreDone,
                            onExploreItem: startExploreGuide,
                            onOpenCapture: { _ in v5Selection = "Rewind" }
                        )
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task(id: v5Selection) {
            markArrival()
        }
    }

    // MARK: Stage transition (ShippingStage.tsx variant "page")

    @ViewBuilder
    private func stagePage<Stage: View>(key: String, @ViewBuilder stage: () -> Stage) -> some View {
        stage()
            .id(key)
            .opacity(1)
            .transition(
                .opacity
                    .combined(with: .offset(y: DesktopMotion.chatRiseY))
            )
            .animation(DesktopMotion.navAnimation(reduceMotion), value: key)
    }

    // MARK: Derived state

    private var captureActive: Bool {
        store.rewindCaptureState.capturing
    }

    /// The toggle hides while capture is unavailable
    /// (`RewindCaptureState.available`); busy disables it mid-transition.
    private var captureAvailable: Bool {
        session == DesktopSessionPhase.ready && store.rewindCaptureState.available
    }

    private var exploreDone: Set<ExploreCheck> {
        parseExploreProgress(store.preferences.exploreProgress)
    }

    /// Arriving at a surface ticks its checklist item off, once, forever
    /// (progress persists through `omi.onboarding.exploreProgress`, per-IA).
    private func markArrival() {
        var done = exploreDone
        func record(_ check: ExploreCheck) {
            guard !done.contains(check) else { return }
            done.insert(check)
            Task {
                await store.setPreference(
                    desktopPreferenceKeys.exploreProgress,
                    PreferenceValue.string(serializeExploreProgress(done))
                )
            }
        }
        if chatOpen {
            record(ExploreCheck.chat)
            return
        }
        if store.preferences.uiVersion == DesktopUiVersion.v5 {
            switch v5Selection {
            case "Rewind": record(ExploreCheck.recall)
            case "Conversations": record(ExploreCheck.conversations)
            case "Tasks": record(ExploreCheck.tasks)
            case "Settings": record(ExploreCheck.settings)
            default: break
            }
            return
        }
        switch desktopRoute {
        case DesktopRoute.settings:
            record(ExploreCheck.settings)
        case DesktopRoute.home:
            switch filter {
            case TimelineFilter.conversations: record(ExploreCheck.conversations)
            case TimelineFilter.tasks: record(ExploreCheck.tasks)
            case TimelineFilter.recall: record(ExploreCheck.recall)
            default: break
            }
        case DesktopRoute.rewind:
            record(ExploreCheck.recall)
        }
    }

    /// The checklist item's destination flies open with the guide highlight.
    private func startExploreGuide(_ check: ExploreCheck) {
        switch check {
        case ExploreCheck.chat:
            openChat()
        case ExploreCheck.settings:
            if store.preferences.uiVersion == DesktopUiVersion.v5 {
                v5Selection = "Settings"
            } else {
                desktopRoute = DesktopRoute.settings
            }
            guideTarget = nil
        case ExploreCheck.recall:
            if store.preferences.uiVersion == DesktopUiVersion.v5 {
                v5Selection = "Rewind"
            } else {
                mode = OmnibarMode.search
                desktopRoute = DesktopRoute.rewind
            }
        case ExploreCheck.conversations:
            if store.preferences.uiVersion == DesktopUiVersion.v5 {
                v5Selection = "Conversations"
            } else {
                mode = OmnibarMode.ask
                filter = TimelineFilter.conversations
                desktopRoute = DesktopRoute.home
            }
        case ExploreCheck.tasks:
            if store.preferences.uiVersion == DesktopUiVersion.v5 {
                v5Selection = "Tasks"
            } else {
                mode = OmnibarMode.ask
                filter = TimelineFilter.tasks
                desktopRoute = DesktopRoute.home
            }
        }
        if guideTarget == nil {
            guideTarget = check
        }
    }

    private func openChat() {
        mode = OmnibarMode.ask
        inlineAnswerOpen = false
        chatOpen = true
    }
}

// MARK: - Session probe (DesktopApp.tsx DesktopSessionProbe)

/// The probing window keeps traffic-light space and the mark — never an empty
/// sheet, never signed-in chrome.
struct DesktopSessionProbe: View {
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                // Reserved window-controls slot (12/44 row geometry).
                Color.clear
                    .frame(
                        width: DesktopLayout.trafficLightRowWidth,
                        height: DesktopLayout.trafficLightButton
                    )
                Spacer(minLength: 0)
            }
            .frame(height: DesktopLayout.omnibarHeight, alignment: .center)
            OmiLoadingMark(size: 80, ink: tokens.ink)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .accessibilityLabel("Session check")
    }
}

// MARK: - v5 pages (DesktopPages.tsx LibraryPage / TasksPage)

/// Conversations + memories list (v5 IA). Selection opens the readable detail.
struct DesktopLibraryPage: View {
    @EnvironmentObject var store: AppStore

    @Environment(\.desktopTokens) private var tokens
    @State private var selectedEntryId: String?

    var body: some View {
        let entries = libraryEntries
        FadedScrollView {
            VStack(alignment: .leading, spacing: 0) {
                PageHeading(
                    title: "Conversations",
                    subtitle: "Conversations and memories, newest first."
                )
                ForEach(entries, id: \.id) { entry in
                    Button {
                        selectedEntryId = entry.id == selectedEntryId ? nil : entry.id
                    } label: {
                        ReadRowView(entry: entry)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(GlassPressableStyle())
                    if entry.id == selectedEntryId {
                        detailCard(entry)
                    }
                }
                if entries.isEmpty {
                    EmptyCopy(
                        store.readsLoading
                            ? "Loading conversations…"
                            : "Nothing captured in this window yet."
                    )
                }
                olderButton
            }
            .padding(.horizontal, 8)
        }
        .accessibilityLabel("Conversations")
    }

    /// Conversations + memories newest first, query-matched through the
    /// store's merged timeline (Conversations bucket).
    private var libraryEntries: [TimelineEntry] {
        mergeTimeline(store.outcomes, query: store.searchQuery, filter: TimelineFilter.conversations).entries
    }

    @ViewBuilder
    private func detailCard(_ entry: TimelineEntry) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(entry.title)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(tokens.ink)
            Text(entry.detail.isEmpty ? "No transcript loaded for this entry." : entry.detail)
                .font(.system(size: 14))
                .foregroundStyle(tokens.inkMuted)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14).fill(tokens.glassQuiet))
        .padding(.bottom, 8)
        .accessibilityLabel("Selected details")
    }

    @ViewBuilder
    private var olderButton: some View {
        Button {
            Task { await store.loadOlderConversations() }
        } label: {
            Text(store.readsLoading ? "Loading…" : "Load older")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(tokens.inkMuted)
                .padding(10)
        }
        .buttonStyle(GlassPressableStyle())
        .accessibilityLabel("Load older conversations")
    }
}

/// Tasks page (v5 IA): toggle completion inline.
struct DesktopTasksPage: View {
    @EnvironmentObject var store: AppStore

    @Environment(\.desktopTokens) private var tokens
    @State private var newTaskTitle = ""

    var body: some View {
        let tasks = visibleTasks
        FadedScrollView {
            VStack(alignment: .leading, spacing: 8) {
                PageHeading(title: "Tasks", subtitle: "What you said you'd do.")
                HStack(spacing: 8) {
                    TextField("Add a task", text: $newTaskTitle)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .foregroundStyle(tokens.ink)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 10).fill(tokens.glassQuiet)
                        )
                        .onSubmit {
                            let title = newTaskTitle
                            newTaskTitle = ""
                            Task { await store.addTask(title: title) }
                        }
                }
                ForEach(tasks) { task in
                    TaskRowView(task: task) {
                        Task { await store.toggleTask(task) }
                    }
                }
                if tasks.isEmpty {
                    EmptyCopy(store.readsLoading ? "Loading…" : "No tasks yet")
                }
            }
            .padding(.horizontal, 8)
        }
        .accessibilityLabel("Tasks")
    }

    private var visibleTasks: [TaskProjection] {
        guard let tasksRead = store.tasksRead else { return [] }
        let needle = store.searchQuery.trimmingCharacters(in: .whitespaces).lowercased()
        return tasksRead.items.filter { task in
            needle.isEmpty || task.searchableText.lowercased().contains(needle)
        }
    }
}

// MARK: - Post-setup overlay (PostSetupOverlay.tsx)

/// The "prove it" card: first time the workspace reads ready after setup,
/// point at Search and let the user dismiss it.
struct DesktopPostSetupOverlay: View {
    let onClose: () -> Void

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        ZStack {
            Color.black.opacity(0.16)
            VStack(spacing: 12) {
                DesktopIcon.sparkles
                    .frame(width: 20, height: 20)
                    .foregroundStyle(tokens.ink)
                Text("Your day is in.")
                    .font(.system(size: 19, weight: .medium))
                    .foregroundStyle(tokens.ink)
                Text("Press Search in the omnibar to recall anything you've seen or heard.")
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.inkMuted)
                    .multilineTextAlignment(.center)
                Button {
                    onClose()
                } label: {
                    Text("Got it")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(tokens.surfaceInk)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(RoundedRectangle(cornerRadius: 10).fill(tokens.ink))
                }
                .buttonStyle(GlassPressableStyle())
                .accessibilityLabel("Dismiss")
            }
            .padding(24)
            .frame(maxWidth: 360)
            .background(
                RoundedRectangle(cornerRadius: DesktopLayout.glassCornerRadius)
                    .fill(tokens.surfaceInk)
                    .overlay(
                        RoundedRectangle(cornerRadius: DesktopLayout.glassCornerRadius)
                            .strokeBorder(tokens.lineStrong, lineWidth: 1)
                    )
            )
        }
        .accessibilityLabel("Post setup")
    }
}

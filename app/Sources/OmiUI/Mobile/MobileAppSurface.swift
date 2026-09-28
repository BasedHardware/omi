import OmiKit
import SwiftUI

// Mobile app surface, ported from `react-native/src/mobile/MobileAppSurface.tsx`
// over the shared `AppStore`. Owns the bottom tab navigation, the omnibar
// dock, the home dashboard (action items + recent conversations), the device
// pill and its expandable details, capture status, the edge-fade gradients,
// and the stage routing for Conversations / Tasks / Settings / Apps.

/// Projection read states for the mobile panels (`MobileProjectionStatus`).
public enum MobileProjectionStatus: Equatable {
    case ready
    case loading
    case empty
    case offline
    case error

    var label: String {
        switch self {
        case .ready: return "ready"
        case .loading: return "loading"
        case .empty: return "empty"
        case .offline: return "offline"
        case .error: return "error"
        }
    }
}

public struct MobileAppSurface: View {
    @EnvironmentObject private var store: AppStore

    @State private var omnibarMode: MobileOmnibarMode = .search
    /// Route to restore when chat closes (Ask keeps one shared draft).
    @State private var routeBeforeChat: MobileRoute = .home
    @State private var devicePanelOpen = false
    @State private var selectedTaskId: String?
    @State private var reduceMotion = false

    public init() {}

    private var route: MobileRoute { store.mobileRoute }
    /// Ask opens the chat surface on the Conversations destination; closing
    /// restores the previous page without remounting the shared draft.
    @State private var chatOpen = false
    private var chatActive: Bool { route == MobileRoute.chat && chatOpen }

    // MARK: Projections

    private var conversationOutcome: ReadOutcome<DomainRead<ConversationProjection>>? {
        store.outcomes?.conversations
    }

    private var conversations: [ConversationProjection] {
        if case .success(let read) = conversationOutcome { return read.items }
        return []
    }

    private var conversationStatus: MobileProjectionStatus {
        guard let outcome = conversationOutcome else { return .loading }
        switch outcome {
        case .success(let read):
            return read.items.isEmpty ? .empty : .ready
        case .error:
            return .error
        }
    }

    private var tasks: [TaskProjection] {
        store.tasksRead?.items ?? []
    }

    private var taskStatus: MobileProjectionStatus {
        guard let read = store.tasksRead else { return .loading }
        return read.items.isEmpty ? .empty : .ready
    }

    private var openTasks: [TaskProjection] {
        tasks.filter { !$0.completed }
    }

    /// Writes need a current account epoch; without one, tasks stay read-only.
    private var writesAvailable: Bool {
        store.tasksRead?.accountEpoch != nil
    }

    private var captureActive: Bool {
        store.captureStage == .waiting || store.captureStage == .active
    }

    private var deviceConnected: Bool { store.connectedDeviceName != nil }

    private var deviceLabel: String {
        if let name = store.connectedDeviceName { return name }
        if store.scanning { return "Scanning…" }
        return "No device"
    }

    public var body: some View {
        VStack(spacing: 0) {
            if chatActive {
                MobileChat(onClose: closeChat, reduceMotion: reduceMotion)
            } else {
                if route == MobileRoute.apps {
                    appsTopBar
                } else if route == MobileRoute.home {
                    homeTopBar
                    if let deviceMessage = store.deviceErrorCopy, !devicePanelOpen {
                        Text(deviceMessage)
                            .font(MobileType.body.font)
                            .foregroundColor(MobilePalette.text)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(MobileSpace.md)
                            .accessibilityLabel(deviceMessage)
                    }
                }
                stage
            }
            MobileOmnibar(
                mode: $omnibarMode,
                value: $store.composerText,
                busy: chatBusy,
                canStop: chatCanStop,
                onSubmit: submitOmnibar,
                onStop: { Task { await store.cancelChatGeneration() } }
            )
            MobileTabBar(selected: route == MobileRoute.apps ? MobileRoute.settings : route) { destination in
                if destination == MobileRoute.chat {
                    chatOpen = false
                }
                store.navigate(mobileRoute: destination)
            }
        }
        .background(MobilePalette.background)
        .onAppear { refreshIfReady() }
    }

    // MARK: Chat state

    private var chatBusy: Bool {
        if case .pending = store.chatGeneration { return true }
        if case .streaming = store.chatGeneration { return true }
        return false
    }

    private var chatCanStop: Bool {
        switch store.chatGeneration {
        case .pending: return true
        case .streaming: return true
        case .idle: return false
        }
    }

    // MARK: Omnibar behavior (one shared draft; Search submits to Home)

    private func submitOmnibar() {
        let text = store.composerText
        if omnibarMode == .search {
            store.searchActive = true
            if route != MobileRoute.home {
                store.navigate(mobileRoute: MobileRoute.home)
            }
            return
        }
        routeBeforeChat = route
        chatOpen = true
        store.navigate(mobileRoute: MobileRoute.chat)
        let draft = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !draft.isEmpty {
            Task { await store.sendChat(draft) }
        }
    }

    private func closeChat() {
        chatOpen = false
        store.navigate(mobileRoute: routeBeforeChat == MobileRoute.chat ? MobileRoute.home : routeBeforeChat)
    }

    // MARK: Stage

    @ViewBuilder
    private var stage: some View {
        ContentEdges {
            Group {
                if route == MobileRoute.home {
                    homeStage
                } else if route == MobileRoute.settings {
                    SettingsPage()
                        .padding(.horizontal, MobileSpace.md)
                        .accessibilityLabel("Settings stage")
                } else if route == MobileRoute.apps {
                    ConnectorsPage()
                        .padding(.horizontal, MobileSpace.md)
                        .accessibilityLabel("Connectors stage")
                } else if route == MobileRoute.tasks {
                    tasksStage
                } else {
                    ConversationsPage(embedded: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .top).frame(maxHeight: .infinity)
        }
        .padding(.top, 12)
    }

    // MARK: Home

    private var homeTopBar: some View {
        HStack(spacing: MobileSpace.sm) {
            HStack(spacing: 8) {
                OmiAvatarView(size: 28, motion: .breathe, reduceMotion: reduceMotion)
                Text("omi")
                    .font(TypeStyle(size: 24, lineHeight: 30, weight: .semibold).font)
                    .foregroundColor(MobilePalette.text)
            }
            .accessibilityLabel("Omi")
            Spacer()
            Button(action: { withAnimation(KitMotion.slide) { devicePanelOpen.toggle() } }) {
                HStack(spacing: MobileSpace.sm) {
                    Capsule()
                        .fill(deviceConnected ? MobilePalette.connected : MobilePalette.textSubtle)
                        .frame(width: 10, height: 10)
                    Text(deviceLabel)
                        .font(TypeStyle(size: 14, lineHeight: 20, weight: .semibold).font)
                        .foregroundColor(MobilePalette.text)
                        .lineLimit(1)
                }
                .padding(.horizontal, MobileSpace.md)
                .frame(minHeight: 44)
                .background(MobilePalette.surface)
                .clipShape(RoundedRectangle(cornerRadius: MobileRadius.round))
            }
            .buttonStyle(KitPressableStyle())
            .accessibilityLabel("Open Omi device")
            .accessibilityAddTraits(devicePanelOpen ? [.isSelected] : [])
        }
        .padding(.horizontal, MobileSpace.md)
        .padding(.top, MobileSpace.sm)
    }

    @ViewBuilder
    private var homeStage: some View {
        if store.searchActive,
            !store.composerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        {
            MobileSearchResults()
        } else {
            ScrollView {
                VStack(spacing: MobileSpace.sm) {
                    if devicePanelOpen {
                        MobileDevicePanel()
                    }
                    if captureActive {
                        Text(captureCopy)
                            .font(MobileType.caption.font)
                            .foregroundColor(MobilePalette.textMuted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 8)
                            .lineLimit(2)
                    }
                    homeSection(
                        title: "Action items",
                        actionLabel: "See all",
                        action: { store.navigate(AppRoute.tasks) }
                    ) {
                        taskFeedback
                        if taskStatus == .ready {
                            if openTasks.isEmpty {
                                KitStatePanel(status: "empty", noun: "tasks")
                            } else {
                                ForEach(openTasks.prefix(3)) { task in
                                    MobileTaskRow(
                                        task: task,
                                        writesAvailable: writesAvailable,
                                        busy: false,
                                        onToggle: writesAvailable
                                            ? { id in
                                                if let projection = tasks.first(where: { $0.id == id }) {
                                                    Task { await store.toggleTask(projection) }
                                                }
                                            } : nil,
                                        onEdit: writesAvailable
                                            ? { id in selectedTaskId = id } : nil
                                    )
                                }
                            }
                        } else {
                            KitStatePanel(
                                status: taskStatus.label, noun: "tasks"
                            )
                        }
                    }
                    homeSection(
                        title: "Recent conversations",
                        actionLabel: "See all",
                        action: { store.navigate(AppRoute.conversations) }
                    ) {
                        if conversationStatus == .ready {
                            if conversations.isEmpty {
                                KitStatePanel(status: "empty", noun: "conversations")
                            } else {
                                ForEach(conversations.prefix(3)) { conversation in
                                    MobileConversationRow(conversation: conversation)
                                }
                            }
                        } else {
                            KitStatePanel(
                                status: conversationStatus.label,
                                noun: "conversations"
                            )
                        }
                    }
                }
                .padding(.horizontal, MobileSpace.md)
                .padding(.top, MobileSpace.sm)
                .padding(.bottom, 12)
            }
        }
    }

    private var captureCopy: String {
        let lead = store.captureStage == .waiting ? "Waiting for audio" : "Listening"
        return lead
    }

    private func homeSection<Content: View>(
        title: String, actionLabel: String, action: @escaping () -> Void,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(spacing: 0) {
            HStack {
                Text(title)
                    .font(TypeStyle(size: 18, lineHeight: 24, weight: .semibold).font)
                    .foregroundColor(MobilePalette.text)
                Spacer()
                Button(action: action) {
                    Text(actionLabel)
                        .font(MobileType.caption.font)
                        .foregroundColor(MobilePalette.textMuted)
                        .frame(minHeight: 44)
                        .padding(.horizontal, MobileSpace.sm)
                }
                .buttonStyle(KitPressableStyle())
                .accessibilityLabel("\(actionLabel) \(title.lowercased())")
            }
            .padding(.horizontal, 2)
            content()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 4)
        .background(MobilePalette.surface)
        .overlay(
            RoundedRectangle(cornerRadius: MobileRadius.lg)
                .strokeBorder(MobilePalette.border, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: MobileRadius.lg))
    }

    /// Task mutation banner plus the inline editor for the selected row.
    @ViewBuilder
    private var taskFeedback: some View {
        TaskMutationStatusView(writesAvailable: writesAvailable, mutationError: nil)
        if writesAvailable, let selectedId = selectedTaskId,
            let selected = tasks.first(where: { $0.id == selectedId })
        {
            TaskEditorView(
                taskId: selected.id, title: selected.title, busy: false,
                onSave: { id, description in
                    if let projection = tasks.first(where: { $0.id == id }) {
                        Task { await store.renameTask(projection, title: description) }
                    }
                },
                onClose: { selectedTaskId = nil }
            )
        }
    }

    // MARK: Tasks stage

    private var tasksStage: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: MobileSpace.sm) {
                taskFeedback
                if taskStatus == .ready {
                    if tasks.isEmpty {
                        KitStatePanel(status: "empty", noun: "tasks")
                    } else {
                        ForEach(tasks) { task in
                            MobileTaskRow(
                                task: task,
                                writesAvailable: writesAvailable,
                                busy: false,
                                onToggle: writesAvailable
                                    ? { id in
                                        if let projection = tasks.first(where: { $0.id == id }) {
                                            Task { await store.toggleTask(projection) }
                                        }
                                    } : nil,
                                onEdit: writesAvailable
                                    ? { id in selectedTaskId = id } : nil
                            )
                        }
                    }
                } else {
                    KitStatePanel(status: taskStatus.label, noun: "tasks")
                }
                tasksPagination
            }
            .padding(.horizontal, MobileSpace.md)
            .padding(.top, MobileSpace.sm)
            .padding(.bottom, 24)
        }
    }

    @ViewBuilder
    private var tasksPagination: some View {
        if let read = store.tasksRead, read.page.hasMore {
            Button(action: { Task { await store.loadOlderTasks() } }) {
                Text("Load more tasks")
                    .font(TypeStyle(size: 13, lineHeight: 18, weight: .regular).font)
                    .foregroundColor(MobilePalette.textMuted)
                    .frame(maxWidth: .infinity, alignment: .leading).frame(minHeight: 44)
            }
            .buttonStyle(KitPressableStyle())
            .accessibilityLabel("Load more tasks")
        }
    }

    // MARK: Apps top bar

    private var appsTopBar: some View {
        HStack(spacing: 4) {
            Button(action: { store.navigate(mobileRoute: MobileRoute.settings) }) {
                HStack(spacing: 4) {
                    KitIcon(.chevronLeft, size: 20, color: MobilePalette.text)
                    Text("Settings")
                        .font(MobileType.caption.font)
                        .foregroundColor(MobilePalette.textMuted)
                }
                .frame(minHeight: 44)
            }
            .buttonStyle(KitPressableStyle())
            .accessibilityLabel("Back to Settings")
            Spacer()
            Text("Apps")
                .font(TypeStyle(size: 18, lineHeight: 24, weight: .semibold).font)
                .foregroundColor(MobilePalette.text)
            Spacer()
            Color.clear.frame(width: 80, height: 1)
        }
        .padding(.horizontal, MobileSpace.md)
        .padding(.top, MobileSpace.sm)
    }

    // MARK: Conversations auto-refresh (entry + 15 s while active)

    private func refreshIfReady() {
        if route == MobileRoute.chat, !store.readsLoading, selectedTaskId == nil {
            Task { await store.refreshReads() }
        }
    }
}

// MARK: - Tab bar (AppNav for compact screens)

public struct MobileTabBar: View {
    public let selected: MobileRoute
    public let onRouteChange: (MobileRoute) -> Void

    public init(selected: MobileRoute, onRouteChange: @escaping (MobileRoute) -> Void) {
        self.selected = selected
        self.onRouteChange = onRouteChange
    }

    private var items: [(route: MobileRoute, label: String, icon: KitIconName)] {
        [
            (.home, "Home", .home),
            (.chat, "Conversations", .chatBubble),
            (.tasks, "Tasks", .checklist),
            (.settings, "Settings", .settings),
        ]
    }

    public var body: some View {
        HStack(spacing: 2) {
            ForEach(items, id: \.route) { item in
                tabButton(item)
            }
        }
        .padding(4)
        .background(MobilePalette.surfaceQuiet)
        .overlay(
            RoundedRectangle(cornerRadius: MobileRadius.lg)
                .strokeBorder(MobilePalette.border, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: MobileRadius.lg))
        .padding(.horizontal, 10)
        .padding(.bottom, 8)
        .accessibilityLabel("Sections")
    }

    private func tabButton(_ item: (route: MobileRoute, label: String, icon: KitIconName))
        -> some View
    {
        let isSelected = selected == item.route
        return Button(action: { onRouteChange(item.route) }) {
            VStack(spacing: 3) {
                KitIcon(item.icon, size: 22, color: iconColor(isSelected))
                    .padding(.vertical, 4)
                Text(item.label)
                    .font(TypeStyle(size: 10, lineHeight: 12, weight: .regular).font)
                    .foregroundColor(
                        isSelected ? MobilePalette.text : MobilePalette.textSubtle
                    )
            }
            .frame(maxWidth: .infinity, minHeight: 60)
            .background(
                RoundedRectangle(cornerRadius: 18)
                    .fill(isSelected ? MobilePalette.surfaceRaised : Color.clear)
            )
        }
        .buttonStyle(KitPressableStyle())
        .animation(KitMotion.slide, value: selected)
        .accessibilityLabel(item.label)
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }

    private func iconColor(_ isSelected: Bool) -> Color {
        isSelected ? MobilePalette.text : MobilePalette.textSubtle
    }
}

// MARK: - Home rows

public struct MobileTaskRow: View {
    public let task: TaskProjection
    public let writesAvailable: Bool
    public let busy: Bool
    public let onToggle: ((String) -> Void)?
    public let onEdit: ((String) -> Void)?

    public init(
        task: TaskProjection, writesAvailable: Bool, busy: Bool,
        onToggle: ((String) -> Void)?, onEdit: ((String) -> Void)?
    ) {
        self.task = task
        self.writesAvailable = writesAvailable
        self.busy = busy
        self.onToggle = onToggle
        self.onEdit = onEdit
    }

    private var toggleEnabled: Bool { onToggle != nil && !busy }
    private var dueCopy: String? {
        if !task.completed, task.dueAt != nil {
            if let due = KitFormat.mobileTaskDue(task.dueAt) {
                return "Due \(due)"
            }
        }
        return nil
    }

    public var body: some View {
        HStack(spacing: MobileSpace.sm) {
            Button(action: { onToggle?(task.id) }) {
                HStack(spacing: 12) {
                    ZStack {
                        Circle()
                            .strokeBorder(
                                MobilePalette.textSubtle, lineWidth: 1.5
                            )
                        if task.completed {
                            Circle().fill(MobilePalette.textSubtle)
                            KitIcon(
                                .check, size: 14,
                                color: MobilePalette.background, filled: false
                            )
                        }
                    }
                    .frame(width: 22, height: 22)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(task.title)
                            .font(TypeStyle(size: 15, lineHeight: 22, weight: .regular).font)
                            .foregroundColor(
                                task.completed ? MobilePalette.textSubtle : MobilePalette.text
                            )
                            .strikethrough(task.completed)
                        if dueCopy != nil || task.owner != nil {
                            Text([dueCopy, task.owner].compactMap { $0 }.joined(separator: " · "))
                                .font(TypeStyle(size: 12, lineHeight: 18, weight: .regular).font)
                                .foregroundColor(MobilePalette.textMuted)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(minHeight: 44)
            }
            .buttonStyle(KitPressableStyle())
            .disabled(!toggleEnabled)
            .opacity(!toggleEnabled ? Opacity.disabled : 1)
            .accessibilityLabel(toggleAccessibility)
            .accessibilityAddTraits(task.completed ? [.isSelected] : [])
            if onEdit != nil {
                Button(action: { onEdit?(task.id) }) {
                    KitIcon(.edit, size: 16, color: MobilePalette.textMuted)
                        .frame(minWidth: 44, minHeight: 44)
                }
                .buttonStyle(KitPressableStyle())
                .disabled(busy)
                .accessibilityLabel("Edit \(task.title)")
            }
        }
        .frame(minHeight: 64)
        .padding(.vertical, MobileSpace.sm)
    }

    private var toggleAccessibility: String {
        let state: String
        if onToggle != nil {
            state = task.completed ? "Reopen" : "Complete"
        } else {
            state = task.completed ? "Completed" : "Open"
        }
        return "\(state) \(task.title)"
    }
}

public struct MobileConversationRow: View {
    public let conversation: ConversationProjection

    public init(conversation: ConversationProjection) {
        self.conversation = conversation
    }

    private var dateCopy: String {
        let value = conversation.startedAt ?? conversation.createdAt
        return KitFormat.conversationDate(value)
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(conversation.title)
                    .font(TypeStyle(size: 15, lineHeight: 22, weight: .medium).font)
                    .foregroundColor(MobilePalette.text)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(dateCopy)
                    .font(TypeStyle(size: 12, lineHeight: 18, weight: .regular).font)
                    .foregroundColor(MobilePalette.textMuted)
            }
            if !conversation.summary.isEmpty {
                Text(conversation.summary)
                    .font(TypeStyle(size: 12, lineHeight: 18, weight: .regular).font)
                    .foregroundColor(MobilePalette.textMuted)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 12)
            }
}

// MARK: - Device details (expand without unmounting pending controls)

public struct MobileDevicePanel: View {
    @EnvironmentObject private var store: AppStore

    public init() {}

    private var panelAvatarMotion: OmiAvatarMotion {
        store.captureStage == CaptureStage.active
            ? OmiAvatarMotion.breathe : OmiAvatarMotion.resting
    }

    private var deviceActions: some View {
        let disconnectLabel = Text("Disconnect")
            .font(TypeStyle(size: 13, lineHeight: 18, weight: .medium).font)
            .foregroundColor(Palette.danger)
            .frame(minHeight: 44)
            .padding(.horizontal, MobileSpace.md)
        let scanLabel = Text("Scan for device")
            .font(TypeStyle(size: 13, lineHeight: 18, weight: .medium).font)
            .foregroundColor(MobilePalette.text)
            .frame(minHeight: 44)
            .padding(.horizontal, MobileSpace.md)
        return HStack(spacing: MobileSpace.sm) {
            if store.connectedDeviceName != nil {
                Button(action: { Task { await store.disconnectDevice() } }) {
                    disconnectLabel
                }
                .buttonStyle(KitPressableStyle())
                .background(MobilePalette.surfaceQuiet)
                .clipShape(RoundedRectangle(cornerRadius: MobileRadius.chip))
                .accessibilityLabel("Disconnect device")
            } else {
                Button(action: {
                    if store.scanning {
                        store.stopScan()
                    } else {
                        Task { await store.startScan() }
                    }
                }) {
                    scanLabel
                }
                .buttonStyle(KitPressableStyle())
                .background(MobilePalette.surfaceQuiet)
                .clipShape(RoundedRectangle(cornerRadius: MobileRadius.chip))
                .accessibilityLabel(store.scanning ? "Stop scan" : "Scan for device")
            }
        }
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: MobileSpace.xs) {
            HStack(spacing: MobileSpace.sm) {
                OmiAvatarView(size: 24, motion: panelAvatarMotion)
                Text(store.connectedDeviceName ?? "No device connected")
                    .font(TypeStyle(size: 15, lineHeight: 22, weight: .semibold).font)
                    .foregroundColor(MobilePalette.text)
                Spacer()
                if let battery = store.batteryLevel {
                    Text("Battery \(battery)%")
                        .font(MobileType.caption.font)
                        .foregroundColor(MobilePalette.textMuted)
                }
            }
            if let info = store.connectedDeviceInfo {
                ForEach(DeviceInfoField.allCases, id: \.rawValue) { field in
                    HStack {
                        Text(field.label)
                            .font(MobileType.caption.font)
                            .foregroundColor(MobilePalette.textSubtle)
                        Spacer()
                        Text(info.displayValue(for: field))
                            .font(MobileType.caption.font)
                            .foregroundColor(MobilePalette.text)
                    }
                }
            }
            deviceActions
            ForEach(store.discoveredDevices) { device in
                Button(action: { Task { await store.connect(device) } }) {
                    HStack {
                        Text(device.name.isEmpty ? "Omi device" : device.name)
                            .font(MobileType.caption.font)
                            .foregroundColor(MobilePalette.text)
                        Spacer()
                        if store.connectingDeviceId == device.id {
                            Text("Connecting…")
                                .font(MobileType.caption.font)
                                .foregroundColor(MobilePalette.textMuted)
                        }
                    }
                    .frame(minHeight: 44)
                }
                .buttonStyle(KitPressableStyle())
                .disabled(store.connectingDeviceId != nil)
                .accessibilityLabel("Connect \(device.name)")
            }
        }
        .padding(MobileSpace.md)
        .background(MobilePalette.surface)
        .overlay(
            RoundedRectangle(cornerRadius: MobileRadius.lg)
                .strokeBorder(MobilePalette.border, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: MobileRadius.lg))
    }
}

public struct MobileSearchResults: View {
    @EnvironmentObject private var store: AppStore

    public init() {}

    private var results: [TimelineEntry] {
        store.mergedTimeline(filter: .all).entries
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: MobileSpace.sm) {
                if store.readsLoading && results.isEmpty {
                    HStack(spacing: 12) {
                        ProgressView().tint(MobilePalette.textMuted)
                        Text("Loading…")
                            .font(TypeStyle(size: 16, lineHeight: 24, weight: .semibold).font)
                            .foregroundColor(Palette.text)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, MobileSpace.md)
                } else if !store.mergedTimeline(filter: .all).failures.isEmpty {
                    Text("Some saved data could not be loaded.")
                        .font(MobileType.body.font)
                        .foregroundColor(MobilePalette.textMuted)
                        .accessibilityLabel("Some saved data could not be loaded.")
                } else if results.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("No loaded results match")
                            .font(TypeStyle(size: 16, lineHeight: 24, weight: .semibold).font)
                            .foregroundColor(Palette.text)
                        Text("Search covers data already loaded on this device.")
                            .font(TypeStyle(size: 16, lineHeight: 24, weight: .semibold).font)
                            .foregroundColor(Palette.textMuted)
                    }
                    .padding(.vertical, MobileSpace.md)
                } else {
                    ForEach(results) { entry in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack(spacing: Space.xs) {
                                Text(entry.kind.label)
                                    .font(Typography.caption.font)
                                    .foregroundColor(MobilePalette.textMuted)
                                if entry.kind == .conversation {
                                    Text("Starred")
                                        .font(Typography.caption.font)
                                        .foregroundColor(MobilePalette.textMuted)
                                }
                            }
                            Text(entry.title)
                                .font(TypeStyle(size: 15, lineHeight: 21, weight: .medium).font)
                                .foregroundColor(MobilePalette.text)
                                .lineLimit(2)
                            Text(entry.detail)
                                .font(TypeStyle(size: 14, lineHeight: 21, weight: .regular).font)
                                .foregroundColor(MobilePalette.textMuted)
                                .lineLimit(2)
                        }
                        .padding(.vertical, MobileSpace.xs)
                                            }
                }
            }
            .padding(.horizontal, MobileSpace.md)
            .padding(.vertical, MobileSpace.sm)
        }
    }
}

// MARK: - Edge fades

/// Non-interactive gradients blending scrolling content into the page
/// background at both edges. They never cover the composer or navigation.
public struct ContentEdges<Content: View>: View {
    public let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        content
            .frame(maxWidth: .infinity).frame(maxHeight: .infinity)
            .overlay(alignment: .top) { edge(top: true) }
            .overlay(alignment: .bottom) { edge(top: false) }
            .clipped()
    }

    private func edge(top: Bool) -> some View {
        LinearGradient(
            colors: top
                ? [MobilePalette.background, MobilePalette.background.opacity(0)]
                : [MobilePalette.background.opacity(0), MobilePalette.background],
            startPoint: top ? .top : .bottom,
            endPoint: top ? .bottom : .top
        )
        .frame(height: 24)
        .frame(maxWidth: .infinity)
        .allowsHitTesting(false)
    }
}

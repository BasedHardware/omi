import SwiftUI
import Charts
import ImageIO

@available(iOS 16.0, *)
@MainActor
final class NativeSurfaceState: ObservableObject {
    @Published private(set) var snapshot: NativeSurfaceSnapshot
    @Published private(set) var valid = true
    @Published private(set) var pending: Set<String> = []
    @Published private(set) var actionFailed = false
    @Published private(set) var completedChatSend = 0
    private var pendingEdits: Set<String> = []
    private var failedEdits: Set<String> = []
    private var editWaiters: [CheckedContinuation<Void, Never>] = []
    private var latestEdits: [String: String] = [:]
    private(set) var sentDraft: String?
    private var queued: [String: Any] = [:]
    // Keypad commands have side effects (DTMF), so every accepted press retains FIFO order.
    // Text edits continue to coalesce to the latest draft instead.
    private var queuedKeys: [String: [String]] = [:]
    private var revision = NativeSnapshotRevision()
    private let perform: (String, Any?) async throws -> Void

    init(snapshot: NativeSurfaceSnapshot, perform: @escaping (String, Any?) async throws -> Void) {
        self.snapshot = snapshot
        self.perform = perform
        _ = revision.accept(snapshot.revision)
    }

    func update(_ snapshot: NativeSurfaceSnapshot) {
        guard valid, revision.accept(snapshot.revision) else { return }
        let editable = Set(snapshot.allRows.filter { $0.kind == "text" }.map(\.id))
        latestEdits = latestEdits.filter { editable.contains($0.key) }
        let current = Set(snapshot.allRows.map(\.id))
        failedEdits = failedEdits.filter { current.contains($0) }
        queued = queued.filter { current.contains($0.key) || $0.key == "_search" && snapshot.searchEnabled }
        queuedKeys = queuedKeys.filter { current.contains($0.key) }
        self.snapshot = snapshot
    }

    func invalidate() {
        valid = false
        queued.removeAll()
        queuedKeys.removeAll()
        latestEdits.removeAll()
        failedEdits.removeAll()
        sentDraft = nil
        finishEditWaiters()
        snapshot = snapshot.withoutContent()
    }

    func send(_ id: String, value: Any? = nil) async {
        guard valid else { return }
        let isKeypad = snapshot.allRows.contains { $0.id == id && $0.kind == "keypad" }
        let isEdit = snapshot.allRows.contains {
            $0.id == id && ["text", "toggle", "choice", "segmented", "color", "date", "slider"].contains($0.kind)
        } || isKeypad
        if let text = value as? String, snapshot.allRows.contains(where: { $0.id == id && $0.kind == "text" }) {
            latestEdits[id] = text
        }
        if pending.contains(id) {
            if isKeypad, let key = value as? String { queuedKeys[id, default: []].append(key) }
            else if let value, id == "_search" || isEdit { queued[id] = value }
            return
        }
        pending.insert(id)
        if isEdit { pendingEdits.insert(id) }
        defer {
            pending.remove(id)
            pendingEdits.remove(id)
            if pendingEdits.isEmpty { finishEditWaiters() }
        }
        if !isEdit && !id.hasPrefix("_visible:") {
            if !pendingEdits.isEmpty { await withCheckedContinuation { editWaiters.append($0) } }
            guard valid else { return }
            let isCancellation = snapshot.toolbar.contains { $0.id == id && ["xmark", "chevron.left"].contains($0.symbol ?? "") }
            guard failedEdits.isEmpty || isCancellation else { actionFailed = true; return }
        }
        if id == "chat_send" { sentDraft = latestEdits["chat_draft"] ?? snapshot.chat?.draft }
        actionFailed = false
        var next = value
        repeat {
            do {
                try await perform(id, next)
                if isEdit { failedEdits.remove(id) }
                if valid && id == "chat_send" { completedChatSend += 1 }
            }
            catch {
                if valid && (!isEdit || snapshot.allRows.contains(where: { $0.id == id })) {
                    actionFailed = true
                    if isEdit { failedEdits.insert(id) }
                }
                if isKeypad { queuedKeys.removeValue(forKey: id); break }
            }
            if isKeypad, var keys = queuedKeys[id], !keys.isEmpty {
                next = keys.removeFirst()
                queuedKeys[id] = keys.isEmpty ? nil : keys
            } else { next = queued.removeValue(forKey: id) }
        } while valid && next != nil
    }
    private func finishEditWaiters() {
        let waiters = editWaiters
        editWaiters.removeAll()
        for waiter in waiters { waiter.resume() }
    }

    func draft(for row: NativeSurfaceRow) -> String {
        if pendingEdits.contains(row.id) || failedEdits.contains(row.id) {
            return latestEdits[row.id] ?? row.value?.text ?? ""
        }
        return row.value?.text ?? ""
    }

}

@available(iOS 16.0, *)
struct NativeSurfaceView: View {
    @ObservedObject var state: NativeSurfaceState
    @State private var search = ""
    @State private var followingChat = true
    @State private var visibleMessages: Set<String> = []
    @State private var readerFrames: [String: CGRect] = [:]
    @State private var readerDragging = false
    @State private var readerUserScroll = false
    @State private var readerTopId: String?

    var body: some View {
        Group {
            if state.valid, let navigation = state.snapshot.navigation {
                mainNavigation(navigation)
            } else {
                screen
            }
        }
        .tint(.primary)
        .modifier(NativeSensitiveCover(enabled: state.snapshot.sensitive == true))
        .preferredColorScheme(state.snapshot.appearance == "system" ? nil
            : state.snapshot.appearance == "dark" ? .dark : .light)
        .environment(\.locale, Locale(identifier: state.snapshot.locale))
        .environment(\.layoutDirection, state.snapshot.direction == "rtl" ? .rightToLeft : .leftToRight)
        .onAppear { search = state.snapshot.searchValue }
        .onChange(of: state.snapshot.searchValue) { value in
            if !state.pending.contains("_search") { search = value }
        }
        .onChange(of: state.valid) { valid in if !valid { search = "" } }
    }

    /// TabView owns its system tab bar, including Liquid Glass on iOS 26+ and
    /// the platform's accessible selection/large-content behavior on older iOS.
    private func mainNavigation(_ navigation: NativeSurfaceRow) -> some View {
        TabView(selection: Binding(get: { state.snapshot.navigation?.value?.text ?? "home" }, set: { id in
            Task { await state.send(navigation.id, value: id) }
        })) {
            ForEach(navigation.options) { option in
                Color.clear
                    .tabItem { Label(option.title, systemImage: Self.tabSymbol(option.id)) }
                    .tag(option.id)
                    .accessibilityIdentifier("main-tab-\(option.id)")
            }
        }
        .disabled(!navigation.enabled)
        .accessibilityIdentifier("native-main-navigation")
    }

    private static func tabSymbol(_ id: String) -> String {
        switch id {
        case "tasks": return "checklist"
        case "memories": return "brain"
        case "apps": return "square.grid.2x2"
        case "settings": return "gearshape"
        default: return "house"
        }
    }

    private var screen: some View {
        NavigationStack {
            if state.valid {
                content
                    .navigationTitle(state.snapshot.title)
                    .navigationBarTitleDisplayMode(state.snapshot.largeTitle == true ? .large : .inline)
                    .toolbar {
                        ToolbarItemGroup(placement: .navigationBarLeading) {
                            ForEach(state.snapshot.toolbar.filter { $0.symbol == "chevron.left" }) { row in
                                rowView(row, compact: true)
                            }
                        }
                        ToolbarItemGroup(placement: .navigationBarTrailing) {
                            ForEach(state.snapshot.toolbar.filter { $0.symbol != "chevron.left" }) { row in
                                rowView(row, compact: true)
                            }
                        }
                    }
            } else { Color.clear.accessibilityIdentifier("native-surface-invalidated") }
        }
    }

    @ViewBuilder private var content: some View {
        if let reader = state.snapshot.reader {
            if state.snapshot.searchEnabled {
                readerView(reader).searchable(text: $search, prompt: state.snapshot.searchPlaceholder)
                    .onChange(of: search) { value in Task { await state.send("_search", value: value) } }
            } else { readerView(reader) }
        } else if let chat = state.snapshot.chat {
            chatView(chat)
        } else if state.snapshot.searchEnabled {
            list.searchable(text: $search, prompt: state.snapshot.searchPlaceholder)
                .onChange(of: search) { value in
                    Task { await state.send("_search", value: value) }
                }
        } else { list }
    }

    private var list: some View {
        List {
            Section {
                if state.snapshot.loading {
                    ProgressView(state.snapshot.loadingLabel).accessibilityIdentifier("native-surface-loading")
                }
                if state.snapshot.failed || state.actionFailed {
                    Text(state.snapshot.error)
                        .accessibilityIdentifier("native-surface-error")
                    if state.snapshot.refreshEnabled {
                        Button(state.snapshot.retry) { Task { await state.send("_refresh") } }
                    }
                }
                if !state.snapshot.loading && !state.snapshot.failed
                    && state.snapshot.sections.allSatisfy({ $0.rows.isEmpty }) {
                    Text(state.snapshot.empty).accessibilityIdentifier("native-surface-empty")
                }
            }.id("native-surface-status")
            ForEach(state.snapshot.sections) { section in
                Section {
                    ForEach(section.rows) { row in
                        rowView(row).onAppear {
                            if row.visibilityEnabled == true { Task { await state.send("_visible:\(row.id)") } }
                        }
                    }
                } header: {
                    if !section.title.isEmpty { Text(section.title) }
                } footer: {
                    if !section.footer.isEmpty { Text(section.footer) }
                }
            }
        }
        .listStyle(.insetGrouped)
        .refreshable { if state.snapshot.refreshEnabled { await state.send("_refresh") } }
    }

    @ViewBuilder private func rowView(_ row: NativeSurfaceRow, compact: Bool = false) -> some View {
        Group {
            switch row.kind {
            case "menu":
                Menu {
                    ForEach(row.options) { option in
                        Button(option.title) { Task { await state.send(row.id, value: option.id) } }
                    }
                } label: {
                    actionLabel(row, compact: compact)
                        .frame(minWidth: compact ? 44 : 0, minHeight: 44)
                        .contentShape(Rectangle())
                }
            case "toggle":
                Toggle(isOn: Binding(get: { row.value?.bool ?? false }, set: { value in
                    Task { await state.send(row.id, value: value) }
                })) { label(row) }
                    .toggleStyle(.switch)
            case "navigation":
                Button {
                    Task { await state.send(row.id) }
                } label: {
                    HStack(spacing: 12) {
                        actionLabel(row)
                        Image(systemName: "chevron.forward")
                            .font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
                    }.frame(minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .contextMenu {
                        ForEach(row.options) { option in
                            Button(option.title, role: option.id == "delete" ? .destructive : nil) {
                                Task { await state.send(row.id, value: option.id) }
                            }
                        }
                    }
            case "transcript":
                Button { Task { await state.send(row.id) } } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(row.subtitle).font(.caption).foregroundStyle(.secondary)
                        Text(nativeHighlighted(AttributedString(row.title), query: state.snapshot.searchValue))
                            .foregroundStyle(.primary)
                    }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).contextMenu {
                    ForEach(row.options) { option in
                        Button(option.title) { Task { await state.send(row.id, value: option.id) } }
                    }
                }
            case "task":
                HStack(spacing: 12) {
                    Button { Task { await state.send(row.id, value: !(row.value?.bool ?? false)) } } label: {
                        Image(systemName: row.value?.bool == true ? "checkmark.circle.fill" : "circle")
                            .font(.title2).frame(minWidth: 44, minHeight: 44)
                    }.accessibilityLabel(row.title).accessibilityAddTraits(row.value?.bool == true ? .isSelected : [])
                    // The title opens the task only when its owner offers 'open'; otherwise it is static text.
                    Group {
                        if row.options.contains(where: { $0.id == "open" }) {
                            Button { Task { await state.send(row.id, value: "open") } } label: { label(row) }
                        } else { label(row) }
                    }.contextMenu {
                        ForEach(row.options) { option in
                            Button(option.title) { Task { await state.send(row.id, value: option.id) } }
                        }
                    }
                }.buttonStyle(.plain)
            case "choice":
                if row.optionSearch != nil {
                    NativeSearchableChoice(row: row, state: state)
                } else {
                VStack(alignment: .leading, spacing: 8) {
                    label(row)
                    Picker(row.title, selection: Binding(get: { row.value?.text ?? "" }, set: { value in
                        Task { await state.send(row.id, value: value) }
                    })) {
                        ForEach(row.options) { option in Text(option.title).tag(option.id) }
                    }.pickerStyle(.menu).labelsHidden()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                }
            case "segmented":
                Picker(row.title, selection: Binding(get: { row.value?.text ?? "" }, set: { value in
                    Task { await state.send(row.id, value: value) }
                })) {
                    ForEach(row.options) { option in Text(option.title).tag(option.id) }
                }.pickerStyle(.segmented)
            case "color":
                VStack(alignment: .leading, spacing: 8) {
                    label(row)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 44))], spacing: 8) {
                        ForEach(row.options) { option in
                            Button { Task { await state.send(row.id, value: option.id) } } label: {
                                let rgb = UInt32(option.id.dropFirst(), radix: 16) ?? 0
                                Circle().fill(Color(red: Double((rgb >> 16) & 255) / 255,
                                    green: Double((rgb >> 8) & 255) / 255, blue: Double(rgb & 255) / 255))
                                    .frame(width: 28, height: 28)
                                    .overlay {
                                        if row.value?.text == option.id { Image(systemName: "checkmark").foregroundStyle(.white).shadow(radius: 1) }
                                    }.frame(minWidth: 44, minHeight: 44)
                            }.buttonStyle(.plain).accessibilityLabel(option.title)
                                .accessibilityAddTraits(row.value?.text == option.id ? .isSelected : [])
                        }
                    }
                }
            case "date":
                DatePicker(row.title, selection: Binding(get: {
                    Date(timeIntervalSince1970: (Double(row.value?.text ?? "") ?? Date().timeIntervalSince1970 * 1000) / 1000)
                }, set: { value in
                    Task { await state.send(row.id, value: String(CheckedIntegerConversion.epochMs(value))) }
                }), in: Date(timeIntervalSince1970: (Double(row.minimumDate ?? "") ?? 0) / 1000)...)
            case "chart":
                VStack(alignment: .leading, spacing: 12) {
                    Text(row.title).font(.headline)
                    if let points = row.points, points.count > 1 {
                        Chart(points) { point in
                            LineMark(x: .value(row.subtitle, point.x), y: .value(row.title, point.y))
                        }.frame(height: 150)
                            .chartXAxis { AxisMarks(values: .automatic(desiredCount: 3)) }
                            .accessibilityLabel(row.title)
                    } else { Text(row.subtitle).foregroundStyle(.secondary) }
                }
            case "waveform":
                Chart(row.points ?? []) { point in
                    BarMark(x: .value(row.title, point.x), yStart: .value(row.title, -point.y), yEnd: .value(row.title, point.y))
                }.frame(height: 36).chartYScale(domain: -1...1)
                    .chartXAxis(.hidden).chartYAxis(.hidden)
                    .accessibilityLabel(row.title)
            case "slider":
                NativePlaybackSlider(row: row, state: state)
            case "progress":
                VStack(alignment: .leading, spacing: 8) {
                    label(row)
                    ProgressView(value: row.value?.number ?? 0, total: row.maximumValue ?? 100)
                }.accessibilityElement(children: .ignore)
                    .accessibilityLabel(row.title).accessibilityValue(row.subtitle)
            case "message_user", "message_ai":
                message(row)
            case "rich_text":
                NativeRichTextView(row: row, state: state, query: state.snapshot.reader == nil ? "" : state.snapshot.searchValue)
            case "image":
                NativeZoomImage(row: row)
            case "text":
                NativeTextRow(row: row, state: state)
            case "keypad":
                NativeKeypadRow(row: row, state: state)
            case "secret":
                NativeSecretRow(row: row, state: state)
            case "label":
                if let symbol = row.symbol {
                    Label { label(row) } icon: {
                        Image(systemName: symbol).foregroundStyle(row.destructive ? Color.red : Color.primary)
                    }.textSelection(.enabled)
                } else { label(row).textSelection(.enabled) }
            default: action(row, compact: compact)
            }
        }
        .disabled(!row.enabled && !["label", "rich_text", "image", "progress", "chart", "waveform", "message_ai", "message_user", "secret"].contains(row.kind) || (state.pending.contains(row.id) && !["text", "keypad", "slider"].contains(row.kind)))
        .accessibilityIdentifier(row.id)
    }

    private func readerView(_ projection: NativeSurfaceSnapshot.Reader) -> some View {
        ScrollViewReader { proxy in
            GeometryReader { viewport in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if state.snapshot.loading { ProgressView(state.snapshot.loadingLabel) }
                        if state.snapshot.failed || state.actionFailed {
                            Text(state.snapshot.error)
                            if state.snapshot.refreshEnabled {
                                Button(state.snapshot.retry) { Task { await state.send("_refresh") } }
                            }
                        }
                        ForEach(state.snapshot.sections) { section in
                            if !section.title.isEmpty { Text(section.title).font(.headline) }
                            ForEach(section.rows) { row in
                                rowView(row)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, row.kind == "rich_text" ? 4 : 8)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(row.id == projection.currentId ? Color.primary.opacity(0.08) : .clear,
                                                in: RoundedRectangle(cornerRadius: 12))
                                    .id(row.id)
                                    .background(GeometryReader { geometry in
                                        Color.clear.preference(key: NativeChatMessageFramesPreference.self,
                                            value: [row.id: geometry.frame(in: .named("native-reader-scroll"))])
                                    })
                            }
                            if !section.footer.isEmpty { Text(section.footer).font(.footnote).foregroundStyle(.secondary) }
                        }
                    }.padding(.horizontal, 16).padding(.vertical, 12)
                }
                .coordinateSpace(name: "native-reader-scroll")
                .refreshable { if state.snapshot.refreshEnabled { await state.send("_refresh") } }
                .onPreferenceChange(NativeChatMessageFramesPreference.self) { frames in
                    readerFrames = frames
                    let visible = Set(frames.filter { $0.value.maxY > 0 && $0.value.minY < viewport.size.height }.keys)
                    let appeared = visible.subtracting(visibleMessages)
                    let disappeared = visibleMessages.subtracting(visible)
                    visibleMessages = visible
                    for id in appeared where state.snapshot.sections.flatMap(\.rows).contains(where: { $0.id == id && $0.visibilityEnabled == true }) {
                        Task { await state.send("_visible:\(id)") }
                    }
                    for id in disappeared where state.snapshot.sections.flatMap(\.rows).contains(where: { $0.id == id && $0.visibilityHiddenEnabled == true }) {
                        Task { await state.send("_hidden:\(id)") }
                    }
                    reportReaderScroll(projection, height: viewport.size.height)
                }
                .simultaneousGesture(DragGesture(minimumDistance: 8)
                    .onChanged { gesture in
                        guard abs(gesture.translation.height) > abs(gesture.translation.width) else { return }
                        if !readerDragging {
                            readerDragging = true
                            readerUserScroll = true
                            if let scroll = projection.scroll { Task { await state.send(scroll.id, value: "suspend") } }
                        }
                    }.onEnded { _ in
                        readerDragging = false
                        reportReaderScroll(projection, height: viewport.size.height)
                    })
                .onChange(of: projection.targetId) { _ in followReader(projection, proxy: proxy) }
                .onChange(of: projection.request) { _ in followReader(projection, proxy: proxy) }
                .onAppear { followReader(projection, proxy: proxy) }
                .safeAreaInset(edge: .bottom) {
                    NativeGlassControls {
                        VStack(spacing: 8) {
                            ForEach(projection.footer.filter { $0.kind == "slider" || $0.kind == "label" }) { row in
                                rowView(row)
                            }
                            ViewThatFits(in: .horizontal) {
                                HStack { readerButtons(projection.footer) }
                                VStack { readerButtons(projection.footer) }
                            }
                        }.padding(12)
                    }.background(Color(uiColor: .systemBackground))
                }
            }
        }
    }

    private func followReader(_ reader: NativeSurfaceSnapshot.Reader, proxy: ScrollViewProxy) {
        guard reader.following, !readerDragging, let target = reader.targetId else { return }
        readerUserScroll = false
        readerTopId = nil
        proxy.scrollTo(target, anchor: .center)
    }

    private func reportReaderScroll(_ reader: NativeSurfaceSnapshot.Reader, height: CGFloat) {
        guard readerUserScroll, let scroll = reader.scroll else { return }
        let target = readerFrames.filter { entry in
            entry.value.maxY > 0 && entry.value.minY < height && scroll.options.contains { $0.id == entry.key }
        }.sorted { $0.value.minY < $1.value.minY }.first?.key
        guard let target, target != readerTopId else { return }
        readerTopId = target
        Task { await state.send(scroll.id, value: target) }
    }

    @ViewBuilder private func readerButtons(_ rows: [NativeSurfaceRow]) -> some View {
        ForEach(rows.filter { !["slider", "label"].contains($0.kind) }) { row in
            rowView(row, compact: true).modifier(NativeGlassButtonStyle())
        }
    }

    private func chatView(_ chat: NativeSurfaceSnapshot.Chat) -> some View {
        GeometryReader { viewport in
            ScrollViewReader { reader in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 20) {
                        if state.snapshot.failed || state.actionFailed {
                            Text(state.snapshot.error)
                            if state.snapshot.refreshEnabled {
                                Button(state.snapshot.retry) { Task { await state.send("_refresh") } }
                            }
                        }
                        if state.snapshot.loading { ProgressView(state.snapshot.loadingLabel) }
                        else if !state.snapshot.sections.flatMap(\.rows).contains(where: { $0.kind.hasPrefix("message_") }) {
                            Text(state.snapshot.empty).font(.title2).padding(.top, 32)
                        }
                        ForEach(state.snapshot.sections) { section in
                            ForEach(section.rows) { row in rowView(row) }
                        }
                        if chat.streaming { ProgressView(state.snapshot.loadingLabel) }
                        Color.clear.frame(height: 1).id("native-chat-bottom")
                            .background(GeometryReader { geometry in
                                Color.clear.preference(key: NativeChatBottomPreference.self,
                                    value: geometry.frame(in: .named("native-chat-scroll")).maxY)
                            })
                    }.padding(20)
                }.coordinateSpace(name: "native-chat-scroll")
                    .scrollDismissesKeyboard(.interactively)
                    .onPreferenceChange(NativeChatBottomPreference.self) { y in
                        followingChat = y < viewport.size.height + 70
                    }
                    .onPreferenceChange(NativeChatMessageFramesPreference.self) { frames in
                        let bounds = CGRect(origin: .zero, size: viewport.size)
                        let visible = Set(frames.filter { $0.value.intersects(bounds) }.keys)
                        let appeared = visible.subtracting(visibleMessages)
                        visibleMessages = visible
                        for id in appeared where state.snapshot.allRows.contains(where: { $0.id == id && $0.visibilityEnabled == true }) {
                            Task { await state.send("_visible:\(id)") }
                        }
                    }
                    .onAppear { reader.scrollTo("native-chat-bottom", anchor: .bottom) }
                    .onChange(of: state.snapshot.sections) { _ in
                        if followingChat { reader.scrollTo("native-chat-bottom", anchor: .bottom) }
                    }
                    .onChange(of: state.completedChatSend) { _ in
                        followingChat = true
                        reader.scrollTo("native-chat-bottom", anchor: .bottom)
                    }
                    .safeAreaInset(edge: .bottom) {
                        NativeGlassControls {
                            VStack(spacing: 10) {
                                if !chat.followup.isEmpty {
                                    Button(chat.followup) { Task { await state.send("chat_followup") } }
                                        .modifier(NativeGlassButtonStyle()).lineLimit(2)
                                }
                                ForEach(chat.actions.filter { ["label", "waveform"].contains($0.kind) }) { row in
                                    rowView(row)
                                }
                                HStack(alignment: .bottom, spacing: 10) {
                                    ForEach(chat.actions.filter { $0.id != "chat_followup" && !["label", "waveform"].contains($0.kind) }) { row in
                                        if row.kind == "text" { rowView(row).padding(12).modifier(NativeGlassComposerStyle()) }
                                        else {
                                            if row.kind == "menu" {
                                                rowView(row, compact: true)
                                                    .disabled(!row.enabled || state.pending.contains(row.id))
                                                    .accessibilityIdentifier(row.id)
                                            } else {
                                                rowView(row, compact: true).frame(minWidth: 44, minHeight: 44)
                                                    .modifier(NativeGlassButtonStyle())
                                                    .disabled(!row.enabled || state.pending.contains(row.id))
                                                    .accessibilityIdentifier(row.id)
                                            }
                                        }
                                    }
                                }
                            }.padding(.horizontal, 16).padding(.vertical, 10)
                        }
                    }
            }
        }
    }

    private func message(_ row: NativeSurfaceRow) -> some View {
        HStack {
            if row.kind == "message_user" { Spacer(minLength: 30) }
            VStack(alignment: .leading, spacing: 8) {
                Group {
                    if row.plainText == true { Text(verbatim: row.title) }
                    else { Text(.init(row.title)) }
                }.textSelection(.enabled)
                if !row.subtitle.isEmpty { Text(row.subtitle).font(.caption).foregroundStyle(.secondary) }
                if row.enabled {
                    Button { Task { await state.send(row.id) } } label: {
                        Image(systemName: row.symbol ?? "ellipsis").frame(minWidth: 44, minHeight: 44)
                    }.accessibilityLabel(row.subtitle)
                }
            }.padding(row.kind == "message_user" ? 14 : 0)
                .background(row.kind == "message_user" ? Color(uiColor: .secondarySystemGroupedBackground) : .clear,
                    in: RoundedRectangle(cornerRadius: 20))
            if row.kind != "message_user" { Spacer(minLength: 10) }
        }.background(GeometryReader { geometry in
            Color.clear.preference(key: NativeChatMessageFramesPreference.self,
                value: [row.id: geometry.frame(in: .named("native-chat-scroll"))])
        })
    }

    private func action(_ row: NativeSurfaceRow, compact: Bool = false) -> some View {
        Button(role: row.destructive ? .destructive : nil) {
            Task { await state.send(row.id) }
        } label: {
            actionLabel(row, compact: compact)
                .frame(minWidth: compact ? 44 : 0, minHeight: 44)
                .contentShape(Rectangle())
        }
            .disabled(!row.enabled || state.pending.contains(row.id))
            .opacity(row.enabled && !state.pending.contains(row.id) ? 1 : 0.45)
            .accessibilityIdentifier(row.id)
    }

    @ViewBuilder private func actionLabel(_ row: NativeSurfaceRow, iconOnly: Bool = false, compact: Bool = false) -> some View {
        if let symbol = row.symbol {
            if iconOnly || compact {
                Image(systemName: symbol).foregroundStyle(row.destructive ? Color.red : Color.primary)
                    .accessibilityLabel(row.title)
            }
            else { Label { label(row) } icon: { Image(systemName: symbol) } }
        } else if compact { Text(row.title) }
        else { label(row) }
    }

    private func label(_ row: NativeSurfaceRow) -> some View {
        HStack(spacing: 12) {
            if let uri = row.imageUri { NativeThumbnail(uri: uri) }
            VStack(alignment: .leading, spacing: 4) {
                Text(row.title).foregroundStyle(row.destructive ? Color.red : Color.primary)
                if let level = row.level {
                    HStack(spacing: 3) {
                        ForEach(0..<3) { step in
                            Capsule().fill(step < level ? Color.primary : Color.secondary.opacity(0.25))
                                .frame(width: 14, height: 5)
                        }
                    }.accessibilityHidden(true)
                }
                if !row.subtitle.isEmpty { Text(row.subtitle).font(.subheadline).foregroundStyle(.secondary) }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

@available(iOS 16.0, *)
private struct NativeKeypadRow: View {
    let row: NativeSurfaceRow
    @ObservedObject var state: NativeSurfaceState

    private var keys: [NativeSurfaceRow.Option] {
        "123456789*0#".compactMap { digit in row.options.first { $0.id == String(digit) } }
    }

    var body: some View {
        VStack(spacing: 20) {
            HStack {
                Text(row.value?.text.isEmpty == false ? row.value?.text ?? "" : row.title)
                    .font(.title.weight(.light)).lineLimit(2)
                    .frame(maxWidth: .infinity).textSelection(.enabled)
                    .accessibilityIdentifier("\(row.id)_number")
                if row.keypadMode == "dialer" && row.value?.text.isEmpty == false {
                    Button { send("erase") } label: {
                        Image(systemName: "delete.left").frame(minWidth: 44, minHeight: 44)
                    }.buttonStyle(.plain)
                        .modifier(NativeKeypadPress(tap: { send("erase") }, hold: { send("clear") }))
                        .accessibilityLabel(row.eraseLabel ?? "")
                        .accessibilityAction(named: Text(row.clearLabel ?? "")) { send("clear") }
                        .accessibilityIdentifier("\(row.id)_erase")
                }
            }
            NativeGlassControls {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 16), count: 3), spacing: 16) {
                    ForEach(keys) { key in
                        Button { send(key.id) } label: {
                            VStack(spacing: 2) {
                                Text(key.id).font(.largeTitle.weight(.light))
                                if !key.title.isEmpty { Text(key.title).font(.caption2.weight(.medium)) }
                            }.frame(maxWidth: .infinity).frame(minHeight: 72).padding(4)
                        }.buttonStyle(.plain).modifier(NativeKeypadGlass())
                            .modifier(NativeKeypadPress(tap: { send(key.id) }, hold:
                                row.keypadMode == "dialer" && key.id == "0" ? { send("+") } : nil))
                            .accessibilityLabel(key.id)
                            .accessibilityActions {
                                if row.keypadMode == "dialer" && key.id == "0" {
                                    Button("+") { send("+") }
                                }
                            }
                            .accessibilityIdentifier("\(row.id)_key_\(key.id)")
                    }
                }
            }
        }.padding(.vertical, 12)
    }

    private func send(_ key: String) { Task { await state.send(row.id, value: key) } }
}

/// A hold excludes a tap; it must not append both '+' and '0' or erase after Clear.
private struct NativeKeypadPress: ViewModifier {
    let tap: () -> Void
    let hold: (() -> Void)?
    @ViewBuilder func body(content: Content) -> some View {
        if let hold {
            content.highPriorityGesture(LongPressGesture(minimumDuration: 0.5).exclusively(before: TapGesture())
                .onEnded { value in
                    switch value {
                    case .first: hold()
                    case .second: tap()
                    }
                })
        } else { content }
    }
}

private struct NativeKeypadGlass: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26, *) { content.glassEffect(.regular.interactive(), in: .circle) }
        else { content.background(.thinMaterial, in: Circle()) }
    }
}

@available(iOS 16.0, *)
private struct NativeSearchableChoice: View {
    let row: NativeSurfaceRow
    @ObservedObject var state: NativeSurfaceState
    @State private var presented = false
    @State private var search = ""

    var body: some View {
        Button {
            search = ""
            presented = true
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                Text(row.title).foregroundStyle(.primary)
                HStack {
                    Text(row.options.first { $0.id == row.value?.text }?.title ?? "")
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.down").font(.caption).foregroundStyle(.secondary)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).frame(minHeight: 44)
        }.buttonStyle(.plain)
            .sheet(isPresented: $presented) {
                NavigationStack {
                    List(row.options.filter { search.isEmpty || $0.title.localizedCaseInsensitiveContains(search)
                        || $0.id.localizedCaseInsensitiveContains(search) }) { option in
                        Button {
                            Task {
                                await state.send(row.id, value: option.id)
                                if state.valid && !state.actionFailed { presented = false }
                            }
                        } label: {
                            HStack {
                                Text(option.title)
                                Spacer()
                                if option.id == row.value?.text { Image(systemName: "checkmark") }
                            }.frame(minHeight: 44)
                        }.disabled(state.pending.contains(row.id))
                            .accessibilityIdentifier("\(row.id)_option_\(option.id)")
                            .accessibilityAddTraits(option.id == row.value?.text ? .isSelected : [])
                    }.searchable(text: $search, prompt: row.optionSearch ?? "")
                        .navigationTitle(row.title).navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) {
                                Button { presented = false } label: {
                                    Label(row.optionClose ?? "", systemImage: "xmark").labelStyle(.iconOnly)
                                }
                            }
                        }
                }.tint(.primary)
            }
            .onChange(of: state.valid) { valid in
                if !valid { search = ""; presented = false }
            }
    }
}

/// Local images come from the existing file-selection owner. Remote thumbnails are presentation
/// assets only; authentication, upload and API requests remain with the current Dart services.
@available(iOS 16.0, *)
private struct NativeThumbnail: View {
    let uri: String
    @Environment(\.displayScale) private var displayScale
    @State private var localImage: UIImage?

    var body: some View {
        Group {
            if let url = URL(string: uri), url.isFileURL {
                if let localImage { Image(uiImage: localImage).resizable().scaledToFill() }
                else { Image(systemName: "photo").foregroundStyle(.secondary) }
            } else {
                AsyncImage(url: URL(string: uri)) { phase in
                    if let image = phase.image { image.resizable().scaledToFill() }
                    else if phase.error != nil { Image(systemName: "photo").foregroundStyle(.secondary) }
                    else { ProgressView() }
                }
            }
        }.frame(width: 72, height: 64).clipped()
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .accessibilityHidden(true)
            .task(id: uri) {
                localImage = nil
                guard let url = URL(string: uri), url.isFileURL else { return }
                let path = url.resolvingSymlinksInPath().standardizedFileURL.path
                let root = URL(fileURLWithPath: NSHomeDirectory()).resolvingSymlinksInPath().standardizedFileURL.path
                guard path.hasPrefix(root + "/") else { return }
                guard displayScale.isFinite, displayScale > 0, displayScale <= 10 else { return }
                let maxPixels = Int((72 * displayScale).rounded(.up))
                let image = await Task.detached(priority: .userInitiated) {
                    guard let source = CGImageSourceCreateWithURL(url as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary) else { return nil as CGImage? }
                    return CGImageSourceCreateThumbnailAtIndex(source, 0, [
                        kCGImageSourceCreateThumbnailFromImageAlways: true,
                        kCGImageSourceCreateThumbnailWithTransform: true,
                        kCGImageSourceThumbnailMaxPixelSize: maxPixels,
                        kCGImageSourceShouldCacheImmediately: true,
                    ] as CFDictionary)
                }.value
                guard !Task.isCancelled else { return }
                if let image { localImage = UIImage(cgImage: image) }
            }
    }
}

@available(iOS 16.0, *)
private struct NativeTextRow: View {
    let row: NativeSurfaceRow
    @ObservedObject var state: NativeSurfaceState
    // Intentional draft seed; provider updates replace it when this field is not being edited.
    @State private var draft = ""
    @State private var initialized = false
    @FocusState private var focused: Bool

    var body: some View {
        input
            .keyboardType(keyboardType)
            .autocorrectionDisabled(row.keyboard != nil && row.keyboard != "default")
            .focused($focused)
            .onAppear {
                if !initialized { draft = state.draft(for: row); initialized = true }
            }
            .onChange(of: row.value) { value in if !focused || (row.id == "chat_draft" && value?.text == "" && draft == state.sentDraft) { draft = value?.text ?? "" } }
            .onChange(of: state.completedChatSend) { _ in
                if row.id == "chat_draft" && row.value?.text == "" && draft == state.sentDraft { draft = "" }
            }
            .onChange(of: draft) { value in
                if value.count > (row.maximumLength ?? 10000) {
                    draft = String(value.prefix(row.maximumLength ?? 10000))
                    return
                }
                if focused && (value != row.value?.text || row.keyboard == "password") { Task { await state.send(row.id, value: value) } }
            }
    }

    @ViewBuilder private var input: some View {
        if row.keyboard == "password" {
            SecureField(row.title, text: $draft).textInputAutocapitalization(.never)
        } else {
            TextField(row.title, text: $draft, axis: .vertical)
        }
    }

    private var keyboardType: UIKeyboardType {
        switch row.keyboard {
        case "phone": return .phonePad
        case "email": return .emailAddress
        case "url": return .URL
        case "decimal": return .decimalPad
        default: return .default
        }
    }
}

private struct NativeChatBottomPreference: PreferenceKey {
    static var defaultValue: CGFloat { 0 }
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

private struct NativeChatMessageFramesPreference: PreferenceKey {
    static var defaultValue: [String: CGRect] { [:] }
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) {
        value.merge(nextValue(), uniquingKeysWith: { _, latest in latest })
    }
}

/// A one-time secret. Copying goes only through the explicit Copy command to the Dart clipboard
/// owner, so the value offers no system text selection. While the surface is redacted for privacy,
/// the value leaves the view (and accessibility) entirely.
@available(iOS 16.0, *)
private struct NativeSecretRow: View {
    let row: NativeSurfaceRow
    @ObservedObject var state: NativeSurfaceState
    @Environment(\.redactionReasons) private var redaction

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(row.title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            // VoiceOver spells the key out, so it can be transcribed character by character.
            Text(verbatim: redaction.contains(.privacy) ? "" : row.value?.text ?? "")
                .speechSpellsOutCharacters()
                .font(.body.monospaced())
                .privacySensitive()
                .fixedSize(horizontal: false, vertical: true)
            if !row.subtitle.isEmpty { Text(row.subtitle).font(.footnote).foregroundStyle(.secondary) }
            Button { Task { await state.send(row.id, value: "copy") } } label: {
                Label(row.options.first(where: { $0.id == "copy" })?.title ?? "", systemImage: "doc.on.doc")
            }.buttonStyle(.bordered).controlSize(.large).disabled(!row.enabled)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A sensitive surface keeps its secret out of the app-switcher snapshot: while the app is inactive,
/// its content is redacted for privacy under a material. The cover takes no touches; an inactive app
/// receives none.
@available(iOS 16.0, *)
private struct NativeSensitiveCover: ViewModifier {
    let enabled: Bool
    @State private var inactive = false

    func body(content: Content) -> some View {
        content
            .redacted(reason: enabled && inactive ? .privacy : [])
            .overlay {
                if enabled && inactive {
                    Rectangle().fill(.ultraThinMaterial).ignoresSafeArea()
                        .allowsHitTesting(false).accessibilityHidden(true)
                }
            }
            // A surface that appears while the app is already inactive starts redacted.
            .onAppear { inactive = UIApplication.shared.applicationState != .active }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.willResignActiveNotification)) { _ in
                inactive = true
            }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                inactive = false
            }
    }
}

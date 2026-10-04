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
    private var queued: [String: String] = [:]
    private var revision = NativeSnapshotRevision()
    private let perform: (String, Any?) async throws -> Void

    init(snapshot: NativeSurfaceSnapshot, perform: @escaping (String, Any?) async throws -> Void) {
        self.snapshot = snapshot
        self.perform = perform
        _ = revision.accept(snapshot.revision)
    }

    func update(_ snapshot: NativeSurfaceSnapshot) {
        guard valid, revision.accept(snapshot.revision) else { return }
        self.snapshot = snapshot
    }

    func invalidate() {
        valid = false
        queued.removeAll()
        latestEdits.removeAll()
        failedEdits.removeAll()
        sentDraft = nil
        finishEditWaiters()
        snapshot = snapshot.withoutContent()
    }

    func send(_ id: String, value: Any? = nil) async {
        guard valid else { return }
        if let text = value as? String, snapshot.allRows.contains(where: { $0.id == id && $0.kind == "text" }) {
            latestEdits[id] = text
        }
        if pending.contains(id) {
            if let text = value as? String, id == "_search" || snapshot.allRows.contains(where: { $0.id == id && $0.kind == "text" }) {
                queued[id] = text
            }
            return
        }
        let isEdit = snapshot.allRows.contains { $0.id == id && $0.kind == "text" }
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
            guard failedEdits.isEmpty else { actionFailed = true; return }
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
                if valid {
                    actionFailed = true
                    if isEdit { failedEdits.insert(id) }
                }
            }
            next = queued.removeValue(forKey: id)
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

    var body: some View {
        NavigationStack {
            if state.valid {
                content
                    .navigationTitle(state.snapshot.title)
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ForEach(state.snapshot.toolbar) { row in
                            ToolbarItem(placement: row.symbol == "chevron.left" ? .navigationBarLeading : .navigationBarTrailing) { rowView(row, compact: true) }
                        }
                    }
            } else { Color.clear.accessibilityIdentifier("native-surface-invalidated") }
        }
        .tint(.primary)
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

    @ViewBuilder private var content: some View {
        if let chat = state.snapshot.chat {
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
                    ForEach(section.rows) { row in rowView(row) }
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
            case "task":
                HStack(spacing: 12) {
                    Button { Task { await state.send(row.id, value: !(row.value?.bool ?? false)) } } label: {
                        Image(systemName: row.value?.bool == true ? "checkmark.circle.fill" : "circle")
                            .font(.title2).frame(minWidth: 44, minHeight: 44)
                    }.accessibilityLabel(row.title).accessibilityAddTraits(row.value?.bool == true ? .isSelected : [])
                    Button { Task { await state.send(row.id, value: "open") } } label: { label(row) }
                        .contextMenu {
                            ForEach(row.options) { option in
                                Button(option.title) { Task { await state.send(row.id, value: option.id) } }
                            }
                        }
                }.buttonStyle(.plain)
            case "choice":
                Picker(selection: Binding(get: { row.value?.text ?? "" }, set: { value in
                    Task { await state.send(row.id, value: value) }
                })) {
                    ForEach(row.options) { option in Text(option.title).tag(option.id) }
                } label: { label(row) }
                    .pickerStyle(.menu)
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
            case "message_user", "message_ai":
                message(row)
            case "text":
                NativeTextRow(row: row, state: state)
            case "label": label(row).textSelection(.enabled)
            default: action(row, compact: compact)
            }
        }
        .disabled(!row.enabled && !["label", "chart", "waveform", "message_ai", "message_user"].contains(row.kind) || (state.pending.contains(row.id) && row.kind != "text"))
        .accessibilityIdentifier(row.id)
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
                        for id in appeared { Task { await state.send("_visible:\(id)") } }
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
                                            rowView(row, compact: true).frame(minWidth: 44, minHeight: 44)
                                                .modifier(NativeGlassButtonStyle())
                                                .disabled(!row.enabled || state.pending.contains(row.id))
                                                .accessibilityIdentifier(row.id)
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
                Text(.init(row.title)).textSelection(.enabled)
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
            .accessibilityIdentifier(row.id)
    }

    @ViewBuilder private func actionLabel(_ row: NativeSurfaceRow, iconOnly: Bool = false, compact: Bool = false) -> some View {
        if let symbol = row.symbol {
            if iconOnly || compact { Image(systemName: symbol).accessibilityLabel(row.title) }
            else { Label { label(row) } icon: { Image(systemName: symbol) } }
        } else if compact { Text(row.title) }
        else { label(row) }
    }

    private func label(_ row: NativeSurfaceRow) -> some View {
        HStack(spacing: 12) {
            if let uri = row.imageUri { NativeThumbnail(uri: uri) }
            VStack(alignment: .leading, spacing: 4) {
                Text(row.title).foregroundStyle(row.destructive ? Color.red : Color.primary)
                if !row.subtitle.isEmpty { Text(row.subtitle).font(.subheadline).foregroundStyle(.secondary) }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
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
        TextField(row.title, text: $draft, axis: .vertical)
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
                if focused && value != row.value?.text { Task { await state.send(row.id, value: value) } }
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

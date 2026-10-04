import SwiftUI

@available(iOS 16.0, *)
@MainActor
final class NativeHomeState: ObservableObject {
    @Published private(set) var snapshot: NativeHomeSnapshot
    @Published private(set) var valid = true
    @Published private(set) var pending: Set<String> = []
    @Published private(set) var actionFailed = false
    private var revision = NativeSnapshotRevision()
    let action: (String, String?) async throws -> NativeConversation?

    init(snapshot: NativeHomeSnapshot,
         action: @escaping (String, String?) async throws -> NativeConversation?) {
        self.snapshot = snapshot
        self.action = action
        _ = revision.accept(snapshot.revision)
    }

    func update(_ snapshot: NativeHomeSnapshot) {
        guard valid, revision.accept(snapshot.revision) else { return }
        self.snapshot = snapshot
    }

    func send(_ method: String, _ id: String? = nil) async {
        guard valid, !pending.contains(method) else { return }
        pending.insert(method)
        actionFailed = false
        defer { pending.remove(method) }
        do { _ = try await action(method, id) }
        catch { if valid { actionFailed = true } }
    }

    func invalidate() {
        valid = false
        snapshot = snapshot.withoutContent()
    }
}

@available(iOS 16.0, *)
struct NativeHomeView: View {
    @ObservedObject var state: NativeHomeState
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var colorScheme: ColorScheme? {
        switch state.snapshot.appearance {
        case "light": return .light
        case "dark": return .dark
        default: return nil
        }
    }

    var body: some View {
        NavigationStack {
            if state.valid {
                library
            } else {
                ProgressView().accessibilityLabel(state.snapshot.copy.loading)
            }
        }
        .tint(.primary)
        .preferredColorScheme(colorScheme)
        .environment(\.locale, Locale(identifier: state.snapshot.locale))
        .environment(\.layoutDirection, state.snapshot.direction == "rtl" ? .rightToLeft : .leftToRight)
    }

    private var library: some View {
        List {
            if let chrome = state.snapshot.chrome {
                if let capture = chrome.capture {
                    Section { captureCard(capture) }
                }
                if !chrome.alerts.isEmpty {
                    Section {
                        ForEach(chrome.alerts) { control($0) }
                    }
                }
                if !chrome.recaps.isEmpty {
                    Section {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 12) {
                                ForEach(chrome.recaps) { recap in
                                    Button { dispatch("recap", recap.id) } label: {
                                        VStack(alignment: .leading, spacing: 12) {
                                            Text("\(recap.emoji)  \(recap.date)").font(.caption).foregroundStyle(.secondary)
                                            Text(recap.title).font(.headline).foregroundStyle(.primary)
                                                .fixedSize(horizontal: false, vertical: true)
                                        }
                                        .frame(width: dynamicTypeSize.isAccessibilitySize ? 300 : 240, alignment: .leading)
                                        .padding(16)
                                        .frame(minHeight: 130, alignment: .topLeading)
                                        .background(Color(uiColor: .secondarySystemGroupedBackground),
                                                    in: RoundedRectangle(cornerRadius: 20))
                                    }.buttonStyle(.plain)
                                        .accessibilityIdentifier("native-recap-\(recap.id)")
                                }
                            }.padding(.vertical, 4)
                        }
                        .listRowInsets(EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 0))
                        .listRowBackground(Color.clear)
                    } header: {
                        HStack {
                            Text(chrome.recapsTitle)
                            Spacer()
                            Button(state.snapshot.copy.viewAll) { dispatch("recaps") }
                                .textCase(nil)
                        }
                    }
                }
            }
            if state.snapshot.chrome != nil {
                Section {
                    Button { dispatch("browse") } label: {
                        HStack { Text(state.snapshot.copy.conversations).font(.headline); Spacer(); Text(state.snapshot.copy.viewAll) }
                    }.buttonStyle(.plain).listRowBackground(Color.clear)
                        .accessibilityIdentifier("native-browse-all")
                }
            }
            if state.snapshot.localRecordingCount > 0 {
                Button {
                    dispatch("browse")
                } label: {
                    HStack {
                        Label(state.snapshot.copy.recordings, systemImage: "waveform")
                        Spacer()
                        Text(state.snapshot.localRecordingCount, format: .number)
                    }
                }
                .accessibilityIdentifier("native-recordings")
            }
            if state.snapshot.failed || state.actionFailed {
                Section {
                    Text(state.snapshot.copy.error)
                    Button(state.snapshot.copy.retry) {
                        dispatch("refresh")
                    }
                    .accessibilityIdentifier("native-retry")
                }
            }
            if state.snapshot.loading && state.snapshot.groups.isEmpty {
                ProgressView().accessibilityLabel(state.snapshot.copy.loading)
            } else if !state.snapshot.failed && state.snapshot.groups.isEmpty {
                Text(state.snapshot.copy.empty).foregroundStyle(.secondary).listRowBackground(Color.clear)
            }
            ForEach(state.snapshot.groups) { group in
                Section(group.title) {
                    ForEach(group.conversations) { conversation in
                        if conversation.locked || conversation.status != "completed" {
                            Button {
                                dispatch("open", conversation.id)
                            } label: {
                                row(conversation)
                            }
                            .accessibilityIdentifier("native-conversation-\(conversation.id)")
                        } else if state.snapshot.nativeDetail == true {
                            Button { dispatch("open", conversation.id) } label: { row(conversation) }
                                .accessibilityIdentifier("native-conversation-\(conversation.id)")
                        } else {
                            NavigationLink {
                                NativeConversationView(conversation: conversation, state: state)
                            } label: {
                                row(conversation)
                            }
                            .accessibilityIdentifier("native-conversation-\(conversation.id)")
                        }
                    }
                }
            }
            if state.snapshot.hasMore {
                Button(state.snapshot.copy.loadMore) {
                    dispatch("loadMore")
                }
                .disabled(state.snapshot.loading)
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(state.snapshot.chrome?.home ?? state.snapshot.copy.conversations)
        .navigationBarTitleDisplayMode(state.snapshot.chrome == nil ? .inline : .large)
        .refreshable { await state.send("refresh") }
        .safeAreaInset(edge: .bottom) {
            if let chrome = state.snapshot.chrome {
                NativeGlassControls {
                    HStack(spacing: 12) {
                        ForEach(chrome.footer) { action in
                            if action.id == "chat" && !dynamicTypeSize.isAccessibilitySize {
                                control(action, expanded: true).labelStyle(.titleAndIcon).modifier(NativeGlassButtonStyle()).frame(maxWidth: .infinity)
                            } else {
                                control(action).labelStyle(.iconOnly).modifier(NativeGlassButtonStyle())
                                    .frame(minWidth: 44, minHeight: 44)
                            }
                        }
                    }.padding(.horizontal, 16).padding(.vertical, 10)
                }
            }
        }
        .toolbar {
            if let chrome = state.snapshot.chrome {
                ToolbarItem(placement: .navigationBarLeading) {
                    if let device = chrome.header.first {
                        Button { dispatch(device.id) } label: {
                            HStack(spacing: 6) {
                                Image(systemName: device.symbol)
                                Text(device.title)
                            }
                        }.disabled(!device.enabled || state.pending.contains(device.id))
                            .accessibilityIdentifier("native-\(device.id)")
                    }
                }
                ToolbarItemGroup(placement: .navigationBarTrailing) {
                    ForEach(Array(chrome.header.dropFirst())) { action in
                        Button { dispatch(action.id) } label: {
                            Image(systemName: action.symbol)
                        }.accessibilityLabel(action.title).accessibilityIdentifier("native-\(action.id)")
                            .disabled(!action.enabled || state.pending.contains(action.id))
                    }
                }
            } else {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(state.snapshot.copy.viewAll) { dispatch("browse") }
                        .accessibilityIdentifier("native-browse-all")
                }
            }
        }
    }

    private func dispatch(_ method: String, _ id: String? = nil) {
        Task { await state.send(method, id) }
    }

    private func control(_ action: NativeHomeSnapshot.Chrome.Action, expanded: Bool = false) -> some View {
        Button { dispatch(action.id) } label: {
            Label { Text(action.title) } icon: { Image(systemName: action.symbol).font(.system(size: 20)) }
                .frame(maxWidth: expanded ? .infinity : nil)
        }
            .disabled(!action.enabled || state.pending.contains(action.id))
            .accessibilityIdentifier("native-\(action.id)")
    }

    private func captureCard(_ capture: NativeHomeSnapshot.Chrome.Capture) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: capture.source == "phone" ? "iphone" : capture.source == "call" ? "phone.fill" : "waveform")
                    .font(.title2).accessibilityHidden(true)
                Button { dispatch("capture") } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(capture.status).font(.headline).foregroundStyle(.primary)
                        Text([capture.elapsed, capture.detail].filter { !$0.isEmpty }.joined(separator: " · "))
                            .font(.subheadline).foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(.plain)
                ForEach(capture.actions) { action in
                    Button { dispatch(action.id) } label: { Image(systemName: action.symbol).frame(minWidth: 44, minHeight: 44) }
                        .accessibilityLabel(action.title).disabled(!action.enabled || state.pending.contains(action.id))
                }
            }
            if !capture.explanation.isEmpty { Text(capture.explanation).font(.footnote).foregroundStyle(.secondary) }
            if !capture.lastLine.isEmpty { Text(capture.lastLine).font(.subheadline).lineLimit(2) }
        }.padding(.vertical, 4)
            .accessibilityIdentifier("native-live-capture")
    }

    private func row(_ conversation: NativeConversation) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(conversation.title).font(.headline)
                if conversation.locked {
                    Image(systemName: "lock.fill").accessibilityHidden(true)
                }
                if conversation.starred {
                    Image(systemName: "star.fill").accessibilityHidden(true)
                }
            }
            Text(conversation.timestamp).font(.subheadline).foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
        .frame(minHeight: 44, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityValue(conversation.starred ? state.snapshot.copy.starred : "")
        .accessibilityHint(conversation.locked ? state.snapshot.copy.lockedHint : "")
    }
}

@available(iOS 16.0, *)
private struct NativeConversationView: View {
    let conversation: NativeConversation
    @ObservedObject var state: NativeHomeState
    @State private var detail: NativeConversation?
    @State private var selectedTab = 0
    @State private var failed = false

    private var available: Bool {
        state.valid && state.snapshot.conversation(id: conversation.id)?.locked == false
    }

    var body: some View {
        Group {
            if !available {
                Text(state.snapshot.copy.noTranscript).foregroundStyle(.secondary)
            } else if let detail {
                VStack(spacing: 0) {
                    Picker("", selection: $selectedTab) {
                        Text(state.snapshot.copy.summary).tag(0)
                        Text(state.snapshot.copy.transcript).tag(1)
                    }
                    .pickerStyle(.segmented)
                    .padding()
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 20) {
                            if selectedTab == 0 {
                                Text(markdown(detail.summary?.isEmpty == false
                                              ? detail.summary ?? "" : state.snapshot.copy.noSummary))
                                    .textSelection(.enabled)
                            } else if let segments = detail.transcript, !segments.isEmpty {
                                ForEach(segments) { segment in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(segment.speaker).font(.subheadline).foregroundStyle(.secondary)
                                        Text(segment.text).textSelection(.enabled)
                                    }
                                }
                            } else {
                                Text(detail.externalText?.isEmpty == false
                                     ? detail.externalText ?? "" : state.snapshot.copy.noTranscript)
                                    .textSelection(.enabled)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                    }
                }
            } else if failed {
                VStack(spacing: 16) {
                    Text(state.snapshot.copy.error)
                    Button(state.snapshot.copy.retry) { Task { await load() } }
                }
                .padding()
            } else {
                ProgressView().accessibilityLabel(state.snapshot.copy.loading)
            }
        }
        .navigationTitle(available
                         ? state.snapshot.conversation(id: conversation.id)?.title ?? conversation.title
                         : state.snapshot.copy.conversations)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    Task {
                        _ = try? await state.action("open", conversation.id)
                        await load()
                    }
                } label: {
                    Label(state.snapshot.copy.more, systemImage: "ellipsis.circle")
                }
                .accessibilityIdentifier("native-conversation-actions")
                .disabled(!available)
            }
        }
        .task { await load() }
        .onChange(of: available) { accessible in
            if !accessible { detail = nil }
        }
    }

    private func load() async {
        guard available else { detail = nil; return }
        failed = false
        do {
            let result = try await state.action("detail", conversation.id)
            guard !Task.isCancelled, available else { detail = nil; return }
            guard result?.id == conversation.id, result?.locked == false else {
                detail = nil
                failed = true
                return
            }
            detail = result
            if result?.summary?.isEmpty != false { selectedTab = 1 }
            failed = result == nil
        } catch {
            guard !Task.isCancelled, available else { detail = nil; return }
            failed = true
        }
    }

    private func markdown(_ text: String) -> AttributedString {
        (try? AttributedString(markdown: text,
                               options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(text)
    }
}

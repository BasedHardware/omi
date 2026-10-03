import SwiftUI

@available(iOS 16.0, *)
@MainActor
final class NativeHomeState: ObservableObject {
    @Published private(set) var snapshot: NativeHomeSnapshot
    @Published private(set) var valid = true
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

    func invalidate() {
        valid = false
        snapshot = snapshot.withoutContent()
    }
}

@available(iOS 16.0, *)
struct NativeHomeView: View {
    @ObservedObject var state: NativeHomeState

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
            if state.snapshot.localRecordingCount > 0 {
                Button {
                    Task { _ = try? await state.action("browse", nil) }
                } label: {
                    HStack {
                        Label(state.snapshot.copy.recordings, systemImage: "waveform")
                        Spacer()
                        Text(state.snapshot.localRecordingCount, format: .number)
                    }
                }
                .accessibilityIdentifier("native-recordings")
            }
            if state.snapshot.failed {
                Section {
                    Text(state.snapshot.copy.error)
                    Button(state.snapshot.copy.retry) {
                        Task { _ = try? await state.action("refresh", nil) }
                    }
                    .accessibilityIdentifier("native-retry")
                }
            }
            if state.snapshot.loading && state.snapshot.groups.isEmpty {
                ProgressView().accessibilityLabel(state.snapshot.copy.loading)
            } else if !state.snapshot.failed && state.snapshot.groups.isEmpty {
                Text(state.snapshot.copy.empty).foregroundStyle(.secondary)
            }
            ForEach(state.snapshot.groups) { group in
                Section(group.title) {
                    ForEach(group.conversations) { conversation in
                        if conversation.locked || conversation.status != "completed" {
                            Button {
                                Task { _ = try? await state.action("open", conversation.id) }
                            } label: {
                                row(conversation)
                            }
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
                    Task { _ = try? await state.action("loadMore", nil) }
                }
                .disabled(state.snapshot.loading)
            }
        }
        .listStyle(.plain)
        .navigationTitle(state.snapshot.copy.conversations)
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { _ = try? await state.action("refresh", nil) }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(state.snapshot.copy.viewAll) {
                    Task { _ = try? await state.action("browse", nil) }
                }
                .accessibilityIdentifier("native-browse-all")
            }
        }
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

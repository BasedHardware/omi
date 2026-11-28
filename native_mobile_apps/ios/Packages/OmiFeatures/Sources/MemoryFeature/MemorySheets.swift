import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Edit a memory's text, pin it as a baseline, keep it private (Flutter `memory_edit_sheet`).
struct EditMemorySheet: View {
    @Environment(MemoriesStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    let memory: Memory
    @State private var text = ""
    @FocusState private var focused: Bool

    private var current: Memory {
        store.memories.first { $0.id == memory.id } ?? memory
    }

    var body: some View {
        NavigationStack {
            Form {
                TextField(L("editMemoryTitle"), text: $text, axis: .vertical)
                    .lineLimit(2 ... 8)
                    .focused($focused)
                    .disabled(memory.isLocked)
                Section {
                    Toggle(isOn: Binding(
                        get: { current.isBaseline },
                        set: { pinned in Task { await store.setBaseline(memory.id, pinned: pinned) } }
                    )) {
                        Label(L("baselineMemory"), systemImage: "pin")
                    }
                    Toggle(isOn: Binding(
                        get: { current.visibility == .private },
                        set: { isPrivate in Task { await store.setVisibility(memory.id, isPrivate ? .private : .public) } }
                    )) {
                        Label(L("nativeMemoryPrivate"), systemImage: "lock")
                    }
                } footer: {
                    Text(L("nativeMemoryPrivateFooter"))
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(L("editMemoryTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("save")) {
                        Task { await store.edit(memory.id, content: text) }
                        dismiss()
                    }
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || text == memory.content)
                }
            }
            .onAppear {
                text = memory.content
                focused = !memory.isLocked
            }
        }
    }
}

/// Tell Omi something by hand; it is stored as a manual memory.
struct NewMemorySheet: View {
    @Environment(MemoriesStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var isSaving = false
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            Form {
                TextField(L("nativeWhatShouldOmiRemember"), text: $text, axis: .vertical)
                    .lineLimit(2 ... 8)
                    .focused($focused)
                if let error = store.lastError {
                    Text(error).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(L("newMemoryTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("save")) {
                        isSaving = true
                        Task {
                            if await store.add(text) {
                                DSHaptics.success()
                                dismiss()
                            }
                            isSaving = false
                        }
                    }
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
                    .accessibilityIdentifier("memories.save")
                }
            }
            .onAppear { focused = true }
        }
    }
}

/// Memories › Memory graph: the knowledge graph full screen, shared as an image.
struct MemoryGraphScreen: View {
    @State private var graph: KnowledgeGraphStore
    @State private var shareImage: Image?

    init(store: KnowledgeGraphStore) {
        _graph = State(initialValue: store)
    }

    var body: some View {
        content
            .background(DS.Palette.background)
            .navigationTitle(L("memoryGraphTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if let shareImage {
                    ShareLink(item: shareImage, message: Text(L("checkOutMyMemoryGraph")),
                              preview: SharePreview(L("memoryGraph"), image: shareImage)) {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .accessibilityLabel(L("share"))
                }
            }
            .task {
                await graph.load()
                renderShareImage()
            }
            .refreshable { await graph.load() }
    }

    @ViewBuilder
    private var content: some View {
        switch graph.phase {
        case .idle, .loading:
            ProgressView(L("loadingKnowledgeGraph")).frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed:
            ContentUnavailableView {
                Label(L("couldNotLoadKnowledgeGraph"), systemImage: "point.3.connected.trianglepath.dotted")
            } actions: {
                Button(L("tryAgain")) { Task { await graph.load() } }
            }
        case .loaded where graph.isEmpty:
            ContentUnavailableView(
                L("noKnowledgeGraphYet"), systemImage: "point.3.connected.trianglepath.dotted",
                description: Text(L("nativeGraphBuildsItself"))
            )
        case .loaded:
            KnowledgeGraphView(store: graph).padding(DS.Spacing.lg)
        }
    }

    /// A square picture with "omi.me" on top, like Flutter's share.
    private func renderShareImage() {
        guard graph.phase == .loaded, !graph.isEmpty else { return }
        let card = VStack(spacing: 24) {
            Text("omi.me").font(.system(size: 48, weight: .bold)).foregroundStyle(.white)
            KnowledgeGraphView(store: graph, interactive: false)
        }
        .padding(60)
        .frame(width: 1080, height: 1080)
        .background(Color.black)
        .environment(\.colorScheme, .dark)
        let renderer = ImageRenderer(content: card)
        renderer.scale = 1
        if let image = renderer.uiImage { shareImage = Image(uiImage: image) }
    }
}

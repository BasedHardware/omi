import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// How Omi helps › Memory (Flutter's onboarding `knowledge_graph_step`, kept here instead of in
/// onboarding): the map of people, places and things Omi learned with a few counts, what it knows
/// about you directly, importing history from another device, and deleting all memories.
/// Memory visibility lives in the Memories screen's menu.
struct KnowledgeSummaryScreen: View {
    @Environment(MemoriesStore.self) private var memories
    @Environment(SessionStore.self) private var session
    @Environment(SettingsStore.self) private var settings
    @State private var graph: KnowledgeGraphStore?
    @State private var confirmDeleteMemories = false
    @State private var deletedMemories: Bool?

    var body: some View {
        SettingsList {
            Section {
                VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                    Text(L("onboardingWhatIKnowAboutYouTitle")).font(DS.Typography.sectionTitle)
                    Text(L("nativeWhatIKnowDescription")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                }
                .padding(.vertical, DS.Spacing.xs)
                graphPreview
                counts
            }
            let aboutYou = memories.visible(category: "system").prefix(5)
            if !aboutYou.isEmpty {
                Section(L("nativeMemoryKindAboutYou")) {
                    ForEach(aboutYou) { memory in
                        Text(memory.content).font(DS.Typography.callout).lineLimit(3)
                    }
                }
            }
            Section {
                NavigationLink { ImportScreen(store: settings.makeImportStore()) } label: {
                    SettingsRowLabel(title: L("nativeSettingsImportHistory"), systemImage: "square.and.arrow.down")
                }
                .accessibilityIdentifier("memory.import")
            } footer: {
                Text(L("nativeSettingsImportFooter"))
            }
            Section {
                Button(L("nativeDeleteAllMemories"), role: .destructive) { confirmDeleteMemories = true }
                    .disabled(memories.phase == .loaded && memories.memories.isEmpty)
                    .accessibilityIdentifier("privacy.deleteAllMemories")
            } footer: {
                if let deletedMemories {
                    Text(deletedMemories ? L("nativeAllMemoriesDeleted") : L("nativeCouldNotDeleteMemories"))
                        .foregroundStyle(deletedMemories ? DS.Palette.inkSecondary : DS.Palette.live)
                }
            }
        }
        .omiPage(L("nativeSettingsMemory"))
        .task { if memories.phase == .idle { await memories.load() } }
        .task {
            let store = graph ?? memories.makeGraphStore(userName: session.displayName)
            graph = store
            await store.load()
        }
        .confirmationDialog(
            L("nativeDeleteAllMemoriesQuestion", String(memories.memories.count)),
            isPresented: $confirmDeleteMemories, titleVisibility: .visible
        ) {
            Button(L("nativeDeleteAllMemories"), role: .destructive) {
                Task {
                    let deleted = await memories.deleteAll()
                    if deleted { DSHaptics.success() }
                    deletedMemories = deleted
                }
            }
        } message: {
            Text(L("nativeDeleteAllMemoriesWarning"))
        }
    }

    @ViewBuilder
    private var graphPreview: some View {
        switch graph?.phase {
        case .loaded?:
            if let graph, !graph.isEmpty {
                KnowledgeGraphView(store: graph, interactive: false)
                    .frame(height: 260)
                    .listRowInsets(EdgeInsets())
            } else {
                Label(L("noKnowledgeGraphYet"), systemImage: "point.3.connected.trianglepath.dotted")
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
        case .failed?:
            retry(L("couldNotLoadKnowledgeGraph")) { await graph?.load() }
        default:
            ProgressView(L("loadingKnowledgeGraph")).frame(maxWidth: .infinity, minHeight: 120)
        }
    }

    /// Memories by kind, and people and places on the map, as one row of numbers.
    private var counts: some View {
        HStack {
            number(count("system"), L("nativeMemoryKindAboutYou"))
            number(count("interesting"), L("filterInteresting"))
            if let graph, graph.phase == .loaded {
                number(String(graph.nodes.count { $0.node.kind == "person" }), L("people"))
                number(String(graph.nodes.count { $0.node.kind == "place" }), L("nativePlaces"))
            } else {
                number(count("manual"), L("filterManual"))
            }
        }
        .padding(.vertical, DS.Spacing.xs)
    }

    private func number(_ value: String, _ label: String) -> some View {
        VStack(spacing: DS.Spacing.xxs) {
            Text(value).font(DS.Typography.sectionTitle).monospacedDigit()
            Text(label).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary).lineLimit(1).minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }

    private func count(_ category: String) -> String {
        String(memories.memories.count { $0.category == category })
    }
}

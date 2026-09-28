import OmiKit
import SwiftUI

// Memories page, ported from `react-native/src/pages/Memories.tsx`: search
// over loaded memories, dated cards with citation counts, the synthesized
// provenance line, Load more, and the ReadStatus footer.

public struct MemoriesPage: View {
    public var embedded: Bool = false

    @EnvironmentObject private var store: AppStore
    @State private var query: String = ""

    public init(embedded: Bool = false) {
        self.embedded = embedded
    }

    private var outcome: ReadOutcome<DomainRead<MemoryProjection>>? {
        store.outcomes?.memories
    }

    private var loading: Bool { store.readsLoading }

    private var memories: [MemoryProjection] {
        if case .success(let read) = outcome { return read.items }
        return []
    }

    private var page: ReadPageState? {
        if case .success(let read) = outcome { return read.page }
        return nil
    }

    private var error: String? {
        if case .error(let message) = outcome { return message }
        return nil
    }

    private var results: [MemoryProjection] {
        memories.filter { matchesSearchQuery($0.searchableText, query) }
    }

    private var filtering: Bool {
        !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !embedded {
                Text("Memories")
                    .font(TypeStyle(size: 22, lineHeight: 28, weight: .semibold).font)
                    .foregroundColor(Color.white)
                    .padding(.bottom, 18)
            }
            searchBox
                .padding(.bottom, 14)
            if loading && outcome == nil {
                VStack(spacing: 12) {
                    ProgressView().tint(OmiColor.hex(0x888888))
                    Text("Loading memories…")
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                }
                .frame(maxWidth: .infinity)
                .padding(24)
            } else if let error {
                VStack(spacing: 8) {
                    Text("Memories unavailable")
                        .font(TypeStyle(size: 16, lineHeight: 22, weight: .semibold).font)
                        .foregroundColor(Palette.text)
                    Text(error)
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                        .accessibilityLabel(error)
                }
                .frame(maxWidth: .infinity)
                .padding(24)
            } else {
                list
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var searchBox: some View {
        HStack(spacing: Space.sm) {
            KitIcon(.search, size: 17, color: OmiColor.hex(0x777777))
            TextField("Search loaded memories", text: $query)
                .font(Typography.body.font)
                .foregroundColor(Color.white)
                .frame(minHeight: 44)
                .accessibilityLabel("Search loaded memories")
        }
        .padding(.horizontal, Space.md)
        .background(Palette.input)
        .overlay(
            RoundedRectangle(cornerRadius: Radius.md)
                .strokeBorder(Palette.line, lineWidth: Borders.width)
        )
        .clipShape(RoundedRectangle(cornerRadius: Radius.md))
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if results.isEmpty {
                    VStack(spacing: 6) {
                        Text(filtering ? "No loaded memories match." : "No memories yet.")
                            .font(TypeStyle(size: 16, lineHeight: 22, weight: .semibold).font)
                            .foregroundColor(Palette.text)
                        if filtering {
                            Text("Search covers the memories loaded on this device.")
                                .font(Typography.caption.font)
                                .foregroundColor(Palette.textMuted)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(24)
                } else {
                    ForEach(results) { memory in
                        MemoryCard(memory: memory)
                    }
                }
                if let page {
                    ReadStatusView(label: "Memories", page: page)
                    if page.hasMore && page.nextCursor != nil {
                        Button(action: { Task { await store.loadOlderMemories() } }) {
                            Text("Load more")
                                .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                                .foregroundColor(Palette.textMuted)
                                .frame(maxWidth: .infinity, alignment: .leading).frame(minHeight: 44)
                        }
                        .buttonStyle(KitPressableStyle())
                        .accessibilityLabel("Load more memories")
                    }
                }
            }
            .padding(.vertical, 14)
            .padding(.bottom, 28)
        }
    }
}

public struct MemoryCard: View {
    public let memory: MemoryProjection

    public init(memory: MemoryProjection) {
        self.memory = memory
    }

    private var citationCopy: String {
        let count = memory.citations.count
        return count == 1 ? "1 citation" : "\(count) citations"
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(KitFormat.memoryDate(memory.timestamp))
                    .font(TypeStyle(size: 11, lineHeight: 14, weight: .semibold).font)
                    .foregroundColor(OmiColor.hex(0x898989))
                Spacer()
                Text(citationCopy)
                    .font(TypeStyle(size: 11, lineHeight: 14, weight: .regular).font)
                    .foregroundColor(OmiColor.hex(0x707070))
            }
            Text(memory.summary)
                .font(Typography.body.font)
                .foregroundColor(Color.white)
            Text("Synthesized memory")
                .font(TypeStyle(size: 11, lineHeight: 14, weight: .regular).font)
                .foregroundColor(OmiColor.hex(0x888888))
                .padding(.top, 3)
        }
        .padding(16)
        .background(Palette.surface)
        .overlay(
            RoundedRectangle(cornerRadius: Radius.lg)
                .strokeBorder(Palette.line, lineWidth: Borders.width)
        )
        .clipShape(RoundedRectangle(cornerRadius: Radius.lg))
        .accessibilityLabel("Memory: \(memory.title)")
    }
}

import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The transcript page, typeset like a document: the recording (if kept), then one paragraph per
/// turn (a speaker's consecutive lines merged), each under a small "Anna · 4:05" label. Search
/// opens from the magnifier above the page or the "…" menu. Long-press a paragraph to correct
/// its words; tap the name to say who it was.
struct TranscriptView: View {
    let store: ConversationDetailStore
    @Binding var query: String
    /// Index into `matches` of the line being shown.
    @Binding var cursor: Int
    /// The search field is open.
    @Binding var showsSearch: Bool
    let onShareAudio: () -> Void
    @State private var editing: ConversationDetail.Line?
    /// A paragraph of several lines being corrected: pick which line first.
    @State private var choosingLine: ConversationDigest.Paragraph?
    /// Chapters opened past their first turns ("Show all").
    @State private var expanded: Set<Int> = []
    @FocusState private var searching: Bool
    // Speaker naming (SpeakerTranscript.swift).
    @State var speakers: TranscriptSpeakersStore
    @State var naming: ConversationDetail.Line?
    @State var reviewsMatches = false
    @Environment(SettingsStore.self) var settings
    @Environment(ConversationsStore.self) var conversations

    init(
        store: ConversationDetailStore, query: Binding<String>, cursor: Binding<Int>, showsSearch: Binding<Bool>,
        onShareAudio: @escaping () -> Void
    ) {
        self.store = store
        _query = query
        _cursor = cursor
        _showsSearch = showsSearch
        self.onShareAudio = onShareAudio
        _speakers = State(initialValue: TranscriptSpeakersStore(detail: store))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            if store.detail?.hasAudio == true { AudioPlayerBar(store: store, onShare: onShareAudio) }
            if let lines = store.detail?.transcript, !lines.isEmpty {
                if showsSearch || !query.isEmpty { searchField }
                speakerTools
                let chapters = ConversationDigest.chapters(lines, sections: store.detail?.chapters ?? [])
                let hits = Set(matches)
                LazyVStack(alignment: .leading, spacing: DS.Spacing.section) {
                    ForEach(chapters) { chapter in
                        // A chapter with a search hit opens by itself.
                        let open = expanded.contains(chapter.id) || chapter.paragraphs
                            .contains { $0.lines.contains { hits.contains($0.id) } }
                        chapterView(chapter, isOpen: open)
                    }
                }
            } else {
                Text(store.detail == nil ? L("loading") : L("noTranscriptMessage"))
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
        }
        .sheet(item: $editing) { line in
            EditLineSheet(line: line) { text in Task { await store.editLine(line.id, text: text) } }
                .presentationDetents([.medium])
        }
        .confirmationDialog(
            L("nativeEditText"),
            isPresented: Binding(get: { choosingLine != nil }, set: { if !$0 { choosingLine = nil } }),
            presenting: choosingLine
        ) { paragraph in
            ForEach(paragraph.lines.filter { $0.segmentID != nil }) { line in
                Button(Self.preview(line.text)) { editing = line }
            }
        }
        .sheet(item: $naming) { line in NameSpeakerSheet(line: line, speakers: speakers) }
        .sheet(isPresented: $reviewsMatches) { VoiceMatchesSheet(speakers: speakers) }
        .task { if settings.people.isEmpty { await settings.loadPeople() } }
        .onChange(of: query) { _, _ in cursor = 0 }
        .onChange(of: showsSearch) { _, shows in searching = shows }
        .onAppear { if showsSearch { searching = true } }
    }

    /// The scroll anchor of the paragraph holding line `id` (`paragraphID` of that line).
    static func anchor(_ id: Int) -> String {
        "paragraph-\(id)"
    }

    /// The paragraph a line belongs to, for scrolling to a search match.
    static func paragraphID(of lineID: Int, in lines: [ConversationDetail.Line]) -> Int? {
        ConversationDigest.paragraphs(lines).first { $0.contains(lineID) }?.id
    }

    var matches: [Int] {
        store.detail?.lines(matching: query) ?? []
    }

    private var searchField: some View {
        HStack(spacing: DS.Spacing.sm) {
            Image(systemName: "magnifyingglass").foregroundStyle(DS.Palette.inkTertiary)
            TextField(L("searchTranscriptOrSummary"), text: $query)
                .focused($searching)
                .submitLabel(.search)
                .autocorrectionDisabled()
                .onSubmit { step(1) }
            if !query.isEmpty {
                Text(matches.isEmpty ? L("noResultsFound") : L("nativeMatchPosition", String(cursor + 1), String(matches.count)))
                    .font(DS.Typography.micro)
                    .monospacedDigit()
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
                Button { step(-1) } label: { Image(systemName: "chevron.up") }
                    .disabled(matches.count < 2)
                    .accessibilityLabel(L("nativePreviousMatch"))
                Button { step(1) } label: { Image(systemName: "chevron.down") }
                    .disabled(matches.count < 2)
                    .accessibilityLabel(L("nativeNextMatch"))
            }
            Button {
                query = ""
                searching = false
                withAnimation(DS.Motion.standard) { showsSearch = false }
            } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(DS.Palette.inkTertiary) }
                .accessibilityLabel(L("cancel"))
        }
        .font(DS.Typography.callout)
        .buttonStyle(.plain)
        .padding(.horizontal, DS.Spacing.md)
        .frame(minHeight: 40)
        .omiSurface(Capsule())
    }

    /// The start of a line, for choosing which one to correct.
    static func preview(_ text: String) -> String {
        text.count > 48 ? String(text.prefix(48)) + "…" : text
    }

    private func step(_ delta: Int) {
        guard !matches.isEmpty else { return }
        DSHaptics.selection()
        cursor = (cursor + delta + matches.count) % matches.count
    }

    /// Turns shown while a chapter is closed.
    static let closedTurns = 3

    /// A chapter: its heading (the notes' section) or its start time, the first turns, and
    /// "Show all (n)" for the rest.
    private func chapterView(_ chapter: ConversationDigest.Chapter, isOpen: Bool) -> some View {
        let shown = isOpen ? chapter.paragraphs : Array(chapter.paragraphs.prefix(Self.closedTurns))
        return VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                if let title = chapter.title {
                    Text(title)
                        .font(DS.Typography.callout.weight(.semibold))
                        .foregroundStyle(DS.Palette.ink)
                        .accessibilityAddTraits(.isHeader)
                }
                Text(ConversationDigest.timestamp(chapter.start))
                    .font(chapter.title == nil ? DS.Typography.callout.weight(.semibold) : DS.Typography.caption)
                    .monospacedDigit()
                    .foregroundStyle(chapter.title == nil ? DS.Palette.ink : DS.Palette.inkTertiary)
            }
            ForEach(shown) { paragraph in
                paragraphView(paragraph).id(Self.anchor(paragraph.id))
            }
            let hidden = chapter.paragraphs.count - shown.count
            if hidden > 0 || (isOpen && expanded.contains(chapter.id) && chapter.paragraphs.count > Self.closedTurns) {
                Button {
                    DSHaptics.selection()
                    withAnimation(DS.Motion.standard) {
                        if hidden > 0 { expanded.insert(chapter.id) } else { expanded.remove(chapter.id) }
                    }
                } label: {
                    HStack(spacing: DS.Spacing.xs) {
                        Text(hidden > 0 ? L("nativeShowAllTurns", String(chapter.paragraphs.count)) : L("nativeLess"))
                        Image(systemName: hidden > 0 ? "chevron.down" : "chevron.up").font(.system(size: 11, weight: .regular))
                    }
                    .font(DS.Typography.caption.weight(.medium))
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("transcript.chapter.\(chapter.id)")
            }
        }
    }

    /// One turn as a paragraph: "Anna  4:05" small and gray above (just the time when the same
    /// speaker goes on), the words in callout size with room between the lines. The paragraph
    /// holding the current search match gets a soft amber wash.
    private func paragraphView(_ paragraph: ConversationDigest.Paragraph) -> some View {
        let current = matches.isEmpty ? nil : matches[min(cursor, matches.count - 1)]
        let isCurrent = current.map(paragraph.contains) ?? false
        return VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                if !paragraph.continuesTurn { speakerLabel(paragraph.first) }
                Text(ConversationDigest.timestamp(paragraph.first.start))
                    .font(DS.Typography.caption)
                    .monospacedDigit()
                    .foregroundStyle(DS.Palette.inkTertiary)
                    .accessibilityHidden(true)
            }
            Text(text(of: paragraph))
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.ink)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
                .onLongPressGesture { correct(paragraph) }
                .accessibilityAction(named: L("nativeEditText")) { correct(paragraph) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, isCurrent ? DS.Spacing.sm : 0)
        .padding(.horizontal, DS.Spacing.sm)
        .background(
            isCurrent ? DS.Palette.warning.opacity(0.12) : .clear,
            in: RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous)
        )
        .padding(.horizontal, -DS.Spacing.sm)
    }

    /// The paragraph's lines as one text, every occurrence of the search highlighted.
    private func text(of paragraph: ConversationDigest.Paragraph) -> AttributedString {
        var text = AttributedString()
        for (index, line) in paragraph.lines.enumerated() {
            if index > 0 { text += AttributedString(" ") }
            text += Self.highlighted(line.text, query: query)
        }
        return text
    }

    /// One line opens its editor at once; a merged paragraph asks which line first.
    private func correct(_ paragraph: ConversationDigest.Paragraph) {
        let editable = paragraph.lines.filter { $0.segmentID != nil }
        guard !editable.isEmpty else { return }
        DSHaptics.tap(.medium)
        if editable.count == 1 { editing = editable[0] } else { choosingLine = paragraph }
    }

    /// Every occurrence of `query` gets a highlight.
    static func highlighted(_ text: String, query: String) -> AttributedString {
        var attributed = AttributedString(text)
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return attributed }
        var searchStart = attributed.startIndex
        while searchStart < attributed.endIndex,
              let range = attributed[searchStart...].range(of: query, options: [.caseInsensitive, .diacriticInsensitive])
        {
            attributed[range].backgroundColor = DS.Palette.warning.opacity(0.35)
            searchStart = range.upperBound
        }
        return attributed
    }
}

/// Correcting what Omi heard in one line.
private struct EditLineSheet: View {
    let line: ConversationDetail.Line
    let onSave: (String) -> Void
    @State private var text: String
    @Environment(\.dismiss) private var dismiss

    init(line: ConversationDetail.Line, onSave: @escaping (String) -> Void) {
        self.line = line
        self.onSave = onSave
        _text = State(initialValue: line.text)
    }

    var body: some View {
        NavigationStack {
            TextEditor(text: $text)
                .font(DS.Typography.body)
                .scrollContentBackground(.hidden)
                .padding(DS.Spacing.md)
                .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
                .padding(DS.Spacing.gutter)
                .navigationTitle(line.speaker)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(L("save")) {
                            onSave(text)
                            dismiss()
                        }
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
                .background(DS.Palette.background)
        }
    }
}

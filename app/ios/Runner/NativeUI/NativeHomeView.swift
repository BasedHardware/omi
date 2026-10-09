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

    /// Loaded, not failed and without a conversation.
    private var isEmpty: Bool {
        !state.snapshot.loading && !state.snapshot.failed && state.snapshot.groups.isEmpty
    }

    /// Nothing else is listed, so the empty state centres on the screen rather than sitting in a row.
    private var showsOnlyEmpty: Bool {
        isEmpty && state.snapshot.chrome == nil && state.snapshot.localRecordingCount == 0
            && !state.snapshot.hasMore && !state.actionFailed
    }

    private var emptyState: some View {
        NativeEmptyState(title: state.snapshot.copy.empty, symbol: "bubble.left.and.text.bubble.right")
    }

    private var library: some View {
        List {
            if let chrome = state.snapshot.chrome { chromeSections(chrome) }
            if state.snapshot.chrome != nil {
                // The browse row is the section's header, so Recordings sits directly beneath it.
                Section {
                    if state.snapshot.localRecordingCount > 0 { recordingsRow }
                } header: {
                    Button { dispatch("browse") } label: {
                        NativeSectionHeader(title: state.snapshot.copy.conversations) {
                            NativeSectionAction(title: state.snapshot.copy.viewAll)
                        }
                    }.buttonStyle(.plain)
                        .accessibilityIdentifier("native-browse-all")
                }
            } else if state.snapshot.localRecordingCount > 0 {
                recordingsRow
            }
            if state.snapshot.failed || state.actionFailed {
                Section {
                    Label {
                        Text(state.snapshot.copy.error)
                    } icon: {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                            .accessibilityHidden(true)
                    }
                    Button(state.snapshot.copy.retry) {
                        dispatch("refresh")
                    }
                    .accessibilityIdentifier("native-retry")
                }
            }
            if state.snapshot.loading && state.snapshot.groups.isEmpty {
                ProgressView().accessibilityLabel(state.snapshot.copy.loading).frame(maxWidth: .infinity)
            } else if isEmpty && !showsOnlyEmpty {
                emptyState.listRowBackground(Color.clear)
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
        .overlay {
            if showsOnlyEmpty { emptyState.allowsHitTesting(false).transition(.opacity) }
        }
        .navigationTitle(state.snapshot.chrome?.home ?? state.snapshot.copy.conversations)
        .navigationBarTitleDisplayMode(state.snapshot.chrome == nil ? .inline : .large)
        .refreshable { await state.send("refresh") }
        .safeAreaInset(edge: .bottom) {
            if let chrome = state.snapshot.chrome {
                NativeGlassControls {
                    // One 44 pt height for the Ask capsule and the round actions, like the composer's controls.
                    HStack(spacing: 10) {
                        ForEach(chrome.footer) { action in
                            if action.id == "chat" && !dynamicTypeSize.isAccessibilitySize {
                                control(action, expanded: true).labelStyle(.titleAndIcon).modifier(NativeGlassButtonStyle()).frame(maxWidth: .infinity)
                            } else {
                                control(action).labelStyle(.iconOnly).buttonStyle(NativeCircleButtonStyle())
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
                                Text(device.title).monospacedDigit()
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

    @ViewBuilder private func chromeSections(_ chrome: NativeHomeSnapshot.Chrome) -> some View {
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
                recaps(chrome.recaps)
                    .listRowInsets(EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 0))
                    .listRowBackground(Color.clear)
            } header: {
                NativeSectionHeader(title: chrome.recapsTitle) {
                    Button { dispatch("recaps") } label: {
                        NativeSectionAction(title: state.snapshot.copy.viewAll)
                            .frame(minHeight: NativeMetrics.rowHeight).contentShape(Rectangle())
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    /// One recap fills the row; several page horizontally with the next card peeking in.
    @ViewBuilder private func recaps(_ recaps: [NativeHomeSnapshot.Chrome.Recap]) -> some View {
        if recaps.count == 1, let recap = recaps.first {
            recapCard(recap)
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(recaps) { recap in
                        recapCard(recap).modifier(NativeCarouselPage(width: dynamicTypeSize.isAccessibilitySize ? 320 : 280))
                    }
                }
                // Cards share the tallest card's height.
                .fixedSize(horizontal: false, vertical: true)
                .modifier(NativeCarouselLayout())
            }
            .modifier(NativeCarouselPaging())
        }
    }

    private func recapCard(_ recap: NativeHomeSnapshot.Chrome.Recap) -> some View {
        Button { dispatch("recap", recap.id) } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(recap.emoji)  \(recap.date)").font(.subheadline).foregroundStyle(.secondary)
                    Text(recap.title).font(.headline).foregroundStyle(.primary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.forward")
                    .font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 88, maxHeight: .infinity, alignment: .leading)
            .background(Color(uiColor: .secondarySystemGroupedBackground),
                        in: RoundedRectangle(cornerRadius: NativeMetrics.cardRadius, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: NativeMetrics.cardRadius, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("native-recap-\(recap.id)")
    }

    private var recordingsRow: some View {
        Button {
            dispatch("browse")
        } label: {
            HStack(spacing: 12) {
                Label(state.snapshot.copy.recordings, systemImage: "waveform")
                Spacer()
                Text(state.snapshot.localRecordingCount, format: .number).foregroundStyle(.secondary)
                // Large text needs the room for the title, as system cells drop their accessory.
                if !dynamicTypeSize.isAccessibilitySize {
                    Image(systemName: "chevron.forward")
                        .font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
                        .accessibilityHidden(true)
                }
            }
            .frame(minHeight: NativeMetrics.rowHeight)
            .contentShape(Rectangle())
        }
        .accessibilityIdentifier("native-recordings")
    }

    private func control(_ action: NativeHomeSnapshot.Chrome.Action, expanded: Bool = false) -> some View {
        Button { dispatch(action.id) } label: {
            Label { Text(action.title).fontWeight(.medium) } icon: { Image(systemName: action.symbol).font(.system(size: 19)) }
                .frame(maxWidth: expanded ? .infinity : nil, minHeight: expanded ? 30 : nil)
        }
            .disabled(!action.enabled || state.pending.contains(action.id))
            .accessibilityIdentifier("native-\(action.id)")
    }

    /// The source in a tinted disc, the status over its elapsed time, round capture controls, and the
    /// latest transcript line set off by a quote rule.
    private func captureCard(_ capture: NativeHomeSnapshot.Chrome.Capture) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: capture.source == "phone" ? "iphone" : capture.source == "call" ? "phone.fill" : "waveform")
                    .font(.title3.weight(.medium))
                    .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                    .symbolRenderingMode(.hierarchical)
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(Color(uiColor: .tertiarySystemFill)))
                    .accessibilityHidden(true)
                Button { dispatch("capture") } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(capture.status).font(.headline).foregroundStyle(.primary)
                        Text([capture.elapsed, capture.detail].filter { !$0.isEmpty }.joined(separator: " · "))
                            .font(.subheadline).monospacedDigit().foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                }.buttonStyle(.plain)
                ForEach(capture.actions) { action in
                    Button { dispatch(action.id) } label: { Image(systemName: action.symbol) }
                        .buttonStyle(NativeCircleButtonStyle(surface: .fill))
                        .accessibilityLabel(action.title).disabled(!action.enabled || state.pending.contains(action.id))
                }
            }
            if !capture.explanation.isEmpty { Text(capture.explanation).font(.footnote).foregroundStyle(.secondary) }
            if !capture.lastLine.isEmpty {
                HStack(spacing: 10) {
                    RoundedRectangle(cornerRadius: 1.5).fill(.tertiary).frame(width: 3).accessibilityHidden(true)
                    Text(capture.lastLine).font(.subheadline).foregroundStyle(.secondary).lineLimit(2)
                }.fixedSize(horizontal: false, vertical: true)
            }
        }.padding(.vertical, 6)
            .accessibilityIdentifier("native-live-capture")
    }

    private func row(_ conversation: NativeConversation) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(conversation.title).font(.headline)
                if conversation.locked {
                    Image(systemName: "lock.fill").font(.footnote).foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                }
                if conversation.starred {
                    Image(systemName: "star.fill").font(.footnote).foregroundStyle(.yellow)
                        .accessibilityHidden(true)
                }
            }
            Text(conversation.timestamp).font(.subheadline).foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
        .frame(minHeight: NativeMetrics.rowHeight, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityValue(conversation.starred ? state.snapshot.copy.starred : "")
        .accessibilityHint(conversation.locked ? state.snapshot.copy.lockedHint : "")
    }
}

/// A carousel card's width: the row less a peek of the next card (iOS 17+), otherwise a fixed width.
@available(iOS 16.0, *)
private struct NativeCarouselPage: ViewModifier {
    let width: CGFloat

    func body(content: Content) -> some View {
        if #available(iOS 17.0, *) {
            content.containerRelativeFrame(.horizontal) { length, _ in max(min(length, width), length - 56) }
        } else {
            content.frame(width: width)
        }
    }
}

@available(iOS 16.0, *)
private struct NativeCarouselLayout: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 17.0, *) { content.scrollTargetLayout() } else { content }
    }
}

/// Swipes settle on a card, and the peeking card is not clipped at the row's edge.
@available(iOS 16.0, *)
private struct NativeCarouselPaging: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 17.0, *) {
            content.scrollTargetBehavior(.viewAligned).scrollClipDisabled()
        } else { content }
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

    private static var moreSymbol: String {
        if #available(iOS 26.0, *) { return "ellipsis" }
        return "ellipsis.circle"
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
                    .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 4)
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 20) {
                            if selectedTab == 0 {
                                // Blank lines separate paragraphs, which get the reader's paragraph rhythm.
                                let summary = detail.summary?.isEmpty == false ? detail.summary ?? "" : state.snapshot.copy.noSummary
                                VStack(alignment: .leading, spacing: 14) {
                                    ForEach(Array(paragraphs(summary).enumerated()), id: \.offset) { _, paragraph in
                                        Text(markdown(paragraph)).lineSpacing(3)
                                    }
                                }
                                .textSelection(.enabled)
                            } else if let segments = detail.transcript, !segments.isEmpty {
                                ForEach(segments) { segment in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(segment.speaker).font(.subheadline.weight(.semibold))
                                            .foregroundStyle(NativeSpeakerTint.color(for: segment.speaker))
                                        Text(segment.text).lineSpacing(2).textSelection(.enabled)
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
                    // iOS 26 toolbar buttons are already glass circles, so the plain glyph avoids a ring in a ring.
                    Label(state.snapshot.copy.more, systemImage: Self.moreSymbol)
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

    private func paragraphs(_ text: String) -> [String] {
        let parts = text.components(separatedBy: "\n\n").filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        return parts.isEmpty ? [text] : parts
    }

    private func markdown(_ text: String) -> AttributedString {
        (try? AttributedString(markdown: text,
                               options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(text)
    }
}

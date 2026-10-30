import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The one entry for memories Omi has a reason to doubt, at the top of Memories ("2 memories to
/// check"). Shown only when there are any: a contradiction, someone else as the subject, an old
/// fact, something heard unclearly. Opens `MemoryReviewSheet`.
struct MemoryReviewEntry: View {
    let count: Int
    let onOpen: () -> Void

    var body: some View {
        DecisionCard(
            kicker: .init(symbol: "questionmark.circle", text: L("nativeMemoryDoubtsKicker"), color: DS.Palette.agent),
            title: count == 1 ? L("nativeMemoryDoubtsOne") : L("nativeMemoryDoubts", String(count)),
            subtitle: L("nativeMemoryDoubtsHint"),
            pills: [],
            onTap: onOpen
        )
        .accessibilityIdentifier("memories.review")
    }
}

/// One doubt at a time, asked the way that fits it ("Is this still true?", "Is this about
/// Lena, not you?", "Earlier one thing, now another: which is right?"). The memory itself is
/// shown as a quote under the question, never as the question. The queue is fixed when the
/// sheet opens, so answering does not reshuffle it.
struct MemoryReviewSheet: View {
    @Environment(MemoriesStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    let sources: (Memory) -> String?
    @State private var queue: [MemoryReviewItem] = []
    @State private var loaded = false
    @State private var index = 0
    @State private var editing: Memory?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 0) {
                if let item = current {
                    question(item).id(item.id).transition(.push(from: .trailing))
                } else if loaded {
                    finished
                }
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(DS.Palette.background)
            .navigationTitle(current == nil ? "" : L("nativeMemoryReviewProgress", String(index + 1), String(queue.count)))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(L("close"))
                }
            }
            .sheet(item: $editing, onDismiss: afterEdit) { memory in
                EditMemorySheet(memory: memory).presentationDetents([.medium, .large])
            }
        }
        .task {
            await store.loadReviewQueue()
            if queue.isEmpty { queue = Self.demoQueue ?? store.reviewQueue }
            // -omiDemoMemoryReviewStart <n> opens the demo at its n-th question.
            if Self.demoQueue != nil { index = DebugLaunch.string("omiDemoMemoryReviewStart").flatMap { Int($0) } ?? 0 }
            loaded = true
        }
    }

    private var current: MemoryReviewItem? {
        queue.indices.contains(index) ? queue[index] : nil
    }

    // MARK: Question

    private func question(_ item: MemoryReviewItem) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            Text(Self.questionText(item.question))
                .font(DS.Typography.title)
                .foregroundStyle(DS.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, DS.Spacing.xl)
                .accessibilityAddTraits(.isHeader)
            if case let .whichIsRight(earlier, now) = item.question {
                VStack(spacing: DS.Spacing.sm) {
                    if let earlier {
                        option(L("nativeMemoryEarlier"), earlier, id: "memory.review.earlier") { answer(item, .keepEarlier) }
                    }
                    option(L("nativeMemoryNow"), now, id: "memory.review.now") { answer(item, .keepNew) }
                }
                Spacer(minLength: DS.Spacing.xl)
                Button(L("nativeMemoryNeither")) { answer(item, .neither) }
                    .buttonStyle(.omiSecondary)
                    .accessibilityIdentifier("memory.review.neither")
                    .padding(.bottom, DS.Spacing.lg)
            } else {
                quote(item)
                Spacer(minLength: DS.Spacing.xl)
                verdicts(item)
            }
        }
    }

    /// The memory under the question, with where it came from.
    @ViewBuilder
    private func quote(_ item: MemoryReviewItem) -> some View {
        if case let .memory(memory, _, _) = item {
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                Text("“\(memory.content)”")
                    .font(DS.Typography.body)
                    .foregroundStyle(DS.Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(meta(memory))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkTertiary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .omiCard()
        }
    }

    private func option(_ label: String, _ text: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                Text(label)
                    .font(DS.Typography.caption.weight(.semibold))
                    .foregroundStyle(DS.Palette.agent)
                Text(text)
                    .font(DS.Typography.body)
                    .foregroundStyle(DS.Palette.ink)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .omiCard()
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    private func verdicts(_ item: MemoryReviewItem) -> some View {
        VStack(spacing: DS.Spacing.sm) {
            Button(L("nativeMemoryReviewYes")) { answer(item, .yes) }
                .buttonStyle(.omiPrimary)
                .accessibilityIdentifier("memory.review.right")
            Button(L("nativeMemoryReviewNo")) { answer(item, .no) }
                .buttonStyle(.omiSecondary)
                .accessibilityIdentifier("memory.review.wrong")
            if case let .memory(memory, _, _) = item {
                Button(L("edit")) { editing = memory }
                    .font(DS.Typography.button)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .accessibilityIdentifier("memory.review.edit")
            }
        }
        .padding(.bottom, DS.Spacing.lg)
    }

    private var finished: some View {
        VStack(spacing: DS.Spacing.md) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(DS.Palette.success)
                .accessibilityHidden(true)
            Text(L("nativeMemoryReviewDone")).font(DS.Typography.sectionTitle).foregroundStyle(DS.Palette.ink)
            Button(L("done")) { dismiss() }.buttonStyle(.omiPillSubtle)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// The question in the user's language, from why Omi doubts it.
    static func questionText(_ question: MemoryReviewQuestion) -> String {
        switch question {
        case .whichIsRight: L("nativeMemoryAskWhich")
        case let .aboutSomeoneElse(name): name.map { L("nativeMemoryAskAboutName", $0) } ?? L("nativeMemoryAskAboutSomeone")
        case .stillTrue: L("nativeMemoryAskStillTrue")
        case .heardOnce: L("nativeMemoryAskHeardOnce")
        case .unclear: L("nativeMemoryAskUnclear")
        }
    }

    /// "From Q4 roadmap with Anna · 7 Oct" or just the date.
    private func meta(_ memory: Memory) -> String {
        let date = memory.createdAt.formatted(date: .abbreviated, time: .omitted)
        return sources(memory).map { L("nativeFromConversation", $0) + " · " + date } ?? date
    }

    private func answer(_ item: MemoryReviewItem, _ answer: MemoryReviewAnswer) {
        DSHaptics.success()
        if Self.demoQueue == nil { Task { await store.answer(item, answer) } }
        withAnimation(DS.Motion.standard) { index += 1 }
    }

    /// An edited memory counts as right (the user fixed it); an untouched one stays to answer.
    private func afterEdit() {
        guard let item = current, case let .memory(memory, _, _) = item,
              let edited = store.memories.first(where: { $0.id == memory.id }), edited.content != memory.content else { return }
        DSHaptics.success()
        Task { await store.review(memory.id, isRight: true) }
        withAnimation(DS.Motion.standard) { index += 1 }
    }

    /// `-omiDemoMemoryReview YES` (Debug): one question of each kind, answers go nowhere.
    static var demoQueue: [MemoryReviewItem]? {
        guard DebugLaunch.flag("omiDemoMemoryReview") else { return nil }
        let date = Date.now.addingTimeInterval(-86400)
        func memory(_ id: String, _ content: String) -> Memory {
            Memory(id: id, content: content, headline: nil, category: "interesting", createdAt: date, conversationID: nil)
        }
        return [
            .conflict(
                MemoryConflict(
                    id: "demo-c",
                    factID: "demo-new",
                    candidate: "Lives in Munich.",
                    conflictsWith: ["demo-old"],
                    createdAt: date
                ),
                earlier: memory("demo-old", "Lives in Berlin.")
            ),
            .memory(memory("demo-3p", "Is moving to Lisbon in March."), .aboutSomeoneElse(name: "Lena"), earlier: nil),
            .memory(memory("demo-once", "Prefers flights before 9 am."), .heardOnce, earlier: nil),
            .memory(memory("demo-stale", "Works on the Q3 launch plan."), .stillTrue, earlier: nil),
        ]
    }
}

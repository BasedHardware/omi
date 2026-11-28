import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// "Omi takes over": preview, live progress, result (PLAN.md §4.4).
public struct HandOverSheet: View {
    @Environment(AgentStore.self) private var agent
    @Environment(TasksStore.self) private var tasks
    @Environment(\.dismiss) private var dismiss
    let task: ActionItem
    let conversationTitle: String?

    public init(task: ActionItem, conversationTitle: String?) {
        self.task = task
        self.conversationTitle = conversationTitle
    }

    @State private var showsSteps = false

    /// This session's run, or one recovered from the task's workstream (opened from Home later).
    private var run: AgentStore.Run? {
        agent.runs[task.id] ?? agent.workItems(tasks: [task]).first
    }

    private var isFinished: Bool {
        if case .done = run?.state { true } else { false }
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: DS.Spacing.xl) {
                    VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                        HandOverKicker(symbol: "sparkles", text: L("nativeOmiTakesOver"), color: DS.Palette.agent)
                        Text(task.description).font(DS.Typography.title)
                        if let conversationTitle {
                            Text(L("nativeFromConversation", conversationTitle))
                                .font(DS.Typography.caption)
                                .foregroundStyle(DS.Palette.inkTertiary)
                        }
                    }
                    if let run { progress(run) } else { preview }
                }
                .padding(DS.Spacing.gutter)
            }
            .scrollIndicators(.hidden)
            .background(AuroraBackground())
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if hasAction { bottomBar }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(L("close"))
                }
            }
        }
        // One height for every state: a sheet that grows mid-run shoves the content around.
        .presentationDetents([.large])
        // A finished result seen here is no longer news on Home.
        .onChange(of: isFinished, initial: true) { _, finished in if finished { agent.markOpened(task.id) } }
        // An earlier run (after a restart): its steps and text from the backend.
        .task { if agent.runs[task.id] == nil, task.workstreamID != nil { await agent.loadHistory(for: task) } }
    }

    /// The sheet's one action, over a fade: the result scrolls out under it, never shows below it.
    private var bottomBar: some View {
        actions
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.top, DS.Spacing.xl)
            .padding(.bottom, DS.Spacing.sm)
            .background {
                LinearGradient(
                    stops: [
                        .init(color: DS.Palette.background.opacity(0), location: 0),
                        .init(color: DS.Palette.background, location: 0.4),
                    ],
                    startPoint: .top, endPoint: .bottom
                )
                .ignoresSafeArea(edges: .bottom)
                .allowsHitTesting(false)
            }
    }

    private var hasAction: Bool {
        switch run?.state {
        case nil, .done: true
        case .failed: run?.failure.flatMap(AgentWording.action) != nil && agent.canTakeOver(task)
        default: false
        }
    }

    private var preview: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            row("magnifyingglass", L("nativeHandOverResearch"))
            row("calendar", L("nativeHandOverCalendar"))
            row("doc.text", L("nativeHandOverDrafts"))
            row("hand.raised", L("nativeHandOverTrust"))
        }
        .omiCard()
    }

    /// What Omi will do, text first: a thin gray glyph, one line.
    private func row(_ icon: String, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            Image(systemName: icon)
                .font(.system(size: 15, weight: .regular))
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(width: 22)
                .accessibilityHidden(true)
            Text(text).font(DS.Typography.callout).foregroundStyle(DS.Palette.ink)
        }
    }

    /// While Omi works: what it is doing right now, then the steps so far. Once it is done the
    /// result leads and the steps fold away.
    private func progress(_ run: AgentStore.Run) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            switch run.state {
            case let .working(step):
                if let pending = agent.deviceToolRequests[task.id] { OmiAsksCard(pending: pending) }
                WorkingCard(step: step.isEmpty ? L("nativeWriting") : step, since: run.startedAt)
                earlierSteps(run)
            case .starting:
                WorkingCard(step: L("nativePreparing"), since: run.startedAt)
            case let .done(result):
                VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                    HandOverKicker(symbol: "checkmark.circle", text: L("nativeOmiFinished"), color: DS.Palette.success)
                    MarkdownBlocks(result)
                }
                .omiCard()
                steps(run)
            case let .failed(message):
                Label(AgentWording.failure(message), systemImage: "exclamationmark.triangle")
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.warning)
                    .omiCard()
                // What Omi had written before it stopped.
                if !run.partialText.isEmpty { MarkdownBlocks(run.partialText).omiCard() }
                steps(run)
            }
        }
    }

    /// The steps before the current one, plus what Omi has written so far.
    @ViewBuilder
    private func earlierSteps(_ run: AgentStore.Run) -> some View {
        if run.steps.count > 1 {
            StepList(steps: Array(run.steps.dropLast()), isWorking: false)
        }
        if !run.partialText.isEmpty {
            MarkdownBlocks(run.partialText).omiCard()
        }
        Label(L("nativeKeepsWorkingHint"), systemImage: "moon.zzz")
            .font(DS.Typography.caption)
            .foregroundStyle(DS.Palette.inkTertiary)
    }

    @ViewBuilder
    private func steps(_ run: AgentStore.Run) -> some View {
        if !run.steps.isEmpty {
            DisclosureGroup(isExpanded: $showsSteps) {
                StepList(steps: run.steps, isWorking: false).padding(.top, DS.Spacing.sm)
            } label: {
                let count = run.steps.count(where: { !$0.isEmpty })
                Label(count == 1 ? L("nativeStepsCountOne") : L("nativeStepsCount", String(count)), systemImage: "list.bullet")
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
            .tint(DS.Palette.inkSecondary)
        }
    }

    @ViewBuilder
    private var actions: some View {
        switch run?.state {
        case nil:
            Button {
                DSHaptics.tap(.medium)
                Task { await agent.takeOver(task, conversationTitle: conversationTitle) }
            } label: {
                Label(L("nativeStart"), systemImage: "sparkles")
            }
            .buttonStyle(.omiPrimary)
            .accessibilityIdentifier("handover.start")
        case .done:
            Button {
                DSHaptics.success()
                Task { await tasks.setCompleted(task.id, true) }
                dismiss()
            } label: {
                Label(L("nativeMarkDone"), systemImage: "checkmark")
            }
            .buttonStyle(.omiPrimary)
        case .failed:
            // Resume a stopped run in its own thread; try again otherwise.
            Button {
                DSHaptics.tap(.medium)
                Task { await agent.resume(task, conversationTitle: conversationTitle) }
            } label: {
                Label(run?.failure.flatMap(AgentWording.action) ?? L("retry"), systemImage: "arrow.clockwise")
            }
            .buttonStyle(.omiPrimary)
            .accessibilityIdentifier("handover.resume")
        default:
            EmptyView()
        }
    }
}

/// Omi at work, as a For you card: the blue "Omi is on it" kicker (its glyph breathes), how long
/// it has been going, and the current step.
struct WorkingCard: View {
    let step: String
    let since: Date

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            HStack {
                HandOverKicker(symbol: "sparkles", text: L("nativeOmiOnIt"), color: DS.Palette.agent, pulses: true)
                Spacer()
                TimelineView(.periodic(from: since, by: 1)) { context in
                    Text(Duration.seconds(max(0, context.date.timeIntervalSince(since))).formatted(.time(pattern: .minuteSecond)))
                        .font(DS.Typography.caption.monospacedDigit())
                        .foregroundStyle(DS.Palette.inkTertiary)
                }
            }
            Text(step)
                .font(.body.weight(.medium))
                .foregroundStyle(DS.Palette.ink)
                .contentTransition(.opacity)
                .animation(DS.Motion.standard, value: step)
        }
        .omiCard()
        .accessibilityElement(children: .combine)
    }
}

/// The small colored line over a hand-over card (as the For you cards' kicker): a glyph and a few
/// words, blue for Omi's work, green once it is done.
struct HandOverKicker: View {
    let symbol: String
    let text: String
    let color: Color
    var pulses = false

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .semibold))
                .symbolEffect(.pulse, isActive: pulses)
            Text(text).font(.footnote.weight(.semibold))
        }
        .foregroundStyle(color)
        .accessibilityElement(children: .combine)
    }
}

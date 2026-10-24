import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Home's "Needs you": at most five decision cards in `HomeAttention` order (the day's tidy-up,
/// Omi asks, finished runs, What matters now, the condensed tasks, one connection), then
/// "Later (n)" folded, then a quiet "All tasks (n)" row to the full list. Gone when empty.
struct NeedsYouSection: View {
    @Environment(AgentStore.self) var agent
    @Environment(TasksStore.self) var tasks
    @Environment(VoicesStore.self) var voices
    @Environment(ConversationsStore.self) var conversations
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(AppleHealthStore.self) private var health
    /// Connections the user said "Not now" to (comma separated) and the first Home visit.
    @AppStorage("omi.connectDismissed") private var connectDismissed = ""
    @AppStorage("omi.firstHomeAt") private var firstHomeAt: Double = 0
    /// Shared with the app shell's Siri tip sheet.
    @AppStorage("omi.siriHintDismissed") var siriTipDismissed = false
    @State private var showsLater = DebugLaunch.flag("omiShowLater")
    @State private var showsSpeakerPrompt = false
    @State private var reviewsTidyUp = DebugLaunch.flag("omiShowTidyUp")
    /// Task id → its recommendation, taken when Omi started on it from the card (`doNow` drops
    /// it): fed back while the run is on, so the card keeps its rank.
    @State var heldRecommendations: [String: Recommendation] = [:]
    /// The last card swiped to Later, for the undo toast (shown by `TodayScreen`).
    @Binding var laterUndo: LaterUndo?
    let forYou: ForYouStore?
    let onOpenRun: (String) -> Void
    let onHandOver: (ActionItem) -> Void
    let onOpenConversation: (String) -> Void
    let onOpenSiriTip: () -> Void
    let onOpenAllTasks: () -> Void
    let onOpenTask: (ActionItem) -> Void
    let onAskOmi: (String) -> Void

    var body: some View {
        let inbox = HomeAttention.inbox(input)
        VStack(alignment: .leading, spacing: DS.Spacing.sm + 2) {
            if !inbox.needsYou.isEmpty {
                label(L("nativeForYouNeedsYou"))
                ForEach(inbox.needsYou, id: \.id) { card($0) }
            }
            if !inbox.later.isEmpty {
                laterRow(count: inbox.later.count)
                if showsLater {
                    ForEach(inbox.later, id: \.id) { card($0) }
                }
            }
            if tasks.openCount > 0 { allTasksRow }
        }
        .padding(.bottom, inbox.isEmpty && tasks.openCount == 0 ? 0 : DS.Spacing.lg)
        .animation(DS.Motion.standard, value: inbox.needsYou.map(\.id))
        .animation(DS.Motion.standard, value: showsLater)
        .sheet(isPresented: $showsSpeakerPrompt) { SpeakerPromptSheet() }
        .sheet(isPresented: Binding(get: { reviewsTidyUp && tasks.currentTidyUp != nil }, set: { reviewsTidyUp = $0 })) {
            TidyUpSheet()
        }
        .task { await ConnectSuggestion.prepare(capabilities, health, firstHomeAt: $firstHomeAt) }
        // Where open tasks came from: the "From: …" line, and the words that tell a request to
        // someone else or a guessed deadline apart (newest first, each conversation once).
        .task(id: tasks.tasks.count) { await conversations.loadSources(for: tasks.tasks.filter(\.isOpen)) }
        .task { await debugStartFirstCard() }
    }

    /// The words each open task was extracted from, where its conversation is loaded.
    private var quotes: [String: String] {
        var quotes: [String: String] = [:]
        for task in tasks.tasks where task.isOpen {
            if let quote = conversations.quote(of: task) { quotes[task.id] = quote }
        }
        return quotes
    }

    var input: HomeAttention.Input {
        HomeAttention.Input(
            // A failed run on a task Omi should not take (a climb, someone else's job) is not news.
            runs: agent.workItems(tasks: tasks.tasks).filter { run in
                guard case .failed = run.state, let task = task(run.id) else { return true }
                return agent.canTakeOver(task)
            },
            asks: agent.pendingDeviceTools,
            openedRunIDs: agent.openedRunIDs,
            recommendations: agent.openRecommendations(tasks: tasks.tasks)
                + heldRecommendations.filter { agent.runs[$0.key]?.isActive == true }.map(\.value),
            tasks: tasks.tasks,
            snoozes: tasks.snoozes,
            quotes: quotes,
            tidyUp: tasks.currentTidyUp,
            speakerPrompt: voices.currentPrompt,
            nudges: forYou?.items ?? [],
            showsSiriTip: !siriTipDismissed,
            connect: ConnectSuggestion.ids(capabilities, health, dismissed: connectDismissed, firstHomeAt: firstHomeAt)
        )
    }

    private func label(_ text: String) -> some View {
        Text(text)
            .font(DS.Typography.sectionLabel)
            .foregroundStyle(DS.Palette.inkSecondary)
            .accessibilityAddTraits(.isHeader)
    }

    /// "Later (3)": tap to unfold what can wait.
    private func laterRow(count: Int) -> some View {
        Button {
            DSHaptics.selection()
            showsLater.toggle()
        } label: {
            HStack(spacing: DS.Spacing.xs) {
                Text(L("nativeHomeLaterCount", String(count)))
                Image(systemName: "chevron.down")
                    .font(.caption.weight(.semibold))
                    .rotationEffect(.degrees(showsLater ? 180 : 0))
                Spacer(minLength: 0)
            }
            .font(DS.Typography.sectionLabel)
            .foregroundStyle(DS.Palette.inkSecondary)
            .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.top, DS.Spacing.xs)
        .accessibilityAddTraits(showsLater ? .isSelected : [])
        .accessibilityIdentifier("home.later")
    }

    /// The full task list, one level down.
    private var allTasksRow: some View {
        Button(action: onOpenAllTasks) {
            HStack(spacing: DS.Spacing.sm) {
                Image(systemName: "checklist")
                    .font(.system(size: 15, weight: .regular))
                    .foregroundStyle(DS.Palette.inkSecondary)
                Text(L("nativeHomeAllTasksCount", String(tasks.openCount)))
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(DS.Palette.inkTertiary)
            }
            .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("home.allTasks")
    }

    // MARK: Cards

    @ViewBuilder
    private func card(_ item: HomeAttention.Item) -> some View {
        Group {
            switch item {
            case let .omiAsks(pending):
                // Omi waits on the user mid-run: the question with its own choices; the card opens the run.
                OmiAsksCard(pending: pending, onOpen: { onOpenRun(pending.taskID) })
            case let .connect(id):
                ConnectSuggestionCard(id: id) {
                    withAnimation(DS.Motion.standard) {
                        connectDismissed = connectDismissed.isEmpty ? id : connectDismissed + "," + id
                    }
                }
                .accessibilityIdentifier("forYou.connect.\(id)")
            case let .task(card):
                taskCard(card)
            case let .tidyUp(proposal):
                tidyUpCard(proposal)
            default:
                decisionCard(item)
            }
        }
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private func tidyUpCard(_ proposal: TaskTidyUp.Proposal) -> some View {
        DecisionCard(
            kicker: DecisionCard.Kicker(symbol: "sparkles", text: L("nativeForYouSuggestion"), color: DS.Palette.agent),
            title: TidyUpWording.title(proposal),
            subtitle: L("nativeTidyUpSubtitle"),
            pills: [
                DecisionCard.Pill(title: L("nativeTidyUpReview"), isPrimary: true) { reviewsTidyUp = true },
                DecisionCard.Pill(title: L("notNow")) { withAnimation(DS.Motion.standard) { tasks.dismissTidyUp() } },
            ],
            onTap: { reviewsTidyUp = true }
        )
        .accessibilityIdentifier("forYou.tidyup")
    }

    /// Omi's runs, nudges, tips and suggestions without a task (as before on Home).
    private func decisionCard(_ item: HomeAttention.Item) -> some View {
        let content = ForYouRow.Content(item, taskSource: { conversations.source(of: $0).map(\.displayTitle) })
        let pills = pills(for: item)
        let lines = contextLines(for: item, content: content)
        // Buttons only for a real choice; a single action is the tap on the card.
        return DecisionCard(
            kicker: kicker(for: item), title: content.title, subtitle: lines.subtitle, source: lines.source,
            pulses: content.pulses, pills: pills.count > 1 ? pills : [], onTap: action(for: item)
        )
        .contextMenu { menu(for: item) }
        .accessibilityIdentifier("forYou.\(item.id)")
        .task(id: item.id) { await appeared(item) }
    }

    /// What kind of item this is, in one colored line above the title.
    private func kicker(for item: HomeAttention.Item) -> DecisionCard.Kicker {
        switch item {
        case .finished, .finishedGroup:
            DecisionCard.Kicker(symbol: "checkmark.circle", text: L("nativeForYouDone"), color: DS.Palette.success)
        case .working:
            DecisionCard.Kicker(symbol: "sparkles", text: L("nativeForYouWorking"), color: DS.Palette.agent)
        case .recommendation, .tidyUp, .task:
            DecisionCard.Kicker(symbol: "sparkles", text: L("nativeForYouSuggestion"), color: DS.Palette.agent)
        case let .needsHelp(run):
            DecisionCard.Kicker(
                symbol: run.isStopped ? "pause.circle" : "exclamationmark.triangle",
                text: run.isStopped ? L("nativeForYouStopped") : L("nativeForYouNeedsYou"), color: DS.Palette.warning
            )
        case .omiAsks:
            OmiAsksPresentation.kicker
        case .connect:
            DecisionCard.Kicker(symbol: "link", text: L("nativeForYouConnect"), color: DS.Palette.agent)
        case .speakerPrompt:
            DecisionCard.Kicker(symbol: "person.wave.2", text: L("nativeForYouWhoWasThat"), color: DS.Palette.agent)
        case .nudge, .siriTip:
            DecisionCard.Kicker(symbol: "lightbulb", text: L("nativeForYouTip"), color: DS.Palette.warning)
        }
    }

    /// The card's buttons: the main thing first (filled), then the quiet way out.
    private func pills(for item: HomeAttention.Item) -> [DecisionCard.Pill] {
        switch item {
        case let .finished(run):
            return [DecisionCard.Pill(title: L("nativeForYouView"), isPrimary: true) { onOpenRun(run.id) }]
        case let .needsHelp(run):
            // Try again (or resume a stopped run) right here; the reason is the card's line.
            var pills = [DecisionCard.Pill]()
            if let failure = run.failure, let action = AgentWording.action(failure), let task = task(run.id), agent.canTakeOver(task) {
                pills.append(DecisionCard.Pill(title: action, isPrimary: true) { resume(task) })
            }
            pills.append(DecisionCard.Pill(title: L("nativeForYouView"), isPrimary: pills.isEmpty) { onOpenRun(run.id) })
            return pills
        case .finishedGroup:
            return [DecisionCard.Pill(title: L("nativeForYouShowAll"), isPrimary: true) { showsLater = true }]
        case let .recommendation(recommendation):
            return [
                DecisionCard.Pill(title: L("nativeForYouMarkDone"), isPrimary: true) { decide(recommendation, .complete) },
                DecisionCard.Pill(title: L("nativeForYouLater")) { decide(recommendation, .later) },
            ]
        case .speakerPrompt:
            return [
                DecisionCard.Pill(title: L("nativeForYouAssign"), isPrimary: true) { showsSpeakerPrompt = true },
                DecisionCard.Pill(title: L("notNow")) { Task { await voices.dismissPrompts() } },
            ]
        case let .nudge(nudge):
            var pills = [DecisionCard.Pill]()
            if nudge.target != nil { pills.append(DecisionCard.Pill(title: L("nativeForYouView"), isPrimary: true) { open(nudge) }) }
            pills.append(DecisionCard.Pill(title: L("notNow")) { send(.dismissed, nudge) })
            return pills
        case .siriTip:
            return [
                DecisionCard.Pill(title: L("nativeForYouView"), isPrimary: true) {
                    siriTipDismissed = true
                    onOpenSiriTip()
                },
                DecisionCard.Pill(title: L("notNow")) { siriTipDismissed = true },
            ]
        case .omiAsks, .connect, .working, .task, .tidyUp:
            return []
        }
    }

    /// The tap on the card itself: every card opens something (`HomeTapTargets` names where).
    private func action(for item: HomeAttention.Item) -> () -> Void {
        switch HomeTapTargets.target(item) {
        case let .run(id): { onOpenRun(id) }
        case .later:
            {
                DSHaptics.selection()
                showsLater = true
            }
        case .speakerPrompt: { showsSpeakerPrompt = true }
        case .siriTip:
            {
                siriTipDismissed = true
                onOpenSiriTip()
            }
        case let .conversation(id): {
                opened(item)
                onOpenConversation(id)
            }
        case let .task(id): {
                opened(item)
                if let task = task(id) { onOpenTask(task) } else { onOpenAllTasks() }
            }
        case let .ask(text): {
                opened(item)
                onAskOmi(text)
            }
        case .tidyUp: { reviewsTidyUp = true }
        // Connection cards run their own flow (`ConnectSuggestionCard`); here for completeness.
        case .connect: { onOpenAllTasks() }
        }
    }

    /// A nudge the user followed: the proactivity feed hears it.
    private func opened(_ item: HomeAttention.Item) {
        if case let .nudge(nudge) = item { Task { await forYou?.send(.opened, for: nudge) } }
    }
}

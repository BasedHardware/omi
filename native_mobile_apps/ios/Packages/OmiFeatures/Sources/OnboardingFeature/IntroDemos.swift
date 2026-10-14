import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

// The introduction's live demos: small scenes built from the app's own rows (a conversation,
// tasks, memories, the For you card, a Live Activity), looping while their page shows.

extension View {
    /// A quiet surface edged by a hairline, as the app's cards are.
    func demoSurface(_ radius: CGFloat) -> some View {
        background(DS.Palette.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(DS.Palette.cardStroke, lineWidth: DS.Stroke.regular)
            }
    }
}

/// Steps a demo through its scenes while its page is showing, then starts over.
struct DemoClock: ViewModifier {
    let isActive: Bool
    let durations: [Double]
    @Binding var scene: Int
    /// Each round starts as a fresh view, cross-faded, instead of unwinding the last scene.
    @State private var round = 0

    func body(content: Content) -> some View {
        content
            .id(round)
            .transition(.opacity)
            .task(id: isActive) {
                scene = 0
                guard isActive else { return }
                while !Task.isCancelled {
                    for (index, seconds) in durations.enumerated() {
                        if index == 0 {
                            if round > 0 || scene > 0 { withAnimation(.easeInOut(duration: 0.45)) { round += 1; scene = 0 } }
                        } else {
                            withAnimation(DS.Motion.standard) { scene = index }
                        }
                        try? await Task.sleep(for: .seconds(seconds))
                        if Task.isCancelled { return }
                    }
                }
            }
    }
}

extension View {
    func demoClock(_ isActive: Bool, _ durations: [Double], scene: Binding<Int>) -> some View {
        modifier(DemoClock(isActive: isActive, durations: durations, scene: scene))
    }
}

enum Demo {
    static func conversation(processing: Bool) -> Conversation {
        let now = Date()
        return Conversation(
            id: "demo", title: processing ? "" : L("nativeDemoConversationTitle"), overview: L("nativeDemoConversationOverview"),
            emoji: "☕️", category: nil, createdAt: now.addingTimeInterval(-600), startedAt: now.addingTimeInterval(-600),
            finishedAt: now.addingTimeInterval(-120), status: processing ? .processing : .completed, isStarred: false,
            actionItemCount: processing ? 0 : 2
        )
    }

    static func task(_ key: String, id: String) -> ActionItem {
        ActionItem(
            id: id, description: L(key), isCompleted: false, dueAt: nil, conversationID: "demo", owner: .user,
            workstreamID: nil, createdAt: nil
        )
    }
}

/// A conversation recorded live, processed, then its summary and next steps.
struct ListenDemo: View {
    let isActive: Bool
    @State private var scene = 0
    @State private var since = Date()

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            if scene == 0 {
                OmiLivePill(since: since)
                    .transition(.opacity)
                TranscriptLine(speaker: L("nativeSpeakerYou"), text: L("nativeDemoLineYou"), isUser: true)
                TranscriptLine(speaker: L("nativeDemoSpeaker", "1"), text: L("nativeDemoLineOther"), isUser: false)
            } else {
                ConversationRow(Demo.conversation(processing: scene == 1))
                    .transition(.opacity)
                if scene == 2 {
                    Text(L("nativeDemoConversationOverview"))
                        .font(DS.Typography.callout)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, DS.Spacing.xs)
                        .transition(.opacity)
                    VStack(spacing: DS.Spacing.sm) {
                        TaskRow(Demo.task("nativeDemoTaskSlides", id: "t1"), onToggle: {})
                        TaskRow(Demo.task("nativeDemoTaskTable", id: "t2"), onToggle: {})
                    }
                    .padding(.horizontal, DS.Spacing.xs)
                    .transition(.opacity.combined(with: .offset(y: 8)))
                }
            }
        }
        .demoClock(isActive, [2.6, 1.3, 3.6], scene: $scene)
        .onChange(of: scene) { _, scene in if scene == 0 { since = Date().addingTimeInterval(-42) } }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// One line of a transcript: who, then what was said.
struct TranscriptLine: View {
    let speaker: String
    let text: String
    let isUser: Bool
    var icon: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Label {
                Text(speaker)
            } icon: {
                Image(systemName: icon ?? (isUser ? "person.fill" : "person"))
            }
            .font(DS.Typography.micro)
            .foregroundStyle(isUser ? DS.Palette.agent : DS.Palette.inkSecondary)
            .contentTransition(.opacity)
            Text(text)
                .font(DS.Typography.body)
                .foregroundStyle(DS.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(DS.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .demoSurface(DS.Radius.md)
    }
}

/// "What I know about you", growing one memory at a time.
struct MemoryDemo: View {
    let isActive: Bool
    @State private var scene = 0
    private let keys = ["nativeDemoMemory1", "nativeDemoMemory2", "nativeDemoMemory3", "nativeDemoMemory4"]
    private let symbols = ["person.2", "sunrise", "figure.run", "fork.knife"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(L("nativeWhatIKnowAboutYou"))
                .font(DS.Typography.sectionTitle)
                .foregroundStyle(DS.Palette.ink)
                .padding(.bottom, DS.Spacing.md)
            VStack(spacing: 0) {
                ForEach(Array(keys.prefix(scene + 1).enumerated()), id: \.offset) { index, key in
                    if index > 0 { OmiHairline(leading: 44) }
                    HStack(spacing: DS.Spacing.md) {
                        Image(systemName: symbols[index])
                            .font(.body)
                            .foregroundStyle(DS.Palette.inkSecondary)
                            .frame(width: 32, height: 32)
                            .background(DS.Palette.tile, in: RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
                        Text(L(key))
                            .font(DS.Typography.body)
                            .foregroundStyle(DS.Palette.ink)
                        Spacer(minLength: 0)
                        Image(systemName: "ellipsis")
                            .foregroundStyle(DS.Palette.inkTertiary)
                    }
                    .padding(.vertical, DS.Spacing.sm + 2)
                    .transition(.opacity.combined(with: .offset(y: -6)))
                }
            }
            .padding(.horizontal, DS.Spacing.md)
            .demoSurface(DS.Radius.card)
            Text(L("nativeDemoMemoryHint"))
                .font(DS.Typography.caption)
                .foregroundStyle(DS.Palette.inkTertiary)
                .padding(.top, DS.Spacing.sm)
                .opacity(scene == keys.count - 1 ? 1 : 0)
        }
        .demoClock(isActive, [1.1, 1.1, 1.1, 3.2], scene: $scene)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// "Speaker 1" until Omi asks once who it was; from then on, the name.
struct VoicesDemo: View {
    let isActive: Bool
    @State private var scene = 0

    private var other: String {
        scene >= 2 ? "Anna" : L("nativeDemoSpeaker", "1")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            TranscriptLine(speaker: L("nativeSpeakerYou"), text: L("nativeDemoLineYou"), isUser: true)
            TranscriptLine(
                speaker: other, text: L("nativeDemoLineOther"), isUser: false,
                icon: scene >= 2 ? "person.crop.circle.badge.checkmark" : nil
            )
            if scene == 1 {
                HStack(spacing: DS.Spacing.sm) {
                    Text(L("nativeDemoWhoWasThis"))
                        .font(DS.Typography.cardTitle)
                        .foregroundStyle(DS.Palette.ink)
                    Spacer(minLength: 0)
                    OmiChip("Anna", tint: DS.Palette.agent)
                    OmiChip("Ben")
                }
                .padding(DS.Spacing.md)
                .background(DS.Palette.agentSoft, in: RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
                .transition(.opacity.combined(with: .offset(y: 8)))
            }
            if scene >= 2 {
                TranscriptLine(
                    speaker: "Anna", text: L("nativeDemoLineOther2"), isUser: false, icon: "person.crop.circle.badge.checkmark"
                )
                .transition(.opacity.combined(with: .offset(y: 8)))
            }
        }
        .demoClock(isActive, [1.6, 2.0, 3.6], scene: $scene)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// The For you card: a suggestion that came on its own and the daily recap.
struct ForYouDemo: View {
    let isActive: Bool
    @State private var scene = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(L("forYou"))
                .font(DS.Typography.sectionTitle)
                .foregroundStyle(DS.Palette.ink)
                .padding(.bottom, DS.Spacing.md)
            VStack(spacing: 0) {
                row("sparkles", L("nativeDemoForYouPrep"), L("nativeDemoForYouPrepDetail"), tint: DS.Palette.agent)
                if scene >= 1 {
                    OmiHairline(leading: 52)
                    row("moon.stars", L("nativeDemoForYouRecap"), L("nativeDemoForYouRecapDetail"), tint: DS.Palette.inkSecondary)
                        .transition(.opacity.combined(with: .offset(y: -6)))
                }
            }
            .padding(.horizontal, DS.Spacing.md)
            .demoSurface(DS.Radius.card)
            .scaleEffect(scene == 0 ? 0.98 : 1)
        }
        .demoClock(isActive, [1.4, 4], scene: $scene)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func row(_ symbol: String, _ title: String, _ detail: String, tint: Color) -> some View {
        HStack(spacing: DS.Spacing.md) {
            Image(systemName: symbol)
                .foregroundStyle(tint)
                .frame(width: 36, height: 36)
                .background(DS.Palette.tile, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink)
                Text(detail).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(DS.Palette.inkTertiary)
        }
        .padding(.vertical, DS.Spacing.md)
    }
}

/// A task handed over: Omi takes it, works on it, and the Lock Screen shows how far it got.
struct HandOverDemo: View {
    let isActive: Bool
    @State private var scene = 0

    var body: some View {
        VStack(spacing: DS.Spacing.lg) {
            TaskRow(
                Demo.task("nativeDemoTaskTable", id: "t2"),
                agentStatus: scene >= 1 ? .working : nil,
                onToggle: {}, onHandOver: {}
            )
            .padding(DS.Spacing.md)
            .demoSurface(DS.Radius.card)
            if scene >= 1 {
                LockScreenActivity(progress: scene >= 2 ? 0.66 : 0.33)
                    .transition(.opacity.combined(with: .offset(y: 8)))
            }
        }
        .demoClock(isActive, [1.6, 1.6, 3.2], scene: $scene)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// A Live Activity as it looks on the Lock Screen.
struct LockScreenActivity: View {
    let progress: Double

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            HStack(spacing: DS.Spacing.sm) {
                OmiPendantThumbnail(size: 22)
                Text(L("nativeOmiOnIt"))
                    .font(DS.Typography.cardTitle)
                    .foregroundStyle(DS.Palette.ink)
                Spacer(minLength: 0)
                Image(systemName: "lock.fill").font(.caption).foregroundStyle(DS.Palette.inkTertiary)
            }
            Text(L("nativeDemoLockScreen"))
                .font(DS.Typography.caption)
                .foregroundStyle(DS.Palette.inkSecondary)
            GeometryReader { proxy in
                Capsule().fill(DS.Palette.ink.opacity(0.1))
                    .overlay(alignment: .leading) {
                        Capsule().fill(DS.Palette.agent).frame(width: proxy.size.width * progress)
                    }
            }
            .frame(height: 4)
        }
        .padding(DS.Spacing.lg)
        .background(DS.Palette.cardRaised, in: RoundedRectangle(cornerRadius: DS.Radius.hero, style: .continuous))
        .animation(DS.Motion.standard, value: progress)
    }
}

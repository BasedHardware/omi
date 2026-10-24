import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// A task on Home as one compact row: who or what it is about (`EntityAvatar`), the task, one meta
/// line (why now, where it came from) and Omi's answer as a round button at the end: sparkles
/// when Omi can take over, a checkmark to mark it done, a spinning ring while Omi is on it.
/// Swipe right to put it off until tomorrow (Home is the first page, so that direction is free; a
/// left drag still pages to Chat).
struct TaskCardView: View {
    /// What the round button does.
    enum Answer {
        case omiTakesOver, markDone, running
    }

    struct Status {
        let text: String
        let color: Color
        var pulses = false
    }

    let visual: EntityVisual
    let fallback: EntityVisual
    let title: String
    let status: Status
    let source: String?
    let answer: Answer
    let onTap: () -> Void
    let onButton: () -> Void
    /// Nil where swiping makes no sense (already put off).
    let onLater: (() -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var offset: CGFloat = 0
    @State private var width: CGFloat = 0
    @State private var leaving = false

    /// Share of the card's width past which a let-go puts it off; a fast fling does too.
    static let threshold: CGFloat = 0.35
    static let flingVelocity: CGFloat = 900

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            EntityAvatar(visual, size: 40, fallback: fallback)
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.body.weight(.medium))
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                meta
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            magicButton
        }
        .multilineTextAlignment(.leading)
        .padding(14)
        .background(DS.Palette.card, in: shape)
        .contentShape(shape)
        .onTapGesture(perform: onTap)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityAction(named: buttonLabel, onButton)
        .modifier(LaterSwipe(onLater: onLater, offset: $offset, width: $width, leaving: $leaving, reduceMotion: reduceMotion))
    }

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 22, style: .continuous)
    }

    /// "● Overdue · Pricing sync · Wed"
    private var meta: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(status.color)
                .frame(width: 6, height: 6)
                .modifier(Pulse(isActive: status.pulses && !reduceMotion))
            Text(status.text)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(status.color)
                .lineLimit(1)
                .layoutPriority(1)
            if let source, !source.isEmpty {
                Text("·").font(.footnote).foregroundStyle(DS.Palette.inkTertiary)
                Text(source)
                    .font(.footnote)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
            }
        }
    }

    private var magicButton: some View {
        Button(action: onButton) {
            ZStack {
                Circle().fill(answer == .markDone ? DS.Palette.fill : DS.Palette.agentSoft)
                switch answer {
                case .omiTakesOver:
                    Image(systemName: "sparkles")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(DS.Palette.agent)
                case .markDone:
                    Image(systemName: "checkmark")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(DS.Palette.ink)
                case .running:
                    SpinningRing(reduceMotion: reduceMotion)
                }
            }
            .frame(width: 36, height: 36)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(buttonLabel)
        .accessibilityIdentifier("forYou.task.button")
    }

    private var buttonLabel: String {
        switch answer {
        case .omiTakesOver: L("nativeOmiTakesOver")
        case .markDone: L("nativeMarkDone")
        case .running: L("nativeOmiOnIt")
        }
    }
}

/// Omi at work: a short arc of agent blue going round (Reduce Motion: it stands still).
private struct SpinningRing: View {
    let reduceMotion: Bool
    @State private var turning = false

    var body: some View {
        Circle()
            .trim(from: 0, to: 0.7)
            .stroke(DS.Palette.agent, style: StrokeStyle(lineWidth: 2, lineCap: .round))
            .frame(width: 16, height: 16)
            .rotationEffect(.degrees(turning ? 360 : 0))
            .animation(reduceMotion ? nil : .linear(duration: 0.9).repeatForever(autoreverses: false), value: turning)
            .onAppear { turning = true }
    }
}

/// The status dot breathing while Omi works.
private struct Pulse: ViewModifier {
    let isActive: Bool
    @State private var dim = false

    func body(content: Content) -> some View {
        content
            .opacity(isActive && dim ? 0.3 : 1)
            .animation(isActive ? .easeInOut(duration: 0.8).repeatForever() : .default, value: dim)
            .onAppear { dim = true }
    }
}

/// Swipe right to "Later": the card follows the finger; past `threshold` of its width (or a fast
/// fling) it slides out (Reduce Motion: fades) and `onLater` runs, else it springs back.
private struct LaterSwipe: ViewModifier {
    let onLater: (() -> Void)?
    @Binding var offset: CGFloat
    @Binding var width: CGFloat
    @Binding var leaving: Bool
    let reduceMotion: Bool
    @State private var pastThreshold = false

    func body(content: Content) -> some View {
        if let onLater {
            content
                .offset(x: reduceMotion && leaving ? 0 : offset)
                .opacity(leaving ? 0 : 1)
                .onGeometryChange(for: CGFloat.self, of: \.size.width) { width = $0 }
                .gesture(SidewaysPan(direction: 1, onChange: changed, onEnd: { ended($0, $1, onLater) }))
                .accessibilityAction(named: L("nativeForYouLater"), onLater)
        } else {
            content
        }
    }

    private func changed(_ translation: CGFloat) {
        guard !leaving else { return }
        offset = max(0, translation)
        let past = offset >= width * TaskCardView.threshold
        if past, !pastThreshold { DSHaptics.soft(0.7) }
        pastThreshold = past
    }

    private func ended(_ translation: CGFloat, _ velocity: CGFloat, _ onLater: @escaping () -> Void) {
        pastThreshold = false
        let commits = translation >= width * TaskCardView.threshold || (translation > 0 && velocity > TaskCardView.flingVelocity)
        guard commits, !leaving else {
            withAnimation(.snappy(duration: 0.32, extraBounce: 0.05)) { offset = 0 }
            return
        }
        withAnimation(.easeOut(duration: 0.22)) {
            leaving = true
            if !reduceMotion { offset = width + 40 }
        } completion: {
            onLater()
            // Still here (a card overflowing into Later stays in that list): back in place.
            leaving = false
            offset = 0
        }
    }
}

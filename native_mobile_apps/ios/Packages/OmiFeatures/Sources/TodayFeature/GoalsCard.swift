import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Home's goals (Flutter `goals_widget.dart`) as one quiet line at the bottom: the first goal's
/// progress as dots and "3/4 workouts", "+1" for more. Only when there are goals; tapping opens
/// all goals, where each one can be moved or edited.
struct GoalsCard: View {
    @Environment(GoalsStore.self) private var goals
    @State private var showsAll = false

    /// More steps than this read better as a bar than as dots.
    static let maxDots = 10

    var body: some View {
        if let goal = goals.goals.first {
            Button { showsAll = true } label: { line(goal) }
                .buttonStyle(.hapticTap)
                .accessibilityIdentifier("home.goals")
                .accessibilityHint(L("nativeHomeOpenGoals"))
                .padding(.top, DS.Spacing.xl)
                .sheet(isPresented: $showsAll) { NavigationStack { GoalsScreen() } }
        }
    }

    private func line(_ goal: Goal) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DS.Spacing.md) { parts(goal) }
            VStack(alignment: .leading, spacing: DS.Spacing.sm) { parts(goal) }
        }
        .padding(.horizontal, DS.Spacing.lg)
        .padding(.vertical, DS.Spacing.md)
        .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
        .omiCardSurface()
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func parts(_ goal: Goal) -> some View {
        Text(L("goals")).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink).fixedSize()
        progress(goal)
        HStack(spacing: DS.Spacing.xs) {
            Text(verbatim: "\(GoalRow.number(goal.current))/\(GoalRow.number(goal.target))")
                .monospacedDigit()
                .foregroundStyle(DS.Palette.ink)
            Text(goal.title).foregroundStyle(DS.Palette.inkSecondary).lineLimit(1)
            if goals.goals.count > 1 {
                Text(verbatim: "+\(goals.goals.count - 1)").foregroundStyle(DS.Palette.inkTertiary)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(DS.Palette.inkTertiary)
        }
        .font(DS.Typography.callout)
    }

    @ViewBuilder
    private func progress(_ goal: Goal) -> some View {
        let steps = Int(goal.target)
        if goal.target == goal.target.rounded(), steps > 0, steps <= Self.maxDots {
            HStack(spacing: 3) {
                ForEach(0 ..< steps, id: \.self) { index in
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(Double(index) < goal.current ? GoalRow.tint(goal.progress) : DS.Palette.fill)
                        .frame(width: 8, height: 8)
                }
            }
            .accessibilityHidden(true)
        } else {
            ProgressView(value: goal.progress)
                .tint(GoalRow.tint(goal.progress))
                .frame(width: 56)
                .accessibilityHidden(true)
        }
    }
}

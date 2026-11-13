import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// One goal: title, a progress bar, "3 of 10", and − / + to move the number.
public struct GoalRow: View {
    @Environment(GoalsStore.self) private var goals
    let goal: Goal

    public init(_ goal: Goal) {
        self.goal = goal
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.md) {
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                Text(goal.title).font(DS.Typography.body).foregroundStyle(DS.Palette.ink).lineLimit(2)
                ProgressView(value: goal.progress).tint(Self.tint(goal.progress))
                Text(L("nativeGoalProgress", Self.number(goal.current), Self.number(goal.target)))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkTertiary)
                    .monospacedDigit()
            }
            step("minus", L("nativeDecreaseProgress"), by: -1).disabled(goal.current <= 0)
            step("plus", L("nativeIncreaseProgress"), by: 1)
        }
        .padding(.vertical, DS.Spacing.xs)
    }

    private func step(_ symbol: String, _ label: String, by delta: Double) -> some View {
        Button {
            DSHaptics.selection()
            Task { await goals.setProgress(goal.id, current: goal.current + delta) }
        } label: {
            Image(systemName: symbol)
                .font(.system(size: 13, weight: .bold))
                .frame(width: 32, height: 32)
                .background(DS.Palette.fill, in: Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }

    /// Flutter's colors: green from 80 %, orange from 20 %.
    public static func tint(_ progress: Double) -> Color {
        progress >= 0.8 ? DS.Palette.success : progress >= 0.2 ? DS.Palette.warning : DS.Palette.inkTertiary
    }

    public static func number(_ value: Double) -> String {
        value == value.rounded() ? String(Int(value)) : value.formatted(.number.precision(.fractionLength(1)))
    }
}

/// Add or edit a goal (Flutter `goal_form_sheet.dart`): title, current, target; delete when editing.
public struct GoalFormSheet: View {
    @Environment(GoalsStore.self) private var goals
    @Environment(\.dismiss) private var dismiss
    let goal: Goal?
    @State private var title = ""
    @State private var current = "0"
    @State private var target = "100"
    @State private var isSaving = false
    @FocusState private var focused: Bool

    /// `goal == nil` adds one.
    public init(goal: Goal?) {
        self.goal = goal
    }

    public var body: some View {
        NavigationStack {
            Form {
                TextField(L("goalTitle"), text: $title).focused($focused)
                LabeledContent(L("current")) { number($current) }
                LabeledContent(L("target")) { number($target) }
                if let error = goals.lastError {
                    Text(error).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                }
                if let goal {
                    Section {
                        Button(L("deleteGoal"), role: .destructive) {
                            dismiss()
                            goals.deleteWithUndo(goal.id)
                        }
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(goal == nil ? L("addGoal") : L("editGoal"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(goal == nil ? L("addGoal") : L("save"), action: save)
                        .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty || isSaving)
                }
            }
            .onAppear {
                guard let goal else {
                    focused = true
                    return
                }
                title = goal.title
                current = GoalRow.number(goal.current)
                target = GoalRow.number(goal.target)
            }
        }
    }

    private func number(_ text: Binding<String>) -> some View {
        TextField("0", text: text)
            .keyboardType(.decimalPad)
            .multilineTextAlignment(.trailing)
            .monospacedDigit()
    }

    private func save() {
        let currentValue = Self.parse(current) ?? goal?.current ?? 0
        let targetValue = Self.parse(target) ?? goal?.target ?? 100
        isSaving = true
        Task {
            let saved = if let goal {
                await goals.update(goal.id, title: title, current: currentValue, target: targetValue)
            } else {
                await goals.create(title: title, current: currentValue, target: targetValue)
            }
            isSaving = false
            if saved {
                DSHaptics.success()
                dismiss()
            }
        }
    }

    /// Accepts "2,5" as well as "2.5".
    static func parse(_ text: String) -> Double? {
        Double(text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: "."))
    }
}

/// All goals: tap to edit, swipe to delete (with Undo), + to add (at most four).
public struct GoalsScreen: View {
    @Environment(GoalsStore.self) private var goals
    @State private var editing: Goal?
    @State private var adding = false

    public init() {}

    public var body: some View {
        List {
            ForEach(goals.goals) { goal in
                GoalRow(goal)
                    .contentShape(Rectangle())
                    .onTapGesture { editing = goal }
                    .swipeActions {
                        Button(role: .destructive) { goals.deleteWithUndo(goal.id) } label: { Label(L("delete"), systemImage: "trash") }
                    }
            }
            if !goals.canAdd {
                Text(L("maximumGoalsAllowed", String(GoalsStore.maxGoals)))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkTertiary)
                    .listRowBackground(Color.clear)
            }
        }
        .overlay {
            if goals.phase == .loaded, goals.goals.isEmpty {
                ContentUnavailableView {
                    Label(L("nativeNoGoals"), systemImage: "flag")
                } description: {
                    Text(L("nativeNoGoalsBody"))
                } actions: {
                    Button(L("addGoal")) { adding = true }.buttonStyle(.omiPillSubtle)
                }
            }
        }
        .overlay(alignment: .bottom) { GoalUndoToast().padding(.bottom, DS.Spacing.lg) }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { adding = true } label: { Image(systemName: "plus") }
                    .disabled(!goals.canAdd)
                    .accessibilityLabel(L("addGoal"))
            }
        }
        .sheet(isPresented: $adding) { GoalFormSheet(goal: nil).presentationDetents([.medium]) }
        .sheet(item: $editing) { GoalFormSheet(goal: $0).presentationDetents([.medium]) }
        .refreshable { await goals.load() }
        .task { await goals.load() }
        .omiPage(L("goals"))
    }
}

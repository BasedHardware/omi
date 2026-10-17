import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The tidy-up's changes, each with Omi's reason and a switch; nothing changes until "Apply".
struct TidyUpSheet: View {
    @Environment(TasksStore.self) private var tasks
    @Environment(\.dismiss) private var dismiss
    /// Changes the user switched off.
    @State private var skipped: Set<String> = []
    @State private var isApplying = false

    var body: some View {
        let edits = tasks.currentTidyUp?.edits ?? []
        let kept = edits.filter { !skipped.contains($0.id) }
        NavigationStack {
            List {
                section(L("nativeTidyUpSectionMerge"), edits.filter(\.isMerge))
                section(L("nativeTidyUpSectionDone"), edits.filter { $0.kind == .done })
                section(L("nativeTidyUpSectionNotTask"), edits.filter { $0.kind == .notTask })
                Section {} footer: { Text(L("nativeTidyUpFooter")) }
            }
            .safeAreaInset(edge: .bottom) {
                Button {
                    apply(kept)
                } label: {
                    Group {
                        if isApplying { ProgressView() } else { Text(L("nativeTidyUpApply", String(kept.count))) }
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.omiPrimary)
                .disabled(kept.isEmpty || isApplying)
                .padding(DS.Spacing.lg)
                .accessibilityIdentifier("tidyUp.apply")
            }
            .omiPage(L("nativeTidyUpSheetTitle"))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
            }
        }
    }

    @ViewBuilder
    private func section(_ title: String, _ edits: [TaskTidyUp.Edit]) -> some View {
        if !edits.isEmpty {
            Section {
                ForEach(edits) { edit in row(edit) }
            } header: {
                Text(title)
            }
        }
    }

    private func row(_ edit: TaskTidyUp.Edit) -> some View {
        Toggle(isOn: Binding(
            get: { !skipped.contains(edit.id) },
            set: { on in if on { skipped.remove(edit.id) } else { skipped.insert(edit.id) } }
        )) {
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                Text(text(edit.taskID)).font(DS.Typography.body).foregroundStyle(DS.Palette.ink)
                if case let .merge(keep) = edit.kind {
                    Text(L("nativeTidyUpInto", text(keep)))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                if !edit.why.isEmpty {
                    Text(edit.why).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
                }
            }
        }
        .tint(DS.Palette.agent)
        .accessibilityIdentifier("tidyUp.\(edit.id)")
    }

    private func text(_ id: String) -> String {
        tasks.tasks.first { $0.id == id }?.description ?? ""
    }

    private func apply(_ edits: [TaskTidyUp.Edit]) {
        isApplying = true
        Task {
            await tasks.applyTidyUp(edits)
            DSHaptics.success()
            isApplying = false
            dismiss()
        }
    }
}

/// "Tidy up: merge 6, mark 4 done".
enum TidyUpWording {
    @MainActor
    static func title(_ proposal: TaskTidyUp.Proposal) -> String {
        var parts: [String] = []
        if proposal.mergedCount > 0 { parts.append(L("nativeTidyUpMerge", String(proposal.mergedCount))) }
        if !proposal.done.isEmpty { parts.append(L("nativeTidyUpDone", String(proposal.done.count))) }
        if !proposal.notTask.isEmpty { parts.append(L("nativeTidyUpNotTasks", String(proposal.notTask.count))) }
        return L("nativeTidyUpTitle", parts.joined(separator: ", "))
    }
}

extension TaskTidyUp.Edit {
    var isMerge: Bool {
        if case .merge = kind { true } else { false }
    }
}

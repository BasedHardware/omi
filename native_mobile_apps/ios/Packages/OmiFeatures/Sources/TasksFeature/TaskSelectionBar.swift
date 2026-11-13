import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// While selecting tasks: how many, then done, export, share, delete (with Undo), finish.
struct TaskSelectionBar: View {
    @Environment(TasksStore.self) private var store
    @Binding var selection: Set<String>?
    let onShare: ([String]) -> Void

    var body: some View {
        HStack(spacing: DS.Spacing.lg) {
            Text(L("selectedCount", String(ids.count)))
                .font(DS.Typography.callout.weight(.semibold))
                .monospacedDigit()
            Spacer(minLength: 0)
            icon("checkmark.circle", L("nativeMarkDone")) {
                let chosen = ids
                Task { await store.setCompleted(chosen, true) }
                selection = nil
            }
            Menu {
                ExportMenu(title: "", ids: { ids }, onDone: { selection = nil })
            } label: {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(ids.isEmpty ? DS.Palette.inkDisabled : DS.Palette.ink)
            }
            .disabled(ids.isEmpty)
            .accessibilityLabel(L("exportButton"))
            // The backend shares at most 20 tasks per link.
            icon("link", L("nativeShareLink"), enabled: (1 ... 20).contains(ids.count)) {
                onShare(ids)
                selection = nil
            }
            icon("trash", L("deleteSelected"), tint: DS.Palette.live) {
                DSHaptics.tap(.medium)
                withAnimation(DS.Motion.standard) { store.deleteWithUndo(ids) }
                selection = nil
            }
            Button(L("done")) { withAnimation(DS.Motion.standard) { selection = nil } }
                .font(DS.Typography.callout.weight(.semibold))
                .accessibilityIdentifier("tasks.selection.done")
        }
        .padding(.horizontal, DS.Spacing.lg)
        .frame(minHeight: 52)
        .omiSurface(Capsule())
        .padding(.horizontal, DS.Spacing.lg)
    }

    /// Picked rows still in the list, in list order.
    private var ids: [String] {
        let chosen = selection ?? []
        return store.tasks.filter { chosen.contains($0.id) }.map(\.id)
    }

    private func icon(
        _ systemImage: String, _ label: String, tint: Color = DS.Palette.ink, enabled: Bool = true, action: @escaping () -> Void
    ) -> some View {
        let isEnabled = enabled && !ids.isEmpty
        return Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(isEnabled ? tint : DS.Palette.inkDisabled)
        }
        .disabled(!isEnabled)
        .accessibilityLabel(label)
    }
}

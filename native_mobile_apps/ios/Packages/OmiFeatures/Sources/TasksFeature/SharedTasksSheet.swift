import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// Someone shared tasks by link (Flutter `AcceptSharedTasksSheet`): what they are, and one button
/// to add them to my list.
struct SharedTasksSheet: View {
    @Environment(TasksStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    let share: SharedTasks
    @State private var isAdding = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(Array(share.tasks.enumerated()), id: \.offset) { _, item in
                        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
                            Image(systemName: "circle").foregroundStyle(DS.Palette.inkTertiary)
                            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                                Text(item.description).font(DS.Typography.body)
                                if let due = item.dueAt {
                                    Text(L("taskDueDate", Formatting.relativeDay(due)))
                                        .font(DS.Typography.caption)
                                        .foregroundStyle(DS.Palette.inkTertiary)
                                }
                            }
                        }
                    }
                } header: {
                    Text(L("addToYourTaskList"))
                }
            }
            .safeAreaInset(edge: .bottom) {
                Button {
                    isAdding = true
                    Task {
                        if await store.acceptShare() { DSHaptics.success() }
                        isAdding = false
                        dismiss()
                    }
                } label: {
                    Group {
                        if isAdding { ProgressView() } else { Text(L("nativeAddSharedTasks")) }
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.omiPrimary)
                .disabled(isAdding)
                .padding(DS.Spacing.lg)
                .accessibilityIdentifier("sharedTasks.add")
            }
            .omiPage(L("nativeSharedBy", share.senderName ?? L("sharedTasksUnknownSender")))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
            }
        }
    }
}

#if canImport(UIKit)
    /// The system share sheet for a task link.
    struct ActivitySheet: UIViewControllerRepresentable {
        let items: [Any]

        func makeUIViewController(context _: Context) -> UIActivityViewController {
            UIActivityViewController(activityItems: items, applicationActivities: nil)
        }

        func updateUIViewController(_: UIActivityViewController, context _: Context) {}
    }
#endif

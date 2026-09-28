import SwiftUI

// Task mutation affordances ported from `react-native/src/ui/TaskEditor.tsx`:
// the TaskMutationStatus read-only/error banner with Retry/Dismiss, and the
// inline TaskEditor with its save rules (no empty or unchanged saves).

public struct TaskMutationStatusView: View {
    public let writesAvailable: Bool
    public let mutationError: String?
    public let onRetry: (() -> Void)?
    public let onDismiss: (() -> Void)?

    public init(
        writesAvailable: Bool, mutationError: String?,
        onRetry: (() -> Void)? = nil, onDismiss: (() -> Void)? = nil
    ) {
        self.writesAvailable = writesAvailable
        self.mutationError = mutationError
        self.onRetry = onRetry
        self.onDismiss = onDismiss
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !writesAvailable {
                copy("Task editing is unavailable for this connection.")
            }
            if let mutationError {
                copy(mutationError).accessibilityLabel(mutationError)
            }
            if mutationError != nil, writesAvailable {
                HStack(spacing: Space.sm) {
                    if onRetry != nil {
                        quietAction("Retry", label: "Retry task change", action: onRetry!)
                    }
                    if onDismiss != nil {
                        quietAction("Dismiss", label: "Dismiss task change", action: onDismiss!)
                    }
                }
            }
        }
    }

    private func copy(_ text: String) -> some View {
        Text(text)
            .font(TypeStyle(size: 13, lineHeight: 19, weight: .regular).font)
            .foregroundColor(MobilePalette.textMuted)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func quietAction(
        _ title: String, label: String, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(title)
                .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                .foregroundColor(Color.white)
                .padding(.horizontal, 12)
        }
        .buttonStyle(KitPressableStyle())
        .frame(minWidth: 44, minHeight: 44)
        .accessibilityLabel(label)
    }
}

/// The inline description editor shown under a selected task.
public struct TaskEditorView: View {
    public let taskId: String
    public let title: String
    public let busy: Bool
    public let failed: Bool
    public let onSave: (_ id: String, _ description: String) -> Void
    public let onClose: () -> Void

    @State private var description: String = ""
    @State private var loadedTaskId: String = ""

    public init(
        taskId: String, title: String, busy: Bool, failed: Bool = false,
        onSave: @escaping (_ id: String, _ description: String) -> Void,
        onClose: @escaping () -> Void
    ) {
        self.taskId = taskId
        self.title = title
        self.busy = busy
        self.failed = failed
        self.onSave = onSave
        self.onClose = onClose
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            TextField("Task description", text: $description, axis: .vertical)
                .font(TypeStyle(size: 14, lineHeight: 21, weight: .regular).font)
                .foregroundColor(Color.white)
                .padding(12)
                .frame(minHeight: 64, alignment: .topLeading)
                .background(OmiColor.hex(0x1F1F25))
                .overlay(
                    RoundedRectangle(cornerRadius: MobileRadius.sm)
                        .strokeBorder(OmiColor.hex(0xB9B9B9), lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: MobileRadius.sm))
                .disabled(busy)
                .accessibilityLabel("Task description")
            HStack(spacing: Space.sm) {
                Button(action: { onSave(taskId, description) }) {
                    Text(busy && !failed ? "Saving…" : "Save")
                        .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                        .foregroundColor(Color.white)
                        .padding(.horizontal, 12)
                        .frame(minWidth: 44, minHeight: 44)
                        .background(disabled ? Color.clear : MobilePalette.text)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .opacity(disabled ? 0.45 : 1)
                }
                .buttonStyle(KitPressableStyle())
                .disabled(disabled)
                .accessibilityLabel("Save task description")
                Button(action: onClose) {
                    Text("Close")
                        .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                        .foregroundColor(Color.white)
                        .padding(.horizontal, 12)
                        .frame(minWidth: 44, minHeight: 44)
                }
                .buttonStyle(KitPressableStyle())
                .accessibilityLabel("Close task editor")
            }
        }
        .padding(.vertical, 12)
        .onAppear { syncTask() }
        .onChange(of: taskId) { _ in syncTask() }
        .onChange(of: title) { _ in syncTask() }
    }

    /// Port of the TaskEditor effect: follow the selected task until the user
    /// edits, then keep the typed draft across conflict refreshes.
    private func syncTask() {
        if loadedTaskId != taskId {
            loadedTaskId = taskId
            description = title
        } else if description == loadedTitle {
            description = title
        }
    }

    private var loadedTitle: String { title }

    private var disabled: Bool {
        busy || description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || description == title
    }
}

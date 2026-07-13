import SwiftUI
import OmiTheme

struct DailyTaskCreationSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var taskDescription = ""
    @State private var priority = "medium"
    @State private var isCreating = false
    @FocusState private var isTextFieldFocused: Bool

    let onCreate: (String, String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.xl) {
            // Header
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
                HStack {
                    Image(systemName: "repeat.circle.fill")
                        .scaledFont(size: OmiType.heading)
                        .foregroundColor(OmiColors.accent)

                    Text("Create Daily Task")
                        .scaledFont(size: OmiType.heading, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)

                    Spacer()

                    Button("Cancel") {
                        dismiss()
                    }
                    .buttonStyle(.plain)
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                }

                Text("This task will repeat every day until completed")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
            }

            // Task description
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
                Text("Task Description")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                TextField("What needs to be done daily?", text: $taskDescription)
                    .textFieldStyle(.roundedBorder)
                    .scaledFont(size: OmiType.body)
                    .focused($isTextFieldFocused)
                    .onSubmit {
                        createTask()
                    }
            }

            // Priority selection
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
                Text("Priority")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: OmiSpacing.md) {
                    ForEach(["high", "medium", "low"], id: \.self) { level in
                        let isSelected = priority == level

                        Button {
                            priority = level
                        } label: {
                            HStack(spacing: OmiSpacing.xs) {
                                Image(systemName: level == "high" ? "flag.fill" : "flag")
                                    .scaledFont(size: OmiType.caption)
                                    .foregroundColor(isSelected ? .white : priorityColor(level))

                                Text(level.capitalized)
                                    .scaledFont(size: OmiType.body)
                                    .foregroundColor(isSelected ? .white : OmiColors.textPrimary)
                            }
                            .padding(.horizontal, OmiSpacing.md)
                            .padding(.vertical, OmiSpacing.sm)
                            .background(
                                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                                    .fill(isSelected ? priorityColor(level) : OmiColors.backgroundSecondary)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                    Spacer()
                }
            }

            Spacer()

            // Create button
            HStack {
                Spacer()

                Button {
                    createTask()
                } label: {
                    HStack(spacing: OmiSpacing.sm) {
                        if isCreating {
                            ProgressView()
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "plus.circle.fill")
                        }
                        Text(isCreating ? "Creating..." : "Create Daily Task")
                    }
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(.white)
                    .padding(.horizontal, OmiSpacing.xl)
                    .padding(.vertical, OmiSpacing.sm)
                    .background(
                        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                            .fill(taskDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?
                                  OmiColors.textTertiary : OmiColors.accent)
                    )
                }
                .buttonStyle(.plain)
                .disabled(taskDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isCreating)
            }
        }
        .padding(OmiSpacing.xxl)
        .frame(width: 450, height: 320)
        .background(OmiColors.backgroundPrimary)
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                isTextFieldFocused = true
            }
        }
    }

    private func priorityColor(_ level: String) -> Color {
        switch level {
        case "high": return Color.red
        case "medium": return Color.orange
        case "low": return Color.blue
        default: return OmiColors.textSecondary
        }
    }

    private func createTask() {
        let trimmedDescription = taskDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedDescription.isEmpty, !isCreating else { return }

        isCreating = true
        onCreate(trimmedDescription, priority)

        // Dismiss after a brief delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            dismiss()
        }
    }
}

#if canImport(PreviewsMacros)
#Preview {
    DailyTaskCreationSheet { description, priority in
        print("Create daily task: \(description) with priority: \(priority)")
    }
}#endif

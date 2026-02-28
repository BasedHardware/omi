import SwiftUI

struct DailyTaskCreationSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var taskDescription = ""
    @State private var priority = "medium"
    @State private var isCreating = false
    @FocusState private var isTextFieldFocused: Bool

    let onCreate: (String, String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: "repeat.circle.fill")
                        .scaledFont(size: 20)
                        .foregroundColor(OmiColors.purplePrimary)

                    Text("Create Daily Task")
                        .scaledFont(size: 18, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)

                    Spacer()

                    Button("Cancel") {
                        dismiss()
                    }
                    .buttonStyle(.plain)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                }

                Text("This task will repeat every day until completed")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }

            // Task description
            VStack(alignment: .leading, spacing: 8) {
                Text("Task Description")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                TextField("What needs to be done daily?", text: $taskDescription)
                    .textFieldStyle(.roundedBorder)
                    .scaledFont(size: 14)
                    .focused($isTextFieldFocused)
                    .onSubmit {
                        createTask()
                    }
            }

            // Priority selection
            VStack(alignment: .leading, spacing: 8) {
                Text("Priority")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: 12) {
                    ForEach(["high", "medium", "low"], id: \.self) { level in
                        let isSelected = priority == level

                        Button {
                            priority = level
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: level == "high" ? "flag.fill" : "flag")
                                    .scaledFont(size: 12)
                                    .foregroundColor(isSelected ? .white : priorityColor(level))

                                Text(level.capitalized)
                                    .scaledFont(size: 13)
                                    .foregroundColor(isSelected ? .white : OmiColors.textPrimary)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
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
                    HStack(spacing: 8) {
                        if isCreating {
                            ProgressView()
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "plus.circle.fill")
                        }
                        Text(isCreating ? "Creating..." : "Create Daily Task")
                    }
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(taskDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?
                                  OmiColors.textTertiary : OmiColors.purplePrimary)
                    )
                }
                .buttonStyle(.plain)
                .disabled(taskDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isCreating)
            }
        }
        .padding(24)
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

#Preview {
    DailyTaskCreationSheet { description, priority in
        print("Create daily task: \(description) with priority: \(priority)")
    }
}
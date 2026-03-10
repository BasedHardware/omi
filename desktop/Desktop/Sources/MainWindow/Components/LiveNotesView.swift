import SwiftUI

/// Live notes view showing AI-generated and manual notes during recording
struct LiveNotesView: View {
    @ObservedObject var monitor: LiveNotesMonitor = .shared

    /// Text for manual note input
    @State private var manualNoteText: String = ""

    /// Currently editing note ID
    @State private var editingNoteId: Int64?

    /// Edit text buffer
    @State private var editText: String = ""

    /// Focus state for manual input
    @FocusState private var isInputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Header with AI toggle
            headerView

            Divider()
                .background(OmiColors.border)

            // Notes list
            if monitor.notes.isEmpty {
                emptyStateView
            } else {
                notesListView
            }

            // Manual note input
            manualInputView
        }
        .background(OmiColors.backgroundSecondary)
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            Text("Notes")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Spacer()

            // AI toggle
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .scaledFont(size: 12)
                    .foregroundColor(monitor.isAiEnabled ? OmiColors.purplePrimary : OmiColors.textQuaternary)

                Toggle("", isOn: $monitor.isAiEnabled)
                    .toggleStyle(.switch)
                    .scaleEffect(0.7)
                    .frame(width: 40)
            }

            // Generating indicator
            if monitor.isGenerating {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 16, height: 16)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    // MARK: - Empty State

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Spacer()

            Image(systemName: "note.text")
                .scaledFont(size: 32)
                .foregroundColor(OmiColors.textQuaternary)

            Text("Notes will appear here")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)

            if monitor.isAiEnabled {
                Text("AI generates notes as you speak")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textQuaternary)
            }

            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Notes List

    private var notesListView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(monitor.notes) { note in
                        NoteRowView(
                            note: note,
                            isEditing: editingNoteId == note.id,
                            editText: $editText,
                            onStartEdit: { startEditing(note) },
                            onSaveEdit: { saveEdit(note) },
                            onCancelEdit: { cancelEdit() },
                            onDelete: { deleteNote(note) }
                        )
                        .id(note.id)
                    }
                }
                .padding(12)
            }
            .onChange(of: monitor.notes.count) { _, _ in
                // Auto-scroll to latest note
                if let lastNote = monitor.notes.last {
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo(lastNote.id, anchor: .bottom)
                    }
                }
            }
        }
    }

    // MARK: - Manual Input

    private var manualInputView: some View {
        VStack(spacing: 0) {
            Divider()
                .background(OmiColors.border)

            HStack(spacing: 8) {
                TextField("Add a note...", text: $manualNoteText)
                    .textFieldStyle(.plain)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textPrimary)
                    .focused($isInputFocused)
                    .onSubmit {
                        addManualNote()
                    }

                Button(action: addManualNote) {
                    Image(systemName: "plus.circle.fill")
                        .scaledFont(size: 18)
                        .foregroundColor(manualNoteText.isEmpty ? OmiColors.textQuaternary : OmiColors.purplePrimary)
                }
                .buttonStyle(.plain)
                .disabled(manualNoteText.isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(OmiColors.backgroundTertiary)
        }
    }

    // MARK: - Actions

    private func addManualNote() {
        let text = manualNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        monitor.addManualNote(text: text)
        manualNoteText = ""
    }

    private func startEditing(_ note: LiveNote) {
        editingNoteId = note.id
        editText = note.text
    }

    private func saveEdit(_ note: LiveNote) {
        let text = editText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            cancelEdit()
            return
        }

        monitor.updateNote(id: note.id, text: text)
        cancelEdit()
    }

    private func cancelEdit() {
        editingNoteId = nil
        editText = ""
    }

    private func deleteNote(_ note: LiveNote) {
        monitor.deleteNote(id: note.id)
    }
}

// MARK: - Note Row View

private struct NoteRowView: View {
    let note: LiveNote
    let isEditing: Bool
    @Binding var editText: String
    let onStartEdit: () -> Void
    let onSaveEdit: () -> Void
    let onCancelEdit: () -> Void
    let onDelete: () -> Void

    @State private var isHovering = false
    @FocusState private var isEditFocused: Bool

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f
    }()

    private var formattedTime: String {
        Self.timeFormatter.string(from: note.timestamp)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            // AI indicator
            if note.isAiGenerated {
                Image(systemName: "sparkles")
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.purplePrimary)
                    .frame(width: 14)
            } else {
                Image(systemName: "pencil")
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textTertiary)
                    .frame(width: 14)
            }

            VStack(alignment: .leading, spacing: 4) {
                if isEditing {
                    // Edit mode
                    TextField("", text: $editText)
                        .textFieldStyle(.plain)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textPrimary)
                        .focused($isEditFocused)
                        .onSubmit { onSaveEdit() }
                        .onAppear { isEditFocused = true }
                        .onExitCommand { onCancelEdit() }
                } else {
                    // Display mode
                    Text(note.text)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(nil)
                        .onTapGesture(count: 2) {
                            onStartEdit()
                        }
                }

                // Timestamp
                Text(formattedTime)
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textQuaternary)
            }

            Spacer()

            // Action buttons (visible on hover or editing)
            if isHovering || isEditing {
                HStack(spacing: 4) {
                    if isEditing {
                        Button(action: onSaveEdit) {
                            Image(systemName: "checkmark")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.success)
                        }
                        .buttonStyle(.plain)

                        Button(action: onCancelEdit) {
                            Image(systemName: "xmark")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                    } else {
                        Button(action: onStartEdit) {
                            Image(systemName: "pencil")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)

                        Button(action: onDelete) {
                            Image(systemName: "trash")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.error)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isHovering || isEditing ? OmiColors.backgroundTertiary : Color.clear)
        )
        .onHover { hovering in
            isHovering = hovering
        }
    }
}

// MARK: - Preview

#Preview {
    LiveNotesView()
        .frame(width: 300, height: 500)
        .background(OmiColors.backgroundPrimary)
}

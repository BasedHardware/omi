import SwiftUI

/// Modal sheet for naming a speaker in a transcript
struct NameSpeakerSheet: View {
    let segment: TranscriptSegment
    let allSegments: [TranscriptSegment]
    let people: [Person]
    let onSave: (_ personId: String?, _ isUser: Bool, _ segmentIds: [Int]) -> Void
    let onCreatePerson: (_ name: String) async -> Person?
    let onDismiss: () -> Void

    @State private var selectedPersonId: String? = nil
    @State private var isUserSelected: Bool = false
    @State private var isAddingNewPerson: Bool = false
    @State private var newPersonName: String = ""
    @State private var duplicateWarning: String? = nil
    @State private var tagAllFromSpeaker: Bool = true
    @State private var isSaving: Bool = false
    @State private var isCreating: Bool = false

    /// Segments from the same speaker in this conversation
    private var sameSpeakerSegments: [TranscriptSegment] {
        allSegments.filter { $0.speaker == segment.speaker && !$0.isUser }
    }

    /// Segment indices (positional index in allSegments) for the same speaker
    private var sameSpeakerIndices: [Int] {
        allSegments.enumerated().compactMap { index, seg in
            seg.speaker == segment.speaker && !seg.isUser ? index : nil
        }
    }

    /// Index of the tapped segment
    private var tappedSegmentIndex: Int {
        allSegments.firstIndex(where: { $0.id == segment.id }) ?? 0
    }

    /// Preview text from the tapped segment
    private var previewText: String {
        let text = segment.text
        if text.count > 120 {
            return String(text.prefix(120)) + "..."
        }
        return text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("Name Speaker")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: onDismiss)
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 12)

            Divider()
                .background(OmiColors.border)

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Speaker info
                    speakerInfoSection

                    // People selection
                    peopleSelectionSection

                    // Tag other segments toggle
                    if sameSpeakerSegments.count > 1 {
                        tagOtherSegmentsToggle
                    }
                }
                .padding(20)
            }

            Divider()
                .background(OmiColors.border)

            // Action buttons
            HStack {
                Spacer()
                Button("Cancel") {
                    onDismiss()
                }
                .buttonStyle(.plain)
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)

                Button(action: save) {
                    if isSaving {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 14, height: 14)
                    } else {
                        Text("Save")
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(canSave ? .black : OmiColors.textTertiary)
                .padding(.horizontal, 20)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(canSave ? Color.white : OmiColors.backgroundTertiary)
                )
                .disabled(!canSave || isSaving)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
        }
        .frame(width: 400, height: 450)
        .background(OmiColors.backgroundPrimary)
    }

    // MARK: - Speaker Info

    private var speakerInfoSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Circle()
                    .fill(OmiColors.backgroundQuaternary)
                    .frame(width: 28, height: 28)
                    .overlay(
                        Text(String(segment.speakerId))
                            .scaledFont(size: 12, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)
                    )
                Text("Speaker \(segment.speakerId)")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
            }

            Text("\"\(previewText)\"")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .italic()
                .lineLimit(3)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(OmiColors.backgroundSecondary)
        )
    }

    // MARK: - People Selection

    private var peopleSelectionSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Who is this?")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            FlowLayout(spacing: 8) {
                // "You" chip
                personChip(label: "You", isSelected: isUserSelected) {
                    isUserSelected = true
                    selectedPersonId = nil
                    isAddingNewPerson = false
                    newPersonName = ""
                    duplicateWarning = nil
                }

                // Existing people chips
                ForEach(people) { person in
                    personChip(label: person.name, isSelected: selectedPersonId == person.id) {
                        selectedPersonId = person.id
                        isUserSelected = false
                        isAddingNewPerson = false
                        newPersonName = ""
                        duplicateWarning = nil
                    }
                }

                // "+ Add Person" chip
                personChip(label: "+ Add Person", isSelected: isAddingNewPerson, isAction: true) {
                    isAddingNewPerson = true
                    isUserSelected = false
                    selectedPersonId = nil
                    duplicateWarning = nil
                }
            }

            // Inline text field for new person name
            if isAddingNewPerson {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        TextField("Person name", text: $newPersonName)
                            .textFieldStyle(.plain)
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(OmiColors.backgroundSecondary)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(duplicateWarning != nil ? OmiColors.error : OmiColors.border, lineWidth: 1)
                            )
                            .onChange(of: newPersonName) { _, newValue in
                                validateName(newValue)
                            }
                            .onSubmit {
                                if !newPersonName.trimmingCharacters(in: .whitespaces).isEmpty && duplicateWarning == nil {
                                    Task { await createAndSelect() }
                                }
                            }

                        Button(action: {
                            Task { await createAndSelect() }
                        }) {
                            if isCreating {
                                ProgressView()
                                    .scaleEffect(0.5)
                                    .frame(width: 14, height: 14)
                            } else {
                                Text("Add")
                                    .scaledFont(size: 12, weight: .medium)
                            }
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(canCreate ? .black : OmiColors.textTertiary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(
                            Capsule()
                                .fill(canCreate ? Color.white : OmiColors.backgroundTertiary)
                        )
                        .disabled(!canCreate || isCreating)
                    }

                    if let warning = duplicateWarning {
                        Text(warning)
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.error)
                    }
                }
            }
        }
    }

    // MARK: - Tag Other Segments Toggle

    private var tagOtherSegmentsToggle: some View {
        Toggle(isOn: $tagAllFromSpeaker) {
            Text("Also tag \(sameSpeakerSegments.count - 1) other segment\(sameSpeakerSegments.count - 1 == 1 ? "" : "s") from this speaker")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
        }
        .toggleStyle(.checkbox)
    }

    // MARK: - Helpers

    private var canSave: Bool {
        isUserSelected || selectedPersonId != nil
    }

    private var canCreate: Bool {
        let trimmed = newPersonName.trimmingCharacters(in: .whitespaces)
        return !trimmed.isEmpty && duplicateWarning == nil
    }

    private func validateName(_ name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        if people.contains(where: { $0.name.lowercased() == trimmed.lowercased() }) {
            duplicateWarning = "A person with this name already exists"
        } else {
            duplicateWarning = nil
        }
    }

    private func createAndSelect() async {
        let trimmed = newPersonName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty, duplicateWarning == nil else { return }

        isCreating = true
        if let person = await onCreatePerson(trimmed) {
            selectedPersonId = person.id
            isAddingNewPerson = false
            newPersonName = ""
        }
        isCreating = false
    }

    private func save() {
        isSaving = true
        let indices = tagAllFromSpeaker ? sameSpeakerIndices : [tappedSegmentIndex]
        onSave(selectedPersonId, isUserSelected, indices)
    }

    private func personChip(label: String, isSelected: Bool, isAction: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)
                .foregroundColor(isSelected ? .black : (isAction ? OmiColors.purplePrimary : OmiColors.textPrimary))
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(isSelected ? Color.white : OmiColors.backgroundTertiary)
                )
                .overlay(
                    Capsule()
                        .stroke(isSelected ? OmiColors.border : (isAction ? OmiColors.purplePrimary.opacity(0.3) : Color.clear), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

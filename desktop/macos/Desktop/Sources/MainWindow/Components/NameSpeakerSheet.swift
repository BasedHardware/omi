import SwiftUI
import OmiTheme

/// Modal sheet for naming a speaker in a transcript
struct NameSpeakerSheet: View {
    let segment: TranscriptSegment
    let allSegments: [TranscriptSegment]
    let people: [Person]
    let onSave: (_ personId: String?, _ isUser: Bool, _ segmentIndices: [Int]) -> Void
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
                    .scaledFont(size: OmiType.subheading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: onDismiss)
            }
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.top, OmiSpacing.xl)
            .padding(.bottom, OmiSpacing.md)

            Divider()
                .background(OmiColors.border)

            ScrollView {
                VStack(alignment: .leading, spacing: OmiSpacing.xl) {
                    // Speaker info
                    speakerInfoSection

                    // People selection
                    peopleSelectionSection

                    // Tag other segments toggle
                    if sameSpeakerSegments.count > 1 {
                        tagOtherSegmentsToggle
                    }
                }
                .padding(OmiSpacing.xl)
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
                .padding(.horizontal, OmiSpacing.lg)
                .padding(.vertical, OmiSpacing.sm)

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
                .padding(.horizontal, OmiSpacing.xl)
                .padding(.vertical, OmiSpacing.sm)
                .background(
                    Capsule()
                        .fill(canSave ? Color.white : OmiColors.backgroundTertiary)
                )
                .disabled(!canSave || isSaving)
            }
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.md)
        }
        .frame(width: 400, height: 450)
        .background(OmiColors.backgroundPrimary)
    }

    // MARK: - Speaker Info

    private var speakerInfoSection: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            HStack(spacing: OmiSpacing.sm) {
                Circle()
                    .fill(OmiColors.backgroundQuaternary)
                    .frame(width: 28, height: 28)
                    .overlay(
                        Text(String(segment.speakerId))
                            .scaledFont(size: OmiType.caption, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)
                    )
                Text("Speaker \(segment.speakerId)")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
            }

            Text("\"\(previewText)\"")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textSecondary)
                .italic()
                .lineLimit(3)
        }
        .padding(OmiSpacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(OmiColors.backgroundSecondary)
        )
    }

    // MARK: - People Selection

    private var peopleSelectionSection: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Who is this?")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            FlowLayout(spacing: OmiSpacing.sm) {
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
                VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                    HStack(spacing: OmiSpacing.sm) {
                        TextField("Person name", text: $newPersonName)
                            .textFieldStyle(.plain)
                            .scaledFont(size: OmiType.body)
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, OmiSpacing.sm)
                            .padding(.vertical, OmiSpacing.sm)
                            .background(
                                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                                    .fill(OmiColors.backgroundSecondary)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
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
                                    .scaledFont(size: OmiType.caption, weight: .medium)
                            }
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(canCreate ? .black : OmiColors.textTertiary)
                        .padding(.horizontal, OmiSpacing.md)
                        .padding(.vertical, OmiSpacing.xs)
                        .background(
                            Capsule()
                                .fill(canCreate ? Color.white : OmiColors.backgroundTertiary)
                        )
                        .disabled(!canCreate || isCreating)
                    }

                    if let warning = duplicateWarning {
                        Text(warning)
                            .scaledFont(size: OmiType.caption)
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
                .scaledFont(size: OmiType.body)
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
        let segmentIndices = tagAllFromSpeaker ? sameSpeakerIndices : [tappedSegmentIndex]
        onSave(selectedPersonId, isUserSelected, segmentIndices)
    }

    private func personChip(label: String, isSelected: Bool, isAction: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .scaledFont(size: OmiType.body, weight: isSelected ? .semibold : .regular)
                .foregroundColor(isSelected ? .black : (isAction ? OmiColors.accent : OmiColors.textPrimary))
                .padding(.horizontal, OmiSpacing.md)
                .padding(.vertical, OmiSpacing.sm)
                .background(
                    Capsule()
                        .fill(isSelected ? Color.white : OmiColors.backgroundTertiary)
                )
                .overlay(
                    Capsule()
                        .stroke(isSelected ? OmiColors.border : (isAction ? OmiColors.accent.opacity(0.3) : Color.clear), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

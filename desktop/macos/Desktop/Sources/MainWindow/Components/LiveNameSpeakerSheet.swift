import SwiftUI
import OmiTheme

/// Modal sheet for naming a speaker during live transcription
struct LiveNameSpeakerSheet: View {
    let speakerId: Int
    let sampleText: String
    let people: [Person]
    let currentPersonId: String?
    let onSave: (_ personId: String) -> Void
    let onCreatePerson: (_ name: String) async -> Person?
    let onDismiss: () -> Void

    @State private var selectedPersonId: String? = nil
    @State private var isAddingNewPerson: Bool = false
    @State private var newPersonName: String = ""
    @State private var duplicateWarning: String? = nil
    @State private var isCreating: Bool = false

    /// Preview text from the segment
    private var previewText: String {
        if sampleText.count > 120 {
            return String(sampleText.prefix(120)) + "..."
        }
        return sampleText
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
                    Text("Save")
                }
                .buttonStyle(.plain)
                .foregroundColor(canSave ? .black : OmiColors.textTertiary)
                .padding(.horizontal, OmiSpacing.xl)
                .padding(.vertical, OmiSpacing.sm)
                .background(
                    Capsule()
                        .fill(canSave ? Color.white : OmiColors.backgroundTertiary)
                )
                .disabled(!canSave)
            }
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.md)
        }
        .frame(width: 400, height: 400)
        .background(OmiColors.backgroundPrimary)
        .onAppear {
            selectedPersonId = currentPersonId
        }
    }

    // MARK: - Speaker Info

    private var speakerInfoSection: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            HStack(spacing: OmiSpacing.sm) {
                Circle()
                    .fill(OmiColors.backgroundQuaternary)
                    .frame(width: 28, height: 28)
                    .overlay(
                        Text(String(speakerId))
                            .scaledFont(size: OmiType.caption, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)
                    )
                Text("Speaker \(speakerId)")
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
                // Existing people chips
                ForEach(people) { person in
                    personChip(label: person.name, isSelected: selectedPersonId == person.id) {
                        selectedPersonId = person.id
                        isAddingNewPerson = false
                        newPersonName = ""
                        duplicateWarning = nil
                    }
                }

                // "+ Add Person" chip
                personChip(label: "+ Add Person", isSelected: isAddingNewPerson, isAction: true) {
                    isAddingNewPerson = true
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

            Text("This name will apply to all segments from this speaker in the current recording and will be saved when the conversation ends.")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textQuaternary)
                .padding(.top, OmiSpacing.xxs)
        }
    }

    // MARK: - Helpers

    private var canSave: Bool {
        selectedPersonId != nil
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
        guard let personId = selectedPersonId else { return }
        onSave(personId)
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

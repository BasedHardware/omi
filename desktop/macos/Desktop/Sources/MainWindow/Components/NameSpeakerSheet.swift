import OmiTheme
import SwiftUI

/// Modal sheet for naming a speaker in a transcript
struct NameSpeakerSheet: View {
  let segment: TranscriptSegment
  let allSegments: [TranscriptSegment]
  let people: [Person]
  let onSave: (_ personId: String?, _ isUser: Bool, _ segmentIndices: [Int]) async -> Bool
  let onCreatePerson: ((_ name: String) async -> Person?)?
  let onDismiss: () -> Void

  @State private var selectedPersonId: String? = nil
  @State private var isUserSelected: Bool = false
  @State private var isAddingNewPerson: Bool = false
  @State private var newPersonName: String = ""
  @State private var duplicateWarning: String? = nil
  @State private var tagAllFromSpeaker: Bool = true
  @State private var isSaving: Bool = false
  @State private var isCreating: Bool = false
  @State private var saveError: String? = nil

  /// Segments from the same speaker in this conversation
  private var sameSpeakerSegments: [TranscriptSegment] {
    Self.sameSpeakerIndices(of: segment, in: allSegments).map { allSegments[$0] }
  }

  /// Segment indices (positional index in allSegments) for the same speaker
  private var sameSpeakerIndices: [Int] {
    Self.sameSpeakerIndices(of: segment, in: allSegments)
  }

  /// Positions of the segments "Also tag" covers: the tapped segment's speaker, on the same side of
  /// "You" as the tapped segment. A segment marked as you is only grouped with other "You" segments,
  /// so fixing or clearing a wrong "You" reaches them, and naming someone else never overwrites them.
  static func sameSpeakerIndices(of segment: TranscriptSegment, in segments: [TranscriptSegment]) -> [Int] {
    segments.enumerated().compactMap { index, candidate in
      candidate.speaker == segment.speaker && candidate.isUser == segment.isUser ? index : nil
    }
  }

  /// Whether the segment currently has an identity the sheet can take away.
  static func canUnassign(_ segment: TranscriptSegment) -> Bool {
    segment.isUser || segment.personId != nil
  }

  /// Index of the tapped segment
  private var tappedSegmentIndex: Int {
    allSegments.firstIndex(where: { $0.id == segment.id }) ?? 0
  }

  /// Preview text from the tapped segment
  private var previewText: String {
    let text = segment.text
    if text.count > 120 {
      return String(text.prefix(120)) + "…"
    }
    return text
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Header
      HStack {
        Text("Name Speaker")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
        DismissButton(action: onDismiss)
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.top, OmiSpacing.xl)
      .padding(.bottom, OmiSpacing.md)

      Divider()
        .background(Ink.separator)

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
        .background(Ink.separator)

      if let saveError {
        Text(saveError)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.errorRed)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.bottom, OmiSpacing.sm)
      }

      // Action buttons
      HStack {
        // Back to anonymous "Speaker N": no person, not you.
        if Self.canUnassign(segment) {
          Button("Unassign") {
            Task { await save(personId: nil, isUser: false) }
          }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
          .disabled(isSaving)
          .help("Return this speaker to \(SpeakerLabelFormatter.anonymousLabel(speakerId: segment.speakerId))")
          .accessibilityIdentifier("name-speaker-unassign")
        }
        Spacer()
        Button("Cancel") {
          onDismiss()
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        .keyboardShortcut(.cancelAction)

        Button {
          Task { await save(personId: selectedPersonId, isUser: isUserSelected) }
        } label: {
          if isSaving {
            ProgressView()
              .controlSize(.small)
          } else {
            Text("Save")
          }
        }
        .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        .keyboardShortcut(.defaultAction)
        .disabled(!canSave || isSaving)
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.md)
    }
    .frame(width: 400, height: 450)
    .background(Ink.surface)
    .glassContent()
    // Reopening a named speaker starts on who it is now, so fixing a wrong name is one click.
    .onAppear {
      if segment.isUser {
        isUserSelected = true
      } else if let personId = segment.personId {
        selectedPersonId = personId
      }
    }
  }

  private var currentAssignmentName: String? {
    if segment.isUser { return "You" }
    guard let personId = segment.personId else { return nil }
    return people.first { $0.id == personId }?.name
  }

  // MARK: - Speaker Info

  private var speakerInfoSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.sm) {
        Circle()
          .fill(Ink.rowFillHover)
          .frame(width: 28, height: 28)
          .overlay(
            Text(String(SpeakerLabelFormatter.displayNumber(speakerId: segment.speakerId)))
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(Ink.primary)
          )
        VStack(alignment: .leading, spacing: 0) {
          Text(SpeakerLabelFormatter.anonymousLabel(speakerId: segment.speakerId))
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
          if let current = currentAssignmentName {
            Text("Currently: \(current)")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        }
      }

      Text("\"\(previewText)\"")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .italic()
        .lineLimit(3)
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(Ink.rowFill)
    )
  }

  // MARK: - People Selection

  private var peopleSelectionSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text("Who is this?")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.secondary)

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

        if onCreatePerson != nil {
          // "+ Add Person" chip
          personChip(label: "+ Add Person", isSelected: isAddingNewPerson, isAction: true) {
            isAddingNewPerson = true
            isUserSelected = false
            selectedPersonId = nil
            duplicateWarning = nil
          }
        }
      }

      // Inline text field for new person name
      if isAddingNewPerson {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          HStack(spacing: OmiSpacing.sm) {
            TextField("Person name", text: $newPersonName)
              .textFieldStyle(.plain)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.primary)
              .padding(.horizontal, OmiSpacing.sm)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                  .fill(Ink.rowFill)
              )
              .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                  .stroke(duplicateWarning != nil ? Ink.errorRed : Ink.separator, lineWidth: 1)
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
            .foregroundColor(canCreate ? Ink.surface : Ink.secondary)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.xs)
            .background(
              Capsule()
                .fill(canCreate ? Ink.primary : Ink.rowFillHover)
            )
            .disabled(!canCreate || isCreating)
          }

          if let warning = duplicateWarning {
            Text(warning)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.errorRed)
          }
        }
      }
    }
  }

  // MARK: - Tag Other Segments Toggle

  private var tagOtherSegmentsToggle: some View {
    Toggle(isOn: $tagAllFromSpeaker) {
      Text(
        "Also tag \(sameSpeakerSegments.count - 1) other segment\(sameSpeakerSegments.count - 1 == 1 ? "" : "s") from this speaker"
      )
      .scaledFont(size: OmiType.body)
      .foregroundColor(Ink.secondary)
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
    guard !trimmed.isEmpty, duplicateWarning == nil, let onCreatePerson else { return }

    isCreating = true
    if let person = await onCreatePerson(trimmed) {
      selectedPersonId = person.id
      isAddingNewPerson = false
      newPersonName = ""
    }
    isCreating = false
  }

  private func save(personId: String?, isUser: Bool) async {
    guard !isSaving else { return }

    isSaving = true
    saveError = nil
    let segmentIndices = tagAllFromSpeaker ? sameSpeakerIndices : [tappedSegmentIndex]
    let succeeded = await onSave(personId, isUser, segmentIndices)
    isSaving = false

    if succeeded {
      onDismiss()
    } else {
      saveError = "Couldn't assign this speaker. Try again."
    }
  }

  private func personChip(label: String, isSelected: Bool, isAction: Bool = false, action: @escaping () -> Void)
    -> some View
  {
    Button(action: action) {
      Text(label)
        .scaledFont(size: OmiType.body, weight: isSelected ? .semibold : .regular)
        .foregroundColor(isSelected ? Ink.surface : Ink.primary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .background(
          Capsule()
            .fill(isSelected ? Ink.primary : Ink.rowFillHover)
        )
        .overlay(
          Capsule()
            .stroke(
              isSelected ? Ink.separator : (isAction ? Ink.hairline : Color.clear), lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }
}

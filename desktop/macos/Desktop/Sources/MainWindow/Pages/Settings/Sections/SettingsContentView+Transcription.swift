import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var transcriptionSection: some View {
    VStack(spacing: 20) {
      // Language Mode
      settingsCard(settingId: "transcription.languagemode") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "globe")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            Text("Language Mode")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()
          }

          // Auto-Detect option
          Button(action: {
            transcriptionAutoDetect = true
            AssistantSettings.shared.transcriptionAutoDetect = true
            updateTranscriptionPreferences(singleLanguageMode: false)
            restartTranscriptionIfNeeded()
          }) {
            HStack(alignment: .top, spacing: 12) {
              Image(systemName: transcriptionAutoDetect ? "checkmark.circle.fill" : "circle")
                .scaledFont(size: 20)
                .foregroundColor(
                  transcriptionAutoDetect ? OmiColors.purplePrimary : OmiColors.textTertiary)

              VStack(alignment: .leading, spacing: 6) {
                Text("Auto-Detect (Multi-Language)")
                  .scaledFont(size: 14, weight: .medium)
                  .foregroundColor(OmiColors.textPrimary)

                Text("Automatically detects and transcribes:")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)

                // List of supported languages
                Text(
                  "English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch"
                )
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .fixedSize(horizontal: false, vertical: true)
              }

              Spacer()
            }
            .padding(12)
            .background(
              RoundedRectangle(cornerRadius: 8)
                .fill(transcriptionAutoDetect ? OmiColors.purplePrimary.opacity(0.1) : Color.clear)
                .overlay(
                  RoundedRectangle(cornerRadius: 8)
                    .stroke(
                      transcriptionAutoDetect
                        ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.backgroundQuaternary,
                      lineWidth: 1)
                )
            )
          }
          .buttonStyle(.plain)

          // Single Language option
          Button(action: {
            transcriptionAutoDetect = false
            AssistantSettings.shared.transcriptionAutoDetect = false
            updateTranscriptionPreferences(singleLanguageMode: true)
            restartTranscriptionIfNeeded()
          }) {
            HStack(alignment: .top, spacing: 12) {
              Image(systemName: !transcriptionAutoDetect ? "checkmark.circle.fill" : "circle")
                .scaledFont(size: 20)
                .foregroundColor(
                  !transcriptionAutoDetect ? OmiColors.purplePrimary : OmiColors.textTertiary)

              VStack(alignment: .leading, spacing: 6) {
                Text("Single Language (Better Accuracy)")
                  .scaledFont(size: 14, weight: .medium)
                  .foregroundColor(OmiColors.textPrimary)

                Text("Best for speaking in one specific language")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)

                // Language picker (only shown when single language is selected)
                if !transcriptionAutoDetect {
                  HStack {
                    Text("Language:")
                      .scaledFont(size: 12)
                      .foregroundColor(OmiColors.textTertiary)

                    SearchableDropdown(
                      title: "Language",
                      options: languageOptions.map { option in
                        SearchableDropdownOption(id: option.0, title: option.1)
                      },
                      selectedId: transcriptionLanguage,
                      minWidth: 180
                    ) { option in
                      transcriptionLanguage = option.id
                      AssistantSettings.shared.transcriptionLanguage = option.id
                      let supportsMulti = AssistantSettings.supportsAutoDetect(option.id)
                      transcriptionAutoDetect = supportsMulti
                      AssistantSettings.shared.transcriptionAutoDetect = supportsMulti
                      updateTranscriptionPreferences(singleLanguageMode: !supportsMulti)
                      updateLanguage(option.id)
                      restartTranscriptionIfNeeded()
                    }
                  }
                  .padding(.top, 4)
                }
              }

              Spacer()
            }
            .padding(12)
            .background(
              RoundedRectangle(cornerRadius: 8)
                .fill(!transcriptionAutoDetect ? OmiColors.purplePrimary.opacity(0.1) : Color.clear)
                .overlay(
                  RoundedRectangle(cornerRadius: 8)
                    .stroke(
                      !transcriptionAutoDetect
                        ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.backgroundQuaternary,
                      lineWidth: 1)
                )
            )
          }
          .buttonStyle(.plain)

          // Info about language support
          HStack(spacing: 8) {
            Image(systemName: "info.circle")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)

            Text(
              "Single language mode supports \(AssistantSettings.supportedLanguages.count) languages including Chinese, Ukrainian, Russian, and more."
            )
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
          }
        }
      }

      // Voice assistant (push-to-talk) languages
      settingsCard(settingId: "transcription.voicelanguages") {
        VoiceAssistantLanguagesCard()
      }

      // Custom Vocabulary
      settingsCard(settingId: "transcription.vocabulary") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "text.book.closed")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Custom Vocabulary")
                .scaledFont(size: 15, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Text("Improve recognition of names, brands, and technical terms")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            if !vocabularyList.isEmpty {
              Text("\(vocabularyList.count) terms")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          // Current vocabulary display with removable tags
          if !vocabularyList.isEmpty {
            FlowLayout(spacing: 6) {
              ForEach(vocabularyList, id: \.self) { term in
                HStack(spacing: 4) {
                  Text(term)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)

                  Button(action: {
                    removeVocabularyWord(term)
                  }) {
                    Image(systemName: "xmark")
                      .scaledFont(size: 9, weight: .medium)
                      .foregroundColor(OmiColors.textTertiary)
                  }
                  .buttonStyle(.plain)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(
                  RoundedRectangle(cornerRadius: 6)
                    .fill(OmiColors.backgroundQuaternary)
                )
              }
            }
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          // Add new word input
          HStack(spacing: 8) {
            TextField("Add a word...", text: $newVocabularyWord)
              .textFieldStyle(.roundedBorder)
              .onSubmit {
                addVocabularyWord()
              }

            Button(action: {
              addVocabularyWord()
            }) {
              Image(systemName: "plus.circle.fill")
                .scaledFont(size: 20)
                .foregroundColor(
                  newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty
                    ? OmiColors.textTertiary : OmiColors.purplePrimary)
            }
            .buttonStyle(.plain)
            .disabled(newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty)
          }

          Text("Press Enter or click + to add • Click × to remove")
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }
      }

      // Local VAD Gate
      settingsCard(settingId: "transcription.vadgate") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Image(systemName: "waveform.badge.minus")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Local VAD Gate")
                .scaledFont(size: 15, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Text(
                "Uses on-device voice activity detection to skip silence, reducing Deepgram API usage. May save ~40% on transcription costs."
              )
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textTertiary)
              .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            Toggle("", isOn: $vadGateEnabled)
              .toggleStyle(.switch)
              .onChange(of: vadGateEnabled) { _, newValue in
                AssistantSettings.shared.vadGateEnabled = newValue
                restartTranscriptionIfNeeded()
              }
          }
        }
      }

    }
  }

  /// Add a word to the vocabulary
  func addVocabularyWord() {
    let word = newVocabularyWord.trimmingCharacters(in: .whitespaces)
    guard !word.isEmpty else { return }

    // Don't add duplicates (case-insensitive check)
    guard !vocabularyList.contains(where: { $0.lowercased() == word.lowercased() }) else {
      newVocabularyWord = ""
      return
    }

    vocabularyList.append(word)
    newVocabularyWord = ""
    saveVocabulary()
  }

  /// Remove a word from the vocabulary
  func removeVocabularyWord(_ word: String) {
    vocabularyList.removeAll { $0 == word }
    saveVocabulary()
  }

  /// Save vocabulary to local settings and backend
  func saveVocabulary() {
    // Save to local settings
    AssistantSettings.shared.transcriptionVocabulary = vocabularyList

    // Sync to backend
    updateTranscriptionPreferences(vocabulary: vocabularyList.joined(separator: ", "))
  }

  /// Restart transcription if currently running to apply new settings
  func restartTranscriptionIfNeeded() {
    guard appState.isTranscribing else { return }

    // Stop and restart to apply new language settings
    appState.stopTranscription()

    // Wait a moment for cleanup, then restart
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
      self.appState.startTranscription()
    }
  }

  // MARK: - Notifications Section

}

/// Multi-select for the languages the user speaks to the VOICE ASSISTANT (push-to-talk).
/// Order matters: the first selection is the primary. Self-contained — reads and writes
/// `AssistantSettings.voiceLanguages` directly and re-warms the realtime hub so the new
/// set reaches the session's system instruction without an app restart. Deliberately
/// separate from the ambient Language Mode card above: this never touches the always-on
/// transcriber's language settings.
private struct VoiceAssistantLanguagesCard: View {
  @State private var selection: [String] = []

  private var chipOptions: [(code: String, name: String)] {
    let common = OnboardingPagedIntroCoordinator.commonLanguages
    let extra =
      selection
      .filter { code in !common.contains(where: { $0.code == code }) }
      .map { code in
        (
          code: code,
          name: AssistantSettings.supportedLanguages.first(where: { $0.code == code })?.name
            ?? code
        )
      }
    return common + extra
  }

  private var addableLanguages: [(code: String, name: String)] {
    AssistantSettings.supportedLanguages.filter { option in
      !option.code.contains("-") && !selection.contains(option.code)
        && !chipOptions.contains(where: { $0.code == option.code })
    }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      HStack {
        Image(systemName: "person.wave.2")
          .scaledFont(size: 16)
          .foregroundColor(OmiColors.textSecondary)

        VStack(alignment: .leading, spacing: 4) {
          Text("Voice Assistant Languages")
            .scaledFont(size: 15, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)

          Text("Languages you speak to Omi over push-to-talk — the first is your primary. Omi identifies which one you're speaking each turn.")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        }

        Spacer()
      }

      FlowLayout(spacing: 6) {
        ForEach(chipOptions, id: \.code) { option in
          languageChip(option)
        }
        if !addableLanguages.isEmpty {
          SearchableDropdown(
            title: "Add language",
            label: "More…",
            options: addableLanguages.map { option in
              SearchableDropdownOption(id: option.code, title: option.name)
            },
            selectedId: nil
          ) { option in
            selection.append(option.id)
            persist()
          }
          .fixedSize()
        }
      }
    }
    .onAppear {
      selection = AssistantSettings.shared.voiceLanguages
    }
  }

  private func languageChip(_ option: (code: String, name: String)) -> some View {
    let isSelected = selection.contains(option.code)
    let isPrimary = selection.first == option.code
    return Button(action: {
      if let idx = selection.firstIndex(of: option.code) {
        selection.remove(at: idx)
      } else {
        selection.append(option.code)
      }
      persist()
    }) {
      Text(isPrimary ? "\(option.name) ✓" : option.name)
        .scaledFont(size: 12, weight: isSelected ? .semibold : .regular)
        .foregroundColor(isSelected ? OmiColors.backgroundPrimary : OmiColors.textSecondary)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
          Capsule().fill(isSelected ? Color.white.opacity(0.9) : Color.clear)
            .overlay(Capsule().stroke(OmiColors.backgroundQuaternary, lineWidth: isSelected ? 0 : 1))
        )
    }
    .buttonStyle(.plain)
  }

  private func persist() {
    guard !selection.isEmpty else {
      // Never store an empty set — fall back to the current stored value.
      selection = AssistantSettings.shared.voiceLanguages
      return
    }
    AssistantSettings.shared.voiceLanguages = selection
    selection = AssistantSettings.shared.voiceLanguages
    // The voiceLanguages setter posts .voiceLanguagesDidChange; the hub controller
    // observes it to prewarm the LID model and re-warm the session's instructions.
  }
}

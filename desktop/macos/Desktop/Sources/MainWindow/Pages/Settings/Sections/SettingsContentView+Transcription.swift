import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

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

                    Picker("", selection: $transcriptionLanguage) {
                      ForEach(languageOptions, id: \.0) { option in
                        Text(option.1).tag(option.0)
                      }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 180)
                    .onChange(of: transcriptionLanguage) { _, newValue in
                      AssistantSettings.shared.transcriptionLanguage = newValue
                      let supportsMulti = AssistantSettings.supportsAutoDetect(newValue)
                      transcriptionAutoDetect = supportsMulti
                      AssistantSettings.shared.transcriptionAutoDetect = supportsMulti
                      updateTranscriptionPreferences(singleLanguageMode: !supportsMulti)
                      updateLanguage(newValue)
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

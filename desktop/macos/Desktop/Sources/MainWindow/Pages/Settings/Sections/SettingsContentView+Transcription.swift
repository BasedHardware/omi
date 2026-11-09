import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  var transcriptionSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Microphone (input device — e.g. Ray-Ban Meta glasses)
      settingsCard(settingId: "transcription.microphone") {
        MicrophonePickerCard(onChanged: { restartTranscriptionIfNeeded() })
      }

      // Language Mode
      settingsCard(settingId: "transcription.languagemode") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "globe")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            Text("Language Mode")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)

            Spacer()
          }

          // Auto-Detect option
          Button(action: {
            guard autoDetectSupported else { return }
            transcriptionAutoDetect = true
            AssistantSettings.shared.transcriptionAutoDetect = true
            updateTranscriptionPreferences(singleLanguageMode: false)
            restartTranscriptionIfNeeded()
          }) {
            HStack(alignment: .top, spacing: OmiSpacing.md) {
              Image(systemName: autoDetectIsActive ? "checkmark.circle.fill" : "circle")
                .scaledFont(size: OmiType.heading)
                .foregroundColor(
                  SettingsSelection.optionMark(isSelected: autoDetectIsActive))

              VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                Text("Auto-Detect (Multi-Language)")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.primary)

                Text("Automatically detects and transcribes:")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)

                // List of supported languages
                Text(
                  "English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch"
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

                // Why the option is inert for this account, rather than a checkmark that
                // moves and a transcriber that ignores it.
                if !autoDetectSupported {
                  HStack(spacing: OmiSpacing.xs) {
                    Image(systemName: "exclamationmark.triangle.fill")
                      .scaledFont(size: OmiType.micro)
                      .foregroundColor(SettingsInk.notice)

                    Text("\(autoDetectSubtitle) — pick one of the ten above to use it.")
                      .scaledFont(size: OmiType.caption)
                      .foregroundColor(SettingsInk.notice)
                      .fixedSize(horizontal: false, vertical: true)
                  }
                  .padding(.top, OmiSpacing.xxs)
                }
              }

              Spacer()
            }
            .padding(OmiSpacing.md)
            .background(
              RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                .fill(autoDetectIsActive ? SettingsSelection.optionFill(isSelected: true) : Color.clear)
                .overlay(
                  RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                    .stroke(SettingsSelection.optionStroke(isSelected: autoDetectIsActive), lineWidth: 1)
                )
            )
            .contentShape(RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous))
          }
          .buttonStyle(.plain)
          .disabled(!autoDetectSupported)

          // Single Language option
          Button(action: {
            transcriptionAutoDetect = false
            AssistantSettings.shared.transcriptionAutoDetect = false
            updateTranscriptionPreferences(singleLanguageMode: true)
            restartTranscriptionIfNeeded()
          }) {
            HStack(alignment: .top, spacing: OmiSpacing.md) {
              Image(systemName: !autoDetectIsActive ? "checkmark.circle.fill" : "circle")
                .scaledFont(size: OmiType.heading)
                .foregroundColor(
                  SettingsSelection.optionMark(isSelected: !autoDetectIsActive))

              VStack(alignment: .leading, spacing: OmiSpacing.xs) {
                Text("Single Language (Better Accuracy)")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.primary)

                Text("Best for speaking in one specific language")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)

                // Language picker (only shown when single language is selected)
                if !autoDetectIsActive {
                  HStack {
                    Text("Language:")
                      .scaledFont(size: OmiType.caption)
                      .foregroundColor(Ink.secondary)

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
                      saveSingleLanguageSelection(option.id)
                      restartTranscriptionIfNeeded()
                    }
                  }
                  .padding(.top, OmiSpacing.xxs)
                }
              }

              Spacer()
            }
            .padding(OmiSpacing.md)
            .background(
              RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                .fill(!autoDetectIsActive ? SettingsSelection.optionFill(isSelected: true) : Color.clear)
                .overlay(
                  RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                    .stroke(SettingsSelection.optionStroke(isSelected: !autoDetectIsActive), lineWidth: 1)
                )
            )
            .contentShape(RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous))
          }
          .buttonStyle(.plain)

          // Info about language support
          HStack(spacing: OmiSpacing.sm) {
            Image(systemName: "info.circle")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)

            Text(
              "Single language mode supports \(AssistantSettings.supportedLanguages.count) languages including Chinese, Ukrainian, Russian, and more."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
          }

          if CloudTranscriptionLanguageHint.isShown(for: selectedLanguage, isAppleSilicon: AppState.isAppleSilicon) {
            CloudTranscriptionLanguageHint()
          }
        }
      }

      // Voice assistant (push-to-talk) languages
      settingsCard(settingId: "transcription.voicelanguages") {
        VoiceAssistantLanguagesCard()
      }

      // Custom Vocabulary
      settingsCard(settingId: "transcription.vocabulary") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "text.book.closed")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Custom Vocabulary")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text("Improve recognition of names, brands, and technical terms")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            }

            Spacer()

            if !vocabularyList.isEmpty {
              Text("\(vocabularyList.count) terms")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
            }
          }

          // Current vocabulary display with removable tags
          if !vocabularyList.isEmpty {
            FlowLayout(spacing: OmiSpacing.xs) {
              ForEach(vocabularyList, id: \.self) { term in
                HStack(spacing: OmiSpacing.xxs) {
                  Text(term)
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)

                  Button(action: {
                    removeVocabularyWord(term)
                  }) {
                    Image(systemName: "xmark")
                      .scaledFont(size: OmiType.micro, weight: .medium)
                      .foregroundColor(Ink.secondary)
                  }
                  .buttonStyle(.plain)
                }
                .padding(.horizontal, OmiSpacing.sm)
                .padding(.vertical, OmiSpacing.xs)
                .background(
                  RoundedRectangle(cornerRadius: SettingsGlassMetrics.pillRadius, style: .continuous)
                    .fill(Ink.hairline)
                )
              }
            }
          }

          GlassSeparator()

          // Add new word input
          HStack(spacing: OmiSpacing.sm) {
            TextField("Add a word…", text: $newVocabularyWord)
              .settingsTextInputStyle()
              .onSubmit {
                addVocabularyWord()
              }

            Button(action: {
              addVocabularyWord()
            }) {
              Image(systemName: "plus.circle.fill")
                .scaledFont(size: OmiType.heading)
                .foregroundColor(
                  newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty
                    ? Ink.secondary : Ink.accent)
            }
            .buttonStyle(.plain)
            .disabled(newVocabularyWord.trimmingCharacters(in: .whitespaces).isEmpty)
          }

          Text("Press Enter or click + to add • Click × to remove")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)

          if let vocabularySaveError {
            Text(vocabularySaveError)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.errorRed)
              .accessibilityIdentifier("vocabulary-save-error")
          }
        }
      }

      // Local VAD Gate
      settingsCard(settingId: "transcription.vadgate") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "waveform.badge.minus")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Local VAD Gate")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text(
                "Skips silent audio before sending it for transcription. Can cut transcription usage by about 40%."
              )
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            Toggle("", isOn: $vadGateEnabled)
              .toggleStyle(OmiToggleStyle())
              .onChange(of: vadGateEnabled) { _, newValue in
                AssistantSettings.shared.vadGateEnabled = newValue
                restartTranscriptionIfNeeded()
              }
          }
        }
      }

      // Silent Type
      settingsCard(settingId: "transcription.silenttype") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "keyboard.badge.eye")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Silent Type")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text("Keeps what you dictate with Omi Type out of the chat.")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            Toggle("", isOn: $shortcutSettings.silentTypeEnabled)
              .toggleStyle(OmiToggleStyle())
          }
        }
      }

      // Ignore dictation apps
      settingsCard(settingId: "transcription.ignoredictationapps") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Image(systemName: "mic.slash")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Ignore Dictation Apps")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text(
                "While Wispr Flow, superwhisper, or macOS Dictation is using the microphone, Omi stops listening so dictations don't become conversations. Calls are never muted."
              )
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            Toggle("", isOn: $shortcutSettings.ambientIgnoresDictationApps)
              .toggleStyle(OmiToggleStyle())
          }
        }
      }

    }
  }

  /// What the transcriber will actually do, as opposed to what the stored flag says.
  ///
  /// `AssistantSettings.effectiveTranscriptionLanguage` only enters multi-language mode when the
  /// selected language is one the provider can auto-detect. This pane used to paint the raw
  /// `transcriptionAutoDetect` flag, so an account left on a language outside that set (Ukrainian,
  /// Chinese, …) with the flag on showed "Auto-Detect" ticked, hid the language picker behind that
  /// tick, and transcribed in the single language anyway — a state you could neither see nor leave.
  var autoDetectIsActive: Bool {
    transcriptionAutoDetect && autoDetectSupported
  }

  /// Mirrors `AssistantSettings.transcriptionLanguageSelection` from this pane's live state.
  var selectedLanguage: STTLanguageCapability.Selection {
    STTLanguageCapability.Selection(
      effective: autoDetectIsActive ? STTLanguageCapability.autoDetect : transcriptionLanguage,
      primary: transcriptionLanguage
    )
  }

  /// Persists a Single-Language selection to the account in the one order that survives a reload.
  ///
  /// See `TranscriptionLanguageWriter` for why the order is the whole point.
  func saveSingleLanguageSelection(_ language: String) {
    AnalyticsManager.shared.languageChanged(language: language)
    Task { @MainActor in
      _ = await TranscriptionLanguageWriter.apply(
        language: language,
        singleLanguageMode: true,
        setLanguage: { code in
          _ = try await APIClient.shared.updateUserLanguage(code)
        },
        setSingleLanguageMode: { mode in
          _ = try await APIClient.shared.updateTranscriptionPreferences(singleLanguageMode: mode)
        }
      )
    }
  }

  /// Add a word to the vocabulary
  func addVocabularyWord() {
    let word = newVocabularyWord.trimmingCharacters(in: .whitespaces)
    guard !word.isEmpty else { return }

    Task { @MainActor in
      // When nothing could be saved, the word stays in the field to try again.
      guard await editVocabulary(.add(word)) else { return }
      // Keep anything typed while the account's list was being read.
      if newVocabularyWord.trimmingCharacters(in: .whitespaces) == word {
        newVocabularyWord = ""
      }
    }
  }

  /// Remove a word from the vocabulary
  func removeVocabularyWord(_ word: String) {
    Task { @MainActor in
      await editVocabulary(.remove(word))
    }
  }

  /// Applies `edit` through `TranscriptionVocabularyWriter`, which reads the account's list first
  /// when this pane's list did not come from it. Returns `false` when nothing could be saved.
  @discardableResult
  func editVocabulary(_ edit: TranscriptionVocabularyWriter.Edit) async -> Bool {
    // One read at a time: an edit made during a read would start from the list that read replaces.
    guard !isReadingVocabulary else { return false }
    isReadingVocabulary = !vocabularyLoadedFromAccount
    defer { isReadingVocabulary = false }

    guard
      let terms = await TranscriptionVocabularyWriter.apply(
        edit,
        to: vocabularyList,
        loadedFromAccount: vocabularyLoadedFromAccount,
        readAccountTerms: { try await APIClient.shared.getTranscriptionPreferences().vocabulary },
        save: { saveVocabulary($0) }
      )
    else { return false }

    vocabularyList = terms
    vocabularyLoadedFromAccount = true
    return true
  }

  /// Save vocabulary to local settings and backend
  func saveVocabulary(_ terms: [String]) {
    // Save to local settings
    AssistantSettings.shared.transcriptionVocabulary = terms

    // Sync to backend
    updateTranscriptionPreferences(vocabulary: terms.joined(separator: ", "))
  }

  /// Restart transcription if currently running to apply new settings
  func restartTranscriptionIfNeeded() {
    Task { @MainActor in
      if await appState.prepareTranscriptionRestartAfterSettingsChange() {
        appState.startTranscription()
      }
    }
  }

  // MARK: - Notifications Section

}

/// The two account writes a transcription-language change needs, in the only order that survives.
///
/// `PATCH /v1/users/language` is not only a language write. The backend follows it with
/// `set_user_transcription_preferences(single_language_mode: not supports_live_multilingual_mode(language))`,
/// and that predicate is true — so `single_language_mode` lands as `false` — for every language this
/// picker offers. The pane used to fire that PATCH and the transcription-preferences PATCH as two
/// unordered `Task`s, so the language write raced the mode the user had just chosen and normally
/// won. The next `loadBackendSettings()`, where the account is the authority for language, then
/// pushed both this pane and `AssistantSettings` back to Auto-Detect: choosing Single Language and
/// a language did not survive reopening Settings.
///
/// Ordering is the repair. The language write goes first precisely because it clobbers the mode;
/// the mode write goes last so the user's choice is what the account ends up holding.
@MainActor
enum TranscriptionLanguageWriter {
  /// Which of the two writes landed. Reported rather than thrown so a half-written change is
  /// visible to the caller instead of disappearing into a detached `Task`.
  struct Outcome: Equatable {
    var languageWritten = false
    var modeWritten = false

    var isComplete: Bool { languageWritten && modeWritten }
  }

  static func apply(
    language: String,
    singleLanguageMode: Bool,
    setLanguage: (String) async throws -> Void,
    setSingleLanguageMode: (Bool) async throws -> Void
  ) async -> Outcome {
    var outcome = Outcome()

    do {
      try await setLanguage(language)
      outcome.languageWritten = true
    } catch {
      logError("Settings: failed to save transcription language", error: error)
      // Fall through deliberately. The language PATCH is the thing that resets the mode, so a
      // failed one leaves the stored mode untouched and re-asserting the user's choice is still
      // the correct next write.
    }

    do {
      try await setSingleLanguageMode(singleLanguageMode)
      outcome.modeWritten = true
    } catch {
      logError("Settings: failed to save transcription language mode", error: error)
    }

    return outcome
  }
}

/// Custom-vocabulary edits, which the account stores as one list.
///
/// `PATCH /v1/users/transcription-preferences` replaces the account's whole vocabulary with the list
/// it is sent. This pane shows the local copy in `AssistantSettings` until `loadBackendSettings()`
/// has read the account's list, and keeps showing it when that load fails. The copy is empty on a
/// new Mac or after a reinstall, and out of date after edits on the phone or the web. Adding a word
/// used to save that copy plus the word, so every other word on the account was gone, without an
/// error; removing a word did the same.
///
/// So an edit starts from a list read from the account: the pane's own once it has loaded,
/// otherwise a fresh read. When that read fails, nothing is saved.
@MainActor
enum TranscriptionVocabularyWriter {
  enum Edit {
    case add(String)
    case remove(String)

    func applied(to terms: [String]) -> [String] {
      switch self {
      case .add(let word):
        // Don't add duplicates (case-insensitive check)
        guard !terms.contains(where: { $0.lowercased() == word.lowercased() }) else { return terms }
        return terms + [word]
      case .remove(let word):
        return terms.filter { $0 != word }
      }
    }
  }

  /// Applies `edit` to the account's list and saves the result when the edit changed it.
  ///
  /// `terms` is the list the pane shows. Unless it was `loadedFromAccount`, the account's list is
  /// read through `readAccountTerms` and the edit applies to that instead. `save` stores a list as
  /// the account's whole vocabulary.
  ///
  /// - Returns: the list after the edit, or `nil` when the account's list could not be read and
  ///   nothing was saved.
  static func apply(
    _ edit: Edit,
    to terms: [String],
    loadedFromAccount: Bool,
    readAccountTerms: () async throws -> [String],
    save: ([String]) -> Void
  ) async -> [String]? {
    var accountTerms = terms
    if !loadedFromAccount {
      do {
        accountTerms = try await readAccountTerms()
      } catch {
        logError("Settings: failed to load custom vocabulary, so the edit was not saved", error: error)
        return nil
      }
    }

    let edited = edit.applied(to: accountTerms)
    if edited != accountTerms {
      save(edited)
    }
    return edited
  }
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
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack {
        Image(systemName: "person.wave.2")
          .scaledFont(size: OmiType.subheading)
          .foregroundColor(Ink.secondary)

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Voice Assistant Languages")
            .scaledFont(size: OmiType.subheading, weight: .medium)
            .foregroundColor(Ink.primary)

          Text(
            "Languages you speak to Omi over push-to-talk — the first is your primary. Omi identifies which one you're speaking each turn."
          )
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        }

        Spacer()
      }

      FlowLayout(spacing: OmiSpacing.xs) {
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
        .scaledFont(size: OmiType.caption, weight: isSelected ? .semibold : .regular)
        .foregroundColor(isSelected ? Ink.surface : Ink.secondary)
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xs)
        .background(
          Capsule().fill(isSelected ? Ink.primary : Color.clear)
            .overlay(Capsule().stroke(Ink.hairline, lineWidth: isSelected ? 0 : 1))
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

/// One-line notice that meetings in the selected language use cloud STT, because no on-device
/// Parakeet model covers it (`STTLanguageCapability`). Intel Macs are always cloud, so no notice.
struct CloudTranscriptionLanguageHint: View {
  nonisolated static func isShown(for language: STTLanguageCapability.Selection, isAppleSilicon: Bool) -> Bool {
    isAppleSilicon && !language.isCoveredOnDevice
  }

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "cloud")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      Text("This language isn't available on-device, so Omi transcribes meetings in the cloud.")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
    }
  }
}

import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// How Omi helps › Listening: the language you speak, words and names to recognize, when a
/// conversation ends, recordings still on the iPhone; the speech model, on-device transcription,
/// Transcribe later and the transcription log sit one level down in Advanced.
struct CaptureSettingsScreen: View {
    @Environment(CaptureStore.self) private var capture
    @Environment(SettingsStore.self) private var settings
    @State private var detectsLanguages = true

    var body: some View {
        @Bindable var capture = capture
        SettingsList {
            Section {
                Picker(selection: Binding(
                    get: { settings.spokenLanguage ?? "en" },
                    set: { code in Task { await settings.setSpokenLanguage(code) } }
                )) {
                    ForEach(settings.languages, id: \.code) { Text($0.name).tag($0.code) }
                } label: {
                    SettingsRowLabel(title: L("nativeSpokenLanguage"), systemImage: "globe")
                }
                .pickerStyle(.navigationLink)
                Toggle(isOn: Binding(
                    get: { detectsLanguages },
                    set: { value in
                        detectsLanguages = value
                        Task { if await !settings.setLanguageDetection(value) { detectsLanguages = !value } }
                    }
                )) {
                    SettingsRowLabel(title: L("nativeDetectLanguages"), systemImage: "character.bubble")
                }
                .accessibilityIdentifier("capture.detectLanguages")
            } footer: {
                Text(L("nativeDetectLanguagesFooter"))
            }
            Section {
                NavigationLink {
                    VocabularyScreen()
                } label: {
                    SettingsRowLabel(
                        title: L("nativeSettingsVocabulary"), systemImage: "text.book.closed",
                        value: settings.vocabulary.isEmpty ? nil : String(settings.vocabulary.count)
                    )
                }
                .accessibilityIdentifier("capture.vocabulary")
                Picker(selection: $capture.conversationTimeout) {
                    ForEach(CaptureStore.conversationTimeouts, id: \.self) { Text(Self.timeoutLabel($0)).tag($0) }
                } label: {
                    SettingsRowLabel(title: L("nativeSettingsEndsAfter"), systemImage: "timer")
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("capture.timeout")
            } footer: {
                Text(L("nativeConversationTimeoutFooter"))
            }
            PhoneRecordingsSection()
            Section {
                NavigationLink {
                    ListeningAdvancedScreen()
                } label: {
                    SettingsRowLabel(title: L("nativeSettingsAdvanced"), systemImage: "slider.horizontal.3")
                }
                .accessibilityIdentifier("capture.advanced")
            }
        }
        .omiPage(L("nativeSettingsListening"))
        .task { await settings.loadVocabulary() }
        .task { await settings.loadLanguages() }
        .task {
            detectsLanguages = settings.detectsLanguages
            detectsLanguages = await settings.loadLanguageDetection()
        }
    }

    static func timeoutLabel(_ seconds: Int) -> String {
        switch seconds {
        case 120: L("timeout2Minutes")
        case 300: L("timeout5Minutes")
        case 600: L("timeout10Minutes")
        case 1800: L("timeout30Minutes")
        case -1: L("timeout4Hours")
        default: Duration.seconds(seconds).formatted(.units(allowed: [.hours, .minutes], width: .wide))
        }
    }
}

/// Listening › Advanced: which speech model the server uses, transcribing on the iPhone instead,
/// Transcribe later, and the transcription log.
struct ListeningAdvancedScreen: View {
    @Environment(CaptureStore.self) private var capture

    var body: some View {
        @Bindable var capture = capture
        SettingsList {
            Section {
                Picker(L("nativeSpeechModel"), selection: $capture.usesParakeet) {
                    Text(L("nativeSpeechModelOmi")).tag(false)
                    Text(L("nativeSpeechModelParakeet")).tag(true)
                }
                .pickerStyle(.menu)
                .disabled(capture.isLive || capture.transcribesOnDevice)
                Toggle(L("nativeOnDeviceTranscription"), isOn: $capture.transcribesOnDevice)
                    .disabled(capture.isLive)
            } footer: {
                Text(L("nativeOnDeviceTranscriptionFooter") + " " + L("nativeSpeechModelFooter"))
            }
            Section {
                Toggle(L("nativeTranscribeLater"), isOn: $capture.transcribesLater)
                    .disabled(capture.isLive)
                    .accessibilityIdentifier("capture.transcribeLater")
            } footer: {
                Text(L("nativeTranscribeLaterFooter"))
            }
            Section {
                NavigationLink(L("nativeAdvancedTranscription")) { AdvancedTranscriptionScreen() }
                    .accessibilityIdentifier("capture.advancedTranscription")
                NavigationLink(L("nativeTranscriptionLog")) { DebugLogScreen(source: "stt") }
            } footer: {
                Text(L("nativeTranscriptionLogFooter"))
            }
        }
        .omiPage(L("nativeSettingsAdvanced"))
    }
}

/// Listening › Words and names: the words Omi should recognize; add on top, swipe to remove.
struct VocabularyScreen: View {
    @Environment(SettingsStore.self) private var settings
    @State private var newWord = ""

    var body: some View {
        SettingsList {
            Section {
                HStack {
                    TextField(L("nativeAddWord"), text: $newWord)
                        .submitLabel(.done)
                        .onSubmit(add)
                    if !newWord.trimmingCharacters(in: .whitespaces).isEmpty {
                        Button(L("nativeAdd"), action: add).fontWeight(.semibold)
                    }
                }
            } footer: {
                Text(L("nativeVocabularyFooter"))
            }
            if !settings.vocabulary.isEmpty {
                Section {
                    ForEach(settings.vocabulary, id: \.self) { Text($0) }
                        .onDelete { offsets in Task { await settings.removeWords(at: offsets) } }
                }
            }
        }
        .omiPage(L("nativeSettingsVocabulary"))
        .task { await settings.loadVocabulary() }
    }

    private func add() {
        let word = newWord
        newWord = ""
        Task { await settings.addWord(word) }
    }
}

/// Recordings the phone's microphone kept (offline, or Transcribe later) that the backend does not
/// have yet: play, share, process now, delete.
private struct PhoneRecordingsSection: View {
    @Environment(SyncStore.self) private var sync
    @State private var player = AudioClipPlayer()

    var body: some View {
        if !sync.phoneRecordings.isEmpty {
            Section {
                ForEach(sync.phoneRecordings, id: \.filename) { recording in
                    PendingRecordingRow(recording: recording, player: player)
                }
                .onDelete { offsets in
                    for filename in offsets.map({ sync.phoneRecordings[$0].filename }) {
                        sync.delete(filename)
                    }
                }
            } header: {
                SettingsHeader(L("nativeRecordingsOnPhone"))
            } footer: {
                Text(L("nativeRecordingsOnPhoneFooter"))
            }
            .onDisappear { player.stop() }
        }
    }
}

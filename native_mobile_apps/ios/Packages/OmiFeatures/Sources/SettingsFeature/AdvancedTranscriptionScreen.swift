import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Listening › Advanced transcription (Flutter `transcription_settings_page`, "Cloud provider"):
/// your own speech-to-text service with its key, model, language and endpoint. Omi is the
/// default; the iPhone's own recognizer stays the switch in Listening (on iOS Flutter uses Apple
/// speech there too, so there is no Whisper model to download).
struct AdvancedTranscriptionScreen: View {
    @Environment(CustomSTTSettings.self) private var customSTT
    @Environment(SettingsStore.self) private var settings
    @Environment(CaptureStore.self) private var capture
    @State private var provider: CustomSTTProvider?
    @State private var apiKey = ""
    @State private var model = ""
    @State private var language = ""
    @State private var url = ""
    @State private var showsKey = false
    @State private var notice: String?

    var body: some View {
        List {
            Section {
                Picker(L("provider"), selection: $provider) {
                    Text(L("transcriptionSourceOmi")).tag(CustomSTTProvider?.none)
                    ForEach(CustomSTTProvider.allCases, id: \.self) { Text($0.displayName).tag(CustomSTTProvider?.some($0)) }
                }
                .pickerStyle(.navigationLink)
                .accessibilityIdentifier("customStt.provider")
            } footer: {
                Text(provider == nil ? L("speechToTextProviderDesc") : L("payYourSttProvider") + " " + L("nativeCustomSttFooter"))
            }
            if let provider {
                providerSection(provider)
            }
            Section {
                LabeledContent(L("onDeviceTranscription"), value: L("usingNativeIosSpeech"))
            } footer: {
                Text(L("nativeEngineNoDownload"))
            }
        }
        .omiPage(L("nativeAdvancedTranscription"))
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button(L("save"), action: save)
                    .disabled(capture.isLive || !hasChanges)
                    .accessibilityIdentifier("customStt.save")
            }
        }
        .alert(notice ?? "", isPresented: Binding(get: { notice != nil }, set: { if !$0 { notice = nil } })) {
            Button(L("ok"), role: .cancel) {}
        }
        .task { await settings.loadLanguages() }
        .onAppear(perform: fill)
    }

    @ViewBuilder
    private func providerSection(_ provider: CustomSTTProvider) -> some View {
        Section {
            if provider.requiresAPIKey {
                HStack {
                    Group {
                        if showsKey { TextField(L("enterApiKey"), text: $apiKey) } else { SecureField(L("enterApiKey"), text: $apiKey) }
                    }
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .textContentType(.password)
                    .accessibilityIdentifier("customStt.apiKey")
                    Button { showsKey.toggle() } label: { Image(systemName: showsKey ? "eye.slash" : "eye") }
                        .buttonStyle(.borderless)
                        .accessibilityLabel(showsKey ? L("hideApiKey") : L("showApiKey"))
                }
                if let link = provider.apiKeyURL { Link(L("getApiKey"), destination: link) }
            }
            if provider.takesURL {
                TextField(provider.defaultURL ?? L("endpointUrl"), text: $url)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("customStt.url")
            }
            if provider.models.count > 1 {
                Picker(L("model"), selection: $model) {
                    ForEach(provider.models, id: \.self) { Text($0).tag($0) }
                }
            } else if let only = provider.models.first {
                LabeledContent(L("model"), value: only)
            }
            Picker(L("transcriptionLanguage"), selection: $language) {
                Text(L("sttFilterAuto")).tag("multi")
                ForEach(settings.languages, id: \.code) { Text($0.name).tag($0.code) }
            }
            .pickerStyle(.navigationLink)
        } header: {
            SettingsHeader(provider.displayName)
        }
    }

    private var draft: CustomSTTConfig? {
        let key = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedKey: String? = key.isEmpty ? nil : key
        let trimmedURL = url.trimmingCharacters(in: .whitespacesAndNewlines)
        return provider.map {
            CustomSTTConfig(
                provider: $0, apiKey: $0.requiresAPIKey ? trimmedKey : nil,
                model: model.isEmpty ? nil : model, language: language,
                url: $0.takesURL && !trimmedURL.isEmpty ? trimmedURL : nil
            )
        }
    }

    private var hasChanges: Bool {
        draft != customSTT.config
    }

    private func fill() {
        let config = customSTT.config
        provider = config?.provider
        apiKey = config?.apiKey ?? ""
        model = config?.model ?? ""
        language = config?.effectiveLanguage ?? "multi"
        url = config?.url ?? ""
    }

    private func save() {
        if let draft, !draft.isComplete {
            notice = draft.provider.requiresAPIKey && draft.apiKey?.isEmpty != false ? L("apiKeyRequired") : L("nativeCustomSttInvalidUrl")
            return
        }
        customSTT.save(draft)
        notice = L("saved")
    }
}

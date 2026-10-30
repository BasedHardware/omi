import Foundation
import Observation
import OmiNetwork
import OmiPersistence

/// Settings › Listening › Advanced transcription: which speech-to-text service the phone uses
/// (Flutter `transcription_settings_page`). Off means Omi transcribes. The provider, model,
/// language and endpoint stay under Flutter's `customSttConfig` key; the API key goes to the
/// Keychain, and a key the Flutter app had saved in its JSON moves there on first read.
@MainActor
@Observable
public final class CustomSTTSettings {
    /// The saved provider; nil when Omi (or the iPhone) transcribes.
    public private(set) var config: CustomSTTConfig?

    private let preferences: Preferences
    private let secrets: any SecretStore
    static let keyName = "customStt.apiKey"

    public init(preferences: Preferences, secrets: any SecretStore) {
        self.preferences = preferences
        self.secrets = secrets
        config = load()
    }

    /// A provider is chosen and ready to receive audio.
    public var isActive: Bool {
        config?.isComplete == true
    }

    /// Saves the setup (the key to the Keychain). `nil` goes back to Omi's transcription.
    public func save(_ config: CustomSTTConfig?) {
        guard let config else {
            preferences.set(nil as String?, for: .customSttConfig)
            secrets.setSecret(nil, for: Self.keyName)
            self.config = nil
            return
        }
        let trimmedKey = config.apiKey?.trimmingCharacters(in: .whitespacesAndNewlines)
        secrets.setSecret(config.provider.requiresAPIKey ? trimmedKey : nil, for: Self.keyName)
        preferences.set(Self.json(config), for: .customSttConfig)
        var saved = config
        saved.apiKey = config.provider.requiresAPIKey ? trimmedKey : nil
        self.config = saved
    }

    /// Reads Flutter's JSON. Providers native does not run (Gemini, on-device Whisper, custom live)
    /// read as off; Flutter's on-device choice is the iPhone's own recognizer here.
    private func load() -> CustomSTTConfig? {
        guard let text = preferences.string(.customSttConfig),
              let object = (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [String: Any]
        else {
            // Signed out (preferences cleared): the key goes too.
            secrets.setSecret(nil, for: Self.keyName)
            return nil
        }
        let flutterKey = (object["api_key"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        if object["provider"] as? String == "onDeviceWhisper" {
            preferences.set(true, for: .onDeviceTranscription)
        }
        guard let provider = (object["provider"] as? String).flatMap(CustomSTTProvider.init(rawValue:)) else {
            if flutterKey != nil { preferences.set(nil as String?, for: .customSttConfig) }
            return nil
        }
        var config = CustomSTTConfig(
            provider: provider, model: object["model"] as? String, language: object["language"] as? String,
            url: object["url"] as? String
        )
        if let flutterKey {
            // Out of UserDefaults for good: the JSON is rewritten without it (and without headers holding it).
            secrets.setSecret(flutterKey, for: Self.keyName)
            preferences.set(Self.json(config), for: .customSttConfig)
        }
        config.apiKey = provider.requiresAPIKey ? secrets.secret(Self.keyName) : nil
        return config
    }

    /// Flutter's field names, no secrets.
    static func json(_ config: CustomSTTConfig) -> String? {
        var object: [String: Any] = ["provider": config.provider.rawValue, "send_raw_audio_to_omi": true]
        if let model = config.model, !model.isEmpty { object["model"] = model }
        if let language = config.language, !language.isEmpty { object["language"] = language }
        if config.provider.takesURL, let url = config.url, !url.isEmpty { object["url"] = url }
        if config.provider.isLive { object["request_type"] = "streaming" }
        return (try? JSONSerialization.data(withJSONObject: object, options: .sortedKeys)).flatMap { String(data: $0, encoding: .utf8) }
    }
}

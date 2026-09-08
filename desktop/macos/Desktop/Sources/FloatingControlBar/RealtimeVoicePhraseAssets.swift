import Foundation

/// The exact native realtime voice for which a shipped acknowledgement clip was generated.
///
/// This is intentionally separate from `ShortcutSettings.VoiceOption`: that picker controls the
/// legacy/batch TTS output, while these clips bridge the native realtime provider's voice during a
/// slow-tool handoff. Keeping the two identities distinct prevents a Shimmer clip from being
/// played in a Gemini/Charon turn.
enum RealtimeVoicePhraseProfile: String, CaseIterable, Sendable {
  case geminiCharon = "gemini-charon"
  case openAICedar = "openai-cedar"

  init(provider: RealtimeHubProvider) {
    switch provider {
    case .gemini: self = .geminiCharon
    case .openai: self = .openAICedar
    }
  }

  var provider: RealtimeHubProvider {
    switch self {
    case .geminiCharon: return .gemini
    case .openAICedar: return .openai
    }
  }

  /// The provider's exact voice spelling, as sent in the realtime session payload.
  var voiceName: String {
    RealtimeHubVoicePolicy.voiceName(for: provider)
  }

  /// The resource prefix used by the generation script and runtime locator. Derive the voice part
  /// from `RealtimeHubVoicePolicy` so a provider voice change cannot silently reuse stale audio.
  var resourcePrefix: String { "\(provider.rawValue)-\(voiceName.lowercased())" }
}

/// A deterministic identity for one generated realtime acknowledgement clip.
struct RealtimeVoicePhraseAsset: Equatable, Sendable {
  let profile: RealtimeVoicePhraseProfile
  let kind: RealtimeSlowToolAcknowledgementKind
  let phrase: String

  /// Files are deliberately flat under `Resources/VoicePhrases`. SwiftPM may flatten processed
  /// resource subdirectories, so the complete identity belongs in the filename itself.
  var fileName: String {
    "\(profile.resourcePrefix)-\(kind.rawValue)-\(Self.slug(phrase)).wav"
  }

  static func slug(_ phrase: String) -> String {
    var result = ""
    var needsSeparator = false

    for scalar in phrase.lowercased().unicodeScalars {
      if scalar.value >= 97 && scalar.value <= 122 || scalar.value >= 48 && scalar.value <= 57 {
        if needsSeparator, !result.isEmpty { result.append("-") }
        needsSeparator = false
        result.append(Character(scalar))
      } else if scalar.value == 39 || scalar.value == 8217 {
        // Keep contractions together: "I'll" becomes "ill", matching the generator script.
        continue
      } else {
        needsSeparator = true
      }
    }

    return result
  }
}

/// Locates provider-keyed, pre-recorded acknowledgement clips in the app's processed resources.
///
/// `Package.swift` processes the complete `Resources` directory. Depending on whether the caller
/// is an installed app, a SwiftPM test host, or a local executable, the resource bundle may expose
/// `VoicePhrases/` as a directory or flatten its contents next to the bundle. Search both forms;
/// a missing clip is a normal fallback condition, never a launch failure.
struct RealtimeVoicePhraseAssetLocator: Sendable {
  /// Searched in order; the first readable match wins.
  let roots: [URL]

  func url(
    for provider: RealtimeHubProvider,
    kind: RealtimeSlowToolAcknowledgementKind,
    phrase: String
  ) -> URL? {
    url(
      for: RealtimeVoicePhraseAsset(profile: RealtimeVoicePhraseProfile(provider: provider), kind: kind, phrase: phrase)
    )
  }

  func url(for asset: RealtimeVoicePhraseAsset) -> URL? {
    for root in roots {
      let candidates = [
        root.appendingPathComponent(asset.fileName),
        root.appendingPathComponent("VoicePhrases", isDirectory: true)
          .appendingPathComponent(asset.fileName),
      ]
      for candidate in candidates where FileManager.default.isReadableFile(atPath: candidate.path) {
        return candidate
      }
    }
    return nil
  }

  /// Every place an installed app, local build, or SwiftPM test host can expose processed assets.
  static let bundled = RealtimeVoicePhraseAssetLocator(roots: bundledRoots())

  static func bundledRoots() -> [URL] {
    let main = Bundle.main.bundleURL
    let containers: [URL] = [
      Bundle.main.resourceURL,
      main.appendingPathComponent("Contents/Resources"),
      main,
      main.deletingLastPathComponent(),
    ].compactMap { $0 }

    var roots: [URL] = []
    var seen = Set<String>()
    func add(_ url: URL) {
      guard seen.insert(url.standardizedFileURL.path).inserted else { return }
      roots.append(url)
    }

    for container in containers {
      add(container)
      add(container.appendingPathComponent("VoicePhrases", isDirectory: true))

      let contents =
        (try? FileManager.default.contentsOfDirectory(at: container, includingPropertiesForKeys: nil)) ?? []
      for bundle in contents where bundle.pathExtension == "bundle" {
        add(bundle)
        add(bundle.appendingPathComponent("VoicePhrases", isDirectory: true))
        add(bundle.appendingPathComponent("Contents/Resources"))
        add(bundle.appendingPathComponent("Contents/Resources/VoicePhrases", isDirectory: true))
      }
    }
    return roots
  }
}

/// Production selection policy for slow-tool acknowledgements. Keeping the
/// resource read behind this small seam makes the bundled-first guarantee and
/// malformed-asset fallback directly testable without driving AVFoundation.
enum RealtimeVoicePhraseAudioSelection: Equatable, Sendable {
  case bundled(Data)
  case fallback

  static func select(
    provider: RealtimeHubProvider,
    kind: RealtimeSlowToolAcknowledgementKind,
    phrase: String,
    locator: RealtimeVoicePhraseAssetLocator = .bundled,
    load: (URL) throws -> Data = { try Data(contentsOf: $0) }
  ) -> Self {
    guard let url = locator.url(for: provider, kind: kind, phrase: phrase),
      let data = try? load(url),
      data.count > 44,
      String(data: data.prefix(4), encoding: .ascii) == "RIFF",
      String(data: data.dropFirst(8).prefix(4), encoding: .ascii) == "WAVE"
    else { return .fallback }
    return .bundled(data)
  }
}

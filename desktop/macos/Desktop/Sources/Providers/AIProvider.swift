import Foundation

/// Describes an AI provider available for desktop chat.
/// Each provider maps to a `BridgeMode` in ChatProvider and drives
/// the Settings UI (picker label, logo, attribution line).
struct AIProvider: Identifiable {
  let id: String
  /// Human-readable name shown in the picker.
  let displayName: String
  /// Short attribution line shown below the picker.
  let tagline: String
  /// Optional URL for the project (opens in browser on click).
  let attributionURL: URL?
  /// SF Symbol name used as inline logo.
  let sfSymbol: String
  /// Optional bundle resource name for a custom logo PNG.
  /// When non-nil, the resource is loaded from `Bundle.resourceBundle`.
  let logoResource: String?
  /// The raw value stored in UserDefaults `chatBridgeMode`.
  let bridgeModeRawValue: String

  // MARK: - Built-in providers

  static let piMono = AIProvider(
    id: "piMono",
    displayName: "Omi AI",
    tagline: "Built-in AI assistant (built with pi.dev)",
    attributionURL: nil,
    sfSymbol: "",
    logoResource: nil,
    bridgeModeRawValue: "piMono"
  )

  static let claude = AIProvider(
    id: "claude",
    displayName: "Claude",
    tagline: "Your Claude Pro/Max subscription",
    attributionURL: URL(string: "https://claude.ai"),
    sfSymbol: "",
    logoResource: nil,
    bridgeModeRawValue: "claudeCode"
  )

  static let all: [AIProvider] = [.piMono, .claude]

  /// Look up a provider by its `chatBridgeMode` raw value.
  static func from(bridgeMode: String) -> AIProvider? {
    all.first { $0.bridgeModeRawValue == bridgeMode }
  }
}

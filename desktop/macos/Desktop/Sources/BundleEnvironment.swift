import Foundation

/// Loads bundle `.env` into the process environment before Firebase/auth bootstrap.
enum BundleEnvironment {
  private nonisolated(unsafe) static var didLoad = false
  /// A shipped stable or Beta bundle may take its serving endpoints from the
  /// channel contract, but its Firebase identity is signed into the bundle.
  /// Host .env/launch settings are never an authority for that identity.
  private static let productionFirebaseOverrideKeys: Set<String> = [
    "FIREBASE_API_KEY",
    "FIREBASE_AUTH_EMULATOR_HOST",
    "FIREBASE_PROJECT_ID",
    "OMI_DESKTOP_LOCAL_PROFILE",
  ]
  /// Capture process-provided values before any bundled environment file is
  /// applied. This makes explicit `open`/launchd overrides authoritative while
  /// retaining the existing merge order between bundled, working-directory,
  /// and user environment files.
  private static let launchEnvironment = ProcessInfo.processInfo.environment

  static func shouldApplyBundledValue(
    for key: String,
    launchEnvironment: [String: String] = BundleEnvironment.launchEnvironment,
    bundleIdentifier: String? = AppBuild.bundleIdentifier
  ) -> Bool {
    guard !isProductionFirebaseOverride(key, bundleIdentifier: bundleIdentifier) else { return false }
    let launchValue = launchEnvironment[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return launchValue.isEmpty
  }

  static func isProductionFirebaseOverride(_ key: String, bundleIdentifier: String?) -> Bool {
    guard let bundleIdentifier else { return false }
    return AppBuild.productionFamilyBundleIdentifiers.contains(bundleIdentifier)
      && productionFirebaseOverrideKeys.contains(key)
  }

  static func normalizedKey(from assignmentKey: String) -> String? {
    var key = assignmentKey.trimmingCharacters(in: .whitespaces)
    guard key != "export" else { return nil }
    if key.hasPrefix("export ") {
      key = String(key.dropFirst("export ".count)).trimmingCharacters(in: .whitespaces)
    }
    return key.isEmpty ? nil : key
  }

  static func loadIfNeeded() {
    guard !didLoad else { return }
    didLoad = true

    // Clear inherited launchd/shell values before reading any local file. The
    // Beta artifact intentionally uses development serving endpoints, but it
    // shares stable's Firebase Auth and Firestore identity.
    for key in productionFirebaseOverrideKeys
    where isProductionFirebaseOverride(key, bundleIdentifier: AppBuild.bundleIdentifier) {
      unsetenv(key)
    }

    let envPaths = [
      Bundle.main.path(forResource: ".env", ofType: nil),
      FileManager.default.currentDirectoryPath + "/.env",
      NSHomeDirectory() + "/.omi.env",
    ].compactMap { $0 }

    for path in envPaths {
      guard let contents = try? String(contentsOfFile: path, encoding: .utf8) else { continue }
      log("Loading environment from: \(path)")
      for line in contents.components(separatedBy: .newlines) {
        let parts = line.split(separator: "=", maxSplits: 1)
        guard parts.count == 2 else { continue }
        guard let key = normalizedKey(from: String(parts[0])) else { continue }
        guard !key.hasPrefix("#") else { continue }
        let backendServedKeys = ["GEMINI_API_KEY", "GOOGLE_CALENDAR_API_KEY"]
        if backendServedKeys.contains(key) {
          log("  Skipped \(key) (fetched from backend via APIKeyService)")
          continue
        }
        guard shouldApplyBundledValue(for: key) else {
          log("  Skipped \(key) (explicit launch environment override)")
          continue
        }
        let value = String(parts[1]).trimmingCharacters(in: .whitespaces)
          .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
        setenv(key, value, 1)
        if key.contains("API_KEY") || key.contains("KEY") {
          log("  Set \(key)=***")
        }
      }
    }

    DesktopBackendEnvironment.applyReleaseChannelDefaults()
    log("Environment loaded (API keys will be fetched from backend after auth)")
  }
}

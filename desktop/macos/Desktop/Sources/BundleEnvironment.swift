import Foundation

/// Loads bundle `.env` into the process environment before Firebase/auth bootstrap.
enum BundleEnvironment {
  private static var didLoad = false
  /// Capture process-provided values before any bundled environment file is
  /// applied. This makes explicit `open`/launchd overrides authoritative while
  /// retaining the existing merge order between bundled, working-directory,
  /// and user environment files.
  private static let launchEnvironment = ProcessInfo.processInfo.environment

  static func shouldApplyBundledValue(
    for key: String,
    launchEnvironment: [String: String] = BundleEnvironment.launchEnvironment
  ) -> Bool {
    let launchValue = launchEnvironment[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return launchValue.isEmpty
  }

  static func loadIfNeeded() {
    guard !didLoad else { return }
    didLoad = true

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
        let key = String(parts[0]).trimmingCharacters(in: .whitespaces)
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

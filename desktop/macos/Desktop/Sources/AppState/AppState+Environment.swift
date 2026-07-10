import AVFoundation
import Combine
import SwiftUI
import UserNotifications

@MainActor
extension AppState {
  func loadEnvironment() {
    // Try to load from .env file in various locations
    let envPaths = [
      Bundle.main.path(forResource: ".env", ofType: nil),
      FileManager.default.currentDirectoryPath + "/.env",
      NSHomeDirectory() + "/.omi.env",
    ].compactMap { $0 }

    for path in envPaths {
      if let contents = try? String(contentsOfFile: path, encoding: .utf8) {
        log("Loading environment from: \(path)")
        for line in contents.components(separatedBy: .newlines) {
          let parts = line.split(separator: "=", maxSplits: 1)
          if parts.count == 2 {
            var key = String(parts[0]).trimmingCharacters(in: .whitespaces)
            // Skip comments
            guard !key.hasPrefix("#") else { continue }
            if key.hasPrefix("export ") {
              key = String(key.dropFirst("export ".count)).trimmingCharacters(in: .whitespaces)
            }
            // API keys are fetched from the backend at runtime (APIKeyService).
            // Do NOT load them from .env — defer entirely to APIKeyService.fetchKeys().
            let backendServedKeys = ["GEMINI_API_KEY", "GOOGLE_CALENDAR_API_KEY"]
            if backendServedKeys.contains(key) {
              log("  Skipped \(key) (fetched from backend via APIKeyService)")
              continue
            }
            let value = String(parts[1]).trimmingCharacters(in: .whitespaces)
              .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            setenv(key, value, 1)
            // Log key names (not values for security)
            if key.contains("API_KEY") || key.contains("KEY") {
              log("  Set \(key)=***")
            }
          }
        }
        // Don't break - load all .env files to merge keys
      }
    }

    DesktopBackendEnvironment.applyReleaseChannelDefaults()

    log("Environment loaded (API keys will be fetched from backend after auth)")
  }

}

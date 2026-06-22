import Foundation

/// Runtime switches for the harness-owned Omi Dev Local desktop profile.
///
/// Production, beta, and the default Omi Dev bundle keep their existing bundle
/// identifiers, preferences domains, Firebase config, and storage paths.  The
/// local profile is activated only by the generated launch environment from
/// `make desktop-run-local USER=<profile>` and uses a named non-production bundle
/// (`com.omi.omi-local-v17`) plus separate Application Support/Caches roots.
enum DesktopLocalProfile {
  static var isEnabled: Bool {
    value("OMI_DESKTOP_LOCAL_PROFILE") == "1"
  }

  static var storageDirectoryName: String {
    guard isEnabled else { return "Omi" }
    return nonEmpty(value("OMI_LOCAL_PROFILE_STORAGE_NAME")) ?? "Omi Dev Local"
  }

  static var authEmulatorHost: String? {
    guard isEnabled else { return nil }
    return nonEmpty(value("FIREBASE_AUTH_EMULATOR_HOST"))
  }

  static var selectedUser: String? { nonEmpty(value("OMI_LOCAL_AUTH_USER")) }
  static var selectedEmail: String? { nonEmpty(value("OMI_LOCAL_AUTH_EMAIL")) }
  static var selectedPassword: String? { nonEmpty(value("OMI_LOCAL_AUTH_PASSWORD")) }
  static var selectedDisplayName: String? { nonEmpty(value("OMI_LOCAL_AUTH_DISPLAY_NAME")) }

  static func applicationSupportURL() -> URL {
    let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    return base.appendingPathComponent(storageDirectoryName, isDirectory: true)
  }

  static func cachesURL() -> URL {
    let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
    return base.appendingPathComponent(storageDirectoryName, isDirectory: true)
  }

  private static func value(_ key: String) -> String? {
    guard let raw = getenv(key), let value = String(validatingUTF8: raw) else { return nil }
    return value.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private static func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }
}

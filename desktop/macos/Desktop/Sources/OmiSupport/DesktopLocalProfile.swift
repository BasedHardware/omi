import Foundation

/// Runtime switches for the harness-owned Omi Dev local profile.
///
/// Production and beta keep their existing bundle identifiers. The local harness
/// reuses the default ``Omi Dev`` bundle (`com.omi.desktop-dev`) so macOS
/// permissions and storage paths are preserved; only API endpoints and Firebase
/// Auth switch to localhost emulators when ``OMI_DESKTOP_LOCAL_PROFILE=1``.
package enum DesktopLocalProfile {
  package static var isEnabled: Bool {
    value("OMI_DESKTOP_LOCAL_PROFILE") == "1"
  }

  package static var storageDirectoryName: String {
    guard isEnabled else { return "Omi" }
    return nonEmpty(value("OMI_LOCAL_PROFILE_STORAGE_NAME")) ?? "Omi"
  }

  package static var authEmulatorHost: String? {
    guard isEnabled else { return nil }
    return nonEmpty(value("FIREBASE_AUTH_EMULATOR_HOST"))
  }

  package static var selectedUser: String? { nonEmpty(value("OMI_LOCAL_AUTH_USER")) }
  package static var selectedEmail: String? { nonEmpty(value("OMI_LOCAL_AUTH_EMAIL")) }
  package static var selectedPassword: String? { nonEmpty(value("OMI_LOCAL_AUTH_PASSWORD")) }
  package static var selectedDisplayName: String? { nonEmpty(value("OMI_LOCAL_AUTH_DISPLAY_NAME")) }

  package static func applicationSupportURL() -> URL {
    let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    return base.appendingPathComponent(storageDirectoryName, isDirectory: true)
  }

  package static func cachesURL() -> URL {
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

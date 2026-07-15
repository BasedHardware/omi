import Foundation

/// Runtime switches for the harness-owned Omi Dev local profile.
///
/// Production and beta keep their existing bundle identifiers and storage paths.
/// The default Omi Dev bundle (`com.omi.desktop-dev`) also retains the established
/// Omi storage root. Every other named development bundle gets a dedicated root,
/// so parallel QA bundles cannot race one another against the same SQLite/WAL files.
package enum DesktopLocalProfile {
  package static var isEnabled: Bool {
    value("OMI_DESKTOP_LOCAL_PROFILE") == "1"
  }

  package static var storageDirectoryName: String {
    storageDirectoryName(
      bundleIdentifier: Bundle.main.bundleIdentifier,
      localProfileEnabled: isEnabled,
      localProfileStorageName: nonEmpty(value("OMI_LOCAL_PROFILE_STORAGE_NAME")))
  }

  /// Resolves the app-support directory name without reading process state so the
  /// production, Omi Dev, local-profile, and named-bundle boundaries stay testable.
  package static func storageDirectoryName(
    bundleIdentifier: String?,
    localProfileEnabled: Bool,
    localProfileStorageName: String?
  ) -> String {
    if localProfileEnabled {
      return localProfileStorageName ?? "Omi"
    }

    guard let bundleIdentifier, isNamedDevelopmentBundle(bundleIdentifier) else {
      return "Omi"
    }
    return "Omi-\(sanitizeForDirectoryName(bundleIdentifier))"
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

  private static func isNamedDevelopmentBundle(_ bundleIdentifier: String) -> Bool {
    bundleIdentifier.hasPrefix("com.omi.")
      && bundleIdentifier != "com.omi.computer-macos"
      && bundleIdentifier != "com.omi.desktop-dev"
  }

  private static func sanitizeForDirectoryName(_ value: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: ".-_"))
    return String(value.unicodeScalars.map { allowed.contains($0) ? Character($0) : "_" })
  }
}

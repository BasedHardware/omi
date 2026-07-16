import Foundation

/// The identity-derived storage boundary for a running desktop bundle.
///
/// A regular named development build gets a separate root regardless of how it
/// was launched. This is deliberately derived from the signed bundle ID instead
/// of a launcher environment variable: macOS can reopen an installed app without
/// `run.sh`, and that relaunch must remain isolated.
package struct DesktopStorageIdentity: Equatable {
  package static let namedDevelopmentBundlePrefix = "com.omi.omi-"

  package let bundleIdentifier: String?
  package let localProfileEnabled: Bool
  package let localProfileStorageName: String?

  package init(
    bundleIdentifier: String?,
    localProfileEnabled: Bool,
    localProfileStorageName: String?
  ) {
    self.bundleIdentifier = bundleIdentifier
    self.localProfileEnabled = localProfileEnabled
    self.localProfileStorageName = localProfileStorageName
  }

  package var isNamedDevelopmentBundle: Bool {
    guard let bundleIdentifier else { return false }
    guard bundleIdentifier.hasPrefix(Self.namedDevelopmentBundlePrefix) else { return false }
    let suffix = bundleIdentifier.dropFirst(Self.namedDevelopmentBundlePrefix.count)
    guard !suffix.isEmpty else { return false }
    return suffix.unicodeScalars.allSatisfy { scalar in
      switch scalar.value {
      case 48...57, 65...90, 97...122, 45, 46:
        true
      default:
        false
      }
    }
  }

  package var usesIsolatedStorage: Bool {
    localProfileEnabled || isNamedDevelopmentBundle
  }

  package var applicationSupportPathComponents: [String] {
    if let bundleIdentifier, isNamedDevelopmentBundle {
      return ["Omi Dev Bundles", bundleIdentifier]
    }
    if localProfileEnabled {
      return [localProfileStorageName ?? "Omi"]
    }
    return ["Omi"]
  }
}

/// Runtime switches for the harness-owned Omi Dev local profile and named
/// development bundle storage. Production, beta, and canonical Omi Dev preserve
/// their existing shared storage roots.
package enum DesktopLocalProfile {
  package static var isEnabled: Bool {
    value("OMI_DESKTOP_LOCAL_PROFILE") == "1"
  }

  package static var storageDirectoryName: String {
    storageIdentity.applicationSupportPathComponents.joined(separator: "/")
  }

  package static var usesIsolatedStorage: Bool { storageIdentity.usesIsolatedStorage }
  package static var isNamedDevelopmentBundle: Bool { storageIdentity.isNamedDevelopmentBundle }

  package static var storageIdentity: DesktopStorageIdentity {
    DesktopStorageIdentity(
      bundleIdentifier: Bundle.main.bundleIdentifier,
      localProfileEnabled: isEnabled,
      localProfileStorageName: nonEmpty(value("OMI_LOCAL_PROFILE_STORAGE_NAME"))
    )
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
    return storageIdentity.applicationSupportPathComponents.reduce(base) {
      $0.appendingPathComponent($1, isDirectory: true)
    }
  }

  package static func cachesURL() -> URL {
    let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
    return storageIdentity.applicationSupportPathComponents.reduce(base) {
      $0.appendingPathComponent($1, isDirectory: true)
    }
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

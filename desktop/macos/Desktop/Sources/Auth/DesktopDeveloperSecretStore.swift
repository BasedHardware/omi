import Foundation
import OmiSupport

/// File-backed secret store for non-production desktop bundles.
///
/// Production-family apps keep using the login keychain. Developer bundles (Omi Dev,
/// named `omi-*` apps, ad-hoc / Apple Development local builds) persist the same
/// service/account strings in a JSON file so rebuilds never prompt SecurityAgent.
///
/// Layout:
/// `~/Library/Application Support/<DesktopLocalProfile.storageDirectoryName>/developer-secrets/<bundle-id>.json`.
/// Omi Dev shares the `Omi` Application Support root with stable, so the file is keyed
/// by bundle id. Keys are `service + NUL + account` (`"\u{0}"`).
final class DesktopDeveloperSecretStore: @unchecked Sendable {
  static let shared = DesktopDeveloperSecretStore()

  static let directoryName = "developer-secrets"
  static let keySeparator = "\u{0}"

  private let lock = NSLock()
  private let fileManager: FileManager
  private let rootDirectoryOverride: URL?
  private let bundleIdentifierOverride: String?
  private var cache: [String: String]?
  private var didLogUnreadableFile = false

  init(
    rootDirectory: URL? = nil,
    bundleIdentifier: String? = nil,
    fileManager: FileManager = .default
  ) {
    self.rootDirectoryOverride = rootDirectory
    self.bundleIdentifierOverride = bundleIdentifier
    self.fileManager = fileManager
  }

  static func storageKey(service: String, account: String) -> String {
    "\(service)\(keySeparator)\(account)"
  }

  static func fileURL(rootDirectory: URL, bundleIdentifier: String) -> URL {
    rootDirectory
      .appendingPathComponent(directoryName, isDirectory: true)
      .appendingPathComponent("\(bundleIdentifier).json", isDirectory: false)
  }

  func readString(service: String, account: String) -> String? {
    lock.lock()
    defer { lock.unlock() }
    let values = loadLocked()
    let key = Self.storageKey(service: service, account: account)
    guard let value = values[key], !value.isEmpty else {
      return nil
    }
    return value
  }

  @discardableResult
  func setString(_ value: String, service: String, account: String) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    var values = loadLocked()
    values[Self.storageKey(service: service, account: account)] = value
    guard persistLocked(values) else {
      return false
    }
    cache = values
    return true
  }

  func delete(service: String, account: String) {
    lock.lock()
    defer { lock.unlock() }
    var values = loadLocked()
    let key = Self.storageKey(service: service, account: account)
    guard values.removeValue(forKey: key) != nil else {
      return
    }
    if persistLocked(values) {
      cache = values
    }
  }

  func secretsDirectoryURL() -> URL {
    fileURL().deletingLastPathComponent()
  }

  func fileURL() -> URL {
    Self.fileURL(rootDirectory: rootDirectory(), bundleIdentifier: resolvedBundleIdentifier())
  }

  private func rootDirectory() -> URL {
    rootDirectoryOverride ?? DesktopLocalProfile.applicationSupportURL()
  }

  private func resolvedBundleIdentifier() -> String {
    if let bundleIdentifierOverride, !bundleIdentifierOverride.isEmpty {
      return bundleIdentifierOverride
    }
    if let bundleIdentifier = Bundle.main.bundleIdentifier, !bundleIdentifier.isEmpty {
      return bundleIdentifier
    }
    return "unknown.bundle"
  }

  private func loadLocked() -> [String: String] {
    if let cache {
      return cache
    }
    let loaded = readFileLocked()
    cache = loaded
    return loaded
  }

  private func readFileLocked() -> [String: String] {
    let url = fileURL()
    guard fileManager.fileExists(atPath: url.path) else {
      return [:]
    }
    do {
      let data = try Data(contentsOf: url)
      guard !data.isEmpty else {
        return [:]
      }
      let object = try JSONSerialization.jsonObject(with: data)
      guard let dictionary = object as? [String: Any] else {
        logUnreadableFileLocked(url)
        return [:]
      }
      var values: [String: String] = [:]
      for (key, value) in dictionary {
        if let string = value as? String {
          values[key] = string
        }
      }
      return values
    } catch {
      logUnreadableFileLocked(url)
      return [:]
    }
  }

  private func logUnreadableFileLocked(_ url: URL) {
    guard !didLogUnreadableFile else { return }
    didLogUnreadableFile = true
    log("DesktopDeveloperSecretStore: ignoring unreadable secrets file at \(url.path)")
  }

  private func persistLocked(_ values: [String: String]) -> Bool {
    let url = fileURL()
    let directory = url.deletingLastPathComponent()
    do {
      try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
      try fileManager.setAttributes(
        [.posixPermissions: 0o700],
        ofItemAtPath: directory.path
      )
      let data = try JSONSerialization.data(
        withJSONObject: values,
        options: [.prettyPrinted, .sortedKeys]
      )
      let tempURL = directory.appendingPathComponent(
        ".\(url.lastPathComponent).\(UUID().uuidString)",
        isDirectory: false
      )
      let created = fileManager.createFile(
        atPath: tempURL.path,
        contents: data,
        attributes: [.posixPermissions: 0o600]
      )
      guard created else {
        log("DesktopDeveloperSecretStore: failed to create temp secrets file at \(tempURL.path)")
        return false
      }
      if fileManager.fileExists(atPath: url.path) {
        _ = try fileManager.replaceItemAt(url, withItemAt: tempURL)
      } else {
        try fileManager.moveItem(at: tempURL, to: url)
      }
      try fileManager.setAttributes(
        [.posixPermissions: 0o600],
        ofItemAtPath: url.path
      )
      return true
    } catch {
      log("DesktopDeveloperSecretStore: failed to persist secrets file (\(error.localizedDescription))")
      return false
    }
  }
}

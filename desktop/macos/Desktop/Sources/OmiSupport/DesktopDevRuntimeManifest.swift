import Foundation

/// Token-free state published by a running named development bundle for local
/// diagnostics. This is intentionally local-only: credentials, environment
/// variables, and backend URLs must be obtained from the loopback health route
/// rather than persisted to disk.
package struct DesktopDevRuntimeManifest: Codable, Equatable {
  package static let schemaVersion = 1

  package let schemaVersion: Int
  package let bundleIdentifier: String
  package let processID: Int32
  package let startedAt: Date
  package let appPath: String
  package let profileRoot: String
  package let logPath: String
  package let automationPort: Int

  package init(
    bundleIdentifier: String,
    processID: Int32,
    startedAt: Date,
    appPath: String,
    profileRoot: String,
    logPath: String,
    automationPort: Int
  ) {
    self.schemaVersion = Self.schemaVersion
    self.bundleIdentifier = bundleIdentifier
    self.processID = processID
    self.startedAt = startedAt
    self.appPath = appPath
    self.profileRoot = profileRoot
    self.logPath = logPath
    self.automationPort = automationPort
  }
}

package enum DesktopDevRuntimeManifestStore {
  package static let filename = ".omi-dev-runtime.json"

  package static func path(in profileRoot: URL) -> URL {
    profileRoot.appendingPathComponent(filename, isDirectory: false)
  }

  package static func write(_ manifest: DesktopDevRuntimeManifest, in profileRoot: URL) throws {
    let fileManager = FileManager.default
    try fileManager.createDirectory(
      at: profileRoot,
      withIntermediateDirectories: true,
      attributes: [.posixPermissions: 0o700])

    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    let data = try encoder.encode(manifest)
    let destination = path(in: profileRoot)
    let temporary = profileRoot.appendingPathComponent(".omi-dev-runtime-\(UUID().uuidString).tmp")

    guard
      fileManager.createFile(
        atPath: temporary.path,
        contents: data,
        attributes: [.posixPermissions: 0o600])
    else {
      throw CocoaError(.fileWriteUnknown)
    }
    try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: temporary.path)

    if fileManager.fileExists(atPath: destination.path) {
      _ = try fileManager.replaceItemAt(destination, withItemAt: temporary)
    } else {
      try fileManager.moveItem(at: temporary, to: destination)
    }
    try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path)
  }
}

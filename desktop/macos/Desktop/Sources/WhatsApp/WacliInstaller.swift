import CryptoKit
import Foundation

enum WacliInstallerError: LocalizedError, Equatable {
  case downloadFailed(statusCode: Int)
  case checksumMismatch
  case extractFailed(String)
  case binaryMissing
  case binaryTooOld

  var errorDescription: String? {
    switch self {
    case .downloadFailed(let statusCode):
      return "Failed to download WhatsApp helper (HTTP \(statusCode))."
    case .checksumMismatch:
      return "Downloaded WhatsApp helper failed integrity check."
    case .extractFailed(let detail):
      return "Failed to install WhatsApp helper: \(detail)"
    case .binaryMissing:
      return "WhatsApp helper binary is missing after install."
    case .binaryTooOld:
      return "WhatsApp helper is too old. Reconnect to download an update."
    }
  }
}

/// Downloads and caches the openclaw/wacli binary on demand (not shipped in the app bundle).
enum WacliInstaller {
  static let version = "0.11.2"
  static let archiveSHA256 = "d76b6f8a90ceee03a25adf2b2a1f680d8f63c1b5bba0322aa5e1de07a06dd9e2"

  private static let binaryFileName = "wacli"
  private static let versionFileName = "wacli.version"

  static var downloadURL: URL {
    URL(string: "https://github.com/openclaw/wacli/releases/download/v\(version)/wacli_\(version)_darwin_universal.tar.gz")!
  }

  static func installDirectory(
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> URL {
    homeDirectory
      .appendingPathComponent("Library")
      .appendingPathComponent("Application Support")
      .appendingPathComponent("Omi")
      .appendingPathComponent("whatsapp")
      .appendingPathComponent("bin")
  }

  static func installedBinaryURL(
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> URL {
    installDirectory(homeDirectory: homeDirectory).appendingPathComponent(binaryFileName)
  }

  static func findInstalledBinary(
    fileManager: FileManager = .default,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> String? {
    let binaryURL = installedBinaryURL(homeDirectory: homeDirectory)
    let versionURL = installDirectory(homeDirectory: homeDirectory).appendingPathComponent(versionFileName)
    guard fileManager.isExecutableFile(atPath: binaryURL.path) else { return nil }

    let installedVersion =
      (try? String(contentsOf: versionURL, encoding: .utf8))?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if installedVersion != version {
      return nil
    }
    return binaryURL.path
  }

  /// Returns a usable wacli path, downloading and installing when needed.
  static func ensureInstalled(
    fileManager: FileManager = .default,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
    session: URLSession = .shared
  ) async throws -> String {
    if let existing = findInstalledBinary(fileManager: fileManager, homeDirectory: homeDirectory),
      supportsRequiredAuthFlags(binaryPath: existing)
    {
      return existing
    }

    let installDir = installDirectory(homeDirectory: homeDirectory)
    try fileManager.createDirectory(at: installDir, withIntermediateDirectories: true)

    let (data, response) = try await session.data(from: downloadURL)
    let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
    guard (200..<300).contains(statusCode) else {
      throw WacliInstallerError.downloadFailed(statusCode: statusCode)
    }

    let digest = SHA256.hash(data: data)
    let hex = digest.map { String(format: "%02x", $0) }.joined()
    guard hex == archiveSHA256 else {
      throw WacliInstallerError.checksumMismatch
    }

    let tempRoot = fileManager.temporaryDirectory
      .appendingPathComponent("omi-wacli-\(UUID().uuidString)", isDirectory: true)
    try fileManager.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    defer { try? fileManager.removeItem(at: tempRoot) }

    let archiveURL = tempRoot.appendingPathComponent("wacli.tar.gz")
    try data.write(to: archiveURL, options: .atomic)

    try extractArchive(archiveURL: archiveURL, into: tempRoot)

    let extractedBinary = try locateExtractedBinary(in: tempRoot, fileManager: fileManager)
    guard supportsRequiredAuthFlags(binaryPath: extractedBinary.path) else {
      throw WacliInstallerError.binaryTooOld
    }

    let destination = installedBinaryURL(homeDirectory: homeDirectory)
    if fileManager.fileExists(atPath: destination.path) {
      try fileManager.removeItem(at: destination)
    }
    try fileManager.copyItem(at: extractedBinary, to: destination)
    try fileManager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: destination.path)
    clearQuarantineAttributes(at: destination.path)

    let versionURL = installDir.appendingPathComponent(versionFileName)
    try "\(version)\n".write(to: versionURL, atomically: true, encoding: .utf8)

    guard fileManager.isExecutableFile(atPath: destination.path) else {
      throw WacliInstallerError.binaryMissing
    }

    log("WacliInstaller: installed wacli \(version) at \(destination.path)")
    return destination.path
  }

  static func supportsRequiredAuthFlags(binaryPath: String) -> Bool {
    let authHelp = runHelp(binaryPath: binaryPath, arguments: ["auth", "--help"])
    let globalHelp = runHelp(binaryPath: binaryPath, arguments: ["--help"])
    return authHelp.contains("--qr-format") && globalHelp.contains("--events")
  }

  static func sha256Hex(of data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  private static func extractArchive(archiveURL: URL, into destination: URL) throws {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
    process.arguments = ["-xzf", archiveURL.path, "-C", destination.path]
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    try process.run()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else {
      let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
      throw WacliInstallerError.extractFailed(output.isEmpty ? "tar exited \(process.terminationStatus)" : output)
    }
  }

  private static func locateExtractedBinary(in root: URL, fileManager: FileManager) throws -> URL {
    let direct = root.appendingPathComponent(binaryFileName)
    if fileManager.isExecutableFile(atPath: direct.path) || fileManager.fileExists(atPath: direct.path) {
      return direct
    }

    guard let enumerator = fileManager.enumerator(at: root, includingPropertiesForKeys: nil) else {
      throw WacliInstallerError.binaryMissing
    }
    for case let url as URL in enumerator where url.lastPathComponent == binaryFileName {
      return url
    }
    throw WacliInstallerError.binaryMissing
  }

  private static func clearQuarantineAttributes(at path: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/xattr")
    process.arguments = ["-cr", path]
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    try? process.run()
    process.waitUntilExit()
  }

  private static func runHelp(binaryPath: String, arguments: [String]) -> String {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: binaryPath)
    process.arguments = arguments
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    do {
      try process.run()
      process.waitUntilExit()
    } catch {
      return ""
    }
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
  }
}

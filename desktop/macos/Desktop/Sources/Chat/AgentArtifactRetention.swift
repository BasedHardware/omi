import Foundation

/// Bounded retention for oversized agent control-tool dumps.
///
/// The Node runtime writes truncated tool results under
/// `Application Support/Omi/Artifacts/<bundle>/tool-output` so a later
/// `read_tool_output` can recover them. Those files were never expired, so
/// existing installs accumulated months of JSON. User-facing run artifacts
/// (owner/session/run/attempt copies) are outside this directory and stay.
enum AgentArtifactRetention {
  static let toolOutputDirectoryName = "tool-output"
  static let toolOutputRetention: TimeInterval = 7 * 24 * 60 * 60

  /// Pure retention decision: which files (by last-modified date) are stale
  /// relative to `now`. Extracted so the sweep policy is testable without disk.
  static func staleToolOutputURLs(
    _ files: [(url: URL, modified: Date)],
    now: Date,
    retention: TimeInterval
  ) -> [URL] {
    files.filter { now.timeIntervalSince($0.modified) > retention }.map(\.url)
  }

  /// Delete expired `tool-output` files for this bundle's artifact root.
  /// Existing users are cleaned on the next launch; new dumps expire after a week.
  @discardableResult
  static func pruneExpiredToolOutputs(
    in artifactsDirectory: URL,
    now: Date = Date(),
    retention: TimeInterval = toolOutputRetention,
    fileManager: FileManager = .default
  ) -> Int {
    let toolOutputRoot = artifactsDirectory.appendingPathComponent(
      toolOutputDirectoryName, isDirectory: true)
    var isDirectory: ObjCBool = false
    guard fileManager.fileExists(atPath: toolOutputRoot.path, isDirectory: &isDirectory),
      isDirectory.boolValue
    else {
      return 0
    }

    guard
      let enumerator = fileManager.enumerator(
        at: toolOutputRoot,
        includingPropertiesForKeys: [
          .isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey, .contentModificationDateKey,
        ],
        options: [.skipsPackageDescendants]
      )
    else {
      return 0
    }

    var deleted = 0
    var directories: [URL] = []
    for case let url as URL in enumerator {
      let values = try? url.resourceValues(forKeys: [
        .isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey, .contentModificationDateKey,
      ])
      if values?.isSymbolicLink == true { continue }
      if values?.isDirectory == true {
        directories.append(url)
        continue
      }
      guard values?.isRegularFile == true, let modified = values?.contentModificationDate else {
        continue
      }
      guard now.timeIntervalSince(modified) > retention else { continue }
      do {
        try fileManager.removeItem(at: url)
        deleted += 1
      } catch {
        continue
      }
    }

    for directory in directories.sorted(by: { $0.path.count > $1.path.count }) {
      if let contents = try? fileManager.contentsOfDirectory(atPath: directory.path), contents.isEmpty {
        try? fileManager.removeItem(at: directory)
      }
    }
    return deleted
  }
}

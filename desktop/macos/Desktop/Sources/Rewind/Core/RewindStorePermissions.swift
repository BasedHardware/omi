import Foundation
import OmiSupport

/// Owner-only permissions for the local Rewind store.
///
/// The tree under Application Support holds every screen OCR string, transcript,
/// screenshot, and video chunk in plaintext, so no level of it may stay group- or
/// world-readable. `createDirectory(withIntermediateDirectories: true)` builds the
/// parents with the process umask (0755) and `attributes:` applies only to the
/// leaf, so every creation site routes through here instead of tightening one
/// directory and trusting its ancestors.
enum RewindStorePermissions {
  static let directoryMode = 0o700
  static let fileMode = 0o600

  private static let repairLock = NSLock()
  private nonisolated(unsafe) static var repairedTrees: Set<String> = []

  /// Tighten `directory` and every store ancestor up to the Application Support
  /// root. Cheap enough to call on every directory creation: one `lstat` per
  /// level, and a `chmod` only where the mode is still too permissive.
  static func secureDirectory(
    at directory: URL,
    storeRoot: URL = DesktopLocalProfile.applicationSupportURL()
  ) {
    for url in chain(from: storeRoot, to: directory) {
      tighten(url.path, to: directoryMode, expecting: mode_t(S_IFDIR))
    }
  }

  /// Tighten a single store file. `Data.write(to:)` and `AVAssetWriter` create
  /// their output at 0644 under the default umask.
  static func secureFile(at file: URL) {
    tighten(file.path, to: fileMode, expecting: mode_t(S_IFREG))
  }

  /// Repair a store tree written by an older build, which left 0755 directories
  /// and 0644 files behind. Runs at most once per user directory per launch.
  static func repairStoreTreeIfNeeded(
    at userDirectory: URL,
    storeRoot: URL = DesktopLocalProfile.applicationSupportURL()
  ) {
    let key = userDirectory.standardizedFileURL.path
    repairLock.lock()
    let alreadyRepaired = repairedTrees.contains(key)
    repairedTrees.insert(key)
    repairLock.unlock()
    guard !alreadyRepaired else { return }
    repairStoreTree(at: userDirectory, storeRoot: storeRoot)
  }

  static func repairStoreTree(
    at userDirectory: URL,
    storeRoot: URL = DesktopLocalProfile.applicationSupportURL()
  ) {
    secureDirectory(at: userDirectory, storeRoot: storeRoot)
    guard
      let enumerator = FileManager.default.enumerator(
        at: userDirectory,
        includingPropertiesForKeys: [.isDirectoryKey],
        options: []
      )
    else { return }
    while let url = enumerator.nextObject() as? URL {
      let isDirectory = (try? url.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory ?? false
      tighten(
        url.path,
        to: isDirectory ? directoryMode : fileMode,
        expecting: mode_t(isDirectory ? S_IFDIR : S_IFREG)
      )
    }
  }

  private static func chain(from storeRoot: URL, to directory: URL) -> [URL] {
    let root = storeRoot.standardizedFileURL
    let target = directory.standardizedFileURL
    guard target.path == root.path || target.path.hasPrefix(root.path + "/") else { return [target] }

    var walked: [URL] = []
    var current = target
    while current.path != root.path {
      walked.append(current)
      let parent = current.deletingLastPathComponent().standardizedFileURL
      if parent.path == current.path { break }
      current = parent
    }
    walked.append(root)
    return walked.reversed()
  }

  /// Only clears permission bits, so a path an operator has already made
  /// stricter than the target keeps its mode. A path we do not own (or that is
  /// a symlink or other non-regular node) is left alone, and a failed `chmod`
  /// is logged rather than propagated: capture must not die because one
  /// directory resisted repair.
  private static func tighten(_ path: String, to mode: Int, expecting fileType: mode_t) {
    var info = stat()
    guard lstat(path, &info) == 0 else { return }
    guard (info.st_mode & mode_t(S_IFMT)) == fileType, info.st_uid == getuid() else { return }

    let current = Int(info.st_mode) & 0o777
    let tightened = current & mode
    guard tightened != current else { return }
    if chmod(path, mode_t(tightened)) != 0 {
      log("RewindStorePermissions: could not tighten \(path) (errno \(errno))")
    }
  }
}

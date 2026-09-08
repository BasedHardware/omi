import Foundation

struct FileIndexScanPolicy {
  struct AutomaticScanPlan: Equatable {
    let roots: [URL]
    /// Existing index rows under roots omitted solely because TCC is unavailable
    /// must survive this partial scan's deletion pass.
    let retainedPrefixes: Set<String>
  }

  enum DirectoryEntryPlan: Equatable {
    case skipSubtree
    case descend
    case indexPackage(fileExtension: String, fileType: String)
  }

  static let standard = FileIndexScanPolicy()

  let skipFolders: Set<String>
  let packageExtensions: Set<String>
  let maxDepth: Int
  let maxFileSize: Int64

  init(
    skipFolders: Set<String> = [
      ".Trash", "node_modules", ".git", "__pycache__", ".venv", "venv",
      ".cache", ".npm", ".yarn", "Pods", "DerivedData", ".build",
      "build", "dist", ".next", ".nuxt", "target", "vendor",
      "Library", ".local", ".cargo", ".rustup",
    ],
    packageExtensions: Set<String> = [
      "app", "framework", "bundle", "plugin", "kext",
      "xcodeproj", "xcworkspace", "playground",
    ],
    maxDepth: Int = 3,
    maxFileSize: Int64 = 500 * 1024 * 1024
  ) {
    self.skipFolders = skipFolders
    self.packageExtensions = packageExtensions
    self.maxDepth = maxDepth
    self.maxFileSize = maxFileSize
  }

  func standardScanRoots(
    homeURL: URL,
    applicationsURL: URL = URL(fileURLWithPath: "/Applications", isDirectory: true)
  ) -> [URL] {
    [
      homeURL.appendingPathComponent("Downloads", isDirectory: true),
      homeURL.appendingPathComponent("Documents", isDirectory: true),
      homeURL.appendingPathComponent("Desktop", isDirectory: true),
      homeURL.appendingPathComponent("Developer", isDirectory: true),
      homeURL.appendingPathComponent("Projects", isDirectory: true),
      homeURL.appendingPathComponent("Code", isDirectory: true),
      homeURL.appendingPathComponent("src", isDirectory: true),
      homeURL.appendingPathComponent("repos", isDirectory: true),
      homeURL.appendingPathComponent("Sites", isDirectory: true),
      applicationsURL,
      homeURL.appendingPathComponent("Applications", isDirectory: true),
    ]
  }

  /// Home subfolders macOS protects with per-folder TCC (Files and Folders):
  /// enumerating them without Full Disk Access raises a system consent dialog.
  static let tccProtectedFolderNames: Set<String> = ["Documents", "Desktop", "Downloads"]

  /// Roots the **automatic** indexer (initial backfill, periodic rescan) may
  /// enumerate. Without Full Disk Access the protected roots are dropped rather
  /// than scanned — a background scan must never be the thing that throws a
  /// "grant access to Documents?" sheet at the user. Explicit user-initiated scans
  /// (Settings → Rescan files) keep the full root set.
  func automaticScanRoots(
    homeURL: URL,
    applicationsURL: URL = URL(fileURLWithPath: "/Applications", isDirectory: true),
    fullDiskAccessGranted: Bool
  ) -> [URL] {
    automaticScanPlan(
      homeURL: homeURL,
      applicationsURL: applicationsURL,
      fullDiskAccessGranted: fullDiskAccessGranted
    ).roots
  }

  func automaticScanPlan(
    homeURL: URL,
    applicationsURL: URL = URL(fileURLWithPath: "/Applications", isDirectory: true),
    fullDiskAccessGranted: Bool
  ) -> AutomaticScanPlan {
    let roots = standardScanRoots(homeURL: homeURL, applicationsURL: applicationsURL)
    guard !fullDiskAccessGranted else {
      return AutomaticScanPlan(roots: roots, retainedPrefixes: [])
    }
    let allowedRoots = roots.filter { root in
      guard root.deletingLastPathComponent().standardizedFileURL == homeURL.standardizedFileURL else {
        return true
      }
      return !Self.tccProtectedFolderNames.contains(root.lastPathComponent)
    }
    let allowedPaths = Set(allowedRoots.map(\.standardizedFileURL))
    let retainedPrefixes = Set(
      roots
        .filter { !allowedPaths.contains($0.standardizedFileURL) }
        .map { relativePath(for: $0, homePath: homeURL.path) })
    return AutomaticScanPlan(roots: allowedRoots, retainedPrefixes: retainedPrefixes)
  }

  func shouldScanDirectory(atDepth depth: Int) -> Bool {
    depth <= maxDepth
  }

  func planDirectoryEntry(_ url: URL) -> DirectoryEntryPlan {
    let name = url.lastPathComponent
    if skipFolders.contains(name) {
      return .skipSubtree
    }

    let ext = url.pathExtension.lowercased()
    if packageExtensions.contains(ext) {
      return .indexPackage(fileExtension: ext, fileType: ext == "app" ? "application" : "package")
    }

    return .descend
  }

  func makePackageRecord(
    for url: URL,
    folderName: String,
    homePath: String,
    depth: Int,
    createdAt: Date?,
    modifiedAt: Date?
  ) -> IndexedFileRecord? {
    guard case .indexPackage(let ext, let fileType) = planDirectoryEntry(url) else {
      return nil
    }

    return IndexedFileRecord(
      path: relativePath(for: url, homePath: homePath),
      filename: url.lastPathComponent,
      fileExtension: ext,
      fileType: fileType,
      sizeBytes: 0,
      folder: folderName,
      depth: depth,
      createdAt: createdAt,
      modifiedAt: modifiedAt
    )
  }

  func makeFileRecord(
    for url: URL,
    folderName: String,
    homePath: String,
    depth: Int,
    isRegularFile: Bool,
    sizeBytes: Int64,
    createdAt: Date?,
    modifiedAt: Date?
  ) -> IndexedFileRecord? {
    guard isRegularFile, sizeBytes > 0, sizeBytes <= maxFileSize else {
      return nil
    }

    let ext = url.pathExtension.isEmpty ? nil : url.pathExtension.lowercased()
    let fileType = FileTypeCategory.from(extension: ext)

    return IndexedFileRecord(
      path: relativePath(for: url, homePath: homePath),
      filename: url.lastPathComponent,
      fileExtension: ext,
      fileType: fileType.rawValue,
      sizeBytes: sizeBytes,
      folder: folderName,
      depth: depth,
      createdAt: createdAt,
      modifiedAt: modifiedAt
    )
  }

  func relativePath(for url: URL, homePath: String) -> String {
    var path = url.path
    if path.hasPrefix(homePath) {
      path = "~" + path.dropFirst(homePath.count)
    }
    return path
  }
}

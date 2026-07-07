import Foundation

struct FileIndexScanPolicy {
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
            "Library", ".local", ".cargo", ".rustup"
        ],
        packageExtensions: Set<String> = [
            "app", "framework", "bundle", "plugin", "kext",
            "xcodeproj", "xcworkspace", "playground"
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

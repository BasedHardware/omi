import GRDB
import XCTest

@testable import Omi_Computer

final class FileIndexerServiceTests: XCTestCase {
  private var temporaryRoot: URL!
  private var databasePool: DatabasePool!

  override func setUpWithError() throws {
    try super.setUpWithError()

    temporaryRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-file-indexer-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)

    let databaseURL = temporaryRoot.appendingPathComponent("index.sqlite")
    databasePool = try DatabasePool(path: databaseURL.path)
    try databasePool.write { db in
      try db.create(table: "indexed_files") { t in
        t.autoIncrementedPrimaryKey("id")
        t.column("path", .text).notNull()
        t.column("filename", .text).notNull()
        t.column("fileExtension", .text)
        t.column("fileType", .text).notNull()
        t.column("sizeBytes", .integer).notNull()
        t.column("folder", .text).notNull()
        t.column("depth", .integer).notNull()
        t.column("createdAt", .datetime)
        t.column("modifiedAt", .datetime)
        t.column("indexedAt", .datetime).notNull()
      }
      try db.create(index: "idx_indexed_files_path", on: "indexed_files", columns: ["path"], unique: true)
    }
  }

  override func tearDownWithError() throws {
    databasePool = nil
    if let temporaryRoot {
      try? FileManager.default.removeItem(at: temporaryRoot)
    }
    temporaryRoot = nil
    try super.tearDownWithError()
  }

  func testScanFoldersIndexesRecursiveTreeAndIncrementalScanSkipsOrDeletes() async throws {
    let root = temporaryRoot.appendingPathComponent("Documents", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)

    let rootFile = try writeFile("hello", at: root.appendingPathComponent("root.md"))
    let child = root.appendingPathComponent("Project", isDirectory: true)
    let nested = child.appendingPathComponent("Nested", isDirectory: true)
    try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
    let childFile = try writeFile("print('hi')", at: child.appendingPathComponent("main.py"))
    _ = try writeFile("too deep", at: nested.appendingPathComponent("deep.txt"))

    let skippedFolder = root.appendingPathComponent("node_modules", isDirectory: true)
    try FileManager.default.createDirectory(at: skippedFolder, withIntermediateDirectories: true)
    _ = try writeFile("skip", at: skippedFolder.appendingPathComponent("package.json"))

    let package = root.appendingPathComponent("Example.app", isDirectory: true)
    try FileManager.default.createDirectory(
      at: package.appendingPathComponent("Contents", isDirectory: true),
      withIntermediateDirectories: true
    )
    _ = try writeFile("inside package", at: package.appendingPathComponent("Contents/Info.plist"))
    _ = try writeFile("this file is over the test size limit", at: root.appendingPathComponent("big.bin"))
    let deletedLater = try writeFile("delete me", at: root.appendingPathComponent("remove.txt"))

    let policy = FileIndexScanPolicy(maxDepth: 1, maxFileSize: 12)
    let service = FileIndexerService(databasePool: databasePool, scanPolicy: policy, batchSize: 2)

    let firstCount = await service.scanFolders([root])

    XCTAssertEqual(firstCount, 4)
    var records = try fetchIndexedRecords()
    XCTAssertEqual(records.map(\.filename).sorted(), ["Example.app", "main.py", "remove.txt", "root.md"])
    XCTAssertEqual(records.first(where: { $0.filename == "Example.app" })?.fileType, "application")
    XCTAssertEqual(records.first(where: { $0.filename == "Example.app" })?.depth, 0)
    XCTAssertNil(records.first(where: { $0.filename == "Info.plist" }))
    XCTAssertNil(records.first(where: { $0.filename == "package.json" }))
    XCTAssertNil(records.first(where: { $0.filename == "deep.txt" }))
    XCTAssertNil(records.first(where: { $0.filename == "big.bin" }))

    let rootPath = try XCTUnwrap(records.first { $0.filename == rootFile.lastPathComponent }?.path)
    let childPath = try XCTUnwrap(records.first { $0.filename == childFile.lastPathComponent }?.path)
    let rootIndexedAt = try XCTUnwrap(records.first { $0.path == rootPath }?.indexedAt)
    let childIndexedAt = try XCTUnwrap(records.first { $0.path == childPath }?.indexedAt)
    let deletedFilename = deletedLater.lastPathComponent

    try FileManager.default.removeItem(at: deletedLater)
    _ = try writeFile("new", at: root.appendingPathComponent("new.csv"))

    let secondCount = await service.scanFolders([root], incremental: true)

    XCTAssertEqual(secondCount, 1)
    records = try fetchIndexedRecords()
    XCTAssertEqual(records.map(\.filename).sorted(), ["Example.app", "main.py", "new.csv", "root.md"])
    XCTAssertNil(records.first { $0.filename == deletedFilename })
    XCTAssertEqual(records.first { $0.path == rootPath }?.indexedAt, rootIndexedAt)
    XCTAssertEqual(records.first { $0.path == childPath }?.indexedAt, childIndexedAt)
    XCTAssertEqual(records.first { $0.filename == "new.csv" }?.fileType, FileTypeCategory.spreadsheet.rawValue)
  }

  private func writeFile(_ contents: String, at url: URL) throws -> URL {
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    try contents.data(using: .utf8)?.write(to: url)
    return url
  }

  private func fetchIndexedRecords() throws -> [IndexedFileRecord] {
    try databasePool.read { db in
      try IndexedFileRecord
        .order(IndexedFileRecord.Columns.path)
        .fetchAll(db)
    }
  }
}

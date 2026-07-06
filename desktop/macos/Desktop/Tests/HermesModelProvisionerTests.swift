import XCTest

@testable import Omi_Computer

/// Covers the Hermes free-model provisioning that keeps `model.default` pinned
/// to a free Nous model (no paid credits required).
final class HermesModelProvisionerTests: XCTestCase {

  private let free = HermesModelProvisioner.freeDefaultModel

  // MARK: - rewrite (pure transform)

  func testReplacesPaidDefaultWithFreeAndPreservesEverythingElse() throws {
    let input = """
      model:
        default: qwen/qwen3-235b-a22b-2507
        provider: nous
        base_url: https://openrouter.ai/api/v1
      terminal:
        backend: local
      """
    let out = try XCTUnwrap(HermesModelProvisioner.rewrite(input))
    XCTAssertTrue(out.contains("  default: \(free)"))
    XCTAssertFalse(out.contains("qwen/qwen3-235b-a22b-2507"))
    // Untouched keys survive verbatim.
    XCTAssertTrue(out.contains("  provider: nous"))
    XCTAssertTrue(out.contains("  base_url: https://openrouter.ai/api/v1"))
    XCTAssertTrue(out.contains("terminal:"))
    XCTAssertTrue(out.contains("  backend: local"))
  }

  func testNoChangeWhenAlreadyFree() {
    let input = """
      model:
        default: \(free)
        provider: nous
      """
    XCTAssertNil(HermesModelProvisioner.rewrite(input))
  }

  func testInsertsDefaultWhenModelBlockHasNone() throws {
    let input = """
      model:
        provider: nous
      terminal:
        backend: local
      """
    let out = try XCTUnwrap(HermesModelProvisioner.rewrite(input))
    let lines = out.components(separatedBy: "\n")
    let modelIdx = try XCTUnwrap(lines.firstIndex(of: "model:"))
    XCTAssertEqual(lines[modelIdx + 1], "  default: \(free)")
    XCTAssertTrue(out.contains("  provider: nous"))
  }

  func testPrependsModelBlockWhenAbsent() throws {
    let input = """
      terminal:
        backend: local
      """
    let out = try XCTUnwrap(HermesModelProvisioner.rewrite(input))
    XCTAssertTrue(out.hasPrefix("model:\n  default: \(free)\n  provider: nous"))
    XCTAssertTrue(out.contains("terminal:"))
  }

  func testCreatesBlockForEmptyContents() throws {
    let out = try XCTUnwrap(HermesModelProvisioner.rewrite(""))
    XCTAssertTrue(out.contains("model:"))
    XCTAssertTrue(out.contains("  default: \(free)"))
  }

  func testIsFreeModel() {
    XCTAssertTrue(HermesModelProvisioner.isFreeModel("stepfun/step-3.7-flash:free"))
    XCTAssertTrue(HermesModelProvisioner.isFreeModel("  something:free  "))
    XCTAssertFalse(HermesModelProvisioner.isFreeModel("qwen/qwen3-235b-a22b-2507"))
  }

  // MARK: - ensureFreeDefaultModel (file I/O, idempotent)

  func testEnsureFreeDefaultModelWritesAndIsIdempotent() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-hermes-provision-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let path = dir.appendingPathComponent("config.yaml").path
    try "model:\n  default: qwen/qwen3-235b-a22b-2507\n  provider: nous\n"
      .write(toFile: path, atomically: true, encoding: .utf8)

    let changed = HermesModelProvisioner.ensureFreeDefaultModel(configPath: path)
    XCTAssertTrue(changed)
    let written = try String(contentsOfFile: path, encoding: .utf8)
    XCTAssertTrue(written.contains("  default: \(free)"))
    XCTAssertFalse(written.contains("qwen/qwen3-235b-a22b-2507"))

    // Second call is a no-op.
    XCTAssertFalse(HermesModelProvisioner.ensureFreeDefaultModel(configPath: path))
  }
}

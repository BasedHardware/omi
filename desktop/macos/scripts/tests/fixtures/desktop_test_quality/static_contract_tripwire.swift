func testForbiddenLegacyOwner() throws {
  let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
  // omi-test-quality: source-inspection -- static contract: forbids the legacy second owner symbol
  let source = try String(contentsOf: root.appendingPathComponent("Sources/Feature.swift"))
  XCTAssertFalse(source.contains("LegacySecondOwner"))
}

func testForbiddenLegacyOwner() throws {
  let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
  // omi-test-quality: source-inspection -- this is behavioral coverage
  let source = try String(contentsOf: root.appendingPathComponent("Sources/Feature.swift"))
  XCTAssertFalse(source.contains("LegacySecondOwner"))
}

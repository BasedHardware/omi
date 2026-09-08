func testTitleWiring() throws {
  let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
  let source = try String(
    contentsOf: root.appendingPathComponent("Sources/Feature.swift")
  )
  XCTAssertTrue(source.contains("renderTitle()"))
}

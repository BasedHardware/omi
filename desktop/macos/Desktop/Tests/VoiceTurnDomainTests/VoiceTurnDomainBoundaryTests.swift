import VoiceTurnDomain
import XCTest

@MainActor
final class VoiceTurnDomainBoundaryTests: XCTestCase {
  func testFactFacadeAdvancesTurnWithoutReducerAccess() {
    let domain = VoiceTurnDomain()
    let turnID = VoiceTurnID()

    let reduction = domain.publish(.start(turnID: turnID, ownerID: nil, intent: .hold))

    XCTAssertEqual(reduction.model.turn?.id, turnID)
    XCTAssertEqual(reduction.model.turn?.phase, .recording)
    XCTAssertEqual(domain.model.turn?.id, turnID)
  }

  func testAppSourcesCannotReferenceDomainEventsOrReducer() throws {
    let desktopRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let appSources = desktopRoot.appendingPathComponent("Sources", isDirectory: true)
    let sourceFiles = try FileManager.default.contentsOfDirectory(
      at: appSources,
      includingPropertiesForKeys: nil,
      options: [.skipsHiddenFiles]
    )
    .flatMap(recursiveSwiftFiles)
    .filter { !$0.path.contains("/Sources/VoiceTurnDomain/") }

    let forbiddenReferences = try sourceFiles.compactMap { file -> String? in
      // omi-test-quality: source-inspection -- static contract: app sources cannot name domain-internal lifecycle types
      let source = try String(contentsOf: file, encoding: .utf8)
      guard source.contains("VoiceTurnEvent") || source.contains("VoiceTurnReducer") else { return nil }
      return file.lastPathComponent
    }

    XCTAssertEqual(forbiddenReferences, [])
  }

  private func recursiveSwiftFiles(in directory: URL) -> [URL] {
    let enumerator = FileManager.default.enumerator(
      at: directory,
      includingPropertiesForKeys: nil,
      options: [.skipsHiddenFiles])
    return enumerator?.compactMap { element in
      guard let file = element as? URL, file.pathExtension == "swift" else { return nil }
      return file
    } ?? []
  }
}

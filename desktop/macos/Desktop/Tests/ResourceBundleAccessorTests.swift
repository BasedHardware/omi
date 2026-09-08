import XCTest

@testable import Omi_Computer

/// The SwiftPM-generated `Bundle.module` accessor for the executable target only
/// checks the app ROOT and an absolute `.build` path baked in from the build
/// machine. Both are absent on end-user installs, so any `Bundle.module` use in
/// app code fatalErrors at launch for real users while passing on every dev and
/// CI machine that has the repo checked out (shipped as the v0.12.110 launch
/// crash). All app code must use `Bundle.resourceBundle`, which resolves the
/// bundle inside `Contents/Resources/`.
final class ResourceBundleAccessorTests: XCTestCase {
  func testNoGeneratedBundleModuleAccessorUsageInAppSources() throws {
    // omi-test-quality: source-inspection -- static contract: the generated Bundle.module accessor cannot resolve resources on user installs; this cannot be expressed behaviorally in a hermetic test because it depends on the installed-app filesystem layout.
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources")
    let enumerator = try XCTUnwrap(
      FileManager.default.enumerator(at: sourcesRoot, includingPropertiesForKeys: nil))

    var offenders: [String] = []
    for case let url as URL in enumerator where url.pathExtension == "swift" {
      let source = try String(contentsOf: url, encoding: .utf8)
      // Match dot-access usage (`Bundle.module.urls…`), not prose mentions in comments.
      if source.contains("Bundle.module.") || source.contains("= Bundle.module\n") {
        offenders.append(url.lastPathComponent)
      }
    }
    XCTAssertEqual(
      offenders, [],
      "Use Bundle.resourceBundle instead of the generated Bundle.module accessor: \(offenders)")
  }

  func testFontRegistrationUsesResourceBundle() throws {
    // omi-test-quality: source-inspection -- static contract: regression tripwire for the v0.12.110 launch crash (font registration ran through the generated accessor).
    let file = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Startup/OmiFontRegistration.swift")
    let source = try String(contentsOf: file, encoding: .utf8)
    XCTAssertTrue(source.contains("Bundle.resourceBundle.urls(forResourcesWithExtension:"))
    XCTAssertFalse(source.contains("Bundle.module."))
  }
}

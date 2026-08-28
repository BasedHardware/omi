import XCTest

@testable import Omi_Computer

/// Local skills are plain files at ~/.omi/skills; saving must produce spec-valid
/// frontmatter and the catalog must reflect exactly what is on disk.
final class LocalSkillsStoreTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory

  override func setUpWithError() throws {
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-skills-test-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = tempRoot
  }

  override func tearDownWithError() throws {
    LocalSkillsStore.rootURLOverride = nil
    try? FileManager.default.removeItem(at: tempRoot)
  }

  func testSaveNormalizesFrontmatterAndListsSkill() throws {
    let slug = try LocalSkillsStore.saveSkill(
      title: "Weekly Report Format",
      markdown: "# Steps\nAlways use bullet points.")
    XCTAssertEqual(slug, "weekly-report-format")

    let content = try XCTUnwrap(LocalSkillsStore.loadMarkdown(slug: slug))
    XCTAssertTrue(content.hasPrefix("---\nname: weekly-report-format\ndescription: Always use bullet points.\n---"))

    let skills = LocalSkillsStore.listSkills()
    XCTAssertEqual(skills.map(\.slug), ["weekly-report-format"])
    XCTAssertEqual(skills[0].description, "Always use bullet points.")
    // The plugin manifest for the ACP lane comes along with the first save.
    XCTAssertTrue(
      FileManager.default.fileExists(
        atPath: tempRoot.appendingPathComponent(".claude-plugin/plugin.json").path))
  }

  func testSavePreservesAuthorFrontmatterAndOwnsNameDescription() throws {
    let md = "---\nname: old-name\ndescription: Old desc\nlicense: MIT\n---\nBody text here."
    let slug = try LocalSkillsStore.saveSkill(title: "My Skill", markdown: md)
    let content = try XCTUnwrap(LocalSkillsStore.loadMarkdown(slug: slug))
    XCTAssertTrue(content.contains("name: my-skill"))
    XCTAssertTrue(content.contains("description: Old desc"))
    XCTAssertTrue(content.contains("license: MIT"))
    XCTAssertFalse(content.contains("old-name"))
  }

  func testRenameRemovesOldFolderAndDeleteRemovesSkill() throws {
    let original = try LocalSkillsStore.saveSkill(title: "First Name", markdown: "does things")
    let renamed = try LocalSkillsStore.saveSkill(
      title: "Second Name", markdown: "does things", replacingSlug: original)
    XCTAssertEqual(LocalSkillsStore.listSkills().map(\.slug), [renamed])

    LocalSkillsStore.deleteSkill(slug: renamed)
    XCTAssertTrue(LocalSkillsStore.listSkills().isEmpty)
  }

  func testInvalidTitleThrowsAndMissingDirListsEmpty() {
    XCTAssertThrowsError(try LocalSkillsStore.saveSkill(title: "!!!", markdown: "x"))
    XCTAssertTrue(LocalSkillsStore.listSkills().isEmpty)
  }
}

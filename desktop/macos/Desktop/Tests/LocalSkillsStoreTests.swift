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

  /// The ACP lane gates the user-skills plugin on `.claude-plugin/plugin.json`,
  /// which the UI save path writes. A folder dropped in by hand never runs that
  /// path, so the runtime-spawn safety net must cover it — and must not create
  /// dotfiles for users with no skills at all.
  func testSpawnSafetyNetWritesPluginManifestOnlyWhenSkillsExist() throws {
    let skillsDir = tempRoot.appendingPathComponent("skills", isDirectory: true)
    try FileManager.default.createDirectory(
      at: skillsDir.appendingPathComponent("hand-dropped"), withIntermediateDirectories: true)
    try Data("---\nname: hand-dropped\ndescription: d\n---\nBody.".utf8)
      .write(to: skillsDir.appendingPathComponent("hand-dropped/SKILL.md"))

    LocalSkillsStore.ensurePluginManifestIfSkillsExist()
    XCTAssertTrue(FileManager.default.fileExists(atPath: LocalSkillsStore.pluginManifestURL.path))

    // A machine with a ~/.omi but no skills folder stays untouched.
    let emptyRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-skills-empty-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = emptyRoot
    defer {
      LocalSkillsStore.rootURLOverride = tempRoot
      try? FileManager.default.removeItem(at: emptyRoot)
    }
    LocalSkillsStore.ensurePluginManifestIfSkillsExist()
    XCTAssertFalse(FileManager.default.fileExists(atPath: LocalSkillsStore.pluginManifestURL.path))
    XCTAssertFalse(FileManager.default.fileExists(atPath: emptyRoot.path))
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

  // MARK: - Disabled-slug upkeep

  /// Saves and restores the real defaults key so the suite never leaks toggle
  /// state into (or inherits it from) another test.
  private func withDisabledSkillsDefaults<T>(_ body: () throws -> T) rethrows -> T {
    let defaults = UserDefaults.standard
    let original = defaults.string(forKey: DefaultsKey.disabledSkillsJSON.rawValue)
    defaults.removeObject(forKey: DefaultsKey.disabledSkillsJSON.rawValue)
    defer {
      if let original {
        defaults.set(original, forKey: DefaultsKey.disabledSkillsJSON.rawValue)
      } else {
        defaults.removeObject(forKey: DefaultsKey.disabledSkillsJSON.rawValue)
      }
    }
    return try body()
  }

  /// The disabled set holds slugs: a rename that left the old slug behind
  /// would silently re-enable the renamed skill and let dead entries pile up.
  func testRenameRekeysDisabledSlug() throws {
    try withDisabledSkillsDefaults {
      let original = try LocalSkillsStore.saveSkill(title: "First Name", markdown: "does things")
      LocalSkillsStore.setDisabledSkillNames([original])

      let renamed = try LocalSkillsStore.saveSkill(
        title: "Second Name", markdown: "does things", replacingSlug: original)

      XCTAssertEqual(
        LocalSkillsStore.disabledSkillNames(),
        [renamed],
        "the renamed skill stays disabled under its new slug and the old entry is gone")
    }
  }

  func testDeletePrunesDisabledSlug() throws {
    try withDisabledSkillsDefaults {
      let slug = try LocalSkillsStore.saveSkill(title: "Doomed", markdown: "x")
      LocalSkillsStore.setDisabledSkillNames([slug, "still-here"])

      LocalSkillsStore.deleteSkill(slug: slug)

      XCTAssertEqual(
        LocalSkillsStore.disabledSkillNames(), ["still-here"],
        "deleting a disabled skill removes its entry and leaves others alone")
    }
  }

  func testRenameOfEnabledSkillLeavesDisabledSetUntouched() throws {
    try withDisabledSkillsDefaults {
      let original = try LocalSkillsStore.saveSkill(title: "First Name", markdown: "does things")
      _ = try LocalSkillsStore.saveSkill(
        title: "Second Name", markdown: "does things", replacingSlug: original)

      XCTAssertTrue(LocalSkillsStore.disabledSkillNames().isEmpty)
    }
  }

  /// A catalog skill's SKILL.md references its siblings by relative path, so the folder is the
  /// unit: nested files keep their layout, and a reinstall replaces the folder rather than
  /// layering new files over whatever the last one left.
  func testBundleWritesNestedFilesAndReplacesTheFolder() throws {
    let md = "---\nname: x\ndescription: Does things\n---\nRun scripts/run.py."
    let slug = try LocalSkillsStore.saveSkillBundle(
      title: "Doc Tools", markdown: md,
      files: ["scripts/run.py": Data("print(1)".utf8), "references/a.md": Data("ref".utf8)])

    let dir = LocalSkillsStore.skillsDirURL.appendingPathComponent(slug)
    XCTAssertEqual(
      try String(contentsOf: dir.appendingPathComponent("scripts/run.py"), encoding: .utf8),
      "print(1)")
    XCTAssertEqual(
      try String(contentsOf: dir.appendingPathComponent("references/a.md"), encoding: .utf8), "ref")
    XCTAssertTrue(try XCTUnwrap(LocalSkillsStore.loadMarkdown(slug: slug)).contains("name: doc-tools"))

    _ = try LocalSkillsStore.saveSkillBundle(
      title: "Doc Tools", markdown: md, files: ["scripts/new.py": Data("print(2)".utf8)])
    XCTAssertFalse(
      FileManager.default.fileExists(atPath: dir.appendingPathComponent("scripts/run.py").path),
      "a stale file from the previous version must not survive a reinstall")
    XCTAssertEqual(LocalSkillsStore.listSkills().map(\.slug), [slug])

    // No staging folder is left behind to show up as a skill.
    let left = try FileManager.default.contentsOfDirectory(
      atPath: LocalSkillsStore.skillsDirURL.path)
    XCTAssertEqual(left, [slug])
  }

  /// A half-finished install must not be offered as a skill, however it got there — a crash, or a
  /// folder a user dropped in by hand.
  func testHiddenDirectoriesAreNotSkills() throws {
    let slug = try LocalSkillsStore.saveSkillBundle(
      title: "Real", markdown: "---\nname: x\ndescription: d\n---\nBody.", files: [:])
    let phantom = LocalSkillsStore.skillsDirURL.appendingPathComponent(".half.incoming")
    try FileManager.default.createDirectory(at: phantom, withIntermediateDirectories: true)
    try Data("---\nname: y\ndescription: d\n---\nBody.".utf8)
      .write(to: phantom.appendingPathComponent("SKILL.md"))

    XCTAssertEqual(LocalSkillsStore.listSkills().map(\.slug), [slug])
  }

  /// A reinstall that fails partway must leave the working skill installed. Deleting the
  /// destination before the move meant a throw on the move lost both versions.
  func testAFailedBundleWriteLeavesThePreviousVersionInstalled() throws {
    let slug = try LocalSkillsStore.saveSkillBundle(
      title: "Keeper", markdown: "---\nname: x\ndescription: first\n---\nOriginal body.",
      files: ["notes.md": Data("keep".utf8)])

    // A path whose parent is a file cannot be created, so the staged write throws mid-bundle.
    XCTAssertThrowsError(
      try LocalSkillsStore.saveSkillBundle(
        title: "Keeper", markdown: "---\nname: x\ndescription: second\n---\nNew body.",
        files: ["notes.md": Data("x".utf8), "notes.md/child.md": Data("y".utf8)]))

    let dir = LocalSkillsStore.skillsDirURL.appendingPathComponent(slug)
    XCTAssertEqual(
      try String(contentsOf: dir.appendingPathComponent("notes.md"), encoding: .utf8), "keep")
    XCTAssertTrue(try XCTUnwrap(LocalSkillsStore.loadMarkdown(slug: slug)).contains("Original body."))
  }

  func testBundleSkipsPathsThatEscapeTheFolder() throws {
    let slug = try LocalSkillsStore.saveSkillBundle(
      title: "Safe", markdown: "---\nname: x\ndescription: d\n---\nBody.",
      files: ["../escape.sh": Data("x".utf8), "ok.md": Data("y".utf8)])
    let dir = LocalSkillsStore.skillsDirURL.appendingPathComponent(slug)
    XCTAssertTrue(FileManager.default.fileExists(atPath: dir.appendingPathComponent("ok.md").path))
    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: LocalSkillsStore.skillsDirURL.appendingPathComponent("escape.sh").path))
  }

  func testInvalidTitleThrowsAndMissingDirListsEmpty() {
    XCTAssertThrowsError(try LocalSkillsStore.saveSkill(title: "!!!", markdown: "x"))
    XCTAssertTrue(LocalSkillsStore.listSkills().isEmpty)
  }
}

import XCTest

@testable import Omi_Computer

/// One skill-catalog source of truth per lane: the compact catalog rides the
/// pi-mono lane (and task chat), while the ACP lane receives skills natively
/// through the user-skills plugin and must not get the catalog a second time.
/// The disabled toggle is enforced wherever the catalog or the tools look.
final class ChatSkillCatalogLaneTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory

  override func setUpWithError() throws {
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-skill-lane-test-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = tempRoot
  }

  override func tearDownWithError() throws {
    LocalSkillsStore.rootURLOverride = nil
    try? FileManager.default.removeItem(at: tempRoot)
  }

  private func writeSkill(_ slug: String, description: String) throws {
    let dir = LocalSkillsStore.skillsDirURL.appendingPathComponent(slug, isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    try "---\nname: \(slug)\ndescription: \(description)\n---\n\nBody for \(slug).\n"
      .write(to: dir.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)
  }

  private func skillNames(in projection: [String: Any]) -> [String] {
    ((projection["skills"] as? [[String: String]]) ?? []).map { $0["name"] ?? "" }
  }

  func testCatalogGateInjectsOnPiMonoAndRefusesAcpOnlyWhileThePluginIsActive() throws {
    // No plugin manifest yet (fresh install, hand-dropped skills only): the ACP
    // lane has no native skills source, so the catalog is still needed.
    XCTAssertFalse(ChatProvider.acpSkillsPluginActive())
    XCTAssertTrue(ChatProvider.shouldInjectSkillCatalog(adapterId: AgentAdapterId.acp.rawValue))
    XCTAssertTrue(ChatProvider.shouldInjectSkillCatalog(adapterId: AgentAdapterId.piMono.rawValue))

    LocalSkillsStore.ensurePluginManifest()
    XCTAssertTrue(ChatProvider.acpSkillsPluginActive())
    // The plugin ships the skills natively; injecting the catalog too would
    // hand the model the same index twice.
    XCTAssertFalse(ChatProvider.shouldInjectSkillCatalog(adapterId: AgentAdapterId.acp.rawValue))
    XCTAssertTrue(ChatProvider.shouldInjectSkillCatalog(adapterId: AgentAdapterId.piMono.rawValue))
  }

  func testTaskChatWorkspaceCarriesCatalogOnPiMonoAndOmitsItOnActiveAcpPlugin() async throws {
    let unique = "lane-test-\(UUID().uuidString.lowercased())"
    try writeSkill(unique, description: "Task chat lane test skill")

    let piMonoPayload = await TaskChatRuntime.taskWorkspaceContext(
      workspacePath: "/tmp/omi-task-workspace",
      adapterId: AgentAdapterId.piMono.rawValue
    ).value
    XCTAssertEqual(piMonoPayload["workingDirectory"] as? String, "/tmp/omi-task-workspace")
    XCTAssertTrue(
      skillNames(in: piMonoPayload["skillCatalog"] as? [String: Any] ?? [:]).contains(unique),
      "task chat must index skills so the model can search before loading"
    )

    LocalSkillsStore.ensurePluginManifest()
    let acpPayload = await TaskChatRuntime.taskWorkspaceContext(
      workspacePath: "/tmp/omi-task-workspace",
      adapterId: AgentAdapterId.acp.rawValue
    ).value
    XCTAssertEqual(acpPayload["workingDirectory"] as? String, "/tmp/omi-task-workspace")
    XCTAssertNil(acpPayload["skillCatalog"], "the ACP plugin already indexes the same skills")
  }

  func testTaskChatWorkspaceWithoutAPathStaysEmpty() async {
    let payload = await TaskChatRuntime.taskWorkspaceContext(
      workspacePath: "",
      adapterId: AgentAdapterId.piMono.rawValue
    ).value
    XCTAssertTrue(payload.isEmpty)
  }

  func testDisabledSkillsAreFilteredFromDiskProjectionAndExportedToRuntimeEnv() throws {
    let enabled = "lane-enabled-\(UUID().uuidString.lowercased())"
    let disabled = "lane-disabled-\(UUID().uuidString.lowercased())"
    try writeSkill(enabled, description: "Stays visible")
    try writeSkill(disabled, description: "Hidden everywhere")

    let defaults = UserDefaults.standard
    let original = defaults.string(forKey: DefaultsKey.disabledSkillsJSON.rawValue)
    defer {
      if let original {
        defaults.set(original, forKey: DefaultsKey.disabledSkillsJSON.rawValue)
      } else {
        defaults.removeObject(forKey: DefaultsKey.disabledSkillsJSON.rawValue)
      }
    }

    // Nothing disabled: both visible, and the runtime env stays unset.
    defaults.removeObject(forKey: DefaultsKey.disabledSkillsJSON.rawValue)
    let allVisible = ChatProvider.skillCatalogProjectionFromDisk(workspace: "/tmp/omi-task-workspace")
    XCTAssertTrue(skillNames(in: allVisible).contains(enabled))
    XCTAssertTrue(skillNames(in: allVisible).contains(disabled))
    XCTAssertNil(ChatProvider.disabledSkillsRuntimeEnvValue())

    // Disabling hides the skill from the catalog and exports it to the tools.
    let disabledJSON = try XCTUnwrap(String(data: try JSONEncoder().encode([disabled]), encoding: .utf8))
    defaults.set(disabledJSON, forKey: DefaultsKey.disabledSkillsJSON.rawValue)

    let projection = ChatProvider.skillCatalogProjectionFromDisk(workspace: "/tmp/omi-task-workspace")
    XCTAssertFalse(
      skillNames(in: projection).contains(disabled),
      "a disabled skill must not reach the model through the catalog"
    )
    XCTAssertTrue(skillNames(in: projection).contains(enabled))

    let envValue = try XCTUnwrap(ChatProvider.disabledSkillsRuntimeEnvValue())
    let exported = try JSONDecoder().decode([String].self, from: Data(envValue.utf8))
    XCTAssertEqual(exported, [disabled])
    XCTAssertTrue(
      ChatProvider.disabledSkillNamesFromDefaults() == Set([disabled]),
      "the instance-facing disabled set must agree with the runtime export"
    )
  }
}

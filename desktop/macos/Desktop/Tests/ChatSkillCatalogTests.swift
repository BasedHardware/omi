import XCTest

@testable import Omi_Computer

final class ChatSkillCatalogTests: XCTestCase {
  func testSkillCatalogDeduplicatesProjectSkillsAndKeepsClaudeContentOutOfContext() {
    let global =
      (0..<12).map { index in
        (name: "global-\(index)", description: "Global skill \(index)", path: "/global/\(index)")
      } + [(name: "shared", description: "Global shared description", path: "/global/shared")]
    let project = [(name: "shared", description: "Project shared description", path: "/project/shared")]

    let projection = ChatSkillCatalog.contextProjection(
      globalSkills: global,
      projectSkills: project,
      disabledSkills: ["global-0"]
    )
    let skills = projection["skills"] as? [[String: String]]

    XCTAssertEqual(projection["totalCount"] as? Int, 12)
    XCTAssertFalse(projection["isTruncated"] as? Bool ?? true)
    XCTAssertEqual(skills?.first(where: { $0["name"] == "shared" })?["description"], "Project shared description")
    XCTAssertFalse(skills?.contains(where: { $0["name"] == "global-0" }) ?? true)
    XCTAssertNil(projection["claudeMd"])
    XCTAssertNil(projection["claudeMdContent"])
  }

  func testSkillCatalogUsesSearchWhenTheCompactListOverflows() {
    let global = (0..<13).map { index in
      (name: "skill-\(index)", description: String(repeating: "x", count: 200), path: "/global/\(index)")
    }

    let projection = ChatSkillCatalog.contextProjection(
      globalSkills: global,
      projectSkills: [],
      disabledSkills: []
    )
    let skills = projection["skills"] as? [[String: String]]

    XCTAssertEqual(projection["totalCount"] as? Int, 13)
    XCTAssertTrue(projection["isTruncated"] as? Bool ?? false)
    XCTAssertTrue(projection["searchAvailable"] as? Bool ?? false)
    XCTAssertEqual(skills?.count, 12)
    XCTAssertLessThanOrEqual(skills?.first?["description"]?.count ?? .max, 160)
  }
}

import XCTest

@testable import Omi_Computer

final class MemoryAdmissionGateTests: XCTestCase {

  func testMissingLabelsRefuse() {
    XCTAssertFalse(
      MemoryAdmissionGate.admits(
        memory("User prefers dark mode", scope: nil, evidence: .userAuthored, credential: false)))
    XCTAssertFalse(
      MemoryAdmissionGate.admits(
        memory("User prefers dark mode", scope: .primaryUser, evidence: nil, credential: false)))
    XCTAssertFalse(
      MemoryAdmissionGate.admits(
        memory("User prefers dark mode", scope: .primaryUser, evidence: .userAuthored, credential: nil)))
  }

  func testObservedRefusalCardsAreDenied() {
    let refusals: [(String, MemorySubjectScope, MemorySubjectEvidence, Bool)] = [
      ("ArtyomOleg91 is in the game wearing a Superman skin.", .thirdParty, .renderedContent, false),
      ("A Twitch chatter named xXNovaXx just subscribed.", .thirdParty, .renderedContent, false),
      ("Someone named Jordan is asking for a raid in Discord.", .thirdParty, .renderedContent, false),
      ("YouTube commenter claims the video is fake.", .thirdParty, .renderedContent, false),
      ("Slack message from a coworker about their weekend.", .thirdParty, .addressedToUser, false),
      ("LinkedIn post about a stranger's promotion.", .thirdParty, .renderedContent, false),
      ("Forum user describes their GPU crash.", .thirdParty, .renderedContent, false),
      ("Reddit OP says they live in Austin.", .thirdParty, .renderedContent, false),
      ("Game lobby shows player SkinCollector99.", .thirdParty, .renderedContent, false),
      ("Amazon search suggestions include 'kondome männer'.", .artifact, .uiChrome, false),
      ("Chrome autocomplete offers a password reset URL.", .artifact, .uiChrome, false),
      ("macOS menu bar shows 72% battery.", .artifact, .uiChrome, false),
      ("Finder sidebar lists Downloads.", .artifact, .uiChrome, false),
      ("How to Eat: Relieve hunger by eating creatures, try on a clam.", .artifact, .renderedContent, false),
      ("Recipe site lists ingredients for someone else's cake.", .artifact, .renderedContent, false),
      ("User's email is win…@googlemail.com; 2FA is deactivated.", .primaryUser, .userAuthored, true),
      ("API key sk-live-example is visible in the terminal.", .primaryUser, .userAuthored, true),
      ("Bank account ending 4421 is on screen.", .primaryUser, .addressedToUser, true),
      ("Passport number is visible in a form.", .primaryUser, .userAuthored, true),
    ]
    XCTAssertEqual(refusals.count, 19)
    for (content, scope, evidence, credential) in refusals {
      XCTAssertFalse(
        MemoryAdmissionGate.admits(
          memory(content, scope: scope, evidence: evidence, credential: credential)),
        content)
    }
  }

  func testSystemExemplarsAdmit() {
    let admits = [
      "User's Slack workspace is 'Acme Corp' - they work there",
      "User has a meeting with John Smith (CEO) on calendar",
      "User's GitHub profile shows they maintain a Python ML library",
      "User's email signature shows they're VP of Engineering",
    ]
    XCTAssertEqual(admits.count, 4)
    for content in admits {
      XCTAssertTrue(
        MemoryAdmissionGate.admits(
          memory(content, scope: .primaryUser, evidence: .userAuthored, credential: false)),
        content)
    }
  }

  func testYouTubeHostIsExcluded() {
    XCTAssertTrue(
      MemoryHostExclusion.isExcluded(
        urlString: "https://www.youtube.com/watch?v=abc",
        excludedHosts: ["youtube.com"]))
    XCTAssertTrue(
      MemoryHostExclusion.isExcluded(
        urlString: "https://m.youtube.com/",
        excludedHosts: ["youtube.com"]))
    XCTAssertFalse(
      MemoryHostExclusion.isExcluded(
        urlString: "https://github.com/BasedHardware/omi",
        excludedHosts: ["youtube.com"]))
  }

  private func memory(
    _ content: String,
    scope: MemorySubjectScope?,
    evidence: MemorySubjectEvidence?,
    credential: Bool?
  ) -> ExtractedMemory {
    ExtractedMemory(
      content: content,
      category: .system,
      sourceApp: "Google Chrome",
      confidence: 0.95,
      subjectScope: scope,
      subjectEvidence: evidence,
      containsCredentialOrIdentifier: credential)
  }
}

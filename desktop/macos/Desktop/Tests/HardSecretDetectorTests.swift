import XCTest

@testable import Omi_Computer

final class HardSecretDetectorTests: XCTestCase {
  func testDetectsHardSecrets() {
    XCTAssertTrue(HardSecretDetector.containsHardSecret("OPENAI_API_KEY=sk-1234567890abcdefghijklmnop"))
    XCTAssertTrue(HardSecretDetector.containsHardSecret("token=abcdefghijklmnopqrstuvwxyz123456"))
    XCTAssertTrue(HardSecretDetector.containsHardSecret("password: correct-horse-battery"))
    XCTAssertTrue(HardSecretDetector.containsHardSecret("postgres://user:secret@example.com/db"))
  }

  func testDoesNotTreatEmailPIIAsHardSecret() {
    XCTAssertFalse(HardSecretDetector.containsHardSecret("Reach me at user@example.com"))
  }

  func testCategoriesAreStableAndSorted() {
    let categories = HardSecretDetector.categories(
      in: "token=abcdefghijklmnopqrstuvwxyz123456 and password: correct-horse-battery"
    )

    XCTAssertEqual(categories, ["password", "token"])
  }
}

import XCTest

@testable import Omi_Computer

final class APIClientUserProfilePeopleDecodingTests: XCTestCase {
  private func makeDecoder() -> JSONDecoder {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .custom { decoder in
      let container = try decoder.singleValueContainer()
      let value = try container.decode(String.self)

      let isoWithFractional = ISO8601DateFormatter()
      isoWithFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      if let date = isoWithFractional.date(from: value) {
        return date
      }

      let iso = ISO8601DateFormatter()
      if let date = iso.date(from: value) {
        return date
      }

      throw DecodingError.dataCorruptedError(
        in: container, debugDescription: "Invalid ISO8601 date: \(value)")
    }
    return decoder
  }

  func testUserProfileRequiresUidButToleratesOptionalProfileFields() throws {
    let json = """
      {
        "uid": "user-123",
        "name": "Desktop User",
        "unexpected_profile_field": "ignored"
      }
      """.data(using: .utf8)!

    let profile = try makeDecoder().decode(UserProfileResponse.self, from: json)

    XCTAssertEqual(profile.uid, "user-123")
    XCTAssertEqual(profile.name, "Desktop User")
    XCTAssertNil(profile.email)
    XCTAssertNil(profile.timeZone)
  }

  func testUserProfileStillFailsWithoutUid() {
    let json = """
      {
        "name": "Legacy User"
      }
      """.data(using: .utf8)!

    XCTAssertThrowsError(try makeDecoder().decode(UserProfileResponse.self, from: json))
  }

  func testPersonToleratesLegacyMissingOptionalFields() throws {
    let json = """
      {
        "id": "person-123",
        "name": "Alice"
      }
      """.data(using: .utf8)!

    let person = try makeDecoder().decode(Person.self, from: json)

    XCTAssertEqual(person.id, "person-123")
    XCTAssertEqual(person.name, "Alice")
    XCTAssertNil(person.createdAt)
    XCTAssertNil(person.updatedAt)
    XCTAssertEqual(person.speechSamples, [])
    XCTAssertNil(person.speechSampleTranscripts)
    XCTAssertEqual(person.speechSamplesVersion, 3)
  }

  func testPersonDecodesFullPeoplePayload() throws {
    let json = """
      {
        "id": "person-456",
        "name": "Bob",
        "created_at": "2026-07-06T12:30:00.123Z",
        "updated_at": "2026-07-06T12:45:00Z",
        "speech_samples": ["https://example.test/sample.wav"],
        "speech_sample_transcripts": ["hello"],
        "speech_samples_version": 4
      }
      """.data(using: .utf8)!

    let person = try makeDecoder().decode(Person.self, from: json)

    XCTAssertEqual(person.id, "person-456")
    XCTAssertEqual(person.name, "Bob")
    XCTAssertNotNil(person.createdAt)
    XCTAssertNotNil(person.updatedAt)
    XCTAssertEqual(person.speechSamples, ["https://example.test/sample.wav"])
    XCTAssertEqual(person.speechSampleTranscripts, ["hello"])
    XCTAssertEqual(person.speechSamplesVersion, 4)
  }
}

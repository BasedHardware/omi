import XCTest

@testable import Omi_Computer

final class ConversationPhotoResolverTests: XCTestCase {
  func testStorageBackedPhotoUsesAuthenticatedConversationImageReader() async throws {
    let photo = try decodedPhoto(base64: "", storageID: "permanent-storage")
    let expected = Data([1, 2, 3])
    let resolved = try await ConversationPhotoResolver.resolve(
      photo: photo,
      conversationID: "conversation-1",
      remote: { conversationID, photoID in
        XCTAssertEqual(conversationID, "conversation-1")
        XCTAssertEqual(photoID, "photo-1")
        return expected
      })

    XCTAssertEqual(resolved, expected)
  }

  func testInlinePhotoDoesNotCallRemoteReader() async throws {
    let photo = try decodedPhoto(base64: Data([4, 5, 6]).base64EncodedString(), storageID: nil)
    let resolved = try await ConversationPhotoResolver.resolve(
      photo: photo,
      conversationID: "conversation-1",
      remote: { _, _ in
        XCTFail("inline photo must not call the remote reader")
        return Data()
      })

    XCTAssertEqual(resolved, Data([4, 5, 6]))
  }

  func testStorageMetadataWithoutConversationIdentityFailsClosed() async throws {
    let photo = try decodedPhoto(base64: "", storageID: "permanent-storage")

    do {
      _ = try await ConversationPhotoResolver.resolve(
        photo: photo,
        conversationID: "",
        remote: { _, _ in Data([1]) })
      XCTFail("missing conversation identity must fail")
    } catch {
      XCTAssertEqual(error as? ConversationPhotoResolver.ResolutionError, .unavailable)
    }
  }

  private func decodedPhoto(base64: String, storageID: String?) throws -> ConversationPhoto {
    var object: [String: Any] = [
      "id": "photo-1",
      "base64": base64,
      "created_at": "2026-08-24T00:00:00Z",
      "discarded": false,
    ]
    if let storageID { object["storage_id"] = storageID }
    let data = try JSONSerialization.data(withJSONObject: object)
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode(ConversationPhoto.self, from: data)
  }
}

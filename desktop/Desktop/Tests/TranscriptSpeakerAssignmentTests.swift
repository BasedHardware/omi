import XCTest

@testable import Omi_Computer

final class TranscriptSpeakerAssignmentTests: XCTestCase {
  func testTranscriptSegmentDecodingPreservesBackendId() throws {
    let json = """
      {
        "id": "seg_backend_123",
        "text": "Hello",
        "speaker": "SPEAKER_01",
        "is_user": false,
        "person_id": "person_abc",
        "start": 1.25,
        "end": 2.5
      }
      """.data(using: .utf8)!

    let segment = try JSONDecoder().decode(TranscriptSegment.self, from: json)

    XCTAssertEqual(segment.id, "seg_backend_123")
    XCTAssertEqual(segment.backendId, "seg_backend_123")
    XCTAssertEqual(segment.personId, "person_abc")
  }

  func testTranscriptSegmentDecodingFallsBackToEphemeralIdWhenBackendIdMissing() throws {
    let json = """
      {
        "text": "Hello",
        "speaker": "SPEAKER_01",
        "is_user": false,
        "start": 1.25,
        "end": 2.5
      }
      """.data(using: .utf8)!

    let segment = try JSONDecoder().decode(TranscriptSegment.self, from: json)

    XCTAssertFalse(segment.id.isEmpty)
    XCTAssertNil(segment.backendId)
  }

  func testTranscriptionSegmentRecordRoundTripKeepsBackendId() {
    let record = TranscriptionSegmentRecord(
      sessionId: 1,
      speaker: 1,
      text: "Hello",
      startTime: 1.25,
      endTime: 2.5,
      segmentOrder: 0,
      segmentId: "seg_backend_123",
      speakerLabel: "SPEAKER_01",
      isUser: false,
      personId: "person_abc"
    )

    let segment = record.toTranscriptSegment()

    XCTAssertEqual(segment.id, "seg_backend_123")
    XCTAssertEqual(segment.backendId, "seg_backend_123")
    XCTAssertEqual(segment.personId, "person_abc")
  }

  // MARK: - SpeakerSegment isUser Tests

  func testSpeakerSegmentIsUserTrueWithNonZeroSpeaker() {
    // Backend can return is_user=true with speaker_id != 0 (speech profile match)
    let segment = SpeakerSegment(
      speaker: 1,
      text: "Hello from user",
      start: 0,
      end: 1,
      isUser: true
    )

    XCTAssertTrue(segment.isUser, "Segment with isUser=true should be treated as user regardless of speaker ID")
    XCTAssertEqual(segment.speaker, 1, "Speaker ID should remain 1")
  }

  func testSpeakerSegmentIsUserFalseWithZeroSpeaker() {
    // A segment from speaker 0 that isn't the user (e.g., no speech profile match)
    let segment = SpeakerSegment(
      speaker: 0,
      text: "Hello from someone else",
      start: 0,
      end: 1,
      isUser: false
    )

    XCTAssertFalse(segment.isUser, "Segment with isUser=false should not be treated as user even with speaker 0")
  }

  func testSpeakerSegmentDefaultsIsUserToFalse() {
    let segment = SpeakerSegment(
      speaker: 0,
      text: "Test",
      start: 0,
      end: 1
    )

    XCTAssertFalse(segment.isUser, "isUser should default to false")
  }

  // MARK: - Transcript Export isUser Tests

  func testTranscriptExportUsesIsUserForSpeakerLabel() {
    let segments = [
      TranscriptSegment(
        id: "seg1",
        text: "Hello from user",
        speaker: "SPEAKER_01",
        isUser: true,
        personId: nil,
        start: 0,
        end: 1
      ),
      TranscriptSegment(
        id: "seg2",
        text: "Hello from other",
        speaker: "SPEAKER_00",
        isUser: false,
        personId: nil,
        start: 1,
        end: 2
      ),
    ]

    let conversation = ServerConversation(
      id: "test",
      createdAt: Date(),
      startedAt: nil,
      finishedAt: nil,
      structured: Structured(
        title: "Test",
        overview: "",
        emoji: "",
        category: "other",
        actionItems: [],
        events: []
      ),
      transcriptSegments: segments,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: nil,
      language: nil,
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )

    let transcript = conversation.transcript

    // isUser=true speaker 1 should show "You", not "Speaker 1"
    XCTAssertTrue(transcript.contains("You: Hello from user"), "User segment should use 'You' label based on isUser, not speaker ID")

    // isUser=false speaker 0 should show "Speaker 0", not "You"
    XCTAssertTrue(transcript.contains("Speaker 0: Hello from other"), "Non-user segment with speaker 0 should NOT use 'You' label")
  }

  // MARK: - Translation Tests

  func testTranscriptSegmentDecodesTranslations() throws {
    let json = """
      {
        "id": "seg_trans_1",
        "text": "こんにちは",
        "speaker": "SPEAKER_00",
        "is_user": false,
        "start": 0.0,
        "end": 1.5,
        "translations": [
          {"lang": "en", "text": "Hello"},
          {"lang": "es", "text": "Hola"}
        ]
      }
      """.data(using: .utf8)!

    let segment = try JSONDecoder().decode(TranscriptSegment.self, from: json)

    XCTAssertEqual(segment.translations.count, 2)
    XCTAssertEqual(segment.translations[0].lang, "en")
    XCTAssertEqual(segment.translations[0].text, "Hello")
    XCTAssertEqual(segment.translations[1].lang, "es")
    XCTAssertEqual(segment.translations[1].text, "Hola")
  }

  func testTranscriptSegmentDefaultsToEmptyTranslations() throws {
    let json = """
      {
        "id": "seg_no_trans",
        "text": "Hello",
        "speaker": "SPEAKER_00",
        "is_user": false,
        "start": 0.0,
        "end": 1.0
      }
      """.data(using: .utf8)!

    let segment = try JSONDecoder().decode(TranscriptSegment.self, from: json)
    XCTAssertTrue(segment.translations.isEmpty, "Translations should default to empty array when not present in JSON")
  }

  func testSpeakerSegmentTranslationsPreserved() {
    let translations = [
      SegmentTranslation(lang: "en", text: "Hello"),
      SegmentTranslation(lang: "fr", text: "Bonjour")
    ]
    let segment = SpeakerSegment(
      speaker: 0,
      text: "こんにちは",
      start: 0,
      end: 1,
      isUser: false,
      translations: translations
    )

    XCTAssertEqual(segment.translations.count, 2)
    XCTAssertEqual(segment.translations[0].lang, "en")
    XCTAssertEqual(segment.translations[1].text, "Bonjour")
  }

  func testTranslationsPreservedDuringReassignment() {
    // Simulates the code path in ConversationDetailView.updateDisplayedConversation
    // and AppState.assignSpeakerToSegments where TranscriptSegment is rebuilt
    let original = TranscriptSegment(
      id: "seg1",
      backendId: "backend_seg1",
      text: "こんにちは",
      speaker: "SPEAKER_00",
      isUser: false,
      personId: nil,
      start: 0,
      end: 1,
      translations: [
        TranscriptTranslation(lang: "en", text: "Hello"),
        TranscriptTranslation(lang: "fr", text: "Bonjour")
      ]
    )

    // Rebuild like ConversationDetailView does during speaker reassignment
    let reassigned = TranscriptSegment(
      id: original.id,
      backendId: original.backendId,
      text: original.text,
      speaker: original.speaker,
      isUser: true,
      personId: nil,
      start: original.start,
      end: original.end,
      translations: original.translations
    )

    XCTAssertEqual(reassigned.translations.count, 2, "Translations must survive reassignment")
    XCTAssertEqual(reassigned.translations[0].lang, "en")
    XCTAssertEqual(reassigned.translations[0].text, "Hello")
    XCTAssertEqual(reassigned.backendId, "backend_seg1", "backendId must survive reassignment")
    XCTAssertTrue(reassigned.isUser)
  }

  func testBackendSegmentDecodesTranslations() throws {
    let json = """
      {
        "id": "seg_1",
        "text": "テスト",
        "speaker": "SPEAKER_00",
        "speaker_id": 0,
        "is_user": false,
        "start": 0.0,
        "end": 1.5,
        "translations": [
          {"lang": "en", "text": "Test"}
        ]
      }
      """.data(using: .utf8)!

    let segment = try JSONDecoder().decode(TranscriptionService.BackendSegment.self, from: json)

    XCTAssertEqual(segment.translations?.count, 1)
    XCTAssertEqual(segment.translations?[0].lang, "en")
    XCTAssertEqual(segment.translations?[0].text, "Test")
  }

  // MARK: - TranscriptionSegmentRecord Translation Round-Trip Tests

  func testTranscriptionSegmentRecordRoundTripWithTranslations() {
    let translations = [
      TranscriptTranslation(lang: "en", text: "Hello"),
      TranscriptTranslation(lang: "es", text: "Hola"),
    ]
    let translationsJson = String(data: try! JSONEncoder().encode(translations), encoding: .utf8)

    let record = TranscriptionSegmentRecord(
      sessionId: 1,
      speaker: 0,
      text: "こんにちは",
      startTime: 0.0,
      endTime: 1.5,
      segmentOrder: 0,
      segmentId: "seg_trans_rt",
      isUser: false,
      translationsJson: translationsJson
    )

    let segment = record.toTranscriptSegment()

    XCTAssertEqual(segment.translations.count, 2)
    XCTAssertEqual(segment.translations[0].lang, "en")
    XCTAssertEqual(segment.translations[0].text, "Hello")
    XCTAssertEqual(segment.translations[1].lang, "es")
    XCTAssertEqual(segment.translations[1].text, "Hola")
  }

  func testTranscriptionSegmentRecordRoundTripNilTranslationsJson() {
    let record = TranscriptionSegmentRecord(
      sessionId: 1,
      speaker: 0,
      text: "Hello",
      startTime: 0.0,
      endTime: 1.0,
      segmentOrder: 0,
      segmentId: "seg_no_trans_rt"
    )

    let segment = record.toTranscriptSegment()
    XCTAssertTrue(segment.translations.isEmpty, "Nil translationsJson should produce empty translations array")
  }

  func testTranscriptionSegmentRecordFromSegmentEncodesTranslations() {
    let segment = TranscriptSegment(
      id: "seg_encode_1",
      backendId: "seg_encode_1",
      text: "テスト",
      speaker: "SPEAKER_00",
      isUser: false,
      personId: nil,
      start: 0,
      end: 1,
      translations: [
        TranscriptTranslation(lang: "en", text: "Test"),
        TranscriptTranslation(lang: "fr", text: "Essai"),
      ]
    )

    let record = TranscriptionSegmentRecord.from(segment, sessionId: 1, segmentOrder: 0)

    XCTAssertNotNil(record.translationsJson, "Non-empty translations should be encoded to JSON")

    // Decode back and verify
    let decoded = try! JSONDecoder().decode(
      [TranscriptTranslation].self,
      from: record.translationsJson!.data(using: .utf8)!
    )
    XCTAssertEqual(decoded.count, 2)
    XCTAssertEqual(decoded[0].lang, "en")
    XCTAssertEqual(decoded[1].lang, "fr")
  }

  func testTranscriptionSegmentRecordFromSegmentEmptyTranslations() {
    let segment = TranscriptSegment(
      id: "seg_empty_trans",
      text: "Hello",
      speaker: "SPEAKER_00",
      isUser: false,
      personId: nil,
      start: 0,
      end: 1
    )

    let record = TranscriptionSegmentRecord.from(segment, sessionId: 1, segmentOrder: 0)
    XCTAssertNil(record.translationsJson, "Empty translations should produce nil translationsJson")
  }

  // MARK: - In-Memory Translation Preservation Tests

  func testSpeakerSegmentUpdatePreservesExistingTranslations() {
    // Simulates handleBackendSegments logic: when a segment update arrives
    // without translations, existing translations should be preserved
    var existing = SpeakerSegment(
      segmentId: "seg_preserve",
      speaker: 0,
      text: "Original text",
      start: 0,
      end: 1,
      isUser: false,
      translations: [
        SegmentTranslation(lang: "en", text: "Original text translated"),
      ]
    )

    // Incoming update with no translations (e.g., text refinement)
    let incoming = SpeakerSegment(
      segmentId: "seg_preserve",
      speaker: 0,
      text: "Updated text",
      start: 0,
      end: 1.5,
      isUser: false,
      translations: []
    )

    // Apply the preservation logic from handleBackendSegments
    var updated = incoming
    if incoming.translations.isEmpty && !existing.translations.isEmpty {
      updated.translations = existing.translations
    }
    existing = updated

    XCTAssertEqual(existing.text, "Updated text", "Text should be updated")
    XCTAssertEqual(existing.end, 1.5, "End time should be updated")
    XCTAssertEqual(existing.translations.count, 1, "Translations should be preserved")
    XCTAssertEqual(existing.translations[0].text, "Original text translated")
  }

  func testSpeakerSegmentUpdateReplacesTranslationsWhenNewOnesProvided() {
    var existing = SpeakerSegment(
      segmentId: "seg_replace",
      speaker: 0,
      text: "Original",
      start: 0,
      end: 1,
      isUser: false,
      translations: [
        SegmentTranslation(lang: "en", text: "Old translation"),
      ]
    )

    let incoming = SpeakerSegment(
      segmentId: "seg_replace",
      speaker: 0,
      text: "Updated",
      start: 0,
      end: 1,
      isUser: false,
      translations: [
        SegmentTranslation(lang: "en", text: "New translation"),
        SegmentTranslation(lang: "fr", text: "Nouvelle traduction"),
      ]
    )

    // When incoming has translations, use them
    var updated = incoming
    if incoming.translations.isEmpty && !existing.translations.isEmpty {
      updated.translations = existing.translations
    }
    existing = updated

    XCTAssertEqual(existing.translations.count, 2, "New translations should replace old ones")
    XCTAssertEqual(existing.translations[0].text, "New translation")
    XCTAssertEqual(existing.translations[1].text, "Nouvelle traduction")
  }

  // MARK: - Assignment Metadata Tests

  func testAssignmentMetadataPrefersBackendIdsAndFallsBackToIndices() {
    let segments = [
      TranscriptSegment(
        id: UUID().uuidString,
        backendId: nil,
        text: "Local only",
        speaker: "SPEAKER_00",
        isUser: false,
        personId: nil,
        start: 0,
        end: 1
      ),
      TranscriptSegment(
        id: "seg_backend_123",
        backendId: "seg_backend_123",
        text: "Synced",
        speaker: "SPEAKER_01",
        isUser: false,
        personId: nil,
        start: 1,
        end: 2
      ),
      TranscriptSegment(
        id: "seg_backend_456",
        backendId: "seg_backend_456",
        text: "Also synced",
        speaker: "SPEAKER_02",
        isUser: false,
        personId: nil,
        start: 2,
        end: 3
      ),
    ]

    let assignment = ConversationDetailView.assignmentMetadata(
      for: [0, 1, 99, 2],
      in: segments
    )

    XCTAssertEqual(
      assignment.targets,
      ["#index:0", "seg_backend_123", "seg_backend_456"]
    )
    XCTAssertEqual(
      assignment.backendIds,
      ["seg_backend_123", "seg_backend_456"]
    )
    XCTAssertEqual(assignment.fallbackOrders, [0])
  }
}

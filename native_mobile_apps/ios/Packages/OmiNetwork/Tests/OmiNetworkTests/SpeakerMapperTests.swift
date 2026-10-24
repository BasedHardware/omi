import Foundation
@testable import OmiNetwork
import Testing

/// Shapes captured from the local backend (`GET v1/users/people?include_stats=true`,
/// `GET v1/speaker-tag-prompts`, `GET …/voice-matches`).
struct SpeakerMapperTests {
    private func object(_ json: String) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
    }

    @Test func personWithStats() throws {
        let person = try #require(PersonMapper.map(object("""
        {"id": "p1", "name": "Anna", "speech_samples": ["https://storage.example/a.wav?sig=1"], "pinned": true,
         "confidence": "unverified", "conversation_count": 3, "talk_seconds": 125.5,
         "last_heard_at": "2026-10-07T15:21:44.953024Z"}
        """)))
        #expect(person.sampleCount == 1)
        #expect(person.sampleURLs.first?.host == "storage.example")
        #expect(person.isPinned)
        #expect(person.confidence == .unverified)
        #expect(person.conversationCount == 3)
        #expect(person.talkSeconds == 125.5)
        #expect(person.lastHeardAt != nil)
    }

    @Test func personWithoutStats() throws {
        let person = try #require(PersonMapper.map(object("""
        {"id": "p2", "name": "Ben", "speech_samples": [], "confidence": "likely", "talk_seconds": 0}
        """)))
        #expect(person.confidence == .likely)
        #expect(person.conversationCount == nil)
        #expect(person.talkSeconds == 0)
    }

    @Test func prompt() throws {
        let prompt = try #require(SpeakerMapper.prompt(object("""
        {"id": "q1", "kind": "confirm_person", "origin": "auto_person", "conversation_id": "c1",
         "conversation_title": "Lunch", "speaker_id": 2, "segment_ids": ["s1", "s2"], "clip_start": 3, "clip_end": 9.5,
         "excerpt": "See you then", "suggested_person_id": "p1", "suggested_person_name": "Anna",
         "candidates": [{"person_id": "p1", "name": "Anna", "match_level": 3, "pinned": false}]}
        """)))
        #expect(prompt.kind == .confirmPerson)
        #expect(prompt.origin == "auto_person")
        #expect(prompt.segmentIDs == ["s1", "s2"])
        #expect(prompt.clipEnd == 9.5)
        #expect(prompt.candidates.map(\.name) == ["Anna"])
    }

    @Test func voiceMatchAndSettings() throws {
        let match = try #require(SpeakerMapper.voiceMatch(object("""
        {"conversation_id": "c9", "title": "Standup", "started_at": "2026-10-01T09:00:00Z", "speaker_id": 1,
         "talk_seconds": 42, "segment_ids": ["x"], "clip_start": 0, "clip_end": 6, "match_level": "strong"}
        """)))
        #expect(match.isStrong)
        #expect(match.id == "c9#1")
        let settings = try SpeakerMapper.settings(object(#"{"speaker_tag_prompts_enabled": false, "save_other_voice_profiles": true}"#))
        #expect(settings == VoiceProfileSettings(asksToTag: false, savesOtherVoices: true))
    }
}

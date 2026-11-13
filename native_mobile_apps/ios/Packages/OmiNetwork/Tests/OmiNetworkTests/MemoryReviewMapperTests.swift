import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct MemoryReviewMapperTests {
    /// A `MemoryDB` with the belief fields (shape as the local backend returns it, trimmed).
    static let memoryJSON = """
    {"id": "m1", "uid": "u", "content": "Lena is moving to Lisbon.", "category": "interesting",
     "created_at": "2026-10-06T17:07:56Z", "updated_at": "2026-10-06T17:07:56Z",
     "veracity": 0.37, "capture_confidence": 0.65, "subject_attribution": "third_party",
     "uncertainty_reasons": ["single_source", "third_party_subject"], "arguments": {"subject": "Lena", "place": "Lisbon"},
     "evidence": [{"evidence_id": "ev1", "source_id": "conv-1", "source_type": "conversation", "independence_group": "conv-1",
                   "capture_confidence": 0.65, "captured_at": "2026-10-06T17:00:00Z"}]}
    """

    @Test func mapsBeliefSignals() throws {
        let memory = try MemoryMapper.map(JSONDecoder().decode(OmiAPI.MemoryDB.self, from: Data(Self.memoryJSON.utf8)))
        #expect(memory.veracity == 0.37)
        #expect(memory.captureConfidence == 0.65)
        #expect(memory.uncertaintyReasons == ["single_source", "third_party_subject"])
        #expect(memory.subjectAttribution == "third_party")
        #expect(memory.subjectName == "Lena")
        #expect(memory.evidence.first?.sourceType == "conversation")
        #expect(memory.evidence.first?.sourceID == "conv-1")
        #expect(memory.evidence.first?.capturedAt != nil)
    }

    @Test func mapsReviewQueueConflicts() {
        let item: [String: Any] = [
            "review_id": "review:m9:m1", "fact_id": "m9", "status": "pending", "conflict_with": ["m1"],
            "candidate": ["id": "m9", "content": "Lena is moving to Porto.", "veracity": 0.4],
            "created_at": "2026-10-07T10:00:00Z",
        ]
        let conflict = MemoryConflictMapper.conflict(from: item)
        #expect(conflict?.id == "review:m9:m1")
        #expect(conflict?.factID == "m9")
        #expect(conflict?.candidate == "Lena is moving to Porto.")
        #expect(conflict?.conflictsWith == ["m1"])
        var resolved = item
        resolved["status"] = "accepted"
        #expect(MemoryConflictMapper.conflict(from: resolved) == nil)
        #expect(MemoryConflictMapper.conflict(from: ["review_id": "x", "candidate": ["content": " "]]) == nil)
    }
}

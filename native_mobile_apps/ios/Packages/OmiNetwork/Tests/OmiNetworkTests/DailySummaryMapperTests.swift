import Foundation
@testable import OmiNetwork
import Testing

struct DailySummaryMapperTests {
    @Test func mapsTheBackendShape() throws {
        let json = """
        {"summaries":[{"id":"b451","date":"2026-10-06","created_at":"2026-10-06T22:20:12.694440Z",
        "headline":"An action-packed day","overview":"Business and health.","day_emoji":"🗓️",
        "stats":{"total_conversations":6,"total_duration_minutes":107},
        "highlights":[{"topic":"Q4 Roadmap","emoji":"🚀","summary":"Ship before the holidays.","conversation_ids":["c1"]}],
        "action_items":[],"unresolved_questions":[],"decisions_made":[{"decision":"Ship native iOS app.","conversation_id":"c1"}],
        "knowledge_nuggets":[],"memories_learned":[],"locations":[]}]}
        """
        let object = try JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any]
        let list = (object?["summaries"] as? [[String: Any]] ?? []).compactMap(DailySummaryMapper.map)
        #expect(list.count == 1)
        #expect(list.first?.highlights.first?.topic == "Q4 Roadmap")
        #expect(list.first?.decisions == ["Ship native iOS app."])
        #expect(list.first?.conversationCount == 6)
        #expect(list.first?.day != nil)
    }
}

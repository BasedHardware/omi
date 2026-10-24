import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct RecommendationMapperTests {
    /// Captured from the local backend (`GET v1/what-matters-now`), one recommendation.
    static let json = """
    {"schema_version":1,"evaluation_id":"evaluation_1","output_version":"output_1","material_version":"material_1",
     "generated_at":"2026-10-07T22:20:55.463110Z","expires_at":"2026-10-07T22:50:55.463110Z","recommendations":[{
      "intervention_id":"intervention_9783","output_version":"output_1","subject_kind":"task","subject_id":"gB7z",
      "feedback_subject_kind":"task","feedback_subject_id":"gB7z","destination_task_id":"gB7z",
      "destination_workstream_id":"workstream_e1b0","headline":"Send proof of income to landlord",
      "why_now":"This task is overdue by 2 days.","goal_or_workstream_label":"Move to Berlin",
      "recommended_action":"Send proof of income to landlord","alternative_action":"reschedule:Send proof of income to landlord",
      "evidence_preview":"Created directly by you.","evidence_refs":[{"kind":"conversation","id":"demo-6","version":null,
      "scope":"canonical","device_id":null,"excerpt_hash":null,"transcript_segment_ids":null,"start_seconds":null,
      "end_seconds":null}],"dedupe_key":"recommendation_f9d7","expires_at":"2026-10-07T22:50:55.463110Z"}]}
    """

    @Test func mapsEveryField() throws {
        let projection = try JSONDecoder().decode(OmiAPI.WhatMattersNowProjection.self, from: Data(Self.json.utf8))
        let item = try #require(projection.recommendations.first.map(RecommendationMapper.map))
        #expect(item.id == "intervention_9783")
        #expect(item.taskID == "gB7z")
        #expect(item.workstreamID == "workstream_e1b0")
        #expect(item.goalLabel == "Move to Berlin")
        #expect(item.alternativeAction == "reschedule:Send proof of income to landlord")
        #expect(item.evidencePreview == "Created directly by you.")
        #expect(item.evidence == [.init(kind: "conversation", id: "demo-6")])
        #expect(item.feedbackSubjectKind == "task")
        #expect(item.feedbackSubjectID == "gB7z")
        #expect(item.dedupeKey == "recommendation_f9d7")
        #expect(item.expiresAt == BackendDate.parse("2026-10-07T22:50:55.463110Z"))
    }

    @Test func feedbackBodiesMatchTheBackendContract() throws {
        let item = Recommendation(id: "iv", headline: "H", whyNow: "W", action: "A", taskID: "t1", feedbackSubjectID: "t1")
        let doNow = RecommendationMapper.feedbackBody(item, decision: .doNow)
        #expect(doNow["action"] as? String == "do_now")
        #expect(doNow["intervention_id"] as? String == "iv")
        #expect(doNow["subject_kind"] as? String == "task")
        #expect(doNow["subject_id"] as? String == "t1")
        #expect(doNow["reason"] == nil)
        #expect(RecommendationMapper.feedbackBody(item, decision: .later)["action"] as? String == "later")
        #expect(RecommendationMapper.feedbackBody(item, decision: .dismiss)["action"] as? String == "dismiss")
        #expect(RecommendationMapper.feedbackBody(item, decision: .complete)["action"] as? String == "complete")
        let handled = RecommendationMapper.feedbackBody(item, decision: .alreadyHandled)
        #expect(handled["action"] as? String == "dismiss")
        #expect(handled["reason"] as? String == "already_handled")
    }

    @Test func mapsWorkstreamEventsWithSequenceAndEvidence() throws {
        let json = """
        [{"event_id":"wse_2","workstream_id":"ws","sequence":2,"kind":"agent_update","summary":"Step: Searching",
          "evidence_refs":[{"kind":"external","id":"chat_session:s1","scope":"canonical"}],"sensitivity":"normal",
          "created_at":"2026-10-06T20:06:30.301101Z"}]
        """
        let events = try JSONDecoder().decode([OmiAPI.WorkstreamEvent].self, from: Data(json.utf8)).map(WorkstreamMapper.event)
        #expect(events.first?.sequence == 2)
        #expect(events.first?.evidence == [.init(kind: "external", id: "chat_session:s1")])
        #expect(events.first?.createdAt != nil)
    }
}

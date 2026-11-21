import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

/// Payloads as the local backend returned them (curl, 2026-10-07).
struct AccountAndDiscoverMapperTests {
    @Test func knowledgeGraphDropsSelfLoopsDuplicatesAndDanglingEdges() {
        let graph = KnowledgeGraphMapper.map([
            "nodes": [
                ["id": "kg_alice", "label": "Alice", "node_type": "person", "memory_ids": ["m1"]],
                ["id": "kg_berlin", "label": "Berlin", "node_type": "place"],
            ],
            "edges": [
                ["source_id": "kg_alice", "target_id": "kg_berlin", "label": "lives in"],
                ["source_id": "kg_berlin", "target_id": "kg_alice", "label": "home of"],
                ["source_id": "kg_alice", "target_id": "kg_alice", "label": "is"],
                ["source_id": "kg_alice", "target_id": "kg_gone", "label": "knows"],
            ],
            "truncated": false,
        ])
        #expect(graph.nodes.map(\.kind) == ["person", "place"])
        #expect(graph.nodes.first?.memoryIDs == ["m1"])
        #expect(graph.edges == [.init(source: "kg_alice", target: "kg_berlin", label: "lives in")])
    }

    @Test func wrappedStatesAndResult() {
        let processing = WrappedMapper.map([
            "status": "processing", "year": 2025, "result": NSNull(),
            "progress": ["pct": 0.72, "step": "Finding your funniest moment..."],
        ], year: 2025)
        #expect(processing.status == .processing)
        #expect(processing.progress == "Finding your funniest moment...")

        let done = WrappedMapper.map([
            "status": "done",
            "result": [
                "total_conversations": 120, "days_active": 80, "total_time_hours": 41.5, "top_categories": ["work"],
                "total_action_items": 10, "completed_action_items": 7,
                "memorable_days": ["most_fun_day": ["date": "2025-07-01", "title": "Lake day", "description": "Swimming", "emoji": "🏊"]],
                "funniest_event": ["date": "2025-03-02", "title": "The cake", "story": "It fell.", "emoji": "🎂"],
                "top_buddies": [["name": "Anna", "relationship": "friend", "context": "Climbing", "emoji": "🧗"]],
                "top_phrases": [["phrase": "let's ship it", "count": 12], "honestly"],
            ],
        ], year: 2025)
        #expect(done.conversations == 120 && done.hours == 41.5 && done.tasksDone == 7)
        #expect(done.highlights.map(\.text) == ["Swimming", "It fell."])
        #expect(done.buddies.first?.text == "Climbing")
        #expect(done.topPhrases == ["let's ship it", "honestly"])
        #expect(WrappedMapper.map(["status": "not_generated"], year: 2025).status == .notGenerated)
    }

    @Test func announcementKindsAndButtonLinks() {
        let changelog = AnnouncementMapper.map([
            "id": "a1", "type": "changelog", "app_version": "1.2.0",
            "content": ["title": "1.2.0", "changes": [["title": "Graph", "description": "New", "icon": "🧠"]]],
        ])
        #expect(changelog?.kind == .changelog(version: "1.2.0", changes: [.init(emoji: "🧠", title: "Graph", text: "New")]))
        let message = AnnouncementMapper.map([
            "id": "a2", "type": "announcement",
            "content": ["title": "Hi", "body": "Body", "cta": ["text": "Open", "action": "navigate:/wrapped"]],
        ])
        #expect(message?.kind == .message(body: "Body", imageURL: nil, buttonTitle: "Open", buttonURL: URL(string: "omi://wrapped")))
        #expect(AnnouncementMapper.link("url:https://omi.me") == URL(string: "https://omi.me"))
        #expect(AnnouncementMapper.link("javascript:alert(1)") == nil)
        #expect(AnnouncementMapper.map(["id": "a3", "type": "unknown", "content": [:]]) == nil)
    }

    @Test func importJobs() {
        let job = ImportJobMapper.map([
            "job_id": "j1", "status": "processing", "total_files": 10, "processed_files": 4,
            "conversations_created": 3, "created_at": "2026-10-07T16:40:41.244286+00:00",
        ])
        #expect(job?.isRunning == true)
        #expect(job?.progress == 0.4)
        #expect(job?.createdAt != nil)
        #expect(ImportJobMapper.map(["job_id": "j2", "status": "weird"])?.status == .failed)
    }
}

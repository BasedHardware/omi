import Foundation
@testable import OmiNetwork
import Testing

struct DeveloperAndAppsMapperTests {
    @Test func listenURLCarriesServerModelAndVADGate() throws {
        var options = ListenSocket.Options(codec: .pcm16, source: .phone)
        options.sttService = "parakeet"
        options.vadGate = true
        let url = ListenSocket.url(base: try #require(URL(string: "https://api.omi.me/")), uid: "u1", options: options)
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        #expect(items.first { $0.name == "stt_service" }?.value == "parakeet")
        #expect(items.first { $0.name == "vad_gate" }?.value == "enabled")
        let base = try #require(URL(string: "https://api.omi.me/"))
        let plain = ListenSocket.url(base: base, uid: "u1", options: .init(codec: .pcm16, source: .phone))
        #expect(plain.query?.contains("stt_service") == false)
        #expect(plain.query?.contains("vad_gate") == false)
    }

    @Test func audioWebhookKeepsItsInterval() {
        #expect(DeveloperWebhook.splitAudio("https://x.example/a,9") == ("https://x.example/a", 9))
        #expect(DeveloperWebhook.splitAudio("https://x.example/a") == ("https://x.example/a", 5))
        #expect(DeveloperWebhook.joinAudio(url: "https://x.example/a", seconds: 3) == "https://x.example/a,3")
        #expect(DeveloperWebhook.joinAudio(url: "", seconds: 3) == "")
    }

    @Test func keyCarriesItsSecretOnlyOnCreate() {
        let created = DeveloperKey.from([
            "id": "k1", "name": "Zapier", "key_prefix": "omi_dev_1e0b...ae0a", "created_at": "2026-10-07T16:07:52.472888Z",
            "last_used_at": NSNull(), "scopes": ["conversations:read"], "key": "omi_dev_secret",
        ])
        #expect(created?.secret == "omi_dev_secret")
        #expect(created?.createdAt != nil)
        #expect(DeveloperKey.from(["id": "k1", "name": "Zapier"])?.secret == nil)
    }

    /// The shape of `GET v1/apps/{id}` (checked against the local backend).
    @Test func appDetailReadsSetupReviewsAndPayment() throws {
        let object: [String: Any] = [
            "id": "app1", "name": "Coach", "description": "Helps", "uid": "alice", "private": false,
            "capabilities": ["chat", "external_integration"], "rating_avg": 4.5, "rating_count": 2, "installs": 10,
            "enabled": false, "is_paid": true, "price": 4.99, "payment_plan": "monthly_recurring",
            "payment_link": "https://buy.stripe.com/x?client_reference_id=uid_alice", "is_user_paid": false,
            "chat_prompt": "Be concise.", "memory_prompt": "",
            "external_integration": [
                "auth_steps": [["name": "Connect", "url": "https://coach.example/auth"]],
                "setup_instructions_file_path": "https://coach.example/setup", "is_instructions_url": true,
                "app_home_url": "https://coach.example/home",
            ],
            "reviews": [
                ["uid": "bob", "score": 5, "review": "Great", "rated_at": "2026-10-01T10:00:00Z", "response": ""],
                ["uid": "eve", "score": 1, "review": "", "rated_at": "2026-10-01T10:00:00Z"],
            ],
            "user_review": ["uid": "alice", "score": 4, "review": "Good", "rated_at": "2026-10-02T10:00:00Z"],
        ]
        let detail = try #require(AppDetail.from(object, uid: "alice"))
        #expect(detail.app.worksWithChat)
        #expect(detail.app.isPaid && detail.needsPurchase)
        #expect(detail.reviews.map(\.uid) == ["bob"])
        #expect(detail.reviews.first?.response == nil)
        #expect(detail.userReview?.score == 4)
        #expect(detail.setupSteps.first?.name == "Connect")
        #expect(detail.setupInstructionsURL?.host() == "coach.example")
        #expect(detail.conversationPrompt == nil)
        #expect(detail.isOwn)
        #expect(detail.shareURL?.absoluteString == "https://h.omi.me/apps/app1")
    }

    @Test func taskAppLevelsMatchTheBackendFields() {
        #expect(TaskAppLevel.levels(for: "asana") == [.asanaWorkspace, .asanaProject])
        #expect(TaskAppLevel.levels(for: "todoist").isEmpty)
        #expect(TaskAppLevel.asanaProject.path(parent: "w1") == "v1/task-integrations/asana/projects/w1")
        #expect(TaskAppLevel.asanaProject.path(parent: nil) == nil)
        #expect(TaskAppLevel.clickupList.fields == ("list_id", "list_name"))
    }
}

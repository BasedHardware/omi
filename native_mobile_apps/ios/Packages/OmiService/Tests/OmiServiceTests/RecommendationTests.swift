import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// "What matters now" on Home: every decision goes back to the backend and hides the card at
/// once; stale ones drop off; the card asks the backend's next action as a question.
@MainActor
struct RecommendationTests {
    private func recommendation(
        _ id: String, action: String = "Send proof of income to landlord", task: String? = "t1", expiresAt: Date? = nil,
        preview: String = "", goal: String? = nil
    ) -> Recommendation {
        Recommendation(
            id: id, headline: "Send proof of income to landlord", whyNow: "Overdue by 2 days.", action: action, taskID: task,
            goalLabel: goal, evidencePreview: preview, dedupeKey: "dedupe-\(id)", expiresAt: expiresAt
        )
    }

    @Test func everyDecisionIsSentAndHidesTheCard() async {
        let api = FakeAPIClient()
        api.recommendations = Recommendation.Decision.allCases.indices.map { recommendation("r\($0)", task: nil) }
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadRecommendations()
        #expect(agent.openRecommendations(tasks: []).count == 5)
        for (index, decision) in Recommendation.Decision.allCases.enumerated() {
            await agent.decide(api.recommendations[index], decision)
        }
        #expect(agent.openRecommendations(tasks: []).isEmpty)
        #expect(api.recommendationFeedback == ["r0=doNow", "r1=later", "r2=dismiss", "r3=complete", "r4=alreadyHandled"])
        // The backend stops returning them; a reload keeps them away.
        await agent.loadRecommendations()
        #expect(agent.openRecommendations(tasks: []).isEmpty)
    }

    @Test func aFailedFeedbackStillHidesItForTheSession() async {
        let api = FakeAPIClient()
        api.recommendations = [recommendation("r1")]
        api.failsRecommendationFeedback = true
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadRecommendations()
        await agent.decide(agent.recommendations[0], .dismiss)
        await agent.loadRecommendations()
        #expect(agent.openRecommendations(tasks: [Fixtures.task("t1", "Proof")]).isEmpty)
    }

    @Test func expiredRecommendationsDropOff() async {
        let api = FakeAPIClient()
        api.recommendations = [
            recommendation("old", expiresAt: Fixtures.now.addingTimeInterval(-1)),
            recommendation("fresh", task: "t2", expiresAt: Fixtures.now.addingTimeInterval(1800)),
            recommendation("open", task: "t3"),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadRecommendations()
        #expect(agent.openRecommendations(tasks: []).map(\.id) == ["fresh", "open"])
    }

    @Test func asksTheNextActionAsAQuestion() {
        #expect(recommendation("a", action: "Send Anna the Thursday follow-up.").question == "Send Anna the Thursday follow-up?")
        #expect(recommendation("b", action: "Call the landlord?").question == "Call the landlord?")
        // Coded alternatives read as their text; an empty action falls back to the headline.
        #expect(recommendation("c", action: "reschedule:Book the physio session").question == "Book the physio session?")
        #expect(recommendation("d", action: "  ").question == "Send proof of income to landlord?")
    }

    @Test func templateReasonsGiveWayAndSpecificOnesStay() {
        let reason = { (text: String) in
            Recommendation(id: "r", headline: "H", whyNow: text, action: "A", taskID: nil).specificWhyNow
        }
        #expect(reason("This task is due today and has a concrete next action.") == nil)
        #expect(reason("This task is overdue by 2 days.") == nil)
        #expect(reason("Due tomorrow.") == nil)
        #expect(reason("The due date has passed.") == nil)
        #expect(reason("") == nil)
        #expect(reason("Anna is waiting on the deck before Friday's board call.") ==
            "Anna is waiting on the deck before Friday's board call.")
        #expect(reason("You're near the pharmacy on Main Street.") == "You're near the pharmacy on Main Street.")
    }

    @Test func goalLabelOnlyWhenItAddsSomething() {
        #expect(recommendation("a", goal: "Send proof of income to landlord").distinctGoalLabel == nil)
        #expect(recommendation("b", goal: "Move to Berlin").distinctGoalLabel == "Move to Berlin")
        #expect(recommendation("c", goal: " ").distinctGoalLabel == nil)
    }

    @Test func originWordsOnlyThePreviewsThatSayWhereItComesFrom() {
        #expect(recommendation("a", preview: "Created directly by you.").origin == .addedByYou)
        #expect(recommendation("b", preview: "Progress is waiting on input.").origin == .waitingOnYou)
        #expect(recommendation("c", preview: "Due in 2 days.").origin == nil)
        #expect(recommendation("d", preview: "Linked to 3 evidence sources.").origin == nil)
        let llmPreview = "Anna asked for it in the roadmap sync"
        #expect(recommendation("e", preview: llmPreview).origin == .text(llmPreview))
    }

    @Test func alternativeVerbAndConversationEvidence() {
        let item = Recommendation(
            id: "r", headline: "H", whyNow: "W", action: "A", taskID: nil, alternativeAction: "reschedule:Send it",
            evidence: [.init(kind: "conversation", id: "c1"), .init(kind: "external", id: "x")]
        )
        #expect(item.alternativeVerb == "reschedule")
        #expect(item.conversationIDs == ["c1"])
        #expect(item.feedbackSubjectID == "r")
    }
}

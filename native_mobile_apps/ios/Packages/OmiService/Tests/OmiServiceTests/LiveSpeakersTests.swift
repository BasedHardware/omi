import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct LiveSpeakersTests {
    static let segments = [
        LiveSegment(id: "s1", text: "Hi there", speaker: "SPEAKER_01", speakerID: 1, isUser: false, start: 0, end: 1),
        LiveSegment(id: "s2", text: "How are you", speaker: "SPEAKER_01", speakerID: 1, isUser: false, start: 1, end: 2),
        LiveSegment(id: "s3", text: "Fine", speaker: "SPEAKER_00", speakerID: 0, isUser: true, start: 2, end: 3),
    ]

    func live(_ api: FakeAPIClient, conversationID: String? = "c-live") async throws -> (CaptureStore, LiveSpeakersStore) {
        let capture = CaptureStore(
            api: api, engine: FakePhoneEngine(), deviceEngine: FakeDeviceTranscription(), preferences: freshPreferences(),
            defaultOnDevice: false, userID: { "alice" }
        )
        await capture.startPhone()
        if let conversationID { api.liveChannel.emit(.conversationStarted(id: conversationID)) }
        api.liveChannel.emit(.segments(Self.segments))
        for _ in 0 ..< 400 where capture.segments.count < 3 || (conversationID != nil && capture.liveConversationID == nil) {
            try await Task.sleep(for: .milliseconds(5))
        }
        return (capture, LiveSpeakersStore(api: api, capture: capture))
    }

    @Test func namingAVoiceLabelsItsLinesAndTellsTheSession() async throws {
        let api = FakeAPIClient()
        let (_, speakers) = try await live(api)
        let anna = Person(id: "p1", name: "Anna", sampleCount: 0)
        await speakers.assign(Self.segments[0], to: .person(anna), scope: .voice)
        #expect(api.speakers.log == ["assign:c-live:voice=1:person:p1"])
        #expect(api.liveChannel.speakerAssignments == ["1:p1:Anna:s1,s2"])
        #expect(speakers.label(for: Self.segments[1]) == .init(isUser: false, personID: "p1"))
        #expect(speakers.label(for: Self.segments[2]) == .init(isUser: true, personID: nil))
        // A later line of the same voice is covered too.
        let later = LiveSegment(id: "s9", text: "Bye", speaker: nil, speakerID: 1, isUser: false, start: 9, end: 10)
        #expect(speakers.label(for: later).personID == "p1")
    }

    @Test func oneLineUsesBulkAssignAndANewName() async throws {
        let api = FakeAPIClient()
        let (_, speakers) = try await live(api)
        let created = await speakers.assign(Self.segments[1], to: .newPerson("Ben"), scope: .line)
        #expect(created?.name == "Ben")
        #expect(api.speakers.log == ["assign:c-live:s2:person:p0"])
        #expect(speakers.label(for: Self.segments[1]).personID == "p0")
        #expect(speakers.label(for: Self.segments[0]).personID == nil)
        #expect(speakers.name(for: "p0") == "Ben")
    }

    @Test func withoutTheSessionEventTheInProgressConversationIsLookedUp() async throws {
        let api = FakeAPIClient()
        api.placesAndHealth.inProgressConversationID = "c-rest"
        let (_, speakers) = try await live(api, conversationID: nil)
        await speakers.assign(Self.segments[0], to: .me, scope: .voice)
        #expect(api.placesAndHealth.inProgressLookups == 1)
        #expect(api.speakers.log == ["assign:c-rest:voice=1:user"])
        #expect(api.liveChannel.speakerAssignments == ["1:user::s1,s2"])
    }

    @Test func aRefusedAssignmentChangesNothing() async throws {
        let api = FakeAPIClient()
        api.speakers.failing = ["assign"]
        let (_, speakers) = try await live(api)
        await speakers.assign(Self.segments[0], to: .me, scope: .voice)
        #expect(speakers.lastError != nil)
        #expect(speakers.label(for: Self.segments[0]) == .init(isUser: false, personID: nil))
        #expect(api.liveChannel.speakerAssignments.isEmpty)
    }
}

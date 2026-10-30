import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
final class FakeSpeechPlayer: SpeechAudioPlaying {
    var played: [String] = []
    var spoken: [String] = []
    var stops = 0

    func play(_ audio: Data) async throws {
        played.append(String(bytes: audio, encoding: .utf8) ?? "")
    }

    func speak(_ text: String) async {
        spoken.append(text)
    }

    func stop() {
        stops += 1
    }
}

@MainActor
func waitUntil(_ condition: () -> Bool) async throws {
    for _ in 0 ..< 200 where !condition() {
        try await Task.sleep(for: .milliseconds(5))
    }
}

@MainActor
struct VoicePlaybackTests {
    let api = FakeAPIClient()
    let player = FakeSpeechPlayer()

    func store(mode: Int, headphones: Bool) -> VoicePlaybackStore {
        let prefs = freshPreferences()
        prefs.set(mode, for: .voiceResponseMode)
        return VoicePlaybackStore(api: api, preferences: prefs, player: player, headphonesConnected: { headphones })
    }

    func answer(_ text: String, failure: ChatMessage.Failure? = nil) -> ChatMessage {
        ChatMessage(id: "a1", text: text, sender: .omi, createdAt: Fixtures.now, failure: failure)
    }

    @Test func replyModeDecides() {
        #expect(!VoicePlaybackStore.readsAloud(mode: .off, headphones: true))
        #expect(!VoicePlaybackStore.readsAloud(mode: .headphonesOnly, headphones: false))
        #expect(VoicePlaybackStore.readsAloud(mode: .headphonesOnly, headphones: true))
        #expect(VoicePlaybackStore.readsAloud(mode: .always, headphones: false))
    }

    @Test func readsFinishedAnswersOnlyWhenTheModeAllows() async throws {
        let speaker = store(mode: 1, headphones: false)
        speaker.answerArrived(answer("Hello there."))
        #expect(speaker.playingID == nil)
        #expect(api.chatExtras.speech.isEmpty)

        let always = store(mode: 2, headphones: false)
        always.answerArrived(answer("**Lunch** with [Ana](https://x.y) at `noon`."))
        try await waitUntil { always.playingID == nil }
        #expect(player.played == ["Lunch with Ana at ."])
        #expect(api.chatExtras.speech.first?.voiceID == nil)
    }

    @Test func failedAnswersAreNeverRead() {
        let always = store(mode: 2, headphones: true)
        always.answerArrived(answer("Hi", failure: .interrupted))
        always.answerArrived(answer(ChatStreamEvent.serviceFailureTexts[0]))
        #expect(always.playingID == nil)
    }

    @Test func speakerButtonPlaysEvenWithRepliesOff() async throws {
        let off = store(mode: 0, headphones: false)
        off.toggle(answer("Read me."))
        #expect(off.playingID == "a1")
        try await waitUntil { off.playingID == nil }
        #expect(player.played == ["Read me."])
    }

    @Test func unavailableVoiceFallsBackToTheSystemVoiceExceptForPreviews() async throws {
        api.chatExtras.speechError = .http(status: 402, body: "")
        let always = store(mode: 2, headphones: false)
        always.answerArrived(answer("Fallback please."))
        try await waitUntil { always.playingID == nil }
        #expect(player.spoken == ["Fallback please."])

        always.preview(voiceID: "Kore", sample: "Hi, I'm Omi.")
        try await waitUntil { always.playingID == nil }
        #expect(always.previewFailed)
        #expect(player.spoken.count == 1)
        #expect(api.chatExtras.speech.last?.voiceID == "Kore")
    }

    @Test func longAnswersArriveInSentencePieces() {
        let sentence = String(repeating: "word ", count: 30) + "end."
        let chunks = VoicePlaybackStore.chunks(Array(repeating: sentence, count: 10).joined(separator: " "))
        #expect(chunks.count > 1)
        #expect(chunks.allSatisfy { $0.count <= VoicePlaybackStore.chunkLimit })
        #expect(VoicePlaybackStore.chunks("").isEmpty)
    }
}

@MainActor
struct ChatExtrasTests {
    func settled(_ chat: ChatStore) async throws {
        try await waitUntil { !chat.isStreaming }
    }

    @Test func ratingUsesTheStoredIdAndRollsBack() async throws {
        let api = FakeAPIClient()
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.send("Hi")
        try await settled(chat)
        let reply = try #require(chat.messages.last)
        #expect(reply.serverID == "reply-1")

        #expect(await chat.rate(reply.id, value: 1))
        #expect(chat.messages.last?.rating == 1)
        #expect(await chat.rate(reply.id, value: -1, reason: "too_verbose"))
        #expect(api.chatExtras.ratings.map(\.value) == [1, -1])
        #expect(api.chatExtras.ratings.last?.reason == "too_verbose")
        #expect(api.chatExtras.ratings.allSatisfy { $0.id == "reply-1" })

        api.chatExtras.ratingError = .http(status: 500, body: "")
        #expect(await !chat.rate(reply.id, value: 0))
        #expect(chat.messages.last?.rating == -1)
    }

    @Test func clearChatEmptiesOnlyTheMainSession() async {
        let api = FakeAPIClient()
        api.existingSessions = [("main", "Chat")]
        let chat = ChatStore(api: api, preferences: freshPreferences())
        await chat.loadHistory()
        #expect(await chat.clearChat())
        #expect(api.chatExtras.clearedSessions == ["main"])
        #expect(chat.messages.map(\.id) == ["greeting-2"])
        #expect(!chat.hasEarlier)
    }

    @Test func attachmentsUploadFirstAndTravelWithTheMessage() async throws {
        let api = FakeAPIClient()
        api.chatExtras.uploadDelay = .milliseconds(60)
        let chat = ChatStore(api: api, preferences: freshPreferences())
        await chat.loadHistory()
        chat.attach(data: Data([1]), filename: "photo.jpg", mimeType: "image/jpeg", preview: Data([9]))
        chat.attach(data: Data([2]), filename: "notes.pdf", mimeType: "application/pdf", preview: nil)
        #expect(chat.isUploading)
        chat.send("What is this?")
        #expect(!chat.isStreaming) // waits for the uploads

        try await waitUntil { !chat.isUploading }
        chat.send("What is this?")
        try await settled(chat)
        #expect(api.chatExtras.sentFileIDs.last?.count == 2)
        let question = try #require(chat.messages.last { $0.sender == .user })
        #expect(question.files.map(\.name) == ["photo.jpg", "notes.pdf"])
        #expect(question.files.first?.localPreview == Data([9]))
        #expect(chat.attachments.isEmpty)
    }

    @Test func attachmentsAreCappedAndFailuresStayVisible() async throws {
        let api = FakeAPIClient()
        api.chatExtras.uploadError = .http(status: 400, body: "")
        let chat = ChatStore(api: api, preferences: freshPreferences())
        for index in 0 ..< 6 {
            chat.attach(data: Data(), filename: "f\(index).txt", mimeType: "text/plain", preview: nil)
        }
        #expect(chat.attachments.count == ChatStore.maxAttachments)
        try await waitUntil { !chat.isUploading }
        #expect(chat.attachments.allSatisfy { $0.state == .failed })
        chat.removeAttachment(chat.attachments[0].id)
        #expect(chat.attachments.count == 3)
    }

    @Test func followUpAndChartArriveWithTheAnswer() async throws {
        let api = FakeAPIClient()
        api.chatExtras.followUp = "Want the notes from Tuesday?"
        api.chatExtras.chart = ChatChart(
            kind: .bar, title: "Steps", xLabel: nil, yLabel: nil,
            series: [.init(label: "Steps", points: [.init(label: "Mon", value: 4)], color: nil)]
        )
        let chat = ChatStore(api: api, preferences: freshPreferences())
        var answered: [String] = []
        chat.onAnswer = { answered.append($0.text) }
        chat.send("How did I sleep?")
        try await settled(chat)
        #expect(chat.messages.last?.followUp == "Want the notes from Tuesday?")
        #expect(chat.messages.last?.chart?.series.first?.points.count == 1)
        #expect(answered == [api.chatReply])
    }

    @Test func failuresGetTheirOwnWording() async throws {
        let api = FakeAPIClient()
        api.chatExtras.streamErrorCode = "quota_exceeded"
        api.chatExtras.doneText = "You've hit your monthly limit."
        let chat = ChatStore(api: api, preferences: freshPreferences())
        var answered = 0
        chat.onAnswer = { _ in answered += 1 }
        chat.send("Hi")
        try await settled(chat)
        #expect(chat.messages.last?.failure == .quotaExceeded)
        #expect(answered == 0)

        api.chatExtras.streamErrorCode = nil
        api.chatExtras.doneText = ChatStreamEvent.serviceFailureTexts[2]
        chat.send("Again")
        try await settled(chat)
        #expect(chat.messages.last?.failure == .timeout)

        api.chatExtras.streamError = URLError(.notConnectedToInternet)
        chat.send("Offline?")
        try await settled(chat)
        #expect(chat.messages.last?.failure == .offline)
    }

    @Test func errorMapping() {
        #expect(ChatStore.failure(for: URLError(.timedOut), offline: false) == .timeout)
        #expect(ChatStore.failure(for: URLError(.networkConnectionLost), offline: false) == .offline)
        #expect(ChatStore.failure(for: APIError.http(status: 402, body: ""), offline: false) == .quotaExceeded)
        #expect(ChatStore.failure(for: APIError.http(status: 500, body: ""), offline: false) == .couldNotAnswer)
        #expect(ChatStore.failure(for: APIError.http(status: 500, body: ""), offline: true) == .offline)
        #expect(ChatStore.failure(forStreamCode: "server_error", offline: false) == .couldNotAnswer)
        #expect(ChatStore.failure(forStreamCode: "timeout", offline: false) == .timeout)
    }
}

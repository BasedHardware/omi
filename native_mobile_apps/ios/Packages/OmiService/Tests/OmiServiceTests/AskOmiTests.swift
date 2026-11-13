import Foundation
import OmiCore
import OmiDevice
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct AskOmiTests {
    final class Harness {
        let api = FakeAPIClient()
        var haptics: [OmiGATT.Haptic] = []
        var allowed = true
        var answers: [String] = []
        var codec: OmiGATT.Codec? = .opusFS320
    }

    func make(_ harness: Harness, maxDuration: Duration = .seconds(15)) -> (AskOmiStore, ChatStore) {
        let chat = ChatStore(api: harness.api, preferences: freshPreferences())
        let store = AskOmiStore(
            chat: chat,
            codec: { harness.codec },
            haptic: { harness.haptics.append($0) },
            canAsk: { harness.allowed },
            maxDuration: maxDuration
        )
        store.onAnswer = { harness.answers.append($0) }
        return (store, chat)
    }

    /// With the iPhone's recognizer: frames pass through as PCM, words come from `recognizer`.
    func makeOnDevice(
        _ harness: Harness, recognizer: FakeRecognizer, answerTimeout: Duration = .seconds(30)
    ) -> (AskOmiStore, ChatStore) {
        let chat = ChatStore(api: harness.api, preferences: freshPreferences())
        let store = AskOmiStore(
            chat: chat,
            codec: { harness.codec },
            haptic: { harness.haptics.append($0) },
            canAsk: { harness.allowed },
            recognizer: recognizer,
            language: { "en" },
            makeDecoder: { _ in { $0 } },
            pauseToSend: .milliseconds(300),
            answerTimeout: answerTimeout
        )
        store.onAnswer = { harness.answers.append($0) }
        return (store, chat)
    }

    func waitUntil(_ condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(10))
        }
    }

    func reply(_ question: String, _ answer: String) -> [VoiceMessageEvent] {
        let human = ChatMessage(id: "q1", text: question, sender: .user, createdAt: .now)
        return [.question(human), .chat(.delta(answer))]
    }

    /// Press, speak, press: the Omi's frames go to `v2/voice-messages` in Flutter's file format.
    @Test func pressRecordsAndSecondPressSends() async {
        let harness = Harness()
        harness.api.deviceActions.replyToVoice(reply("What's next?", "Your 3 pm call."))
        let (store, chat) = make(harness)
        store.ingest(Data([9]))
        store.handle(.askToggle)
        #expect(store.isListening)
        store.ingest(Data([0xAA, 0xBB]))
        store.ingest(Data([0xCC]))
        store.handle(.askToggle)
        await store.sendTask?.value
        let upload = harness.api.deviceActions.voiceUploads.first
        #expect(upload?.filename.hasPrefix("audio_omi_opus_fs320_16000_1_fs320_") == true)
        #expect(upload?.audio == Data([2, 0, 0, 0, 0xAA, 0xBB, 1, 0, 0, 0, 0xCC]))
        #expect(harness.haptics == [.short, .medium])
        #expect(harness.answers == ["Your 3 pm call."])
        #expect(chat.messages.suffix(2).map(\.text) == ["What's next?", "Your 3 pm call."])
        #expect(store.phase == .idle)
    }

    @Test func nothingRecordedSendsNothing() async throws {
        let harness = Harness()
        let (store, _) = make(harness)
        store.handle(.askToggle)
        store.handle(.askToggle)
        // The second "nothing heard" buzz follows 80 ms later; wait for it rather than a fixed time.
        for _ in 0 ..< 400 where harness.haptics.count < 3 {
            try await Task.sleep(for: .milliseconds(5))
        }
        #expect(harness.api.deviceActions.voiceUploads.isEmpty)
        #expect(harness.haptics == [.short, .short, .short])
    }

    @Test func noSpeechLeavesTheChatAlone() async {
        let harness = Harness()
        harness.api.deviceActions.replyToVoice([.noSpeech])
        let (store, chat) = make(harness)
        store.handle(.askToggle)
        store.ingest(Data([1]))
        store.handle(.askToggle)
        await store.sendTask?.value
        #expect(chat.messages.allSatisfy { !$0.id.hasPrefix("voice-") && !$0.id.hasPrefix("pending-") })
        #expect(harness.answers.isEmpty)
    }

    @Test func heldPressSendsOnRelease() async {
        let harness = Harness()
        harness.api.deviceActions.replyToVoice(reply("Hi", "Hello"))
        let (store, _) = make(harness)
        // A plain release (sent after every tap) does not end a toggled question.
        store.handle(.askToggle)
        store.handle(.askHoldEnd)
        #expect(store.isListening)
        store.handle(.askToggle)
        store.handle(.askHoldStart)
        store.ingest(Data([1]))
        store.handle(.askHoldEnd)
        await store.sendTask?.value
        #expect(harness.api.deviceActions.voiceUploads.count == 1)
    }

    @Test func mutedOrDisabledOmiAsksNothing() async throws {
        let harness = Harness()
        harness.allowed = false
        let (store, _) = make(harness)
        store.handle(.askToggle)
        #expect(!store.isListening)
        harness.allowed = true
        store.handle(.askToggle)
        store.ingest(Data([1]))
        harness.allowed = false
        store.handle(.askToggle)
        try await Task.sleep(for: .milliseconds(20))
        #expect(harness.api.deviceActions.voiceUploads.isEmpty)
        #expect(store.phase == .idle)
    }

    @Test func sendsByItselfAfterTheLimit() async throws {
        let harness = Harness()
        harness.api.deviceActions.replyToVoice(reply("Hi", "Hello"))
        let (store, _) = make(harness, maxDuration: .milliseconds(10))
        store.handle(.askToggle)
        store.ingest(Data([1]))
        for _ in 0 ..< 200 where harness.answers.isEmpty {
            try await Task.sleep(for: .milliseconds(5))
        }
        #expect(harness.answers == ["Hello"])
        // The press that meant to stop it right after is swallowed, not a new question.
        store.handle(.askToggle)
        #expect(!store.isListening)
    }

    // MARK: Transcribed on the iPhone

    /// A real press: "Hello can you hear me?" shows word by word, goes out as a chat question
    /// (not to `v2/voice-messages`, which a local backend cannot serve), and the answer comes back.
    @Test func theQuestionIsTranscribedOnTheIPhoneAndAskedAsText() async throws {
        let harness = Harness()
        harness.api.chatReply = "Yes, I can hear you."
        let recognizer = FakeRecognizer()
        let (store, chat) = makeOnDevice(harness, recognizer: recognizer)
        store.handle(.askToggle)
        try await waitUntil { recognizer.started > 0 }
        #expect(recognizer.languages == ["en"])
        store.ingest(Data([1, 0, 2, 0]))
        recognizer.say("q", "Hello")
        try await waitUntil { store.question == "Hello" }
        recognizer.say("q", "Hello can you hear me")
        try await waitUntil { store.question == "Hello can you hear me" }
        #expect(store.isListening)
        #expect(recognizer.fed > 0)
        // A pause after the words sends it by itself.
        try await waitUntil { store.lastExchange != nil }
        #expect(store.lastExchange == .init(question: "Hello can you hear me", answer: "Yes, I can hear you."))
        #expect(harness.api.deviceActions.voiceUploads.isEmpty)
        #expect(chat.messages.suffix(2).map(\.text) == ["Hello can you hear me", "Yes, I can hear you."])
        #expect(harness.answers == ["Yes, I can hear you."])
        #expect(store.phase == .idle)
        #expect(store.problem == nil)
    }

    @Test func aSecondPressSendsWhatWasSaidSoFar() async throws {
        let harness = Harness()
        let recognizer = FakeRecognizer()
        let (store, _) = makeOnDevice(harness, recognizer: recognizer)
        store.handle(.askToggle)
        try await waitUntil { recognizer.started > 0 }
        recognizer.say("q1", "What's on")
        recognizer.say("q2", "my calendar")
        try await waitUntil { store.question == "What's on my calendar" }
        store.handle(.askToggle)
        #expect(store.phase == .sending)
        try await waitUntil { store.phase == .idle }
        #expect(store.lastExchange?.question == "What's on my calendar")
    }

    @Test func nothingSaidEndsWithAClearProblem() async throws {
        let harness = Harness()
        let recognizer = FakeRecognizer()
        let (store, _) = makeOnDevice(harness, recognizer: recognizer)
        store.handle(.askToggle)
        try await waitUntil { recognizer.started > 0 }
        store.ingest(Data([0, 0]))
        store.handle(.askToggle)
        try await waitUntil { store.phase == .idle }
        #expect(store.problem == .nothingHeard)
        #expect(harness.api.deviceActions.voiceUploads.isEmpty)
    }

    @Test func anAnswerThatNeverComesTimesOut() async throws {
        let harness = Harness()
        harness.api.chatExtras.hangs = true
        let recognizer = FakeRecognizer()
        let (store, chat) = makeOnDevice(harness, recognizer: recognizer, answerTimeout: .milliseconds(200))
        store.handle(.askToggle)
        try await waitUntil { recognizer.started > 0 }
        recognizer.say("q", "Are you there")
        try await waitUntil { store.question == "Are you there" }
        store.handle(.askToggle)
        try await waitUntil { store.phase == .idle }
        #expect(store.problem == .noAnswer)
        // The chat is free again, and a new press asks again.
        try await waitUntil { !chat.isStreaming }
        store.handle(.askToggle)
        #expect(store.isListening)
        #expect(store.problem == nil)
    }

    @Test func withoutTheIPhonesRecognizerTheRecordingGoesToTheServer() async throws {
        let harness = Harness()
        harness.api.deviceActions.replyToVoice(reply("Hi", "Hello"))
        let recognizer = FakeRecognizer()
        recognizer.available = false
        let (store, _) = makeOnDevice(harness, recognizer: recognizer)
        store.handle(.askToggle)
        try await waitUntil { !recognizer.languages.isEmpty }
        store.ingest(Data([1]))
        store.handle(.askToggle)
        try await waitUntil { store.phase == .idle }
        #expect(harness.api.deviceActions.voiceUploads.count == 1)
        #expect(harness.answers == ["Hello"])
    }

    /// On Home the capture already runs the iPhone's recognizer on the Omi's audio (its live
    /// words); Apple's recognizer does not run twice, so the question is read from that line.
    @Test func whileTheCaptureListensTheQuestionComesFromItsLine() async throws {
        let harness = Harness()
        harness.api.chatReply = "Sunny, 21 degrees."
        let recognizer = FakeRecognizer()
        let chat = ChatStore(api: harness.api, preferences: freshPreferences())
        let line = LineBox()
        line.value = LiveSegment(
            id: "c1", text: "We were talking about lunch", speaker: nil, speakerID: nil, isUser: true, start: 0, end: 2
        )
        let store = AskOmiStore(
            chat: chat, codec: { harness.codec }, haptic: { harness.haptics.append($0) }, canAsk: { true },
            recognizer: recognizer, makeDecoder: { _ in { $0 } },
            sharedLine: { SharedLine(line: line.value) }, pauseToSend: .milliseconds(400)
        )
        store.handle(.askToggle)
        line.value = LiveSegment(
            id: "c1", text: "We were talking about lunch what's the weather", speaker: nil, speakerID: nil, isUser: true, start: 0, end: 3
        )
        try await waitUntil { store.question == "what's the weather" }
        line.value = LiveSegment(id: "c1.1", text: "tomorrow in Berlin", speaker: nil, speakerID: nil, isUser: true, start: 3, end: 4)
        try await waitUntil { store.question == "what's the weather tomorrow in Berlin" }
        try await waitUntil { store.lastExchange != nil }
        #expect(store.lastExchange?.question == "what's the weather tomorrow in Berlin")
        #expect(store.lastExchange?.answer == "Sunny, 21 degrees.")
        #expect(recognizer.started == 0)
    }
}

/// A line the test changes while the store reads it.
@MainActor
final class LineBox {
    var value: LiveSegment?
}

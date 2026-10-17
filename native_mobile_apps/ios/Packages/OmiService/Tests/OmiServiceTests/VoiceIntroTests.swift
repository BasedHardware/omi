import Foundation
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

/// Audio the test pushes by hand: one chunk at a time.
final class ScriptedVoiceInput: VoiceInput, @unchecked Sendable {
    private var continuation: AsyncStream<Data>.Continuation?
    private(set) var stopped = false

    func start() async throws -> AsyncStream<Data> {
        let (stream, continuation) = AsyncStream.makeStream(of: Data.self)
        self.continuation = continuation
        return stream
    }

    /// Seconds of a loud tone (well above the speech level), in 0.5 s chunks.
    func speak(seconds: Double = 1) {
        push(seconds: seconds, amplitude: 8000)
    }

    /// Seconds of silence: a pause.
    func pause(seconds: Double = 1) {
        push(seconds: seconds, amplitude: 0)
    }

    /// Seconds of steady background noise (an Omi microphone with gain hears the room).
    func noise(seconds: Double = 1, amplitude: Int16 = 650) {
        push(seconds: seconds, amplitude: amplitude)
    }

    /// A whisper: words come, the level stays under the speech threshold.
    func whisper(seconds: Double = 1) {
        push(seconds: seconds, amplitude: 150)
    }

    private func push(seconds: Double, amplitude: Int16) {
        for _ in 0 ..< Int(seconds * 2) {
            var samples = [Int16](repeating: 0, count: 8000)
            for index in samples.indices { samples[index] = index % 2 == 0 ? amplitude : -amplitude }
            continuation?.yield(samples.withUnsafeBytes { Data($0) })
        }
    }

    func stop() {
        stopped = true
        continuation?.finish()
    }
}

final class FakeRecognizer: LiveRecognizer, @unchecked Sendable {
    /// False: the iPhone cannot recognize this language (or has no permission).
    var available = true
    private(set) var started = 0
    private(set) var languages: [String] = []
    private(set) var fed = 0
    private(set) var utterances = 0
    var continuation: AsyncStream<LiveSegment>.Continuation?

    func start(language: String) async -> AsyncStream<LiveSegment>? {
        languages.append(language)
        guard available else { return nil }
        started += 1
        let (stream, continuation) = AsyncStream.makeStream(of: LiveSegment.self)
        self.continuation = continuation
        return stream
    }

    func feed(_: Data) {
        fed += 1
    }

    func startNewUtterance() {
        utterances += 1
    }

    func stop() {
        continuation?.finish()
    }

    func say(_ id: String, _ text: String) {
        continuation?.yield(LiveSegment(id: id, text: text, speaker: nil, speakerID: nil, isUser: true, start: 0, end: 1))
    }
}

@MainActor
struct VoiceIntroTests {
    let api = FakeAPIClient()
    let input = ScriptedVoiceInput()
    let recognizer = FakeRecognizer()
    static let templates = [
        "My name is ___ and I spend most of my time ___.",
        "Right now I'm working on ___.",
        "In my free time I love ___.",
    ]

    func makeStore() -> VoiceIntroStore {
        VoiceIntroStore(api: api, recognizer: recognizer, phoneInput: input, deviceInput: { ScriptedVoiceInput() })
    }

    func segment(_ id: String, _ text: String) -> LiveSegment {
        LiveSegment(id: id, text: text, speaker: nil, speakerID: nil, isUser: true, start: 0, end: 1)
    }

    func settle() async {
        for _ in 0 ..< 30 {
            await Task.yield()
        }
        try? await Task.sleep(for: .milliseconds(30))
        for _ in 0 ..< 30 {
            await Task.yield()
        }
    }

    // MARK: Where the words come from

    @Test func theIPhonesRecognizerIsTheFirstSourceOfWords() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        #expect(store.wordSource == .onDevice)
        #expect(api.liveChannel.audioBytes == 0)
        input.speak()
        recognizer.say("a", "Hello")
        recognizer.say("a", "Hello Omi")
        await settle()
        #expect(store.transcript == "Hello Omi")
        #expect(recognizer.fed > 0)
        #expect(store.firstWordsLatency != nil)
    }

    @Test func withoutOnDeviceRecognitionTheServerTranscribes() async {
        recognizer.available = false
        let store = makeStore()
        await store.start(source: .phone, language: "xx")
        #expect(store.wordSource == .server)
        api.liveChannel.emit(.segments([segment("a", "Hello")]))
        api.liveChannel.emit(.segments([segment("a", "Hello Omi")]))
        await settle()
        #expect(store.transcript == "Hello Omi")
    }

    @Test func speechWithoutWordsHandsOverToTheServerAndReplaysTheAudio() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        input.speak(seconds: 1.5)
        await settle()
        #expect(store.wordSource == .onDevice)
        input.speak(seconds: 1.5)
        await settle()
        #expect(store.wordSource == .server)
        // The last seconds went to the server too, so the words said meanwhile are not lost.
        #expect(api.liveChannel.audioBytes > 0)
        api.liveChannel.emit(.segments([segment("s", "Can you hear me")]))
        await settle()
        #expect(store.transcript == "Can you hear me")
    }

    @Test func aServerThatStopsTranscribingHandsBackToTheIPhone() async {
        recognizer.available = false
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        #expect(store.wordSource == .server)
        recognizer.available = true
        api.liveChannel.emit(.status("stt_failed"))
        await settle()
        #expect(store.wordSource == .onDevice)
        recognizer.say("p", "Spoken on the phone")
        input.speak()
        await settle()
        #expect(store.transcript == "Spoken on the phone")
    }

    @Test func whenNeitherGivesWordsTheSentencesMoveOnBySpeech() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates)
        input.speak(seconds: 3)
        await settle()
        // On-device gave nothing, so the server got its turn; it gives nothing either, and the
        // iPhone gets one more try before the sentences go by speech alone.
        #expect(store.wordSource == .server)
        input.speak(seconds: 3)
        await settle()
        #expect(store.wordSource == .onDevice)
        input.speak(seconds: 3)
        await settle()
        // Out of turns: the iPhone keeps listening (it may still bring words), and the sentence
        // moves on by speech.
        #expect(store.wordSource == .onDevice)
        #expect(store.heardSomething)
        input.pause()
        await settle()
        #expect(store.promptIndex == 1)
    }

    // MARK: Sentences and progress

    @Test func aCompleteSentenceAndAPauseMoveToTheNextWithAStep() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates)
        #expect(store.progress == 0)
        input.speak(seconds: 1)
        recognizer.say("u1", "My name is Ada")
        await settle()
        #expect(store.match?.blanks.first == "Ada")
        #expect(store.match?.isComplete == false)
        let partial = store.progress
        #expect(partial > 0 && partial < 1.0 / 3)
        // Still talking: no move yet, even with the sentence complete.
        recognizer.say("u1", "My name is Ada and I spend most of my time building apps")
        input.speak(seconds: 0.5)
        await settle()
        #expect(store.promptIndex == 0)
        input.pause()
        await settle()
        #expect(store.promptIndex == 1)
        #expect(store.progress >= 1.0 / 3)
        #expect(store.answers.map(\.text) == ["My name is Ada and I spend most of my time building apps"])
        // Each sentence starts a fresh utterance on the iPhone's recognizer.
        #expect(recognizer.utterances >= 2)
    }

    @Test func anIncompleteSentenceWaitsForMore() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates)
        input.speak(seconds: 1)
        recognizer.say("u1", "My name is Ada")
        input.pause(seconds: 2)
        await settle()
        #expect(store.promptIndex == 0)
    }

    @Test func theLastSentenceSavesTheVoiceAndTheAnswers() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates)
        let said = [
            "My name is Ada and I spend most of my time building apps",
            "Right now I'm working on a new onboarding",
            "In my free time I love cooking",
        ]
        for (index, text) in said.enumerated() {
            // Words arrive while speaking, as from a real recognizer.
            let words = text.split(separator: " ")
            for part in 1 ... 3 {
                input.speak(seconds: 1)
                recognizer.say("u\(index)", words.prefix(words.count * part / 3).joined(separator: " "))
                await settle()
            }
            input.pause()
            await settle()
        }
        #expect(store.phase == .saved)
        #expect(store.answers.map(\.text) == said)
        let wav = try? #require(api.uploadedVoice)
        #expect(wav.flatMap { String(bytes: $0.prefix(4), encoding: .ascii) } == "RIFF")
        #expect(input.stopped)

        await store.saveAnswers()
        #expect(api.createdMemories == said)
    }

    @Test func tooLittleSpeechAsksForOneMoreSentence() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates)
        let said = ["My name is Ada and I spend most of my time coding", "Right now I'm working on Omi", "In my free time I love tea"]
        for (index, text) in said.enumerated() {
            input.speak(seconds: 1)
            recognizer.say("u\(index)", text)
            await settle()
            input.pause()
            await settle()
        }
        // Three seconds of speech: below the minimum the voice profile needs.
        #expect(store.needsMore)
        #expect(api.uploadedVoice == nil)
        #expect(store.isListening)
        #expect(store.sentence == .free)
        input.speak(seconds: 6)
        recognizer.say("more", "Today I walked to the office and met a friend")
        await settle()
        input.pause()
        await settle()
        #expect(store.phase == .saved)
        #expect(api.uploadedVoice != nil)
    }

    @Test func aFailedUploadKeepsTheRecordingForARetry() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates)
        input.speak(seconds: 10)
        recognizer.say("s", "Plenty of words.")
        await settle()
        api.fail(with: .http(status: 503, body: ""))
        await store.saveVoice()
        #expect(store.phase == .failed(.upload))
        api.fail(with: nil)
        await store.retryUpload()
        #expect(store.phase == .saved)
        #expect(api.uploadedVoice != nil)
    }

    @Test func speechCountsAsHeardBeforeAnyWords() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        #expect(!store.heardSomething)
        store.beginTraining(templates: Self.templates)
        input.speak(seconds: 2)
        await settle()
        #expect(store.heardSomething)
        #expect(store.canAdvance)
        store.nextPrompt()
        #expect(!store.canAdvance)
    }
}

@MainActor
struct OnboardingPathTests {
    func makeStore() -> OnboardingStore {
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        return OnboardingStore(api: FakeAPIClient(), preferences: Preferences(defaults: defaults), updateDisplayName: { _ in })
    }

    @Test func withAnOmiThePathPairsAndExplainsTheLight() {
        let store = makeStore()
        store.step = .hasOmi
        store.chooseOmi(true)
        #expect(store.step == .pair)
        store.next()
        #expect(store.step == .lights)
        store.next()
        #expect(store.step == .hello)
        #expect(store.voiceSource == .device)
    }

    @Test func withoutOneTheIPhoneStandsInAndPairingIsLeftOut() {
        let store = makeStore()
        store.step = .hasOmi
        store.chooseOmi(false)
        #expect(store.step == .hello)
        #expect(store.voiceSource == .phone)
        #expect(!store.path.contains(.pair))
        store.back()
        #expect(store.step == .hasOmi)
    }

    @Test func givingUpOnPairingContinuesWithTheIPhone() {
        let store = makeStore()
        store.step = .hasOmi
        store.chooseOmi(true)
        store.continueWithoutOmi()
        #expect(store.step == .hello)
        #expect(store.voiceSource == .phone)
    }

    @Test func setupEndsInTheReadyMomentAndTheIntroduction() {
        let store = makeStore()
        store.step = .setup
        store.next()
        #expect(store.step == .ready)
        #expect(store.path.last == .ready)
    }
}

struct TranscriptionLanguageTests {
    @Test func mixableLanguagesTranscribeTogether() {
        #expect(TranscriptionLanguage.code(main: "de", spoken: ["de", "en"]) == "multi")
        #expect(TranscriptionLanguage.code(main: "de", spoken: ["de", "en-GB"]) == "multi")
        #expect(TranscriptionLanguage.code(main: "de", spoken: ["de"]) == "de")
        // Arabic is not in nova-3's multi set: the main language is used.
        #expect(TranscriptionLanguage.code(main: "ar", spoken: ["ar", "en"]) == "ar")
    }
}

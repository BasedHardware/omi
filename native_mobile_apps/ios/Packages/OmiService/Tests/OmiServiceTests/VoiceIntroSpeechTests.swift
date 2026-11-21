import Foundation
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

/// Onboarding's voice steps with segment sequences as Apple's recognizer really sends them: the
/// whole line again under one id while it grows, a new id (or a line that starts over) after a
/// pause, lag between speech and words, a noisy Omi microphone, a whisper.
@MainActor
struct VoiceIntroSpeechTests {
    let api = FakeAPIClient()
    let input = ScriptedVoiceInput()
    let recognizer = FakeRecognizer()

    func makeStore() -> VoiceIntroStore {
        // The Omi path hears the same scripted audio as the iPhone one.
        let input = input
        return VoiceIntroStore(api: api, recognizer: recognizer, phoneInput: input, deviceInput: { input })
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

    /// Speaks `text` as a recognizer reports it: the line growing word by word under `id`.
    func say(_ text: String, id: String, seconds: Double = 2) async {
        let words = text.split(separator: " ")
        let steps = 4
        for step in 1 ... steps {
            input.speak(seconds: seconds / Double(steps))
            recognizer.say(id, words.prefix(max(1, words.count * step / steps)).joined(separator: " "))
            await settle()
        }
    }

    // MARK: The whisper demo ("Omi hears you")

    @Test func everyUtteranceStaysInTheRunningTranscript() async {
        let store = makeStore()
        await store.start(source: .device, language: "en")
        await say("You", id: "a", seconds: 0.5)
        await say("Hello can you hear me", id: "a")
        input.pause(seconds: 1.5)
        await settle()
        // After the pause the recognizer starts a new utterance under a new id.
        await say("I am talking to my Omi right now", id: "a.1")
        input.pause()
        await say("And this is the third thing I say", id: "b")
        #expect(store.transcript == "Hello can you hear me I am talking to my Omi right now And this is the third thing I say")
    }

    @Test func aWorkingRecognizerIsNotDroppedWhileItLags() async {
        let store = makeStore()
        await store.start(source: .device, language: "en")
        await say("Hello can you hear me", id: "a")
        // Five more seconds of talking before the recognizer catches up (or a noisy room).
        input.speak(seconds: 5)
        await settle()
        #expect(store.wordSource == .onDevice)
        recognizer.say("a.1", "I keep on talking")
        await settle()
        #expect(store.transcript == "Hello can you hear me I keep on talking")
    }

    @Test func handingOverKeepsTheEarlierWords() async {
        let store = makeStore()
        await store.start(source: .device, language: "en")
        await say("Hello there", id: "a")
        // The iPhone stops giving words for a long stretch of speech: the server gets a turn.
        input.speak(seconds: 9)
        await settle()
        #expect(store.wordSource == .server)
        let server = LiveSegment(id: "s1", text: "and now the server", speaker: nil, speakerID: nil, isUser: true, start: 0, end: 1)
        api.liveChannel.emit(.segments([server]))
        await settle()
        #expect(store.transcript == "Hello there and now the server")
    }

    @Test func outOfTurnsTheLastSourceKeepsListening() async {
        let store = makeStore()
        await store.start(source: .device, language: "en")
        for _ in 0 ..< 4 {
            input.speak(seconds: 3)
            await settle()
        }
        #expect(store.wordSource != .none)
        recognizer.say("late", "Finally some words")
        await settle()
        if store.wordSource == .onDevice { #expect(store.transcript == "Finally some words") }
    }

    @Test func listensInTheFirstPickedLanguage() async {
        // A German iPhone, an English speaker who picked English first.
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let preferences = Preferences(defaults: defaults)
        preferences.set("de", for: .userPrimaryLanguage)
        let onboarding = OnboardingStore(api: api, preferences: preferences, updateDisplayName: { _ in })
        onboarding.toggleLanguage("en")
        onboarding.toggleLanguage("de")
        #expect(onboarding.language == "en")
        let store = makeStore()
        await store.start(source: .phone, language: onboarding.language)
        #expect(recognizer.languages == ["en"])
        // Going back and picking another main language restarts the recognizer in it.
        await store.start(source: .phone, language: "de")
        #expect(recognizer.languages == ["en", "de"])
    }

    // MARK: The voice sample

    static let templates = [
        "My name is ___ and I spend most of my time ___.",
        "Right now I'm working on ___.",
        "In my free time I love ___.",
    ]

    /// Three sentences, said in English through the Omi in a room with some noise.
    @Test func threeSpokenSentencesCompleteAndSaveTheVoice() async {
        let store = makeStore()
        await store.start(source: .device, language: "en")
        store.beginTraining(templates: Self.templates, extra: "Today I ___.")
        let said = [
            "My name is Alex and I spend most of my time doing work",
            "Right now I'm working on something interesting",
            "In my free time I love to play football",
        ]
        for (index, text) in said.enumerated() {
            await say(text, id: "u\(index)", seconds: 3.5)
            input.noise(seconds: 1.2)
            await settle()
            #expect(store.promptIndex == min(index + 1, 2) || store.phase == .saved)
        }
        input.noise(seconds: 1)
        await settle()
        #expect(store.phase == .saved)
        #expect(store.answers.map(\.text) == said)
        #expect(!store.needsMore)
        #expect(api.uploadedVoice != nil)
    }

    @Test func aParaphrasedSentenceStillCounts() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates)
        await say("I'm Alex and mostly I build things for people all day", id: "p")
        input.pause()
        await settle()
        #expect(store.promptIndex == 1)
    }

    @Test func aWhisperedSampleCountsByItsWords() async {
        let store = makeStore()
        await store.start(source: .device, language: "en")
        store.beginTraining(templates: Self.templates)
        let said = [
            "My name is Alex and I spend most of my time doing work at the office",
            "Right now I'm working on something interesting for a new company",
            "In my free time I love to play football with my friends on Sundays",
        ]
        for (index, text) in said.enumerated() {
            let words = text.split(separator: " ")
            for step in 1 ... 4 {
                input.whisper(seconds: 0.5)
                recognizer.say("w\(index)", words.prefix(words.count * step / 4).joined(separator: " "))
                await settle()
            }
            input.pause()
            await settle()
        }
        await settle()
        #expect(store.phase == .saved)
        #expect(!store.needsMore)
    }

    @Test func tooShortAsksForTheExtraSentenceWithAnExample() async {
        let store = makeStore()
        await store.start(source: .phone, language: "en")
        store.beginTraining(templates: Self.templates, extra: "Today I ___.")
        let short = ["My name is Al and I spend most of my time working", "Right now I'm working on apps", "In my free time I love tea"]
        for (index, text) in short.enumerated() {
            input.speak(seconds: 1)
            recognizer.say("x\(index)", text)
            await settle()
            input.pause()
            await settle()
        }
        #expect(store.needsMore)
        #expect(store.sentence == GapSentence("Today I ___."))
        // The extra sentence is said; the sample is long enough only after it.
        await say("Today I walked to the office and had a coffee with a friend", id: "more", seconds: 4)
        input.pause()
        await settle()
        #expect(store.phase == .saved)
    }
}

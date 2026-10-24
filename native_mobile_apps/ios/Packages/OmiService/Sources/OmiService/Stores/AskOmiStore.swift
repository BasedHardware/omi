import Foundation
import Observation
import OmiAudio
import OmiDevice
import OmiNetwork
import OSLog

/// Ask Omi from the wearable: a single press starts a question from the Omi's audio, the next
/// press, a pause after the words (or 15 s) ends it. The iPhone transcribes the question while it
/// is spoken (in the user's main language), so the words show at once, and asks it like a typed
/// question; where the iPhone cannot recognize the language the recording goes to
/// `v2/voice-messages` instead (Flutter's only path). The answer lands in the chat and is read
/// aloud when Settings › Assistant › Spoken replies allows it. Every wait ends: nothing heard and
/// no answer both come back as a `problem`. Older firmware holds the button instead. Mirrors
/// `capture_controller.dart` voice-command sessions.
@MainActor
@Observable
public final class AskOmiStore {
    public enum Phase: Equatable, Sendable {
        case idle
        case listening(since: Date)
        /// The question is out; the answer is on its way.
        case sending
    }

    /// Why the last question got no answer.
    public enum Problem: Equatable, Sendable {
        case nothingHeard
        case noAnswer
    }

    enum Trigger { case toggle, hold }

    /// Where the question's words come from.
    /// `shared`: the capture's recognizer already hears the Omi; its line is read instead.
    enum Recognition { case off, starting, running, shared, unavailable }

    /// The last question asked from the Omi and its answer (the onboarding lesson shows them).
    public struct Exchange: Equatable, Sendable {
        public var question: String
        public var answer: String
    }

    public private(set) var phase: Phase = .idle
    public private(set) var lastExchange: Exchange?
    /// The question's words so far, live while it is spoken (empty without the iPhone's recognizer).
    public internal(set) var question = ""
    public private(set) var problem: Problem?
    /// An answer that is not being read aloud (the app shows it as a notification, like Flutter,
    /// which skips the answer push while it speaks).
    @ObservationIgnored public var onAnswer: ((String) -> Void)?
    /// The onboarding lesson: questions go through even with button actions turned off.
    @ObservationIgnored public var isPractice = false

    private let chat: ChatStore
    private let voice: VoicePlaybackStore?
    private let codec: () -> OmiGATT.Codec?
    private let haptic: (OmiGATT.Haptic) -> Void
    private let canAsk: () -> Bool
    private let recognizer: (any LiveRecognizer)?
    private let language: () -> String
    private let makeDecoder: (OmiGATT.Codec) -> ((Data) -> Data?)?
    let sharedLine: () -> SharedLine?
    private let maxDuration: Duration
    private let autoSendGrace: Duration
    private let pauseToSend: Duration
    private let answerTimeout: Duration
    @ObservationIgnored private var frames: [Data] = []
    @ObservationIgnored private var trigger: Trigger?
    @ObservationIgnored private var timeoutTask: Task<Void, Never>?
    @ObservationIgnored private var pauseTask: Task<Void, Never>?
    @ObservationIgnored var wordsTask: Task<Void, Never>?
    @ObservationIgnored private var autoSentAt: ContinuousClock.Instant?
    @ObservationIgnored var lastWordsAt: ContinuousClock.Instant?
    @ObservationIgnored private var decode: ((Data) -> Data?)?
    @ObservationIgnored var recognition = Recognition.off
    @ObservationIgnored private var pendingAudio: [Data] = []
    @ObservationIgnored var segments: [LiveSegment] = []
    /// Bumped per question: words from an earlier one are dropped.
    @ObservationIgnored var session = 0
    @ObservationIgnored private(set) var sendTask: Task<Void, Never>?
    private let log = Logger(subsystem: "com.omi.native", category: "ask")

    /// - Parameters:
    ///   - codec: the Omi's codec while connected.
    ///   - haptic: a pulse on the Omi (recording started, answer arriving, nothing heard).
    ///   - canAsk: false while the Omi is muted or button actions are off.
    ///   - voice: reads answers aloud (as the reply mode allows); nil keeps them silent.
    ///   - recognizer: transcribes the question on the iPhone; nil sends the recording instead.
    ///   - language: the language the recognizer listens for (the user's main one).
    ///   - sharedLine: the line of a recognizer that already listens to the Omi (the capture's
    ///     live words); nil when none runs. Apple's recognizer does not run twice on one audio.
    ///   - pauseToSend: quiet after the last words that ends a pressed question by itself.
    ///   - answerTimeout: how long an answer may take before the question counts as unanswered.
    public init(
        chat: ChatStore,
        voice: VoicePlaybackStore? = nil,
        codec: @escaping () -> OmiGATT.Codec?,
        haptic: @escaping (OmiGATT.Haptic) -> Void,
        canAsk: @escaping () -> Bool,
        recognizer: (any LiveRecognizer)? = nil,
        language: @escaping () -> String = { "en" },
        makeDecoder: @escaping (OmiGATT.Codec) -> ((Data) -> Data?)? = AskOmiStore.pcmDecoder,
        sharedLine: @escaping () -> SharedLine? = { nil },
        maxDuration: Duration = .seconds(15),
        autoSendGrace: Duration = .seconds(2),
        pauseToSend: Duration = .seconds(2),
        answerTimeout: Duration = .seconds(30)
    ) {
        self.chat = chat
        self.voice = voice
        self.codec = codec
        self.haptic = haptic
        self.canAsk = canAsk
        self.recognizer = recognizer
        self.language = language
        self.makeDecoder = makeDecoder
        self.sharedLine = sharedLine
        self.maxDuration = maxDuration
        self.autoSendGrace = autoSendGrace
        self.pauseToSend = pauseToSend
        self.answerTimeout = answerTimeout
    }

    public var isListening: Bool {
        if case .listening = phase { return true }
        return false
    }

    public func handle(_ action: ButtonAction) {
        switch action {
        case .askToggle:
            if isListening {
                send()
            } else if let autoSentAt, ContinuousClock.now - autoSentAt < autoSendGrace {
                // The press meant to stop a question that just sent itself.
                self.autoSentAt = nil
            } else {
                start(.toggle)
            }
        case .askHoldStart:
            if !isListening { start(.hold) }
        case .askHoldEnd:
            if isListening, trigger == .hold { send() }
        case .endConversation, .toggleStar, .toggleMute:
            break
        }
    }

    /// One codec frame from the Omi (header removed); kept only while a question is recorded.
    public func ingest(_ frame: Data) {
        guard isListening else { return }
        frames.append(frame)
        if let pcm = decode?(frame) { hear(pcm) }
    }

    /// 16 kHz PCM16 for the recognizer only (the simulator's stand-in for the Omi's audio).
    public func ingest(pcm16: Data) {
        guard isListening else { return }
        hear(pcm16)
    }

    /// Drops a question being recorded (button actions turned off, Omi disconnected).
    public func cancel() {
        guard isListening else { return }
        timeoutTask?.cancel()
        pauseTask?.cancel()
        stopRecognizing()
        frames = []
        trigger = nil
        phase = .idle
    }

    private var allowed: Bool {
        isPractice || canAsk()
    }

    private func start(_ trigger: Trigger) {
        guard phase == .idle, let codec = codec(), allowed else { return }
        // A new question cuts off the answer still being read (Flutter `newVoiceQuery`).
        voice?.stop()
        autoSentAt = nil
        frames = []
        question = ""
        segments = []
        problem = nil
        lastWordsAt = nil
        session += 1
        self.trigger = trigger
        phase = .listening(since: .now)
        haptic(.short)
        timeoutTask?.cancel()
        timeoutTask = Task { [weak self, maxDuration] in
            try? await Task.sleep(for: maxDuration)
            guard !Task.isCancelled, let self, isListening else { return }
            autoSentAt = .now
            send()
        }
        startRecognizing(codec)
    }

    // MARK: Words on the iPhone

    private func startRecognizing(_ codec: OmiGATT.Codec) {
        if let shared = sharedLine() {
            readShared(from: shared.line)
        } else if let recognizer, let decode = makeDecoder(codec) {
            recognize(with: recognizer, decode)
        } else {
            recognition = .unavailable
            return
        }
        waitForThePause()
    }

    private func recognize(with recognizer: any LiveRecognizer, _ decode: @escaping (Data) -> Data?) {
        self.decode = decode
        recognition = .starting
        pendingAudio = []
        let session = session
        wordsTask = Task { [weak self, recognizer, language] in
            let words = await recognizer.start(language: language())
            // Pressed again already counts (the words still come); cancelled does not.
            guard let self, self.session == session, recognition == .starting else {
                recognizer.stop()
                return
            }
            guard let words else {
                recognition = .unavailable
                return
            }
            recognition = .running
            pendingAudio.forEach(recognizer.feed)
            pendingAudio = []
            for await segment in words {
                guard self.session == session else { break }
                merge(segment)
            }
        }
    }

    private func waitForThePause() {
        pauseTask = Task { [weak self, pauseToSend] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(200))
                guard let self, isListening else { return }
                // A pressed question ends by itself once the words have paused.
                if trigger == .toggle, !question.isEmpty, let lastWordsAt, ContinuousClock.now - lastWordsAt >= pauseToSend {
                    autoSentAt = .now
                    send()
                    return
                }
            }
        }
    }

    private func hear(_ pcm: Data) {
        switch recognition {
        case .running: recognizer?.feed(pcm)
        case .starting: pendingAudio.append(pcm)
        case .off, .shared, .unavailable: break
        }
    }

    private func stopRecognizing() {
        pauseTask?.cancel()
        if recognition != .shared { recognizer?.stop() }
        decode = nil
        pendingAudio = []
        if recognition != .unavailable { recognition = .off }
    }

    // MARK: Sending

    private func send() {
        guard case let .listening(since) = phase else { return }
        timeoutTask?.cancel()
        pauseTask?.cancel()
        trigger = nil
        let recorded = frames
        frames = []
        // Button actions turned off (or the Omi muted) while recording: nothing is sent.
        guard allowed else {
            stopRecognizing()
            phase = .idle
            return
        }
        let codec = codec()
        let listens = [.running, .starting, .shared].contains(recognition)
        guard listens || !recorded.isEmpty else {
            phase = .idle
            problem = .nothingHeard
            nothingHeard()
            return
        }
        phase = .sending
        sendTask = Task { [weak self] in
            guard let self else { return }
            // A recognizer still starting decides first whether the words come from the iPhone.
            for _ in 0 ..< 20 where recognition == .starting {
                try? await Task.sleep(for: .milliseconds(50))
            }
            let recognized = recognition == .running || recognition == .shared
            let text = recognized ? await finalWords() : ""
            if !recognized { stopRecognizing() }
            let answer: ChatStore.VoiceAnswer? = if !text.isEmpty {
                await within(answerTimeout) { [chat, weak self] in
                    await chat.ask(question: text) { self?.haptic(.medium) }
                }
            } else if !recognized, let codec, !recorded.isEmpty {
                // The iPhone could not listen: the backend transcribes the recording.
                await askServer(recorded, codec: codec, since: since)
            } else {
                .noSpeech
            }
            finish(answer, question: text, path: recognized ? "iPhone" : "server")
        }
    }

    private func finish(_ answer: ChatStore.VoiceAnswer?, question text: String, path: String) {
        phase = .idle
        let words = text.split(separator: " ").count
        log.notice("question via \(path, privacy: .public): \(words) words, answer: \(String(describing: answer), privacy: .private)")
        switch answer {
        case let .answered(reply): answered(reply, question: text)
        case .noSpeech:
            problem = .nothingHeard
            nothingHeard()
        case .failed, nil:
            // The same two buzzes: whoever wears the Omi knows no answer is coming.
            problem = .noAnswer
            nothingHeard()
        }
    }

    private func askServer(_ recorded: [Data], codec: OmiGATT.Codec, since: Date) async -> ChatStore.VoiceAnswer? {
        let file = VoiceMessageEvent.file(
            frames: recorded, codec: codec.listenValue, sampleRate: codec.sampleRate,
            frameSamples: codec == .opusFS320 ? 320 : 160, startedAt: since
        )
        return await within(answerTimeout) { [chat, weak self] in
            await chat.ask(voiceFile: file.name, audio: file.data) { self?.haptic(.medium) }
        }
    }

    /// Ends recognition and gives the last words a moment to arrive.
    private func finalWords() async -> String {
        stopRecognizing()
        try? await Task.sleep(for: .milliseconds(500))
        session += 1
        return question.trimmingCharacters(in: .whitespaces)
    }

    private func answered(_ text: String, question asked: String) {
        let reply = chat.messages.last { $0.sender == .omi && $0.text == text }
        let spokenQuestion = reply.flatMap { reply in
            chat.messages.last { $0.sender == .user && $0.createdAt <= reply.createdAt && $0.id.hasPrefix("voice-") }
        }
        lastExchange = Exchange(question: asked.isEmpty ? spokenQuestion?.text ?? "" : asked, answer: text)
        let spoken = reply.map { voice?.answerArrived($0) ?? false } ?? false
        if !spoken { onAnswer?(text) }
    }

    /// Two short buzzes: nothing was heard (`_playVoiceQuestionFailureHaptic`).
    private func nothingHeard() {
        haptic(.short)
        Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(80))
            self?.haptic(.short)
        }
    }
}

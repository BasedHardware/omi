import Foundation
import Observation
import OmiNetwork
import OSLog

/// Onboarding's "say something" and voice sample. One session runs from the first whisper to the
/// saved voice; nothing said here becomes a conversation. The live words come from the iPhone's
/// own recognizer (instant, works offline); the server's transcription-only socket stands in when
/// the iPhone cannot recognize the language, and a watchdog hands over to the other one when
/// speech keeps arriving without words. The training part also records the audio that becomes
/// the user's voice profile, one gap sentence at a time.
@MainActor
@Observable
public final class VoiceIntroStore {
    public enum Source: Equatable, Sendable { case phone, device }

    /// Where the live words come from right now.
    public enum WordSource: Equatable, Sendable {
        case onDevice, server
        /// Neither produced words: the sentences move on by speech alone.
        case none
    }

    public enum Phase: Equatable, Sendable {
        case idle, starting, listening, saving, saved
        case failed(Failure)
    }

    public enum Failure: Equatable, Sendable {
        /// Microphone or Bluetooth audio could not start.
        case input
        /// The upload failed; the recording is kept for a retry.
        case upload
    }

    /// One finished sentence of the introduction.
    public struct Answer: Identifiable, Equatable, Sendable {
        public let id: Int
        public var text: String
    }

    /// Speech the profile wants before it is saved; the server accepts 5 s and more.
    public static let minimumSeconds: Double = 8
    static let maximumSeconds: Double = 170
    /// Above this level a chunk counts as speech.
    static let speechLevel: Float = 0.008
    /// Speech without a single word before the other source gets its turn.
    static let watchdogSeconds: Double = 2.5
    /// The same, once the source has brought words: recognizers lag and rest between sentences,
    /// so a working one is not dropped for a short silence of its own.
    static let watchdogAfterWordsSeconds: Double = 8
    /// The quietest audio of the last seconds sets how loud speech has to be (a noisy Omi
    /// microphone still has pauses); never above this, so speech always counts.
    static let maximumNoiseFloor: Float = 0.03
    static let noiseWindowSeconds: Double = 4
    /// A recognized word stands for about this much speech in the voice sample.
    static let secondsPerWord: Double = 0.3
    /// The pause after a finished sentence before the next one comes up.
    static let pauseSeconds: Double = 0.7
    /// Without words, a sentence counts as said after this much speech and a pause.
    static let blindSentenceSeconds: Double = 2.5
    /// Audio kept to replay into the next source, so words said during the hand-over are not lost.
    static let replaySeconds: Double = 3
    static let maximumSwitches = 2

    public private(set) var phase: Phase = .idle
    public private(set) var source: Source = .phone
    public internal(set) var wordSource: WordSource = .none
    public private(set) var segments: [LiveSegment] = []
    public private(set) var level: Float = 0
    public private(set) var isTraining = false
    public private(set) var promptIndex = 0
    public private(set) var answers: [Answer] = []
    /// Seconds of speech in the voice sample so far.
    public private(set) var spokenSeconds: Double = 0
    /// Every sentence was said but the sample is too short: one more, free sentence.
    public private(set) var needsMore = false
    /// Speech heard since listening began, words or not (recognition can be unavailable).
    public private(set) var heardSeconds: Double = 0
    /// The current sentence laid over what was said for it.
    public private(set) var match: GapSentence.Match?
    /// Milliseconds from the first speech to the first words of this session (the log has it too).
    public private(set) var firstWordsLatency: Int?
    private var promptSeconds: Double = 0
    private var sentences: [GapSentence] = []
    /// Asked for when the three sentences gave too little speech ("Today I ___.").
    private var extraSentence = GapSentence.free

    /// The user said something: words arrived, or at least a second of speech.
    public var heardSomething: Bool {
        !transcript.isEmpty || heardSeconds >= 1
    }

    /// Speech on the current sentence so far (shows "Omi hears you" before words arrive).
    public var hearsSpeech: Bool {
        promptSeconds >= 0.5
    }

    /// The current sentence was spoken, even when no words could be recognized.
    public var canAdvance: Bool {
        !currentAnswer.isEmpty || promptSeconds >= 1.5
    }

    public var transcript: String {
        segments.map(\.text).joined(separator: " ").trimmingCharacters(in: .whitespaces)
    }

    /// What was said since the current sentence began.
    public var currentAnswer: String {
        segments.dropFirst(promptStart).map(\.text).joined(separator: " ").trimmingCharacters(in: .whitespaces)
    }

    public var isListening: Bool {
        phase == .listening
    }

    /// Enough speech for the profile: measured by loudness, or by the words recognized (a
    /// whisper can stay under the speech level while every word is understood).
    public var canSave: Bool {
        sampleSeconds >= Self.minimumSeconds
    }

    /// Seconds of speech in the voice sample, the larger of both measures.
    public var sampleSeconds: Double {
        let words = (answers.map(\.text) + [currentAnswer]).reduce(0) { $0 + $1.split(separator: " ").count }
        return max(spokenSeconds, Double(words) * Self.secondsPerWord)
    }

    /// The sentence being spoken: one of the prompts, or the extra one asked for at the end.
    public var sentence: GapSentence? {
        needsMore ? extraSentence : sentences.indices.contains(promptIndex) ? sentences[promptIndex] : nil
    }

    /// The current sentence counts as said: it matches, or plenty of words were said for it
    /// (people paraphrase, recognizers mishear) after a moment of speech.
    var sentenceSaid: Bool {
        guard let match else { return false }
        if match.isComplete { return true }
        let words = currentAnswer.split(separator: " ").count
        let wanted = max(4, match.fixedTotal / 2 + match.blanks.count)
        return words >= wanted && promptSeconds >= 1.5
    }

    /// 0…1 along the sentences: a finished sentence is a full step.
    public var progress: Double {
        VoiceProgress.fraction(completed: promptIndex, total: sentences.count, current: match?.progress ?? 0)
    }

    let api: any APIClientProtocol
    let recognizer: any LiveRecognizer
    private let phoneInput: any VoiceInput
    private let deviceInput: () -> any VoiceInput
    private var input: (any VoiceInput)?
    var channel: (any LiveTranscriptionChannel)?
    var language = "en"
    private var tasks: [Task<Void, Never>] = []
    var wordsTask: Task<Void, Never>?
    var switches = 0
    var switching = false
    /// The current word source brought words at least once.
    var sourceGaveWords = false
    /// Recent chunk levels and their length, for the noise floor.
    private var recentLevels: [(level: Float, seconds: Double)] = []
    private var advancing = false
    private var sample = Data()
    var recent = Data()
    private var promptStart = 0
    /// Speech since the last new words: the watchdog's measure.
    var speechWithoutWords: Double = 0
    /// Quiet since the last speech, counted in audio and, when audio stops coming, in time.
    private var silence: Double = 0
    private var lastChunk = Date.distantPast
    private var firstSpeech: Date?
    let log = Logger(subsystem: "com.omi.native", category: "voice")

    public init(
        api: any APIClientProtocol,
        recognizer: any LiveRecognizer,
        phoneInput: any VoiceInput,
        deviceInput: @escaping () -> any VoiceInput
    ) {
        self.api = api
        self.recognizer = recognizer
        self.phoneInput = phoneInput
        self.deviceInput = deviceInput
    }

    /// Starts listening (idempotent while the same source runs in the same language).
    public func start(source: Source, language: String) async {
        if phase == .listening || phase == .starting, self.source == source, self.language == language { return }
        stop()
        self.source = source
        self.language = language
        firstSpeech = nil
        firstWordsLatency = nil
        silence = 0
        phase = .starting
        let input = source == .device ? deviceInput() : phoneInput
        let audio: AsyncStream<Data>
        do {
            audio = try await input.start()
        } catch {
            input.stop()
            phase = .failed(.input)
            return
        }
        self.input = input
        phase = .listening
        tasks.append(Task { [weak self] in
            for await chunk in audio {
                self?.ingest(chunk)
            }
        })
        // Audio from a file (or a quiet Omi) can stop coming: pauses still count.
        tasks.append(Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(200))
                self?.evaluate()
            }
        })
        if await !startOnDevice(), await !startServer() { wordSource = .none }
    }

    // MARK: Sentences

    /// From here on the audio also goes into the voice sample, sentence by sentence.
    /// `templates` are the localized gap sentences ("My name is ___ and …"); `extra` is asked for
    /// when they gave too little speech.
    public func beginTraining(templates: [String], extra: String? = nil) {
        guard !isTraining else { return }
        isTraining = true
        sentences = templates.map(GapSentence.init)
        extraSentence = extra.map(GapSentence.init) ?? .free
        sample = Data()
        spokenSeconds = 0
        promptIndex = 0
        answers = []
        needsMore = false
        newSentence()
    }

    /// Keeps what was said for this sentence and moves to the next one (the Next button, or on
    /// its own once the sentence is complete and the user paused).
    public func nextPrompt() {
        let text = currentAnswer
        if !text.isEmpty { answers.append(Answer(id: answers.count, text: text)) }
        if !needsMore { promptIndex = min(promptIndex + 1, sentences.count) }
        newSentence()
    }

    private func newSentence() {
        promptStart = segments.count
        promptSeconds = 0
        match = sentence?.match("")
        if wordSource == .onDevice { recognizer.startNewUtterance() }
    }

    /// Ends listening and uploads the voice sample. With too little speech it keeps listening
    /// and asks for one more sentence instead. Answers stay for the review.
    public func saveVoice() async {
        nextPrompt()
        guard canSave else {
            needsMore = true
            match = extraSentence.match("")
            return
        }
        needsMore = false
        stop(keepingSample: true)
        await upload()
    }

    /// The same recording again, after a failed upload.
    public func retryUpload() async {
        await upload()
    }

    private func upload() async {
        phase = .saving
        do {
            try await api.uploadSpeechProfile(wav: PCM16.wav(sample))
            phase = .saved
        } catch {
            phase = .failed(.upload)
        }
    }

    /// The answers become memories ("My name is…"), as Flutter keeps them by default.
    public func saveAnswers() async {
        for answer in answers {
            _ = try? await api.createMemory(content: answer.text, category: "system")
        }
    }

    public func stop() {
        stop(keepingSample: false)
    }

    private func stop(keepingSample: Bool) {
        tasks.forEach { $0.cancel() }
        tasks = []
        input?.stop()
        input = nil
        stopWords()
        switches = 0
        recent = Data()
        recentLevels = []
        speechWithoutWords = 0
        level = 0
        if !keepingSample, phase == .listening || phase == .starting {
            phase = .idle
            isTraining = false
        }
    }

    // MARK: Audio

    func ingest(_ chunk: Data, at now: Date = Date()) {
        send(chunk)
        recent.append(chunk)
        let keep = Int(Self.replaySeconds * 32000)
        if recent.count > keep { recent.removeFirst(recent.count - keep) }
        let chunkLevel = PCM16.level(chunk)
        let seconds = Double(chunk.count) / 32000
        let isSpeech = chunkLevel > max(Self.speechLevel, noiseFloor(adding: chunkLevel, seconds: seconds) * 2)
        level = level * 0.6 + chunkLevel * 0.4
        lastChunk = now
        if isSpeech {
            if firstSpeech == nil { firstSpeech = now }
            heardSeconds += seconds
            promptSeconds += seconds
            speechWithoutWords += seconds
            silence = 0
        } else {
            silence += seconds
        }
        if isTraining, Double(sample.count) / 32000 < Self.maximumSeconds {
            sample.append(chunk)
            if isSpeech { spokenSeconds += seconds }
        }
        evaluate(now: now)
    }

    /// The quietest of the last seconds of audio, capped so speech always counts.
    private func noiseFloor(adding level: Float, seconds: Double) -> Float {
        recentLevels.append((level, seconds))
        var total = recentLevels.reduce(0) { $0 + $1.seconds }
        while total > Self.noiseWindowSeconds, recentLevels.count > 1 {
            total -= recentLevels.removeFirst().seconds
        }
        return min(Self.maximumNoiseFloor, recentLevels.map(\.level).min() ?? 0)
    }

    /// The watchdog and the automatic move to the next sentence.
    func evaluate(now: Date = Date()) {
        guard phase == .listening else { return }
        let patience = sourceGaveWords ? Self.watchdogAfterWordsSeconds : Self.watchdogSeconds
        if wordSource != .none, speechWithoutWords >= patience { switchSource() }
        guard isTraining, !advancing, match != nil else { return }
        let quiet = silence + max(0, now.timeIntervalSince(lastChunk) - 0.25)
        // No words for this sentence from a source that never gave any, with no other left.
        let noWords = wordSource == .none || switches >= Self.maximumSwitches && !sourceGaveWords
        let blind = noWords && segments.count == promptStart
        var said = blind ? promptSeconds >= Self.blindSentenceSeconds : sentenceSaid
        // The extra sentence goes on until the sample is long enough.
        if needsMore { said = said && canSave }
        guard said, quiet >= Self.pauseSeconds else { return }
        advancing = true
        Task {
            defer { advancing = false }
            if needsMore || promptIndex >= sentences.count - 1 {
                await saveVoice()
            } else {
                nextPrompt()
            }
        }
    }

    /// Segments are re-sent when refined; the same id replaces the earlier text.
    func merge(_ new: [LiveSegment]) {
        var changed = false
        for segment in new where !segment.text.trimmingCharacters(in: .whitespaces).isEmpty {
            if let index = segments.firstIndex(where: { $0.id == segment.id }) {
                guard segments[index].text != segment.text else { continue }
                segments[index] = segment
            } else {
                segments.append(segment)
            }
            changed = true
        }
        guard changed else { return }
        speechWithoutWords = 0
        sourceGaveWords = true
        if firstWordsLatency == nil {
            let latency = Int(Date().timeIntervalSince(firstSpeech ?? Date()) * 1000)
            firstWordsLatency = latency
            log.notice("first words \(latency) ms after speech (\(String(describing: self.wordSource), privacy: .public))")
        }
        if isTraining { match = sentence?.match(currentAnswer) }
    }
}

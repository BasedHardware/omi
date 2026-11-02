import Flutter
import AVFoundation
import Speech

/// On-device live transcript preview for local-preview listen sessions.
///
/// Display only: it receives a decoded COPY of capture audio (16 kHz mono
/// PCM16) from Dart and returns provisional text. It never stores, uploads or
/// owns audio, never downloads speech assets, never prompts for permission and
/// never falls back to a cloud recognizer. Separate from the single-flight
/// `com.omi/on_device` overflow plugin on purpose.
///
/// Channels: `com.omi/live_preview` (start/feed/stop) and
/// `com.omi/live_preview/events` ({segmentId, text, isFinal}).
@MainActor
final class LivePreviewPlugin: NSObject, FlutterStreamHandler {
    private let channel: FlutterMethodChannel
    private let events: FlutterEventChannel
    private var sink: FlutterEventSink?
    private var session: LivePreviewSession?
    private var generation = 0

    init(messenger: FlutterBinaryMessenger) {
        channel = FlutterMethodChannel(name: "com.omi/live_preview", binaryMessenger: messenger)
        events = FlutterEventChannel(name: "com.omi/live_preview/events", binaryMessenger: messenger)
        super.init()
        channel.setMethodCallHandler { [weak self] call, reply in
            guard let self else { reply(nil); return }
            self.handle(call, reply: reply)
        }
        events.setStreamHandler(self)
    }

    nonisolated func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        MainActor.assumeIsolated { sink = events }
        return nil
    }

    nonisolated func onCancel(withArguments arguments: Any?) -> FlutterError? {
        MainActor.assumeIsolated { sink = nil }
        return nil
    }

    /// The previous session's cleanup; a new start waits for it.
    private var stopping: Task<Void, Never>?

    /// Stops the current session (if any) and records the cleanup so the next
    /// start or stop reply happens only after the recognizer has let go.
    private func retireSession() -> Task<Void, Never> {
        let previous = stopping
        let retiring = session
        session = nil
        let task = Task { @MainActor in
            await previous?.value
            await retiring?.stop()
        }
        stopping = task
        return task
    }

    private func handle(_ call: FlutterMethodCall, reply: @escaping FlutterResult) {
        switch call.method {
        case "start":
            let args = call.arguments as? [String: Any] ?? [:]
            let language = args["language"] as? String ?? "multi"
            let exclude = Set(args["exclude"] as? [String] ?? [])
            generation += 1
            let mine = generation
            let retired = retireSession()
            Task { @MainActor in
                await retired.value
                let (started, choice) = await self.select(language: language, exclude: exclude, generation: mine)
                guard mine == self.generation else {
                    await started?.stop()
                    reply(LivePreviewChoice(engine: "none", reason: "engine_error", bundledInstalled: choice.bundledInstalled).wire)
                    return
                }
                self.session = started
                NSLog("[LivePreview] engine=%@ reason=%@", choice.engine, choice.reason)
                reply(choice.wire)
            }
        case "feed":
            let args = call.arguments as? [String: Any] ?? [:]
            guard let data = (args["pcm"] as? FlutterStandardTypedData)?.data, let session else {
                reply(false); return
            }
            let startedAt = (args["startMs"] as? Double).map { $0 / 1000 }
                ?? (Date().timeIntervalSince1970 - Double(data.count) / 32000)
            reply(session.append(pcm16: data, startedAt: startedAt))
        case "stop":
            generation += 1
            let retired = retireSession()
            Task { @MainActor in
                await retired.value
                reply(nil)
            }
        default:
            reply(FlutterMethodNotImplemented)
        }
    }

    /// A running engine failed for good: tell Dart (closed reason) and release it.
    private func runtimeFailure(engine: String, generation failed: Int) {
        guard failed == generation, session != nil else { return }
        NSLog("[LivePreview] runtime failure engine=%@", engine)
        _ = retireSession()
        sink?(["failure": "engine_error", "engine": engine])
    }

    private func emit(_ segmentId: String, _ text: String, _ isFinal: Bool, _ start: Double, _ end: Double, _ spans: [PreviewTimedSpan]) {
        sink?(["segmentId": "\(generation):\(segmentId)", "text": text, "isFinal": isFinal, "startMs": start * 1000, "endMs": end * 1000,
               "spans": spans.map { ["text": $0.text, "startMs": $0.start * 1000, "endMs": $0.end * 1000] }])
    }

    private var bundledInstalled: Bool {
        let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("on-device-parakeet-v2", isDirectory: true)
        return FileManager.default.fileExists(atPath: directory.appendingPathComponent("installed").path)
    }

    private func select(language: String, exclude: Set<String>, generation mine: Int) async -> (LivePreviewSession?, LivePreviewChoice) {
        let bundled = bundledInstalled
        let onResult: (String, String, Bool, Double, Double, [PreviewTimedSpan]) -> Void = { [weak self] id, text, isFinal, start, end, spans in
            guard let self, mine == self.generation else { return }
            self.emit(id, text, isFinal, start, end, spans)
        }
        func onFailure(_ engine: String) -> () -> Void {
            { [weak self] in self?.runtimeFailure(engine: engine, generation: mine) }
        }

        var analyzer: LivePreviewTier = .unavailable("os_too_old")
        if #available(iOS 26, *) {
            let probe = await AnalyzerPreviewSession.probe(language: language)
            analyzer = probe.tier
            if exclude.contains("speech_transcriber") {
                // Failed at runtime earlier in this session: the next engine is tried once.
                analyzer = .unavailable("engine_error")
            } else if let locale = probe.locale {
                do {
                    let started = try await AnalyzerPreviewSession.start(
                        locale: locale, onResult: onResult, onFailure: onFailure("speech_transcriber"))
                    return (started, LivePreviewSelection.choose(analyzer: .ready, sfSpeech: .unavailable("engine_error"), bundledInstalled: bundled))
                } catch {
                    NSLog("[LivePreview] SpeechAnalyzer start failed: %@", error.localizedDescription)
                    analyzer = .unavailable("engine_error")
                }
            }
        }

        let legacy = exclude.contains("sf_speech")
            ? (tier: LivePreviewTier.unavailable("engine_error"), recognizer: nil)
            : SFSpeechPreviewSession.probe(language: language)
        if let recognizer = legacy.recognizer {
            let started = SFSpeechPreviewSession(recognizer: recognizer, onResult: onResult, onFailure: onFailure("sf_speech"))
            started.begin()
            return (started, LivePreviewSelection.choose(analyzer: analyzer, sfSpeech: .ready, bundledInstalled: bundled))
        }
        return (nil, LivePreviewSelection.choose(analyzer: analyzer, sfSpeech: legacy.tier, bundledInstalled: bundled))
    }
}

@MainActor
protocol LivePreviewSession: AnyObject {
    /// Appends 16 kHz mono little-endian PCM16. False when the chunk was refused.
    func append(pcm16 data: Data, startedAt: TimeInterval) -> Bool
    /// Returns once the recognizer has finished releasing its resources.
    func stop() async
}

private let previewInputFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)

private func int16Buffer(_ data: Data) -> AVAudioPCMBuffer? {
    let frames = AVAudioFrameCount(data.count / 2)
    guard frames > 0, let format = previewInputFormat, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames),
          let channel = buffer.int16ChannelData?[0] else { return nil }
    buffer.frameLength = frames
    data.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { return }
        memcpy(channel, base, Int(frames) * 2)
    }
    return buffer
}

// MARK: - SpeechAnalyzer (iOS 26+)

@available(iOS 26, *)
@MainActor
final class AnalyzerPreviewSession: LivePreviewSession {
    /// Installed-locale check only. A supported locale whose asset is not on
    /// the phone reports `locale_asset_missing`: the preview never starts a
    /// download (that could run on cellular from the capture path).
    static func probe(language: String) async -> (tier: LivePreviewTier, locale: Locale?) {
        guard SpeechTranscriber.isAvailable else { return (.unavailable("os_engine_unavailable"), nil) }
        let device = Locale.current.identifier(.bcp47)
        let code = LivePreviewSelection.languageCode(language, deviceLanguage: Locale.current.language.languageCode?.identifier)
        let installed = await SpeechTranscriber.installedLocales.map { $0.identifier(.bcp47) }
        let supported = await SpeechTranscriber.supportedLocales.map { $0.identifier(.bcp47) }
        let pick = LivePreviewSelection.pickLocale(code: code, installed: installed, supported: supported, device: device)
        guard let identifier = pick.locale else { return (.unavailable(pick.reason), nil) }
        return (.ready, Locale(identifier: identifier))
    }

    static func start(locale: Locale, onResult: @escaping (String, String, Bool, Double, Double, [PreviewTimedSpan]) -> Void,
                      onFailure: @escaping () -> Void) async throws -> AnalyzerPreviewSession {
        let transcriber = SpeechTranscriber(locale: locale, transcriptionOptions: [],
                                            reportingOptions: [.volatileResults, .fastResults], attributeOptions: [.audioTimeRange])
        guard let inputFormat = previewInputFormat else {
            throw NSError(domain: "LivePreview", code: 1, userInfo: [NSLocalizedDescriptionKey: "No PCM16 input format"])
        }
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        let format = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber],
                                                                   considering: inputFormat) ?? inputFormat
        let (stream, continuation) = AsyncStream<AnalyzerInput>.makeStream(bufferingPolicy: .bufferingNewest(64))
        let session = AnalyzerPreviewSession(analyzer: analyzer, inputFormat: inputFormat, format: format,
                                             continuation: continuation)
        session.results = Task { @MainActor [weak session] in
            var ids = LivePreviewSegmentIds(prefix: "a")
            do {
                for try await result in transcriber.results {
                    guard let session, !session.stopped else { return }
                    let text = String(result.text.characters)
                    // Analyzer times run from the session's first sample; the wall clock of
                    // that sample turns them into the audio times the coverage check uses.
                    let origin = session.origin ?? 0
                    let spans = result.text.runs.map { run -> PreviewTimedSpan in
                        let range = run.audioTimeRange ?? result.range
                        return PreviewTimedSpan(text: String(result.text[run.range].characters),
                                                start: origin + range.start.seconds,
                                                end: origin + CMTimeRangeGetEnd(range).seconds)
                    }
                    onResult(ids.id(isFinal: result.isFinal), text, result.isFinal,
                             origin + result.range.start.seconds, origin + CMTimeRangeGetEnd(result.range).seconds, spans)
                }
            } catch {
                NSLog("[LivePreview] SpeechAnalyzer results failed")
            }
            // Results only end on their own when the analyzer failed or finished
            // underneath us; either way the preview is no longer live.
            guard let session, !session.stopped, !Task.isCancelled else { return }
            onFailure()
        }
        do {
            try await analyzer.prepareToAnalyze(in: format)
            try await analyzer.start(inputSequence: stream)
        } catch {
            await session.stop()
            throw error
        }
        return session
    }

    private let analyzer: SpeechAnalyzer
    private let inputFormat: AVAudioFormat
    private let format: AVAudioFormat
    private let continuation: AsyncStream<AnalyzerInput>.Continuation
    private var converter: AVAudioConverter?
    fileprivate var results: Task<Void, Never>?
    fileprivate var stopped = false
    /// Wall-clock seconds of the first sample fed; analyzer result times are relative to it.
    fileprivate var origin: TimeInterval?

    private init(analyzer: SpeechAnalyzer, inputFormat: AVAudioFormat, format: AVAudioFormat,
                 continuation: AsyncStream<AnalyzerInput>.Continuation) {
        self.analyzer = analyzer
        self.inputFormat = inputFormat
        self.format = format
        self.continuation = continuation
    }

    func append(pcm16 data: Data, startedAt: TimeInterval) -> Bool {
        guard !stopped, let input = int16Buffer(data), let buffer = convert(input) else { return false }
        // Buffers stay contiguous on the analyzer's own timeline. Wall-clock start times
        // from bursty BLE delivery overlap or leave gaps, and the analyzer stalls or fails
        // on them; the wall clock is applied to its results instead.
        if origin == nil { origin = startedAt }
        if case .dropped = continuation.yield(AnalyzerInput(buffer: buffer)) { return false }
        return true
    }

    private func convert(_ input: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        if format == inputFormat { return input }
        if converter == nil { converter = AVAudioConverter(from: inputFormat, to: format) }
        guard let converter else { return nil }
        let ratio = format.sampleRate / inputFormat.sampleRate
        let capacity = AVAudioFrameCount((Double(input.frameLength) * ratio).rounded(.up)) + 16
        guard let output = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { return nil }
        var consumed = false
        var error: NSError?
        let status = converter.convert(to: output, error: &error) { _, inputStatus in
            if consumed {
                inputStatus.pointee = .noDataNow
                return nil
            }
            consumed = true
            inputStatus.pointee = .haveData
            return input
        }
        guard status != .error, error == nil, output.frameLength > 0 else { return nil }
        return output
    }

    func stop() async {
        guard !stopped else { return }
        stopped = true
        continuation.finish()
        results?.cancel()
        await analyzer.cancelAndFinishNow()
    }
}

// MARK: - SFSpeechRecognizer on-device (segmented)

@MainActor
final class SFSpeechPreviewSession: LivePreviewSession {
    /// Requires existing speech authorization (never prompts from capture) and
    /// a recognizer that supports on-device recognition for the language.
    static func probe(language: String) -> (tier: LivePreviewTier, recognizer: SFSpeechRecognizer?) {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
            return (.unavailable("speech_permission_denied"), nil)
        }
        let code = LivePreviewSelection.languageCode(language, deviceLanguage: Locale.current.languageCode)
        let supported = SFSpeechRecognizer.supportedLocales().contains { $0.languageCode == code }
        guard supported else { return (.unavailable("locale_unsupported"), nil) }
        guard let recognizer = SpeechRecognitionHandler.onDeviceRecognizer(for: code) else {
            return (.unavailable("os_engine_unavailable"), nil)
        }
        return (.ready, recognizer)
    }

    /// On-device requests are rotated before the recognizer's per-request limit.
    static let rotateAfter: TimeInterval = 50

    private let recognizer: SFSpeechRecognizer
    private let onResult: (String, String, Bool, Double, Double, [PreviewTimedSpan]) -> Void
    private let floatFormat = AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1)
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var tasks: [SFSpeechRecognitionTask] = []
    private var requestClock: PreviewRequestClock?
    private var requestStartedAt = Date()
    private var segment = 0
    private var stopped = false
    private var retryAt = Date.distantPast

    /// Requests that failed in a row with no words; at this many the preview
    /// reports a runtime failure instead of retrying forever.
    static let maxConsecutiveFailures = 3
    private let onFailure: () -> Void
    private var consecutiveFailures = 0

    init(recognizer: SFSpeechRecognizer, onResult: @escaping (String, String, Bool, Double, Double, [PreviewTimedSpan]) -> Void,
         onFailure: @escaping () -> Void) {
        self.recognizer = recognizer
        self.onResult = onResult
        self.onFailure = onFailure
    }

    func begin() {
        guard !stopped else { return }
        segment += 1
        let id = "s\(segment)"
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = true
        if #available(iOS 16, *) { request.addsPunctuation = true }
        self.request = request
        requestStartedAt = Date()
        let audioClock = PreviewRequestClock()
        requestClock = audioClock
        let task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let text = result?.bestTranscription.formattedString
            // "No speech detected" (kAFAssistantErrorDomain 1110) is silence,
            // not a failure: the request just ends and the next audio reopens one.
            let silent = (error as NSError?)?.code == 1110
            let isFinal = (result?.isFinal ?? false) || silent
            let failed = error != nil && !silent
            Task { @MainActor in
                guard let self, !self.stopped else { return }
                if let text {
                    let parts = result?.bestTranscription.segments ?? []
                    let origin = audioClock.origin ?? 0
                    self.onResult(id, text, isFinal,
                                  origin + (parts.first?.timestamp ?? 0),
                                  origin + (parts.last.map { $0.timestamp + $0.duration } ?? 0),
                                  parts.map { PreviewTimedSpan(text: $0.substring, start: origin + $0.timestamp,
                                                               end: origin + $0.timestamp + $0.duration) })
                    if !text.isEmpty { self.consecutiveFailures = 0 }
                }
                if failed, self.request === request {
                    self.consecutiveFailures += 1
                    if self.consecutiveFailures >= Self.maxConsecutiveFailures {
                        self.onFailure()
                        return
                    }
                }
                // A failed or finished current request (silence timeout, a
                // recognizer hiccup) ends; the next audio opens a new one.
                // Requests that fail at once back off so they cannot spin.
                if (failed || isFinal), self.request === request {
                    if failed, let text {
                        let parts = result?.bestTranscription.segments ?? []
                        let origin = audioClock.origin ?? 0
                        self.onResult(id, text, true, origin + (parts.first?.timestamp ?? 0),
                                      origin + (parts.last.map { $0.timestamp + $0.duration } ?? 0),
                                  parts.map { PreviewTimedSpan(text: $0.substring, start: origin + $0.timestamp,
                                                               end: origin + $0.timestamp + $0.duration) })
                    }
                    let quick = Date().timeIntervalSince(self.requestStartedAt) < 1
                    self.request?.endAudio()
                    self.request = nil
                    self.retryAt = failed && quick ? Date().addingTimeInterval(5) : .distantPast
                }
            }
        }
        tasks.append(task)
        if tasks.count > 4 { tasks.removeFirst().cancel() }
    }

    private func rotate() {
        request?.endAudio()
        request = nil
        begin()
    }

    func append(pcm16 data: Data, startedAt: TimeInterval) -> Bool {
        guard !stopped else { return false }
        if request == nil {
            guard Date() >= retryAt else { return false }
            begin()
        } else if Date().timeIntervalSince(requestStartedAt) >= Self.rotateAfter {
            rotate()
        }
        guard let request, let buffer = floatBuffer(data) else { return false }
        if requestClock?.origin == nil {
            requestClock?.origin = startedAt
        }
        request.append(buffer)
        return true
    }

    private func floatBuffer(_ data: Data) -> AVAudioPCMBuffer? {
        let frames = data.count / 2
        guard frames > 0, let floatFormat,
              let buffer = AVAudioPCMBuffer(pcmFormat: floatFormat, frameCapacity: AVAudioFrameCount(frames)),
              let channel = buffer.floatChannelData?[0] else { return nil }
        buffer.frameLength = AVAudioFrameCount(frames)
        data.withUnsafeBytes { raw in
            let samples = raw.bindMemory(to: Int16.self)
            for index in 0..<frames { channel[index] = Float(Int16(littleEndian: samples[index])) / 32768 }
        }
        return buffer
    }

    func stop() async {
        guard !stopped else { return }
        stopped = true
        request?.endAudio()
        request = nil
        tasks.forEach { $0.cancel() }
        tasks.removeAll()
    }
}

/// One request's audio clock survives rotation until its final result returns.
private final class PreviewRequestClock {
    var origin: TimeInterval?
}

struct PreviewTimedSpan {
    let text: String
    let start: Double
    let end: Double
}

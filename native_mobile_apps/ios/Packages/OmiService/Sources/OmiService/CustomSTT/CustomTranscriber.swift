import Foundation
import OmiNetwork

/// Turns live 16 kHz PCM16 into transcript segments with the user's own provider (Flutter
/// `PurePollingSocket` for the HTTP ones, `PureStreamingStt` for Deepgram). Capture shows the
/// segments and forwards them to `/v4/listen` as `suggested_transcript`.
@MainActor
public protocol CustomTranscribing: AnyObject {
    /// The provider name sent with each `suggested_transcript` (`stt_provider`).
    var providerName: String { get }
    func start() -> AsyncStream<LiveSegment>
    func feed(_ pcm16: Data)
    func stop()
}

@MainActor
public final class CustomTranscriber: CustomTranscribing {
    /// Audio per HTTP request, and the least worth sending (Flutter `AudioPollingConfig`).
    static let chunkSeconds = 3.0
    static let minChunkBytes = 8000
    /// About ten minutes of audio waits while the provider is unreachable; older audio is dropped.
    static let maxBufferBytes = 19_200_000
    static let bytesPerSecond = 32000.0

    public var providerName: String {
        config.provider.rawValue
    }

    private let config: CustomSTTConfig
    private let transport: any CustomSTTTransport
    private let log: DebugLog?
    private let interval: Duration
    private var continuation: AsyncStream<LiveSegment>.Continuation?
    private var buffer = Data()
    /// Seconds of audio already transcribed: offsets the provider's times into the recording's.
    private var offset = 0.0
    private var loop: Task<Void, Never>?
    private var socket: (any CustomSTTSocket)?
    private var failures = 0
    private var nextConnect = ContinuousClock.now

    public init(config: CustomSTTConfig, transport: any CustomSTTTransport, log: DebugLog?, interval: Duration = .seconds(3)) {
        self.config = config
        self.transport = transport
        self.log = log
        self.interval = interval
    }

    public func start() -> AsyncStream<LiveSegment> {
        let (stream, continuation) = AsyncStream.makeStream(of: LiveSegment.self)
        self.continuation = continuation
        log?.add(.info, "stt", "custom STT started (\(config.provider.displayName))")
        if config.provider.isLive {
            openSocket()
        } else {
            loop = Task { [weak self, interval] in
                while !Task.isCancelled {
                    try? await Task.sleep(for: interval)
                    await self?.flush()
                }
            }
        }
        return stream
    }

    public func feed(_ pcm16: Data) {
        if config.provider.isLive {
            // Dropped (a pause, the network): reconnect, at most every five seconds.
            if socket == nil, continuation != nil, ContinuousClock.now >= nextConnect { openSocket() }
            socket?.send(audio: pcm16)
            return
        }
        guard loop != nil else { return }
        buffer.append(pcm16)
        if buffer.count > Self.maxBufferBytes { buffer.removeFirst(buffer.count - Self.maxBufferBytes) }
    }

    public func stop() {
        loop?.cancel()
        loop = nil
        socket?.send(text: #"{"type":"CloseStream"}"#)
        socket?.close()
        socket = nil
        // What is still buffered goes out once more, then the stream ends.
        let rest = buffer
        buffer = Data()
        guard !config.provider.isLive, rest.count >= Self.minChunkBytes else {
            continuation?.finish()
            continuation = nil
            return
        }
        Task {
            await send(rest)
            continuation?.finish()
            continuation = nil
        }
    }

    /// Sends what has gathered (at least `minChunkBytes`); on failure it stays for the next try.
    func flush() async {
        guard buffer.count >= Self.minChunkBytes else { return }
        let chunk = buffer
        buffer = Data()
        if await !send(chunk) {
            buffer = chunk + buffer
            if buffer.count > Self.maxBufferBytes { buffer.removeFirst(buffer.count - Self.maxBufferBytes) }
        }
    }

    @discardableResult
    private func send(_ chunk: Data) async -> Bool {
        let duration = Double(chunk.count) / Self.bytesPerSecond
        do {
            let request = try CustomSTTRequests.upload(config, wav: PCMWave.wav(pcm16: chunk))
            let (data, status) = try await transport.send(request)
            guard (200 ..< 300).contains(status) else { throw CustomSTTError.http(status: status) }
            let segments = try CustomSTTRequests.segments(from: data, duration: duration)
            emit(segments, base: offset)
            offset += duration
            failures = 0
            log?.add(.info, "stt", "custom STT: \(String(format: "%.1f", duration)) s, \(segments.count) segment(s)")
            return true
        } catch {
            failures += 1
            // Only the status or error kind: never the request (it carries the key).
            log?.add(failures > 2 ? .error : .warning, "stt", "custom STT request failed: \(Self.describe(error))")
            return false
        }
    }

    private func openSocket() {
        let request: URLRequest
        do {
            request = try CustomSTTRequests.deepgramSocket(config)
        } catch {
            log?.add(.error, "stt", "custom STT not configured")
            continuation?.finish()
            return
        }
        nextConnect = .now + .seconds(5)
        let socket = transport.openSocket(request)
        self.socket = socket
        loop = Task { [weak self] in
            for await message in socket.messages {
                guard let segments = CustomSTTRequests.deepgramSegments(from: message) else { continue }
                self?.emit(segments, base: 0)
            }
            self?.socketEnded(socket)
        }
    }

    private func socketEnded(_ ended: any CustomSTTSocket) {
        guard socket === ended else { return }
        log?.add(.warning, "stt", "custom STT connection closed")
        socket = nil
    }

    private func emit(_ segments: [CustomSTTSegment], base: Double) {
        for segment in segments {
            let speaker = segment.speaker ?? 0
            continuation?.yield(LiveSegment(
                id: UUID().uuidString.lowercased(), text: segment.text, speaker: "SPEAKER_\(String(format: "%02d", speaker))",
                speakerID: speaker, isUser: false, start: base + segment.start, end: base + segment.end
            ))
        }
    }

    static func describe(_ error: any Error) -> String {
        switch error {
        case let CustomSTTError.http(status): "HTTP \(status)"
        case CustomSTTError.undecodable: "unreadable answer"
        case CustomSTTError.incomplete: "not configured"
        case let error as URLError: "network (\(error.code.rawValue))"
        default: "error"
        }
    }
}

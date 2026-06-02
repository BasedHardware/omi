import Foundation
import Network

// MARK: - Realtime Omni Service
//
// One WebSocket client that talks to either Gemini 3.1 Flash Live or
// OpenAI gpt-realtime-2 and exposes two capabilities the floating bar needs:
//
//   • STT  — stream mic PCM in, receive the user's transcript out.
//   • TTS  — send assistant text in, receive spoken PCM audio out.
//
// Reasoning/tools are NOT done here — the transcript goes to ChatProvider
// (pi-mono/Claude + tools) exactly as before; this service is only the voice
// shell that replaces Deepgram (STT) + OpenAI TTS in the cascade.
//
// Wire protocols are the ones verified in the realtime-voice-demos web app:
//   OpenAI GA:  session.update {audio.input/output pcm}, input_audio_buffer.append,
//               response.create, response.output_audio(.delta), input transcription.
//   Gemini Live: BidiGenerateContentSetup, realtimeInput{audio}, clientContent,
//               serverContent.modelTurn.parts.inlineData / inputTranscription.
//
// Key resolution (phase 1): BYOK / env. Production should proxy through the omi
// backend so keys stay server-side and usage is metered — see `resolveKey`.

@MainActor
protocol RealtimeOmniServiceDelegate: AnyObject {
    func omniDidConnect()
    func omniDidReceiveInputTranscript(_ text: String, isFinal: Bool)
    func omniDidReceiveAudio(_ pcm24k: Data)
    func omniDidFinishTurn()
    func omniDidError(_ message: String)
}

final class RealtimeOmniService: NSObject {
    private let provider: RealtimeOmniProvider  // always concrete (never .auto)
    private let model: String
    /// omi backend base URL (https) — we connect to its /v1/omni/relay WS, which
    /// holds the provider keys and forwards to OpenAI/Gemini server-side.
    private let relayBaseURL: String
    private let authHeader: String
    /// STT-only: don't have the omni model speak — Claude generates the reply,
    /// existing TTS voices it. (When false, the model can speak via `speak`.)
    private let sttOnly: Bool
    private weak var delegate: RealtimeOmniServiceDelegate?

    private var task: URLSessionWebSocketTask?
    private lazy var session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
    private var isOpen = false
    private var pendingAudio: [Data] = []

    // Gemini's Live endpoint resets BOTH of Apple's WebSocket stacks
    // (URLSession drops after the HTTP/2 upgrade; Network.framework gets
    // ECONNABORTED). Node's `ws` connects fine, so Gemini is reached through a
    // small WS relay (localhost in dev → omi backend in prod). OpenAI connects
    // client-direct. So everything now goes over URLSession; NW is unused.
    private var usesNW: Bool { false }
    private var nw: NWConnection?

    /// Mic PCM input rate per provider (Gemini 16k, OpenAI GA requires ≥24k).
    var requiredInputSampleRate: Int { provider == .gptRealtime2 ? 24000 : 16000 }
    /// Both providers emit 24kHz PCM16.
    let outputSampleRate = 24000

    /// `provider` must be concrete (resolve `.auto` via RealtimeOmniSettings.effectiveProvider
    /// first). `apiKey` is resolved by the caller from BYOK / backend token.
    init(provider: RealtimeOmniProvider, relayBaseURL: String, authHeader: String,
         sttOnly: Bool = true, delegate: RealtimeOmniServiceDelegate) {
        self.provider = provider == .auto ? .geminiFlashLive : provider
        self.model = self.provider.modelID
        self.relayBaseURL = relayBaseURL
        self.authHeader = authHeader
        self.sttOnly = sttOnly
        self.delegate = delegate
        super.init()
    }

    // MARK: Lifecycle

    func start() {
        guard let request = makeRequest(), let url = request.url else {
            let name = provider.displayName
            Task { @MainActor in self.delegate?.omniDidError("Could not build \(name) request URL") }
            return
        }
        log("RealtimeOmni: connecting \(provider.displayName) → \(url.host ?? "?")")
        if usesNW {
            startNW(url: url)
            return
        }
        let t = session.webSocketTask(with: request)
        task = t
        t.resume()
        // Receive loop + session setup start from didOpenWithProtocol — touching
        // the socket before the handshake completes yields "Socket is not connected".
    }

    func stop() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        nw?.cancel()
        nw = nil
        isOpen = false
        pendingAudio.removeAll()
    }

    // MARK: - Network.framework transport (Gemini, HTTP/1.1 WebSocket)

    private func startNW(url: URL) {
        let opts = NWProtocolWebSocket.Options()
        opts.autoReplyPing = true
        let tls = NWProtocolTLS.Options()
        let params = NWParameters(tls: tls)
        params.defaultProtocolStack.applicationProtocols.insert(opts, at: 0)
        // NWEndpoint.url carries the path + query so the WS Upgrade hits the
        // BidiGenerateContent path with ?key=… intact.
        let conn = NWConnection(to: .url(url), using: params)
        nw = conn
        conn.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                log("RealtimeOmni: NW WS ready")
                self.receiveNW()
                self.sendSessionSetup()
            case .failed(let err):
                Task { @MainActor in self.delegate?.omniDidError("NW failed: \(err)") }
            case .cancelled:
                break
            default:
                break
            }
        }
        conn.start(queue: .global(qos: .userInitiated))
    }

    private func receiveNW() {
        nw?.receiveMessage { [weak self] data, _, _, error in
            guard let self else { return }
            if let error {
                Task { @MainActor in self.delegate?.omniDidError("NW receive: \(error)") }
                return
            }
            if let data { Task { @MainActor in self.handleMessage(data) } }
            if self.nw?.state == .ready { self.receiveNW() }
        }
    }

    private func sendNW(_ text: String) {
        guard let conn = nw else { return }
        let meta = NWProtocolWebSocket.Metadata(opcode: .text)
        let ctx = NWConnection.ContentContext(identifier: "send", metadata: [meta])
        conn.send(content: Data(text.utf8), contentContext: ctx, isComplete: true,
                  completion: .contentProcessed { [weak self] error in
            if let error { Task { @MainActor in self?.delegate?.omniDidError("NW send: \(error)") } }
        })
    }

    // MARK: STT — stream mic audio in

    /// Feed mic PCM16 mono at `requiredInputSampleRate`. Caller is responsible for
    /// resampling to that rate (16k mic → 24k for OpenAI).
    func sendAudio(_ pcm: Data) {
        let b64 = pcm.base64EncodedString()
        switch provider {
        case .gptRealtime2:
            send(json: ["type": "input_audio_buffer.append", "audio": b64])
        case .geminiFlashLive, .auto:
            send(json: ["realtimeInput": ["audio": ["data": b64, "mimeType": "audio/pcm;rate=16000"]]])
        }
    }

    /// Signal end of the user's PTT turn.
    func commitInputTurn() {
        switch provider {
        case .gptRealtime2:
            send(json: ["type": "input_audio_buffer.commit"])
        case .geminiFlashLive, .auto:
            send(json: ["realtimeInput": ["activityEnd": [:]]])
        }
    }

    // MARK: TTS — speak assistant text out

    /// Speak `text` through the omni model's native voice.
    func speak(_ text: String) {
        switch provider {
        case .gptRealtime2:
            send(json: [
                "type": "conversation.item.create",
                "item": ["type": "message", "role": "assistant",
                         "content": [["type": "output_text", "text": text]]],
            ])
            send(json: ["type": "response.create"])
        case .geminiFlashLive, .auto:
            send(json: ["clientContent": [
                "turns": [["role": "user", "parts": [["text": "Read this aloud verbatim: \(text)"]]]],
                "turnComplete": true,
            ]])
        }
    }

    // MARK: - Session setup per provider

    private func sendSessionSetup() {
        switch provider {
        case .gptRealtime2:
            send(json: [
                "type": "session.update",
                "session": [
                    "type": "realtime",
                    "output_modalities": ["audio"],
                    "audio": [
                        "input": [
                            "format": ["type": "audio/pcm", "rate": 24000],
                            // Manual turn control: PTT decides start/stop.
                            "turn_detection": NSNull(),
                            "transcription": ["model": "whisper-1"],
                        ],
                        "output": ["format": ["type": "audio/pcm", "rate": 24000], "voice": "marin"],
                    ],
                ],
            ])
        case .geminiFlashLive, .auto:
            // gemini-3.1-flash-live only supports AUDIO output (TEXT is rejected
            // with close 1007). For STT-only we ignore the audio and read
            // inputAudioTranscription. PTT controls turns manually, so disable
            // Gemini's automatic VAD and bracket the turn with activityStart/End.
            send(json: [
                "setup": [
                    "model": "models/\(model)",
                    "generationConfig": ["responseModalities": ["AUDIO"]],
                    "inputAudioTranscription": [:],
                    "outputAudioTranscription": [:],
                    "realtimeInputConfig": ["automaticActivityDetection": ["disabled": true]],
                ],
            ])
        }
    }

    private func makeRequest() -> URLRequest? {
        // Connect to the omi backend's omni relay. The backend holds the provider
        // keys and forwards to OpenAI/Gemini — so no keys ship in the client, and
        // Gemini works (server-side `websockets` connects where Apple's stacks can't).
        let base = relayBaseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        let wsBase = base.hasSuffix("/") ? String(base.dropLast()) : base
        let providerParam = provider == .gptRealtime2 ? "openai" : "gemini"
        guard var comps = URLComponents(string: "\(wsBase)/v1/omni/relay") else { return nil }
        comps.queryItems = [
            URLQueryItem(name: "provider", value: providerParam),
            URLQueryItem(name: "model", value: model),
        ]
        guard let url = comps.url else { return nil }
        var r = URLRequest(url: url)
        r.setValue(authHeader, forHTTPHeaderField: "Authorization")
        return r
    }

    // MARK: - Receive loop + parsing

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure(let error):
                log("RealtimeOmni: receive failed: \(error)")
                Task { @MainActor in self.delegate?.omniDidError(error.localizedDescription) }
            case .success(let message):
                let data: Data?
                switch message {
                case .string(let text): data = Data(text.utf8)
                case .data(let d): data = d
                @unknown default: data = nil
                }
                if let data { Task { @MainActor in self.handleMessage(data) } }
                self.receiveLoop()
            }
        }
    }

    @MainActor
    private func handleMessage(_ data: Data) {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        switch provider {
        case .gptRealtime2: handleOpenAI(obj)
        case .geminiFlashLive, .auto: handleGemini(obj)
        }
    }

    @MainActor
    private func handleOpenAI(_ e: [String: Any]) {
        guard let type = e["type"] as? String else { return }
        switch type {
        case "session.updated", "session.created":
            markReady()
        case "response.output_audio.delta":
            if let b64 = e["delta"] as? String, let d = Data(base64Encoded: b64) { delegate?.omniDidReceiveAudio(d) }
        case "conversation.item.input_audio_transcription.delta":
            if let t = e["delta"] as? String { delegate?.omniDidReceiveInputTranscript(t, isFinal: false) }
        case "conversation.item.input_audio_transcription.completed":
            if let t = e["transcript"] as? String { delegate?.omniDidReceiveInputTranscript(t, isFinal: true) }
        case "response.done":
            delegate?.omniDidFinishTurn()
        case "error":
            let msg = (e["error"] as? [String: Any])?["message"] as? String ?? "OpenAI realtime error"
            delegate?.omniDidError(msg)
        default:
            break
        }
    }

    @MainActor
    private func handleGemini(_ e: [String: Any]) {
        if e["setupComplete"] != nil { markReady(); return }
        guard let sc = e["serverContent"] as? [String: Any] else { return }
        if let it = sc["inputTranscription"] as? [String: Any], let t = it["text"] as? String {
            delegate?.omniDidReceiveInputTranscript(t, isFinal: false)
        }
        if let parts = (sc["modelTurn"] as? [String: Any])?["parts"] as? [[String: Any]] {
            for p in parts {
                if let inline = p["inlineData"] as? [String: Any],
                   let mime = inline["mimeType"] as? String, mime.contains("audio/pcm"),
                   let b64 = inline["data"] as? String, let d = Data(base64Encoded: b64) {
                    delegate?.omniDidReceiveAudio(d)
                }
            }
        }
        if (sc["turnComplete"] as? Bool) == true {
            delegate?.omniDidReceiveInputTranscript("", isFinal: true)
            delegate?.omniDidFinishTurn()
        }
    }

    @MainActor
    private func markReady() {
        log("RealtimeOmni: setup complete (ready)")
        guard !isOpen else { return }
        isOpen = true
        // Open the PTT turn before audio flows (Gemini manual-VAD).
        if provider == .geminiFlashLive || provider == .auto {
            send(json: ["realtimeInput": ["activityStart": [:]]])
        }
        for chunk in pendingAudio { sendAudio(chunk) }
        pendingAudio.removeAll()
        delegate?.omniDidConnect()
    }

    // MARK: - Send helpers

    private func send(json: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: json),
              let text = String(data: data, encoding: .utf8) else { return }
        if usesNW {
            sendNW(text)
            return
        }
        task?.send(.string(text)) { [weak self] error in
            if let error { Task { @MainActor in self?.delegate?.omniDidError(error.localizedDescription) } }
        }
    }
}

// MARK: - URLSessionWebSocketDelegate

extension RealtimeOmniService: URLSessionWebSocketDelegate {
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didOpenWithProtocol protocol: String?) {
        log("RealtimeOmni: WS didOpen")
        // Connection is up — now it's safe to receive and send the setup.
        receiveLoop()
        sendSessionSetup()
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        let r = reason.flatMap { String(data: $0, encoding: .utf8) } ?? ""
        Task { @MainActor in self.delegate?.omniDidError("WebSocket closed (\(closeCode.rawValue)) \(r)") }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        log("RealtimeOmni: didComplete err=\(String(describing: error))")
        if let error {
            Task { @MainActor in self.delegate?.omniDidError("WebSocket failed: \(error.localizedDescription)") }
        }
    }
}

import Foundation
import OmiCore

/// One frame of the `POST v2/voice-messages` stream (backend `routers/chat.py`
/// `create_voice_message_stream`): the transcribed question first, then the chat answer frames.
public enum VoiceMessageEvent: Sendable, Equatable {
    /// `message: <base64 JSON>`: the question as the backend heard it.
    case question(ChatMessage)
    case chat(ChatStreamEvent)
    /// `error: {"error":"no_speech",…}`: nothing was said.
    case noSpeech

    static func parse(_ line: String) -> VoiceMessageEvent? {
        if line.hasPrefix("message: ") {
            let encoded = String(line.dropFirst("message: ".count)).trimmingCharacters(in: .whitespaces)
            guard let data = Data(base64Encoded: encoded), let message = ChatMessageMapper.message(fromJSON: data) else { return nil }
            return .question(message)
        }
        if line.hasPrefix("error:402:") { return .chat(.failed(String(line.dropFirst("error:402:".count)))) }
        if line.hasPrefix("error: "), let data = line.dropFirst("error: ".count).data(using: .utf8),
           let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           object["error"] as? String == "no_speech"
        {
            return .noSpeech
        }
        return ChatStreamEvent.parse(line).map(Self.chat)
    }

    /// The Omi's question as an upload: Flutter's `[u32 LE length][frame]…` format, named so the
    /// backend's `decode_files_to_wav` picks the codec and frame size (`audio_…_fs<samples>_<epoch>.bin`).
    public static func file(
        frames: [Data], codec: String, sampleRate: Int, frameSamples: Int, startedAt: Date
    ) -> (name: String, data: Data) {
        var data = Data()
        for frame in frames {
            data += withUnsafeBytes(of: UInt32(frame.count).littleEndian) { Data($0) } + frame
        }
        return ("audio_omi_\(codec)_\(sampleRate)_1_fs\(frameSamples)_\(Int(startedAt.timeIntervalSince1970)).bin", data)
    }
}

public extension APIClient {
    /// `PATCH v1/conversations/{id}/starred?starred=…`.
    func starConversation(id: String, starred: Bool) async throws {
        let query = [URLQueryItem(name: "starred", value: starred ? "true" : "false")]
        _ = try await data(.patch, "v1/conversations/\(id)/starred", query: query)
    }

    /// `POST v2/voice-messages` (multipart `files`): a spoken question in, the chat answer streamed
    /// back like `v2/messages`. Used by the Omi's single press (Flutter `sendVoiceMessageStreamServer`).
    func sendVoiceMessage(filename: String, audio: Data) -> AsyncThrowingStream<VoiceMessageEvent, any Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var request = try await request(
                        .post, "v2/voice-messages",
                        body: .file(field: "files", filename: filename, mimeType: "application/octet-stream", data: audio)
                    )
                    request.setValue("1", forHTTPHeaderField: "X-Omi-Chat-Failure-Protocol")
                    request.timeoutInterval = 180
                    let (bytes, response) = try await session.bytes(for: request)
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard (200 ..< 300).contains(status) else { throw APIError.http(status: status, body: "") }
                    for try await line in bytes.lines where !line.isEmpty && !line.hasPrefix(":") {
                        if let event = VoiceMessageEvent.parse(line) { continuation.yield(event) }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

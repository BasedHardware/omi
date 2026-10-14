import Foundation

/// How audio goes to each provider and how its answer becomes segments, as Flutter builds them
/// (`SttProviderConfig.buildRequestConfig`, `SttResponseSchema`). Pure functions, so the wire
/// shapes test without a network.
public enum CustomSTTRequests {
    /// The HTTP providers: one 16 kHz mono WAV per request (multipart, field `file`).
    public static func upload(_ config: CustomSTTConfig, wav: Data, boundary: String = "omi-\(UUID().uuidString)") throws -> URLRequest {
        guard config.isComplete, !config.provider.isLive, let endpoint = config.endpoint else { throw CustomSTTError.incomplete }
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let key = config.apiKey, config.provider.requiresAPIKey {
            request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        }
        var body = Data()
        for (name, value) in fields(config) {
            body += Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8)
        }
        body += Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n".utf8)
        body += Data("Content-Type: audio/wav\r\n\r\n".utf8) + wav + Data("\r\n--\(boundary)--\r\n".utf8)
        request.httpBody = body
        return request
    }

    /// The form fields per provider; `multi` (detect) sends no language, as the APIs expect.
    static func fields(_ config: CustomSTTConfig) -> [(String, String)] {
        let language = config.effectiveLanguage == "multi" ? nil : config.effectiveLanguage
        var fields: [(String, String)] = []
        switch config.provider {
        case .openai:
            fields = [("model", config.effectiveModel), ("response_format", "verbose_json"), ("timestamp_granularities[]", "segment")]
        case .openaiDiarize:
            fields = [("model", config.effectiveModel), ("response_format", "diarized_json"), ("chunking_strategy", "auto")]
        case .localWhisper:
            fields = [("temperature", "0.0"), ("temperature_inc", "0.2"), ("response_format", "verbose_json")]
        case .custom, .deepgramLive:
            break
        }
        if let language { fields.append(("language", language)) }
        return fields
    }

    /// An HTTP answer: `segments` with times (speakers for diarize), else the whole `text` as one
    /// segment spanning `duration`.
    public static func segments(from data: Data, duration: Double) throws -> [CustomSTTSegment] {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw CustomSTTError.undecodable }
        var speakers: [String: Int] = [:]
        if let segments = object["segments"] as? [[String: Any]], !segments.isEmpty {
            return segments.compactMap { segment in
                let text = (segment["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return nil }
                let start = (segment["start"] as? NSNumber)?.doubleValue ?? 0
                let end = (segment["end"] as? NSNumber)?.doubleValue ?? start
                return CustomSTTSegment(text: text, start: start, end: end, speaker: speakerNumber(segment["speaker"], known: &speakers))
            }
        }
        let text = (object["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? [] : [CustomSTTSegment(text: text, start: 0, end: duration)]
    }

    /// Deepgram live: `wss://api.deepgram.com/v1/listen` with linear16 at 16 kHz, `Token` auth.
    public static func deepgramSocket(_ config: CustomSTTConfig) throws -> URLRequest {
        guard config.isComplete, config.provider == .deepgramLive, let endpoint = config.endpoint,
              var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false) else { throw CustomSTTError.incomplete }
        components.queryItems = [
            ("model", config.effectiveModel), ("language", config.effectiveLanguage), ("smart_format", "true"),
            ("punctuate", "true"), ("diarize", "true"), ("interim_results", "false"), ("no_delay", "true"),
            ("endpointing", "300"), ("encoding", "linear16"), ("sample_rate", "16000"), ("channels", "1"),
        ].map { URLQueryItem(name: $0.0, value: $0.1) }
        guard let url = components.url else { throw CustomSTTError.incomplete }
        var request = URLRequest(url: url)
        request.setValue("Token \(config.apiKey ?? "")", forHTTPHeaderField: "Authorization")
        return request
    }

    /// One Deepgram message: a final `Results` turns into one segment per speaker run; anything
    /// else (metadata, interim results, empty speech) is nil.
    public static func deepgramSegments(from text: String) -> [CustomSTTSegment]? {
        guard let data = text.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              (object["type"] as? String ?? "Results") == "Results", object["is_final"] as? Bool ?? true,
              let alternative = ((object["channel"] as? [String: Any])?["alternatives"] as? [[String: Any]])?.first
        else { return nil }
        let words = alternative["words"] as? [[String: Any]] ?? []
        var runs: [CustomSTTSegment] = []
        for word in words {
            let value = (word["punctuated_word"] as? String ?? word["word"] as? String ?? "")
            guard !value.isEmpty else { continue }
            let start = (word["start"] as? NSNumber)?.doubleValue ?? 0
            let end = (word["end"] as? NSNumber)?.doubleValue ?? start
            let speaker = (word["speaker"] as? NSNumber)?.intValue
            if let last = runs.last, last.speaker == speaker {
                runs[runs.count - 1] = CustomSTTSegment(text: last.text + " " + value, start: last.start, end: end, speaker: speaker)
            } else {
                runs.append(CustomSTTSegment(text: value, start: start, end: end, speaker: speaker))
            }
        }
        if runs.isEmpty, let transcript = alternative["transcript"] as? String, !transcript.isEmpty {
            let start = (object["start"] as? NSNumber)?.doubleValue ?? 0
            runs = [CustomSTTSegment(text: transcript, start: start, end: start + ((object["duration"] as? NSNumber)?.doubleValue ?? 0))]
        }
        return runs.isEmpty ? nil : runs
    }

    /// OpenAI diarize names speakers `A`, `B`…, Deepgram numbers them: both become 0, 1, …
    private static func speakerNumber(_ value: Any?, known: inout [String: Int]) -> Int? {
        if let number = value as? NSNumber { return number.intValue }
        guard let name = value as? String, !name.isEmpty else { return nil }
        if let digits = Int(name.filter(\.isNumber)) { return digits }
        if let index = known[name] { return index }
        known[name] = known.count
        return known[name]
    }
}

/// A 16-bit mono PCM WAV container (what the HTTP providers take).
public enum PCMWave {
    public static func wav(pcm16: Data, sampleRate: Int = 16000) -> Data {
        var header = Data("RIFF".utf8)
        func append(_ value: UInt32) {
            header += withUnsafeBytes(of: value.littleEndian) { Data($0) }
        }
        func append16(_ value: UInt16) {
            header += withUnsafeBytes(of: value.littleEndian) { Data($0) }
        }
        append(UInt32(36 + pcm16.count))
        header += Data("WAVEfmt ".utf8)
        append(16)
        append16(1)
        append16(1)
        append(UInt32(sampleRate))
        append(UInt32(sampleRate * 2))
        append16(2)
        append16(16)
        header += Data("data".utf8)
        append(UInt32(pcm16.count))
        return header + pcm16
    }
}

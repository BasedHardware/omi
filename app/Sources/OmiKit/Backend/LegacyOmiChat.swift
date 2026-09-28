import Foundation

// Port of `react-native/src/legacyOmiChat.ts` — Old-plane (api.omi.me) chat
// history and terminal-stream parsing. The old stream is a line-based SSE
// dialect with base64-encoded JSON payloads; it is parsed with the same
// incremental semantics as the TS source.

public enum OmiChatStreamEvent: Sendable, Equatable {
    case data(text: String)
    case think(text: String)
    case error(text: String)
    case done(message: ChatMessage)
    case message(message: ChatMessage)
}

enum LegacyOmiChat {
    /// `decodeOmiJson`: base64 → percent-hex → UTF-8 (decodeURIComponent over
    /// an all-percent encoding is exactly a UTF-8 decode).
    static func decodeOmiJSON(_ value: String) throws -> JSONValue {
        guard let bytes = Base64Codec.decode(trimWhitespace(value)) else {
            throw ChatClientError.malformed("Omi chat stream is malformed")
        }
        let text = String(decoding: bytes, as: UTF8.self)
        guard let parsed = JSON.parseOrNull(text) else {
            throw ChatClientError.malformed("Omi chat message is malformed")
        }
        return parsed
    }

    static func fieldValue(_ line: String, _ name: String) -> String? {
        guard line.hasPrefix("\(name):") else { return nil }
        var value = String(line.dropFirst(name.count + 1))
        if value.hasPrefix(" ") { value = String(value.dropFirst(1)) }
        return replaceAll(value, "__CRLF__", "\n")
    }

    static func parseLine(_ line: String) throws -> OmiChatStreamEvent? {
        if line.isEmpty || line.hasPrefix(":") { return nil }
        if let data = fieldValue(line, "data") { return .data(text: data) }
        if let think = fieldValue(line, "think") { return .think(text: think) }
        if let error = fieldValue(line, "error") { return .error(text: error) }
        if let done = fieldValue(line, "done") {
            let message = try parseMessage(decodeOmiJSON(done))
            guard message.sender == .ai else {
                throw ChatClientError.malformed("Omi chat terminal sender is invalid")
            }
            return .done(message: message)
        }
        if let side = fieldValue(line, "message") {
            return .message(message: try parseMessage(decodeOmiJSON(side)))
        }
        return nil
    }

    /// Port of `parseOmiMessage`.
    static func parseMessage(_ value: JSONValue?) throws -> ChatMessage {
        guard let row = value, row.isRecord else {
            throw ChatClientError.malformed("Omi chat message is malformed")
        }
        guard let id = row["id"]?.stringValue, !id.isEmpty,
            let text = row["text"]?.stringValue,
            let senderRaw = row["sender"]?.stringValue,
            senderRaw == "human" || senderRaw == "ai",
            let createdAt = row["created_at"].flatMap(createdAtValue)
        else {
            throw ChatClientError.malformed("Omi chat message is malformed")
        }
        return ChatMessage(
            id: id, text: text, sender: ChatSender(rawValue: senderRaw) ?? .ai,
            createdAt: createdAt, generationOutcome: nil
        )
    }

    /// `Date.parse` over the `created_at` string; NaN → malformed.
    static func createdAtValue(_ value: JSONValue) -> Int64? {
        guard let text = value.stringValue else { return nil }
        return parseEpochMilliseconds(text)
    }

    /// Port of `omiHistoryOffset`.
    static func historyOffset(_ cursor: String) throws -> Int {
        let prefix = "omi-offset:"
        guard cursor.hasPrefix(prefix) else {
            throw ChatClientError.malformed("Omi chat cursor is malformed")
        }
        let digits = String(cursor.dropFirst(prefix.count))
        guard !digits.isEmpty else {
            throw ChatClientError.malformed("Omi chat cursor is malformed")
        }
        for scalar in digits.unicodeScalars
        where scalar.value < 0x30 || scalar.value > 0x39 {
            throw ChatClientError.malformed("Omi chat cursor is malformed")
        }
        guard let offset = Int(digits), offset <= Int(Int32.max) else {
            throw ChatClientError.malformed("Omi chat cursor is malformed")
        }
        return offset
    }

    /// Port of `parseOmiHistory`.
    static func parseHistory(_ body: String?, offset: Int) throws -> ChatHistoryPage {
        guard let body, let rows = JSON.parseOrNull(body)?.arrayValue, rows.count <= 50
        else {
            throw ChatClientError.malformed("Omi chat history is malformed")
        }
        let messages = try rows.map(parseMessage).reversed()
        let hasOlder = rows.count == 50
        return ChatHistoryPage(
            messages: Array(messages),
            olderCursor: hasOlder ? "omi-offset:\(offset + rows.count)" : nil,
            hasOlder: hasOlder
        )
    }

    /// Port of `parseOmiChatStream`.
    static func parseStream(_ body: String?) throws -> ChatMessage {
        guard let body, body.count <= 4_000_000 else {
            throw ChatClientError.malformed("Omi chat stream is malformed")
        }
        var parser = IncrementalOmiChatParser()
        let events = try parser.push(body) + parser.finish()
        for event in events.reversed() {
            if case .done(let message) = event { return message }
        }
        throw ChatClientError.malformed("Omi chat ended without a terminal message")
    }
}

/// Incremental Old-plane chat stream parser (`IncrementalOmiChatParser`).
public struct IncrementalOmiChatParser: Sendable {
    var decoder = IncrementalUTF8Decoder()
    var text = ""

    public init() {}

    public mutating func push(_ chunk: String) throws -> [OmiChatStreamEvent] {
        text += chunk
        return try drain(finishing: false)
    }

    public mutating func pushBytes(_ chunk: [UInt8]) throws -> [OmiChatStreamEvent] {
        text += (try? decoder.push(chunk)) ?? ""
        return try drain(finishing: false)
    }

    public mutating func finish() throws -> [OmiChatStreamEvent] {
        _ = try? decoder.finish()
        return try drain(finishing: true)
    }

    mutating func drain(finishing: Bool) throws -> [OmiChatStreamEvent] {
        text = replaceAll(text, "\r\n", "\n")
        text = replaceAll(text, "\r", "\n")
        var events = [OmiChatStreamEvent]()
        while !text.isEmpty {
            guard let end = text.range(of: "\n\n") else {
                if !finishing { return events }
                try consumeFrame(text, into: &events)
                text = ""
                return events
            }
            try consumeFrame(String(text[..<end.lowerBound]), into: &events)
            text = String(text[end.upperBound...])
        }
        return events
    }

    mutating func consumeFrame(_ frame: String, into events: inout [OmiChatStreamEvent]) throws {
        for line in splitDelimiter(frame, "\n") {
            if let event = try LegacyOmiChat.parseLine(line) {
                events.append(event)
            }
        }
    }
}

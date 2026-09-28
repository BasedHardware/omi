import Foundation

// Port of `packages/adapters-platform/src/chat-generation.ts`
// `IncrementalChatGenerationParser`: a stateful UTF-8 + SSE parser. Bytes and
// every SSE field may be split across arbitrary chunks; multi-line data is
// joined with a newline exactly once, per SSE.

public struct ParsedGenerationEvent: Sendable, Equatable {
    public var id: String
    public var frame: ChatGenerationFrame
}

public enum GenerationParseError: Error, Equatable, Sendable {
    case truncatedEventAtStreamEnd
    case eventContainsNUL
    case eventRequiresIdAndName
    case dataIsNotJSON
    case eventNameMismatch
    case invalidUTF8
    case truncatedUTF8
}

public struct IncrementalChatGenerationParser: Sendable {
    var decoder = IncrementalUTF8Decoder()
    var text = ""
    var eventName: String?
    var eventId: String?
    var data = [String]()

    public init() {}

    public mutating func push(_ chunk: String) throws -> [ParsedGenerationEvent] {
        text += chunk
        return try drainLines(finishing: false)
    }

    public mutating func pushBytes(_ chunk: [UInt8]) throws -> [ParsedGenerationEvent] {
        do {
            text += try decoder.push(chunk)
        } catch {
            throw GenerationParseError.invalidUTF8
        }
        return try drainLines(finishing: false)
    }

    public mutating func finish() throws -> [ParsedGenerationEvent] {
        do {
            text += try decoder.finish()
        } catch {
            throw GenerationParseError.truncatedUTF8
        }
        let events = try drainLines(finishing: true)
        if eventName != nil || eventId != nil || !data.isEmpty {
            throw GenerationParseError.truncatedEventAtStreamEnd
        }
        return events
    }

    mutating func drainLines(finishing: Bool) throws -> [ParsedGenerationEvent] {
        var events = [ParsedGenerationEvent]()
        while !text.isEmpty {
            var end = -1
            var width = 0
            var found = false
            let bytes = Array(text.utf8)
            // Scan by UTF-8 byte offsets of ASCII terminators; newline bytes
            // cannot appear inside multi-byte sequences, so index math on the
            // string is safe via utf8 offsets.
            _ = bytes
            var index = text.startIndex
            var offset = 0
            while index < text.endIndex {
                let character = text[index]
                if character == "\n" {
                    end = offset
                    width = 1
                    found = true
                    break
                }
                if character == "\r" {
                    if offset == text.count - 1 && !finishing {
                        return events
                    }
                    let next = text.index(after: index)
                    let nextIsLF = next < text.endIndex && text[next] == "\n"
                    end = offset
                    width = nextIsLF ? 2 : 1
                    found = true
                    break
                }
                index = text.index(after: index)
                offset += 1
            }
            if !found {
                if !finishing { return events }
                let line = text
                text = ""
                try consumeLine(line, into: &events)
                return events
            }
            let line = String(text.prefix(end))
            text = String(text.dropFirst(end + width))
            try consumeLine(line, into: &events)
        }
        return events
    }

    mutating func consumeLine(_ line: String, into events: inout [ParsedGenerationEvent]) throws {
        if line.isEmpty {
            if let event = try dispatch() {
                events.append(event)
            }
            return
        }
        if line.hasPrefix(":") { return }
        guard let colon = line.firstIndex(of: ":") else {
            try applyField(line, value: "")
            return
        }
        let field = String(line[..<colon])
        var value = String(line[line.index(after: colon)...])
        if value.hasPrefix(" ") { value = String(value.dropFirst(1)) }
        try applyField(field, value: value)
    }

    mutating func applyField(_ field: String, value: String) throws {
        if field == "event" {
            eventName = value
        } else if field == "id" {
            if value.utf8.contains(0) {
                throw GenerationParseError.eventContainsNUL
            }
            eventId = value
        } else if field == "data" {
            data.append(value)
        }
    }

    mutating func dispatch() throws -> ParsedGenerationEvent? {
        if data.isEmpty {
            resetEvent()
            return nil
        }
        let name = eventName
        let id = eventId
        let payload = data.joined(separator: "\n")
        resetEvent()
        guard let name, !name.isEmpty, let id, !id.isEmpty else {
            throw GenerationParseError.eventRequiresIdAndName
        }
        guard let raw = JSON.parseOrNull(payload) else {
            throw GenerationParseError.dataIsNotJSON
        }
        guard let frame = wireToChatGenerationFrame(raw), frame.kind == name else {
            throw GenerationParseError.eventNameMismatch
        }
        return ParsedGenerationEvent(id: id, frame: frame)
    }

    mutating func resetEvent() {
        eventName = nil
        eventId = nil
        data = []
    }
}

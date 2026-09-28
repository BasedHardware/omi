import Foundation

// Port of `packages/adapters-platform/src/chat.ts` — the ratified Chat wire
// codecs: history/admission envelope parsing, generation frame validation,
// and the transcript parser. Algorithms ported exactly.

public struct ChatWireMessage: Sendable, Equatable {
    public var id: String
    public var text: String
    /// "human" | "ai" | "unknown"
    public var sender: String
    /// "text" | "day_summary" | "unknown"
    public var type: String
    public var createdAt: Int64
    public var updatedAt: Int64
    public var chatSessionId: String?
    public var appId: String?
    public var journalRevision: Int64
    public var payloadHash: String
    public var messageSource: String
    /// null or number
    public var rating: JSONValue
    public var reported: Bool
    /// "completed" | "cancelled" | "unknown" (unknown only for unknown senders)
    public var generationOutcome: String
    public var revision: String?
    public var attachments: [ChatWireAttachment]
}

public struct ChatWireAttachment: Sendable, Equatable {
    public var id: String
    public var displayName: String
    public var mediaType: String
    public var sizeBytes: Int64
    public var contentReference: String?
}

public struct ChatWireCapabilities: Sendable, Equatable {
    public var maxAttachmentsPerMessage: Int64
    public var maxAttachmentBytes: Int64
    public var allowedAttachmentMimeTypes: [String]
}

public struct ChatWireHistoryEnvelope: Sendable, Equatable {
    public var messages: [ChatWireMessage]
    public var olderCursor: String?
    public var hasOlder: Bool
    public var capabilities: ChatWireCapabilities
}

public struct ChatWireAdmission: Sendable, Equatable {
    public var message: ChatWireMessage
    public var generationId: String
}

public enum ChatGenerationFrame: Sendable, Equatable {
    case snapshot(text: String)
    case delta(text: String)
    case done(message: ChatWireMessage)
    case cancelled(message: ChatWireMessage?)
    case failed(code: String, retryable: Bool)

    public var kind: String {
        switch self {
        case .snapshot: return "snapshot"
        case .delta: return "delta"
        case .done: return "done"
        case .cancelled: return "cancelled"
        case .failed: return "failed"
        }
    }
}

func isNonNegativeInteger(_ value: JSONValue?) -> Bool {
    guard let integer = value?.safeIntegerValue else { return false }
    return integer >= 0
}

func isNullableString(_ value: JSONValue?) -> Bool {
    // Strict: the key must be present, and null or a string (TS `=== null`).
    guard value != nil else { return false }
    return value!.isNull || value!.stringValue != nil
}

private func parseSender(_ value: JSONValue?) -> String {
    let text = value?.stringValue
    if text == "human" || text == "ai" { return text! }
    return "unknown"
}

private func parseType(_ value: JSONValue?) -> String {
    let text = value?.stringValue
    if text == "text" || text == "day_summary" { return text! }
    return "unknown"
}

private func wireToChatAttachment(_ raw: JSONValue?) -> ChatWireAttachment? {
    guard let raw, raw.isRecord else { return nil }
    guard let id = raw["id"]?.stringValue,
        let displayName = raw["displayName"]?.stringValue,
        let mediaType = raw["mediaType"]?.stringValue,
        isNonNegativeInteger(raw["sizeBytes"]),
        isNullableString(raw["contentReference"]),
        !(raw["contentReference"]?.stringValue == "")
    else { return nil }
    return ChatWireAttachment(
        id: id, displayName: displayName, mediaType: mediaType,
        sizeBytes: raw["sizeBytes"]!.safeIntegerValue!,
        contentReference: raw["contentReference"]?.stringValue
    )
}

/// Ratified camel-case wire row → domain record. Unparseable → nil.
public func wireToChatMessage(_ raw: JSONValue?) -> ChatWireMessage? {
    guard let raw, raw.isRecord else { return nil }
    let idRaw = raw["id"]?.stringValue
    let id = idRaw != nil ? parseRecordId(idRaw!) : nil
    let sender = parseSender(raw["sender"])
    let type = parseType(raw["type"])
    let generationOutcome = raw["generationOutcome"]
    guard
        let id,
        let text = raw["text"]?.stringValue,
        isNonNegativeInteger(raw["createdAt"]),
        isNonNegativeInteger(raw["updatedAt"]),
        isNullableString(raw["chatSessionId"]),
        isNullableString(raw["appId"]),
        isNonNegativeInteger(raw["journalRevision"]),
        let payloadHash = raw["payloadHash"]?.stringValue,
        let messageSource = raw["messageSource"]?.stringValue,
        raw["rating"]?.isNull == true || raw["rating"]?.numberValue != nil,
        raw["reported"]?.boolValue != nil,
        (generationOutcome?.isNull == true) || generationOutcome?.stringValue == "completed"
            || generationOutcome?.stringValue == "cancelled",
        !(sender == "human" && generationOutcome?.isNull != true),
        !(sender == "ai" && generationOutcome?.isNull == true),
        isNullableString(raw["revision"]),
        raw["attachments"]?.arrayValue != nil
    else { return nil }
    var attachments = [ChatWireAttachment]()
    for attachment in raw["attachments"]!.arrayValue! {
        guard let parsed = wireToChatAttachment(attachment) else { return nil }
        attachments.append(parsed)
    }
    // `sender == human` pins the outcome to null; `sender == ai` with a
    // non-completed outcome pins to "cancelled".
    let outcome: String
    if sender == "human" {
        outcome = ""
    } else if sender == "ai" {
        outcome = generationOutcome?.stringValue == "completed" ? "completed" : "cancelled"
    } else {
        outcome = generationOutcome?.stringValue ?? "unknown"
    }
    return ChatWireMessage(
        id: id.id, text: text, sender: sender, type: type,
        createdAt: raw["createdAt"]!.safeIntegerValue!,
        updatedAt: raw["updatedAt"]!.safeIntegerValue!,
        chatSessionId: raw["chatSessionId"]?.stringValue,
        appId: raw["appId"]?.stringValue,
        journalRevision: raw["journalRevision"]!.safeIntegerValue!,
        payloadHash: payloadHash, messageSource: messageSource,
        rating: raw["rating"] ?? .null,
        reported: raw["reported"]!.boolValue!,
        generationOutcome: outcome,
        revision: raw["revision"]?.stringValue,
        attachments: attachments
    )
}

public struct ParsedRecordId: Sendable, Equatable {
    public var id: String
}

/// Port of `parseRecordId` from `@omi-core/contracts` (ids.ts): a non-empty
/// record id with no control characters. Kept conservative on purpose — the
/// ratified grammar here is "non-empty string".
public func parseRecordId(_ raw: String) -> ParsedRecordId? {
    guard !raw.isEmpty else { return nil }
    for scalar in raw.unicodeScalars where scalar.value < 0x20 {
        return nil
    }
    return ParsedRecordId(id: raw)
}

private func wireToCapabilities(_ raw: JSONValue?) -> ChatWireCapabilities? {
    guard let raw, raw.isRecord else { return nil }
    guard
        isNonNegativeInteger(raw["maxAttachmentsPerMessage"]),
        isNonNegativeInteger(raw["maxAttachmentBytes"]),
        let mimeTypes = raw["allowedAttachmentMimeTypes"]?.arrayValue,
        mimeTypes.allSatisfy({ $0.stringValue != nil })
    else { return nil }
    return ChatWireCapabilities(
        maxAttachmentsPerMessage: raw["maxAttachmentsPerMessage"]!.safeIntegerValue!,
        maxAttachmentBytes: raw["maxAttachmentBytes"]!.safeIntegerValue!,
        allowedAttachmentMimeTypes: mimeTypes.compactMap { $0.stringValue }
    )
}

/// Strict ratified history envelope. A malformed row invalidates the page.
public func wireToChatHistoryEnvelope(_ raw: JSONValue?) -> ChatWireHistoryEnvelope? {
    guard let raw, raw.isRecord, raw["messages"]?.arrayValue != nil,
        raw["page"]?.isRecord == true
    else { return nil }
    let capabilities = wireToCapabilities(raw["capabilities"])
    let olderCursorJSON = raw["page"]!["olderCursor"]
    let hasOlder = raw["page"]!["hasOlder"]?.boolValue
    guard let capabilities, isNullableString(olderCursorJSON), let hasOlder else {
        return nil
    }
    let olderCursor = olderCursorJSON?.stringValue
    if hasOlder {
        guard olderCursor != nil else { return nil }
    } else {
        guard olderCursor == nil else { return nil }
    }
    var messages = [ChatWireMessage]()
    var seen = Set<String>()
    for rawMessage in raw["messages"]!.arrayValue! {
        guard let message = wireToChatMessage(rawMessage) else { return nil }
        guard !seen.contains(message.id) else { return nil }
        seen.insert(message.id)
        messages.append(message)
    }
    return ChatWireHistoryEnvelope(
        messages: messages, olderCursor: olderCursor, hasOlder: hasOlder,
        capabilities: capabilities
    )
}

/// Validate one parsed SSE data object against the ratified frame grammar.
public func wireToChatGenerationFrame(_ raw: JSONValue?) -> ChatGenerationFrame? {
    guard let raw, raw.isRecord, let kind = raw["kind"]?.stringValue else { return nil }
    switch kind {
    case "snapshot", "delta":
        guard let text = raw["text"]?.stringValue else { return nil }
        return kind == "snapshot" ? .snapshot(text: text) : .delta(text: text)
    case "done":
        let message = wireToChatMessage(raw["message"])
        guard let message, message.sender == "ai", message.generationOutcome == "completed"
        else { return nil }
        return .done(message: message)
    case "cancelled":
        guard raw.objectValue?.contains(where: { $0.0 == "message" }) == true else {
            return nil
        }
        if raw["message"]?.isNull == true { return .cancelled(message: nil) }
        let message = wireToChatMessage(raw["message"])
        guard let message, message.sender == "ai", message.generationOutcome == "cancelled"
        else { return nil }
        return .cancelled(message: message)
    case "failed":
        guard raw.objectValue?.contains(where: { $0.0 == "message" }) == false else {
            return nil
        }
        guard let error = raw["error"], error.isRecord,
            let code = error["code"]?.stringValue,
            let retryable = error["retryable"]?.boolValue
        else { return nil }
        return .failed(code: code, retryable: retryable)
    default:
        return nil
    }
}

/// Validate the complete plain-JSON admission returned by the send POST.
public func wireToChatAdmissionEnvelope(_ raw: JSONValue?) -> ChatWireAdmission? {
    guard let raw, raw.isRecord else { return nil }
    let message = wireToChatMessage(raw["message"])
    let generation = raw["generation"]
    guard let message, message.sender == "human", generation?.isRecord == true,
        let generationId = generation?["id"]?.stringValue, !generationId.isEmpty
    else { return nil }
    return ChatWireAdmission(message: message, generationId: generationId)
}

// MARK: - Complete SSE transcript parsing

struct ParsedChatGenerationEvent: Equatable {
    var id: String
    var frame: ChatGenerationFrame
}

/// Parse a complete SSE transcript. Every data event needs an opaque id and
/// its event name must agree with `data.kind`; comments/heartbeats are
/// ignored. Returns nil on malformed input.
func parseChatGenerationEvents(_ text: String) -> [ParsedChatGenerationEvent]? {
    var events = [ParsedChatGenerationEvent]()
    var seenEventIds = Set<String>()
    let normalized = replaceAll(text, "\r\n", "\n")
    for block in splitDelimiter(normalized, "\n\n") {
        if trimWhitespace(block).isEmpty { continue }
        var eventName: String?
        var eventId: String?
        var data = [String]()
        for line in splitDelimiter(block, "\n") {
            if line.hasPrefix(":") { continue }
            if line.hasPrefix("event:") {
                eventName = trimWhitespace(String(line.dropFirst(6)))
            } else if line.hasPrefix("id:") {
                eventId = trimWhitespace(String(line.dropFirst(3)))
            } else if line.hasPrefix("data:") {
                data.append(trimStart(String(line.dropFirst(5))))
            }
        }
        if data.isEmpty { continue }
        guard let id = eventId, !id.isEmpty else { return nil }
        if seenEventIds.contains(id) { continue }
        seenEventIds.insert(id)
        let raw = JSON.parseOrNull(data.joined(separator: "\n"))
        guard let frame = wireToChatGenerationFrame(raw), eventName == frame.kind else {
            return nil
        }
        events.append(ParsedChatGenerationEvent(id: id, frame: frame))
    }
    return events
}

/// Parse a complete SSE transcript into its frames; nil when malformed.
public func parseChatGenerationEventStream(_ text: String) -> [ChatGenerationFrame]? {
    guard let events = parseChatGenerationEvents(text) else { return nil }
    return events.map { $0.frame }
}

/// FNV-1a over the sorted id list — a stable synthetic set version
/// (`contentHash` in chat.ts, including the 0x2c separator byte).
public func chatContentHash(_ ids: [String]) -> String {
    // FNV-1a in Int with explicit 32-bit masking (Skip-safe: no UInt math).
    var hash = 0x811C9DC5
    for id in ids.sorted() {
        for codeUnit in Array(id.utf16) {
            hash = hash ^ Int(codeUnit)
            hash = (hash &* 0x01000193) & 0xFFFF_FFFF
        }
        hash = hash ^ 0x2C
        hash = (hash &* 0x01000193) & 0xFFFF_FFFF
    }
    return "fnv-\(String(hash, radix: 16))"
}

/// 32-bit wrapping multiply (Math.imul).
func multiply32(_ a: UInt32, _ b: UInt32) -> UInt32 {
    a &* b
}

// MARK: - Small string helpers (Skip-safe: no Character APIs)

public func replaceAll(_ value: String, _ target: String, _ replacement: String) -> String {
    value.replacingOccurrences(of: target, with: replacement)
}

/// Split on an exact multi-character delimiter.
public func splitDelimiter(_ value: String, _ delimiter: String) -> [String] {
    guard !delimiter.isEmpty else { return [value] }
    var parts = [String]()
    var current = ""
    var index = value.startIndex
    while index < value.endIndex {
        if value[index...].hasPrefix(delimiter) {
            parts.append(current)
            current = ""
            index = value.index(index, offsetBy: delimiter.count)
        } else {
            current.append(value[index])
            index = value.index(after: index)
        }
    }
    parts.append(current)
    return parts
}

public func trimWhitespace(_ value: String) -> String {
    var result = value
    while let first = result.first, first == " " || first == "\t" || first == "\n" || first == "\r" {
        result.removeFirst()
    }
    while let last = result.last, last == " " || last == "\t" || last == "\n" || last == "\r" {
        result.removeLast()
    }
    return result
}

func trimStart(_ value: String) -> String {
    var result = value
    while let first = result.first, first == " " || first == "\t" {
        result.removeFirst()
    }
    return result
}

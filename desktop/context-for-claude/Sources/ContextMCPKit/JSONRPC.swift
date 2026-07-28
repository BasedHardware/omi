import Foundation

// MARK: - JSON

/// A whole JSON document as a value type.
///
/// MCP payloads are schema-free at the transport layer — tool arguments are whatever the model
/// decided to send, and tool schemas are arbitrary JSON Schema. A concrete `Codable` tree keeps the
/// server free of `Any` casts and of `JSONSerialization`'s untyped dictionaries.
public enum JSONValue: Codable, Sendable, Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            // Bool before Double: JSONDecoder keeps them distinct, and `true` must not become 1.
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Value is not representable as JSON"
            )
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null:
            try container.encodeNil()
        case .bool(let value):
            try container.encode(value)
        case .number(let value):
            // Request ids round-trip through this enum; a client that sent `1` must get `1` back,
            // not `1.0`. NaN/infinity would make the encoder throw, so they degrade to null.
            guard value.isFinite else {
                try container.encodeNil()
                return
            }
            if value == value.rounded(), abs(value) < 9_007_199_254_740_992 {
                try container.encode(Int64(value))
            } else {
                try container.encode(value)
            }
        case .string(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        }
    }
}

// MARK: - Reading values out

public extension JSONValue {
    var isNull: Bool {
        if case .null = self { return true }
        return false
    }

    var stringValue: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    var doubleValue: Double? {
        switch self {
        case .number(let value): return value
        // Models routinely quote numbers; accepting `"40"` costs nothing and saves a tool error.
        case .string(let value): return Double(value)
        default: return nil
        }
    }

    var intValue: Int? {
        guard let value = doubleValue, value.isFinite else { return nil }
        guard value >= Double(Int.min), value <= Double(Int.max) else { return nil }
        return Int(value)
    }

    var int64Value: Int64? {
        guard let value = doubleValue, value.isFinite else { return nil }
        guard value >= Double(Int64.min), value <= Double(Int64.max) else { return nil }
        return Int64(value)
    }

    var boolValue: Bool? {
        switch self {
        case .bool(let value): return value
        case .string(let value):
            switch value.lowercased() {
            case "true", "yes", "1": return true
            case "false", "no", "0": return false
            default: return nil
            }
        default: return nil
        }
    }

    var arrayValue: [JSONValue]? {
        if case .array(let value) = self { return value }
        return nil
    }

    var objectValue: [String: JSONValue]? {
        if case .object(let value) = self { return value }
        return nil
    }

    /// Member lookup that skips explicit nulls, so `args["since"]` is nil for both a missing key and
    /// a `"since": null` the model sent to mean "unset".
    subscript(key: String) -> JSONValue? {
        guard case .object(let members) = self, let value = members[key], !value.isNull else { return nil }
        return value
    }

    subscript(index: Int) -> JSONValue? {
        guard case .array(let items) = self, index >= 0, index < items.count else { return nil }
        return items[index]
    }
}

// MARK: - Writing values in

/// Literal conformances exist so tool schemas read like the JSON they are:
/// `["type": "object", "properties": ["limit": ["type": "integer", "default": 40]]]`.
extension JSONValue: ExpressibleByNilLiteral {
    public init(nilLiteral: ()) { self = .null }
}

extension JSONValue: ExpressibleByBooleanLiteral {
    public init(booleanLiteral value: Bool) { self = .bool(value) }
}

extension JSONValue: ExpressibleByIntegerLiteral {
    public init(integerLiteral value: Int) { self = .number(Double(value)) }
}

extension JSONValue: ExpressibleByFloatLiteral {
    public init(floatLiteral value: Double) { self = .number(value) }
}

extension JSONValue: ExpressibleByStringLiteral {
    public init(stringLiteral value: String) { self = .string(value) }
}

extension JSONValue: ExpressibleByArrayLiteral {
    public init(arrayLiteral elements: JSONValue...) { self = .array(elements) }
}

extension JSONValue: ExpressibleByDictionaryLiteral {
    public init(dictionaryLiteral elements: (String, JSONValue)...) {
        var members: [String: JSONValue] = [:]
        for (key, value) in elements { members[key] = value }
        self = .object(members)
    }
}

// MARK: - JSON-RPC

/// One decoded request frame. `id` is nil for notifications, which must never be answered.
public struct RPCRequest: Sendable {
    public let id: JSONValue?
    public let method: String
    public let params: JSONValue?

    public init(id: JSONValue?, method: String, params: JSONValue?) {
        self.id = id
        self.method = method
        self.params = params
    }

    public var isNotification: Bool { id == nil }
}

/// Line-delimited JSON-RPC 2.0 framing. Every response this produces is exactly one line: the
/// encoder never pretty-prints, and JSON string escaping guarantees no embedded newline.
public enum RPC {
    public enum Code {
        public static let parseError = -32700
        public static let invalidRequest = -32600
        public static let methodNotFound = -32601
        public static let invalidParams = -32602
        public static let internalError = -32603
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        // No `.prettyPrinted`: one frame per line is the entire framing protocol.
        // `.sortedKeys` only makes output deterministic for tests.
        encoder.outputFormatting = [.withoutEscapingSlashes, .sortedKeys]
        return encoder
    }()

    /// Parses a line into a JSON document, or nil when it is not JSON at all.
    public static func json(line: String) -> JSONValue? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let data = trimmed.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(JSONValue.self, from: data)
    }

    /// Reads a request out of an already-parsed frame. Nil when the frame has no `method`.
    public static func request(from value: JSONValue) -> RPCRequest? {
        guard let method = value["method"]?.stringValue else { return nil }
        return RPCRequest(id: value["id"], method: method, params: value["params"])
    }

    public static func decode(line: String) -> RPCRequest? {
        guard let value = json(line: line) else { return nil }
        return request(from: value)
    }

    /// Encoded success response line (no trailing newline — the transport adds it).
    public static func result(id: JSONValue?, _ value: JSONValue) -> String {
        encode(["jsonrpc": "2.0", "id": id ?? .null, "result": value])
    }

    public static func error(id: JSONValue?, code: Int, message: String) -> String {
        encode([
            "jsonrpc": "2.0",
            "id": id ?? .null,
            "error": ["code": .number(Double(code)), "message": .string(message)],
        ])
    }

    /// Single-line encoding. Falls back to a hand-built internal error rather than throwing, so a
    /// response is always produced and the stream never stalls waiting for one.
    public static func encode(_ value: JSONValue) -> String {
        guard let data = try? encoder.encode(value), let line = String(data: data, encoding: .utf8) else {
            return #"{"error":{"code":-32603,"message":"Response encoding failed"},"id":null,"jsonrpc":"2.0"}"#
        }
        return line
    }
}

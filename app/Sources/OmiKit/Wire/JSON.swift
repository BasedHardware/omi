import Foundation

// Minimal ordered JSON value + parser/serializer. Pure byte scanning so the
// semantics (key order preservation, safe-integer bounds) match the
// TypeScript `JSON.parse`/`JSON.stringify` behavior the wire codecs rely on,
// and so the file transpiles cleanly to Kotlin.

public enum JSONValue: Sendable, Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    /// Ordered object: insertion order is preserved for serialization.
    case object([(String, JSONValue)])

    public static func == (lhs: JSONValue, rhs: JSONValue) -> Bool {
        switch lhs {
        case .null:
            if case .null = rhs { return true }
            return false
        case .bool(let left):
            if case .bool(let right) = rhs { return left == right }
            return false
        case .number(let left):
            if case .number(let right) = rhs { return left == right }
            return false
        case .string(let left):
            if case .string(let right) = rhs { return left == right }
            return false
        case .array(let left):
            if case .array(let right) = rhs { return left == right }
            return false
        case .object(let left):
            guard case .object(let right) = rhs, left.count == right.count else {
                return false
            }
            for (index, member) in left.enumerated() {
                if member.0 != right[index].0 { return false }
                if member.1 != right[index].1 { return false }
            }
            return true
        }
    }

    public var isNull: Bool {
        if case .null = self { return true }
        return false
    }

    public var boolValue: Bool? {
        if case .bool(let value) = self { return value }
        return nil
    }

    public var numberValue: Double? {
        if case .number(let value) = self { return value }
        return nil
    }

    public var stringValue: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    public var arrayValue: [JSONValue]? {
        if case .array(let value) = self { return value }
        return nil
    }

    public var objectValue: [(String, JSONValue)]? {
        if case .object(let value) = self { return value }
        return nil
    }

    /// Object member lookup.
    public subscript(key: String) -> JSONValue? {
        guard case .object(let members) = self else { return nil }
        for (name, value) in members where name == key { return value }
        return nil
    }

    /// `Number.isSafeInteger` over the parsed value.
    public var safeIntegerValue: Int64? {
        guard case .number(let value) = self else { return nil }
        guard value.rounded(.towardZero) == value,
            value >= -9_007_199_254_740_991, value <= 9_007_199_254_740_991
        else { return nil }
        return Int64(value)
    }

    public var isFiniteNumber: Bool {
        guard case .number(let value) = self else { return false }
        return value.isFinite
    }

    /// Strict object shape check (not an array, not null).
    public var isRecord: Bool {
        if case .object = self { return true }
        return false
    }

    public static func integer(_ value: Int64) -> JSONValue { .number(Double(value)) }
}

public enum JSONParseError: Error, Equatable, Sendable {
    case malformed
    case trailing
}

public enum JSON {
    /// Parses `JSON.parse` semantics: one value, no trailing content,
    /// last duplicate key wins.
    public static func parse(_ text: String) throws -> JSONValue {
        var parser = JSONParser(bytes: Array(text.utf8))
        let value = try parser.parseValue()
        parser.skipWhitespace()
        if !parser.atEnd { throw JSONParseError.trailing }
        return value
    }

    /// Parses or returns nil (the pervasive TS `try { JSON.parse }` idiom).
    public static func parseOrNull(_ text: String?) -> JSONValue? {
        guard let text else { return nil }
        return try? parse(text)
    }

    /// Compact `JSON.stringify` encoding with insertion-ordered object keys.
    public static func serialize(_ value: JSONValue) -> String {
        var output = [UInt8]()
        serialize(value, into: &output)
        return String(decoding: output, as: UTF8.self)
    }

    static func serialize(_ value: JSONValue, into output: inout [UInt8]) {
        switch value {
        case .null:
            output.append(contentsOf: Array("null".utf8))
        case .bool(let value):
            output.append(contentsOf: Array((value ? "true" : "false").utf8))
        case .number(let value):
            if value.rounded(.towardZero) == value,
                value >= -9_007_199_254_740_991, value <= 9_007_199_254_740_991
            {
                output.append(contentsOf: Array(String(Int64(value)).utf8))
            } else {
                output.append(contentsOf: Array(String(value).utf8))
            }
        case .string(let value):
            serializeString(value, into: &output)
        case .array(let items):
            output.append(UInt8(ascii: "["))
            for (index, item) in items.enumerated() {
                if index > 0 { output.append(UInt8(ascii: ",")) }
                serialize(item, into: &output)
            }
            output.append(UInt8(ascii: "]"))
        case .object(let members):
            output.append(UInt8(ascii: "{"))
            for (index, member) in members.enumerated() {
                if index > 0 { output.append(UInt8(ascii: ",")) }
                serializeString(member.0, into: &output)
                output.append(UInt8(ascii: ":"))
                serialize(member.1, into: &output)
            }
            output.append(UInt8(ascii: "}"))
        }
    }

    static func serializeString(_ value: String, into output: inout [UInt8]) {
        output.append(UInt8(ascii: "\""))
        for scalar in value.unicodeScalars {
            switch scalar.value {
            case 0x22:
                output.append(contentsOf: Array("\\\"".utf8))
            case 0x5C:
                output.append(contentsOf: Array("\\\\".utf8))
            case 0x0A:
                output.append(contentsOf: Array("\\n".utf8))
            case 0x0D:
                output.append(contentsOf: Array("\\r".utf8))
            case 0x09:
                output.append(contentsOf: Array("\\t".utf8))
            case 0x08:
                output.append(contentsOf: Array("\\b".utf8))
            case 0x0C:
                output.append(contentsOf: Array("\\f".utf8))
            default:
                if scalar.value < 0x20 {
                    let hexBytes = Array("0123456789abcdef".utf8)
                    output.append(contentsOf: Array("\\u00".utf8))
                    output.append(hexBytes[Int((scalar.value >> 4) & 0xF)])
                    output.append(hexBytes[Int(scalar.value & 0xF)])
                } else {
                    output.append(contentsOf: Array(String(scalar).utf8))
                }
            }
        }
        output.append(UInt8(ascii: "\""))
    }
}

struct JSONParser {
    let bytes: [UInt8]
    var position = 0

    init(bytes: [UInt8]) {
        self.bytes = bytes
    }

    var atEnd: Bool { position >= bytes.count }

    mutating func skipWhitespace() {
        while position < bytes.count {
            let byte = bytes[position]
            if byte == 0x20 || byte == 0x09 || byte == 0x0A || byte == 0x0D {
                position += 1
            } else {
                break
            }
        }
    }

    mutating func parseValue() throws -> JSONValue {
        skipWhitespace()
        guard !atEnd else { throw JSONParseError.malformed }
        switch bytes[position] {
        case UInt8(ascii: "{"): return try parseObject()
        case UInt8(ascii: "["): return try parseArray()
        case UInt8(ascii: "\""): return .string(try parseString())
        case UInt8(ascii: "t"):
            try expectLiteral("true")
            return .bool(true)
        case UInt8(ascii: "f"):
            try expectLiteral("false")
            return .bool(false)
        case UInt8(ascii: "n"):
            try expectLiteral("null")
            return .null
        default: return try parseNumber()
        }
    }

    mutating func expectLiteral(_ literal: String) throws {
        for byte in literal.utf8 {
            guard position < bytes.count, bytes[position] == byte else {
                throw JSONParseError.malformed
            }
            position += 1
        }
    }

    mutating func parseObject() throws -> JSONValue {
        position += 1  // '{'
        var members = [(String, JSONValue)]()
        skipWhitespace()
        if position < bytes.count, bytes[position] == UInt8(ascii: "}") {
            position += 1
            return .object(members)
        }
        while true {
            skipWhitespace()
            guard position < bytes.count, bytes[position] == UInt8(ascii: "\"") else {
                throw JSONParseError.malformed
            }
            let key = try parseString()
            skipWhitespace()
            guard position < bytes.count, bytes[position] == UInt8(ascii: ":") else {
                throw JSONParseError.malformed
            }
            position += 1
            let value = try parseValue()
            // JSON.parse keeps only the last duplicate key.
            if let existing = members.firstIndex(where: { $0.0 == key }) {
                members[existing] = (key, value)
            } else {
                members.append((key, value))
            }
            skipWhitespace()
            guard position < bytes.count else { throw JSONParseError.malformed }
            if bytes[position] == UInt8(ascii: ",") {
                position += 1
                continue
            }
            if bytes[position] == UInt8(ascii: "}") {
                position += 1
                return .object(members)
            }
            throw JSONParseError.malformed
        }
    }

    mutating func parseArray() throws -> JSONValue {
        position += 1  // '['
        var items = [JSONValue]()
        skipWhitespace()
        if position < bytes.count, bytes[position] == UInt8(ascii: "]") {
            position += 1
            return .array(items)
        }
        while true {
            items.append(try parseValue())
            skipWhitespace()
            guard position < bytes.count else { throw JSONParseError.malformed }
            if bytes[position] == UInt8(ascii: ",") {
                position += 1
                continue
            }
            if bytes[position] == UInt8(ascii: "]") {
                position += 1
                return .array(items)
            }
            throw JSONParseError.malformed
        }
    }

    mutating func parseString() throws -> String {
        position += 1  // '"'
        var output = [UInt8]()
        while true {
            guard position < bytes.count else { throw JSONParseError.malformed }
            let byte = bytes[position]
            if byte == UInt8(ascii: "\"") {
                position += 1
                return String(decoding: output, as: UTF8.self)
            }
            if byte == UInt8(ascii: "\\") {
                position += 1
                guard position < bytes.count else { throw JSONParseError.malformed }
                let escape = bytes[position]
                switch escape {
                case UInt8(ascii: "\""): output.append(UInt8(ascii: "\""))
                case UInt8(ascii: "\\"): output.append(UInt8(ascii: "\\"))
                case UInt8(ascii: "/"): output.append(UInt8(ascii: "/"))
                case UInt8(ascii: "b"): output.append(0x08)
                case UInt8(ascii: "f"): output.append(0x0C)
                case UInt8(ascii: "n"): output.append(0x0A)
                case UInt8(ascii: "r"): output.append(0x0D)
                case UInt8(ascii: "t"): output.append(0x09)
                case UInt8(ascii: "u"):
                    let scalar = try parseUnicodeEscape()
                    appendScalar(scalar, to: &output)
                default: throw JSONParseError.malformed
                }
                position += 1
                continue
            }
            if byte < 0x20 { throw JSONParseError.malformed }
            output.append(byte)
            position += 1
        }
    }

    private mutating func parseUnicodeEscape() throws -> UInt32 {
        func hex4(at offset: Int) throws -> UInt32 {
            guard offset + 4 <= bytes.count else { throw JSONParseError.malformed }
            var value = 0
            for index in offset..<(offset + 4) {
                let byte = bytes[index]
                let digit: Int
                switch byte {
                case UInt8(ascii: "0")...UInt8(ascii: "9"): digit = Int(byte - UInt8(ascii: "0"))
                case UInt8(ascii: "a")...UInt8(ascii: "f"): digit = Int(byte - UInt8(ascii: "a") + 10)
                case UInt8(ascii: "A")...UInt8(ascii: "F"): digit = Int(byte - UInt8(ascii: "A") + 10)
                default: throw JSONParseError.malformed
                }
                value = value * 16 + digit
            }
            return UInt32(value)
        }
        let first = try hex4(at: position + 1)
        position += 4
        // Surrogate pair.
        if first >= 0xD800, first <= 0xDBFF,
            position + 6 < bytes.count,
            bytes[position + 1] == UInt8(ascii: "\\"),
            bytes[position + 2] == UInt8(ascii: "u")
        {
            let second = try hex4(at: position + 3)
            if second >= 0xDC00, second <= 0xDFFF {
                position += 6
                let scalar = 0x10000 + (Int(first) - 0xD800) << 10 + (Int(second) - 0xDC00)
                return UInt32(scalar)
            }
        }
        return first
    }

    private func appendScalar(_ scalar: UInt32, to output: inout [UInt8]) {
        if let unicode = Unicode.Scalar(scalar) {
            output.append(contentsOf: Array(String(Character(unicode)).utf8))
        } else {
            // Lone surrogate: replace, matching lenient decode behavior.
            output.append(0xEF)
            output.append(0xBF)
            output.append(0xBD)
        }
    }

    mutating func parseNumber() throws -> JSONValue {
        let start = position
        if position < bytes.count, bytes[position] == UInt8(ascii: "-") {
            position += 1
        }
        var sawDigit = false
        while position < bytes.count {
            let byte = bytes[position]
            if byte >= UInt8(ascii: "0"), byte <= UInt8(ascii: "9") {
                sawDigit = true
                position += 1
            } else if byte == UInt8(ascii: ".") || byte == UInt8(ascii: "e")
                || byte == UInt8(ascii: "E") || byte == UInt8(ascii: "+")
                || byte == UInt8(ascii: "-")
            {
                position += 1
            } else {
                break
            }
        }
        guard sawDigit, position > start,
            let value = Double(String(decoding: bytes[start..<position], as: UTF8.self)),
            value.isFinite
        else { throw JSONParseError.malformed }
        return .number(value)
    }
}

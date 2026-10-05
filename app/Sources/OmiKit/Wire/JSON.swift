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
        return utf8String(output)
    }

    static func serialize(_ value: JSONValue, into output: inout [UInt8]) {
        switch value {
        case .null:
            output.append(contentsOf: Array("null".utf8))
        case .bool(let value):
            output.append(contentsOf: Array((value ? "true" : "false").utf8))
        case .number(let value):
            output.append(contentsOf: Array((Policy.jsonFormatNumber(value) ?? "null").utf8))
        case .string(let value):
            serializeString(value, into: &output)
        case .array(let items):
            output.append(ASCII.openBracket)
            for (index, item) in items.enumerated() {
                if index > 0 { output.append(ASCII.comma) }
                serialize(item, into: &output)
            }
            output.append(ASCII.closeBracket)
        case .object(let members):
            output.append(ASCII.openBrace)
            for (index, member) in members.enumerated() {
                if index > 0 { output.append(ASCII.comma) }
                serializeString(member.0, into: &output)
                output.append(ASCII.colon)
                serialize(member.1, into: &output)
            }
            output.append(ASCII.closeBrace)
        }
    }

    static func serializeString(_ value: String, into output: inout [UInt8]) {
        let hexBytes = Array("0123456789abcdef".utf8)
        output.append(ASCII.quote)
        for byte in Array(value.utf8) {
            switch byte {
            case ASCII.quote:
                output.append(contentsOf: Array("\\\"".utf8))
            case ASCII.backslash:
                output.append(contentsOf: Array("\\\\".utf8))
            case ASCII.lineFeed:
                output.append(contentsOf: Array("\\n".utf8))
            case ASCII.carriageReturn:
                output.append(contentsOf: Array("\\r".utf8))
            case ASCII.tab:
                output.append(contentsOf: Array("\\t".utf8))
            case UInt8(0x08):
                output.append(contentsOf: Array("\\b".utf8))
            case UInt8(0x0C):
                output.append(contentsOf: Array("\\f".utf8))
            default:
                if byte < ASCII.space {
                    output.append(contentsOf: Array("\\u00".utf8))
                    output.append(hexBytes[Int(byte) >> 4])
                    output.append(hexBytes[Int(byte) & 0xF])
                } else {
                    output.append(byte)
                }
            }
        }
        output.append(ASCII.quote)
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
            if byte == ASCII.space || byte == ASCII.tab || byte == ASCII.lineFeed
                || byte == ASCII.carriageReturn
            {
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
        case ASCII.openBrace: return try parseObject()
        case ASCII.openBracket: return try parseArray()
        case ASCII.quote: return .string(try parseString())
        case ASCII.lowerT:
            try expectLiteral("true")
            return .bool(true)
        case ASCII.lowerF:
            try expectLiteral("false")
            return .bool(false)
        case ASCII.lowerN:
            try expectLiteral("null")
            return .null
        default: return try parseNumber()
        }
    }

    mutating func expectLiteral(_ literal: String) throws {
        for byte in Array(literal.utf8) {
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
        if position < bytes.count, bytes[position] == ASCII.closeBrace {
            position += 1
            return .object(members)
        }
        while true {
            skipWhitespace()
            guard position < bytes.count, bytes[position] == ASCII.quote else {
                throw JSONParseError.malformed
            }
            let key = try parseString()
            skipWhitespace()
            guard position < bytes.count, bytes[position] == ASCII.colon else {
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
            if bytes[position] == ASCII.comma {
                position += 1
                continue
            }
            if bytes[position] == ASCII.closeBrace {
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
        if position < bytes.count, bytes[position] == ASCII.closeBracket {
            position += 1
            return .array(items)
        }
        while true {
            items.append(try parseValue())
            skipWhitespace()
            guard position < bytes.count else { throw JSONParseError.malformed }
            if bytes[position] == ASCII.comma {
                position += 1
                continue
            }
            if bytes[position] == ASCII.closeBracket {
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
            if byte == ASCII.quote {
                position += 1
                return utf8String(output)
            }
            if byte == ASCII.backslash {
                position += 1
                guard position < bytes.count else { throw JSONParseError.malformed }
                let escape = bytes[position]
                switch escape {
                case ASCII.quote: output.append(ASCII.quote)
                case ASCII.backslash: output.append(ASCII.backslash)
                case ASCII.slash: output.append(ASCII.slash)
                case ASCII.lowerB: output.append(UInt8(0x08))
                case ASCII.lowerF: output.append(UInt8(0x0C))
                case ASCII.lowerN: output.append(ASCII.lineFeed)
                case ASCII.lowerR: output.append(ASCII.carriageReturn)
                case ASCII.lowerT: output.append(ASCII.tab)
                case ASCII.lowerU:
                    let scalar = try parseUnicodeEscape()
                    appendScalar(scalar, to: &output)
                default: throw JSONParseError.malformed
                }
                position += 1
                continue
            }
            if byte < ASCII.space { throw JSONParseError.malformed }
            output.append(byte)
            position += 1
        }
    }

    private mutating func parseUnicodeEscape() throws -> Int {
        func hex4(at offset: Int) throws -> Int {
            guard offset + 4 <= bytes.count else { throw JSONParseError.malformed }
            var value = 0
            for index in offset..<(offset + 4) {
                let byte = bytes[index]
                let digit: Int
                if ASCII.isDigit(byte) {
                    digit = Int(byte) - Int(ASCII.zero)
                } else if byte >= ASCII.lowerA, byte <= ASCII.lowerF {
                    digit = Int(byte) - Int(ASCII.lowerA) + 10
                } else if byte >= ASCII.upperA, byte <= ASCII.upperF {
                    digit = Int(byte) - Int(ASCII.upperA) + 10
                } else {
                    throw JSONParseError.malformed
                }
                value = value * 16 + digit
            }
            return value
        }
        let first = try hex4(at: position + 1)
        position += 4
        // Surrogate pair.
        if first >= 0xD800, first <= 0xDBFF,
            position + 6 < bytes.count,
            bytes[position + 1] == ASCII.backslash,
            bytes[position + 2] == ASCII.lowerU
        {
            let second = try hex4(at: position + 3)
            if second >= 0xDC00, second <= 0xDFFF {
                position += 6
                return 0x10000 + ((first - 0xD800) << 10) + (second - 0xDC00)
            }
        }
        return first
    }

    private func appendScalar(_ scalar: Int, to output: inout [UInt8]) {
        if scalar >= 0xD800, scalar <= 0xDFFF {
            // Lone surrogate: replace, matching lenient decode behavior.
            output.append(UInt8(0xEF))
            output.append(UInt8(0xBF))
            output.append(UInt8(0xBD))
        } else if scalar < 0x80 {
            output.append(UInt8(scalar))
        } else if scalar < 0x800 {
            output.append(UInt8(0xC0 | (scalar >> 6)))
            output.append(UInt8(0x80 | (scalar & 0x3F)))
        } else if scalar < 0x10000 {
            output.append(UInt8(0xE0 | (scalar >> 12)))
            output.append(UInt8(0x80 | ((scalar >> 6) & 0x3F)))
            output.append(UInt8(0x80 | (scalar & 0x3F)))
        } else {
            output.append(UInt8(0xF0 | (scalar >> 18)))
            output.append(UInt8(0x80 | ((scalar >> 12) & 0x3F)))
            output.append(UInt8(0x80 | ((scalar >> 6) & 0x3F)))
            output.append(UInt8(0x80 | (scalar & 0x3F)))
        }
    }

    mutating func parseNumber() throws -> JSONValue {
        let start = position
        while position < bytes.count {
            let byte = bytes[position]
            if ASCII.isDigit(byte) || byte == ASCII.period || byte == ASCII.lowerE
                || byte == ASCII.upperE || byte == ASCII.plus || byte == ASCII.minus
            {
                position += 1
            } else {
                break
            }
        }
        let text = utf8String(Array(bytes[start..<position]))
        guard Policy.jsonNumberValid(text), let value = Double(text), value.isFinite
        else { throw JSONParseError.malformed }
        return .number(value)
    }
}

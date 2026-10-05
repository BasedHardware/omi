import Foundation

// Byte-level helpers shared by the wire codecs and stream parsers.
// Everything here is pure string/byte scanning so it transpiles cleanly to
// Kotlin (no URLError/Character APIs).

/// Incremental, fatal UTF-8 decoder — the port of
/// `new TextDecoder("utf-8", {fatal: true})` with `{stream: true}` pushes.
/// Incomplete trailing sequences are retained across pushes; invalid bytes
/// throw instead of emitting replacement characters.
public struct IncrementalUTF8Decoder: Sendable {
    private var pending: [UInt8] = []

    public init() {}

    /// Decodes one chunk, holding back any incomplete trailing sequence.
    public mutating func push(_ bytes: [UInt8]) throws -> String {
        var input = pending
        pending = []
        input.append(contentsOf: bytes)
        // Overlong encodings, surrogates, and out-of-range scalars.
        guard let consumed = Policy.utf8CompletePrefix(input) else {
            throw StreamDecodeError.invalidUTF8
        }
        if consumed < input.count {
            // Incomplete trailing sequence: hold it for the next push.
            // The held-back suffix begins at `consumed`.
            pending = Array(input[consumed..<input.count])
        }
        return utf8String(Array(input[0..<consumed]))
    }

    /// Flushes any held-back bytes; a truncated sequence at end of stream is
    /// invalid, mirroring the fatal decoder's end-of-stream behavior.
    public mutating func finish() throws -> String {
        guard !pending.isEmpty else { return "" }
        throw StreamDecodeError.truncatedUTF8
    }

    public enum StreamDecodeError: Error, Equatable, Sendable {
        case invalidUTF8
        case truncatedUTF8
    }
}

enum ASCII {
    static let tab = UInt8(0x09)
    static let lineFeed = UInt8(0x0A)
    static let carriageReturn = UInt8(0x0D)
    static let space = UInt8(0x20)
    static let exclamation = UInt8(0x21)
    static let quote = UInt8(0x22)
    static let percent = UInt8(0x25)
    static let apostrophe = UInt8(0x27)
    static let openParen = UInt8(0x28)
    static let closeParen = UInt8(0x29)
    static let asterisk = UInt8(0x2A)
    static let plus = UInt8(0x2B)
    static let comma = UInt8(0x2C)
    static let minus = UInt8(0x2D)
    static let period = UInt8(0x2E)
    static let slash = UInt8(0x2F)
    static let zero = UInt8(0x30)
    static let four = UInt8(0x34)
    static let eight = UInt8(0x38)
    static let nine = UInt8(0x39)
    static let colon = UInt8(0x3A)
    static let upperA = UInt8(0x41)
    static let upperE = UInt8(0x45)
    static let upperF = UInt8(0x46)
    static let upperT = UInt8(0x54)
    static let upperZ = UInt8(0x5A)
    static let openBracket = UInt8(0x5B)
    static let backslash = UInt8(0x5C)
    static let closeBracket = UInt8(0x5D)
    static let underscore = UInt8(0x5F)
    static let lowerA = UInt8(0x61)
    static let lowerB = UInt8(0x62)
    static let lowerE = UInt8(0x65)
    static let lowerF = UInt8(0x66)
    static let lowerN = UInt8(0x6E)
    static let lowerR = UInt8(0x72)
    static let lowerT = UInt8(0x74)
    static let lowerU = UInt8(0x75)
    static let lowerZ = UInt8(0x7A)
    static let openBrace = UInt8(0x7B)
    static let closeBrace = UInt8(0x7D)
    static let tilde = UInt8(0x7E)

    static func isDigit(_ byte: UInt8) -> Bool {
        byte >= zero && byte <= nine
    }

    static func isLowerHex(_ byte: UInt8) -> Bool {
        isDigit(byte) || (byte >= lowerA && byte <= lowerF)
    }

    static func isAlphanumeric(_ byte: UInt8) -> Bool {
        isDigit(byte) || (byte >= upperA && byte <= upperZ) || (byte >= lowerA && byte <= lowerZ)
    }
}

func utf8String(_ validBytes: [UInt8]) -> String {
    String(data: Data(validBytes), encoding: String.Encoding.utf8) ?? ""
}

public func decodeUTF8(_ bytes: [UInt8]) -> String? {
    guard Policy.utf8CompletePrefix(bytes) == bytes.count else { return nil }
    return utf8String(bytes)
}

public func decodeUTF8Lossy(_ bytes: [UInt8]) -> String {
    utf8String(Policy.utf8Lossy(bytes))
}

/// Percent-encodes a value for a query component (`encodeURIComponent`).
public func encodeQueryComponent(_ value: String) -> String {
    let hexBytes = Array("0123456789ABCDEF".utf8)
    var output = [UInt8]()
    for byte in Array(value.utf8) {
        if ASCII.isAlphanumeric(byte) || byte == ASCII.minus || byte == ASCII.underscore
            || byte == ASCII.period || byte == ASCII.exclamation || byte == ASCII.tilde
            || byte == ASCII.asterisk || byte == ASCII.apostrophe || byte == ASCII.openParen
            || byte == ASCII.closeParen
        {
            output.append(byte)
        } else {
            output.append(ASCII.percent)
            output.append(hexBytes[Int(byte) >> 4])
            output.append(hexBytes[Int(byte) & 0x0F])
        }
    }
    return utf8String(output)
}

public enum Base64Codec {
    /// Port of `react-native/src/base64.ts` `encodeBase64`.
    public static func encode(_ bytes: [UInt8]) -> String {
        Data(bytes).base64EncodedString()
    }

    /// Port of `decodeBase64`; returns nil on invalid input.
    public static func decode(_ value: String) -> [UInt8]? {
        guard let data = Data(base64Encoded: value) else { return nil }
        return [UInt8](data)
    }

    /// Base64url (no padding), used by the PKCE/desktop-handoff challenges.
    public static func encodeURL(_ bytes: [UInt8]) -> String {
        encode(bytes)
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

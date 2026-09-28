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
        var consumed = 0
        var scalars = [UInt32]()
        scalars.reserveCapacity(input.count)
        var index = 0
        while index < input.count {
            let byte = input[index]
            let length: Int
            let value: UInt32
            if byte < 0x80 {
                length = 1
                value = UInt32(byte)
            } else if byte & 0xE0 == 0xC0 {
                length = 2
                value = UInt32(byte & 0x1F)
            } else if byte & 0xF0 == 0xE0 {
                length = 3
                value = UInt32(byte & 0x0F)
            } else if byte & 0xF8 == 0xF0 {
                length = 4
                value = UInt32(byte & 0x07)
            } else {
                throw StreamDecodeError.invalidUTF8
            }
            if index + length > input.count {
                // Incomplete trailing sequence: hold it for the next push.
                pending = Array(input[index...])
                break
            }
            var scalar = value
            var continuation = 1
            while continuation < length {
                let next = input[index + continuation]
                guard next & 0xC0 == 0x80 else { throw StreamDecodeError.invalidUTF8 }
                scalar = (scalar << 6) | UInt32(next & 0x3F)
                continuation += 1
            }
            // Overlong encodings, surrogates, and out-of-range scalars.
            let minimum: UInt32
            switch length {
            case 1: minimum = 0x00
            case 2: minimum = 0x80
            case 3: minimum = 0x800
            default: minimum = 0x10000
            }
            guard scalar >= minimum, scalar <= 0x10FFFD,
                !(scalar >= 0xD800 && scalar <= 0xDFFF)
            else { throw StreamDecodeError.invalidUTF8 }
            scalars.append(scalar)
            index += length
            consumed = index
        }
        if consumed < input.count, pending.isEmpty {
            // Only reachable when the loop broke with a held-back sequence.
        }
        if !pending.isEmpty {
            // The held-back suffix begins at `consumed`.
            pending = Array(input[consumed...])
        }
        var characters = [Character]()
        characters.reserveCapacity(scalars.count)
        for scalar in scalars {
            characters.append(Character(Unicode.Scalar(scalar)!))
        }
        return String(characters)
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

/// Percent-encodes a value for a query component (`encodeURIComponent`).
public func encodeQueryComponent(_ value: String) -> String {
    let unreserved: Set<UInt8> = {
        var set = Set<UInt8>()
        for byte in UInt8(ascii: "A")...UInt8(ascii: "Z") { set.insert(byte) }
        for byte in UInt8(ascii: "a")...UInt8(ascii: "z") { set.insert(byte) }
        for byte in UInt8(ascii: "0")...UInt8(ascii: "9") { set.insert(byte) }
        set.insert(UInt8(ascii: "-"))
        set.insert(UInt8(ascii: "_"))
        set.insert(UInt8(ascii: "."))
        set.insert(UInt8(ascii: "!"))
        set.insert(UInt8(ascii: "~"))
        set.insert(UInt8(ascii: "*"))
        set.insert(UInt8(ascii: "'"))
        set.insert(UInt8(ascii: "("))
        set.insert(UInt8(ascii: ")"))
        return set
    }()
    var output = [UInt8]()
    for byte in Array(value.utf8) {
        if unreserved.contains(byte) {
            output.append(byte)
        } else {
            let hexBytes = Array("0123456789ABCDEF".utf8)
            output.append(UInt8(ascii: "%"))
            output.append(hexBytes[Int(byte >> 4)])
            output.append(hexBytes[Int(byte & 0x0F)])
        }
    }
    return String(decoding: output, as: UTF8.self)
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

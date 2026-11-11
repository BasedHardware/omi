import ContextMCPKit
import Foundation
import XCTest

/// What the connector looks like inside Claude.
///
/// The user's report was one sentence — "within Claude the Context for Claude MCP should have our
/// app's logo" — and the whole of the fix is a field on the `initialize` result, so the whole of the
/// guard is that the field is really on the wire, really decodes to the mark, and really costs
/// nobody a network request. Everything asserted here is read back off the encoded response rather
/// than off `ServerIcon`, because a constant that is right and never sent is the bug this prevents.
final class MCPServerIconTests: XCTestCase {

    func testInitializeCarriesTheAppMarkAsAServerIcon() throws {
        let icon = try firstIcon()

        XCTAssertEqual(icon["mimeType"]?.stringValue, "image/png")
        // `sizes` is what lets a client pick between entries, so it has to describe the bytes we
        // actually sent rather than the size we meant to export.
        let sizes = try XCTUnwrap(icon["sizes"]?.arrayValue?.compactMap { $0.stringValue })
        XCTAssertEqual(sizes, ["128x128"])

        let png = try decodedImage(from: icon)
        XCTAssertEqual(try pngDimensions(png).map { "\($0)x\($1)" }, "128x128",
                       "the PNG's own header disagrees with the sizes we advertised")
    }

    /// **The airgap half.** `src` may be `https:` under the spec, and an `https:` icon would have the
    /// *client* fetch an image from a host of our choosing on every connection — egress from a
    /// process `MCPNetworkEgress` cannot see, let alone suppress, on behalf of a user who turned
    /// Airgap Mode on. A `data:` URI is the only form of this field that keeps that switch honest.
    func testTheIconIsSelfContainedSoItCannotReachTheNetwork() throws {
        let source = try XCTUnwrap(try firstIcon()["src"]?.stringValue)

        XCTAssertTrue(source.hasPrefix("data:image/png;base64,"), "unexpected src form: \(source.prefix(40))")
        for scheme in ["http:", "https:", "file:", "ftp:"] {
            XCTAssertFalse(source.hasPrefix(scheme), "an icon fetched over \(scheme) is egress we cannot gate")
        }
    }

    /// `initialize` is one frame on a line-delimited stream and the client is holding the connection
    /// open waiting for it. The mark is a flat two-colour silhouette; if this ever fails it is
    /// because someone pasted in a 512 px or photographic export, and the fix is to re-render at 128
    /// rather than to raise the number.
    func testTheIconIsSmallEnoughToRideOnAHandshake() throws {
        let png = try decodedImage(from: try firstIcon())

        XCTAssertLessThan(png.count, 8 * 1_024, "\(png.count) bytes of icon on every connection")
    }

    // MARK: - Helpers

    private func firstIcon(file: StaticString = #filePath, line: UInt = #line) throws -> JSONValue {
        let server = MCPServer(store: nil)
        let response = try XCTUnwrap(
            server.handle(line: #"{"jsonrpc":"2.0","id":1,"method":"initialize"}"#), file: file, line: line)
        let frame = try XCTUnwrap(RPC.json(line: response), file: file, line: line)
        let icons = try XCTUnwrap(
            frame["result"]?["serverInfo"]?["icons"]?.arrayValue,
            "serverInfo carries no icons, so Claude has nothing to draw", file: file, line: line)
        XCTAssertEqual(icons.count, 1, "one mark, not a set to choose from", file: file, line: line)
        return try XCTUnwrap(icons.first, file: file, line: line)
    }

    private func decodedImage(from icon: JSONValue) throws -> Data {
        let source = try XCTUnwrap(icon["src"]?.stringValue)
        let base64 = String(source.drop(while: { $0 != "," }).dropFirst())
        return try XCTUnwrap(Data(base64Encoded: base64), "src carries no decodable base64 payload")
    }

    /// Reads the width and height out of a PNG's IHDR, which is fixed at bytes 16..<24 immediately
    /// after the 8-byte signature and the chunk header. Nil when the bytes are not a PNG at all —
    /// which is the interesting failure, because a truncated literal still base64-decodes.
    private func pngDimensions(_ data: Data) throws -> (Int, Int)? {
        let signature: [UInt8] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
        let bytes = [UInt8](data)
        guard bytes.count >= 24, Array(bytes[0..<8]) == signature, Array(bytes[12..<16]) == Array("IHDR".utf8)
        else { return nil }
        func bigEndian(_ range: Range<Int>) -> Int {
            bytes[range].reduce(0) { ($0 << 8) | Int($1) }
        }
        return (bigEndian(16..<20), bigEndian(20..<24))
    }
}

import Foundation

/// The Context for Claude mark, in the one shape a Claude client can read it: `Implementation.icons`
/// on the `initialize` result.
///
/// **Why a `data:` URI and not a URL.** MCP allows `https:` and `data:` for an icon's `src` and
/// requires clients to reject everything else — `file:` included, which rules out pointing at the
/// `.icns` inside the app bundle. An `https:` URL would mean the client fetching an image from a
/// host of our choosing on every connection, which is a request this product does not get to make:
/// ``MCPNetworkEgress`` exists because a promise about the network kept in the app and broken in the
/// binary it spawns is not a promise, and an icon URL would break it in the *client's* process,
/// where Airgap Mode cannot reach at all. Bytes compiled into this binary cost no request from
/// anyone, so the switch stays honest and this file needs no gate.
///
/// **Why a literal and not a resource.** `ContextMCPKit` declares no resource bundle, and a stdio
/// server that Claude spawns from `Contents/MacOS/` is the wrong place to start guessing at bundle
/// lookup: a missing icon would be silent, and the failure would show up inside Claude, far from
/// anything that could explain it. A compiled-in constant travels with the executable by
/// construction.
///
/// **Where the pixels come from.** The 128 pt representation of `Resources/ContextForClaude.icns` —
/// the shipping app icon, which `scripts/make-icon.sh` renders from the vector geometry in
/// `ContextMark.swift`. It is not a redrawing, so the connector's mark and the menu bar's cannot
/// drift apart by eye. To regenerate after the icon changes:
///
///     iconutil -c iconset Resources/ContextForClaude.icns -o /tmp/cfc.iconset
///     magick /tmp/cfc.iconset/icon_128x128.png -strip -define png:compression-level=9 /tmp/icon.png
///     base64 -i /tmp/icon.png | tr -d '\n'
///
/// `-strip` drops the colour profile and timestamp chunks iconutil writes; it is pixel-identical to
/// the iconset member and a little under half the size. 128 px keeps the payload at ~2.5 KB, which
/// is sent once per connection during `initialize` and never again — a `512` member would be ten
/// times that for a mark most clients draw at 16-24 pt.
enum ServerIcon {

    /// The edge length of ``base64``'s image, in pixels. Reported to the client as `sizes` so it can
    /// pick sensibly when a server offers several, and asserted against the PNG's own header in
    /// `MCPServerIconTests` so a stale number cannot outlive a re-render.
    static let pixelSize = 128

    /// Stated explicitly even though a `data:` URI already carries it. The spec calls `mimeType` an
    /// override "if the source MIME type is missing or generic", and PNG and JPEG are the two types
    /// a client that renders icons at all is required to support — so saying it costs 18 bytes and
    /// removes a reason to skip us.
    static let mimeType = "image/png"

    static var dataURI: String { "data:\(mimeType);base64," + base64 }

    /// One entry, not four. Multiple icons exist for clients that want to choose per display
    /// context; ours is a single flat mark on its own tile that reads the same everywhere, and every
    /// extra entry is another 2.5 KB on a handshake. `theme` is deliberately absent — the tile
    /// carries its own background, so it is legible on a light and a dark surface alike, and the
    /// spec reads an absent `theme` as exactly that.
    static var json: JSONValue {
        [
            "src": .string(dataURI),
            "mimeType": .string(mimeType),
            "sizes": .array([.string("\(pixelSize)x\(pixelSize)")]),
        ]
    }

    /// The PNG itself. Base64 rather than a byte array so the wire form needs no encoding step at
    /// connection time, and wrapped only for the line limit — the `\` continuations mean the value is
    /// the concatenation with no newlines in it.
    private static let base64 = """
    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
    """
}

import ContextCore
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers
import XCTest

@testable import ContextMCPKit

/// `look` — the one tool that returns pixels.
///
/// Everything here is about the two ways a picture can mislead where prose cannot: a stale frame
/// read as the live screen, and a screenshot handed over after its text was redacted. The image
/// arriving at all is the easy half.
final class LookToolTests: XCTestCase {

    // MARK: - Fixtures

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("look-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { [root] in try? FileManager.default.removeItem(at: root!) }
    }

    private func makeStore() throws -> ContextStore {
        try ContextStore(url: root.appendingPathComponent("context.db"))
    }

    /// A real HEIC on disk, in the format capture actually writes — the point of the whole
    /// conversion is that Claude cannot read that format, so a JPEG fixture would test nothing.
    @discardableResult
    private func writeFrameImage(named name: String, size: Int = 64) throws -> String {
        let url = root.appendingPathComponent(name)
        let context = try XCTUnwrap(
            CGContext(
                data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(red: 0.2, green: 0.4, blue: 0.9, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: size, height: size))
        let image = try XCTUnwrap(context.makeImage())

        let data = NSMutableData()
        let destination = try XCTUnwrap(
            CGImageDestinationCreateWithData(
                data as CFMutableData, UTType.heic.identifier as CFString, 1, nil),
            "this machine cannot encode HEIC")
        CGImageDestinationAddImage(destination, image, nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        try (data as Data).write(to: url)
        return url.path
    }

    private func look(_ arguments: JSONValue?, _ store: ContextStore?) throws -> ToolOutput {
        try Tools.call(name: "look", arguments: arguments, store: store)
    }

    // MARK: - The picture arrives, in a format a model can read

    /// Capture stores HEIC. No Claude surface accepts `image/heic`, so a frame handed over in its
    /// stored format is not a lower-quality answer — it is a rejected request.
    func testTheStoredHEICComesBackAsAJPEGTheModelCanRead() throws {
        let store = try makeStore()
        let path = try writeFrameImage(named: "frame.heic")
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - 5, appName: "Xcode", windowTitle: "Tools.swift",
                ocrText: "static func runLook", imagePath: path))

        let output = try look(nil, store)

        XCTAssertEqual(output.images.count, 1)
        let image = try XCTUnwrap(output.images.first)
        XCTAssertEqual(image.mimeType, "image/jpeg")
        let decoded = try XCTUnwrap(Data(base64Encoded: image.base64), "the payload is not base64")
        // The JPEG SOI marker. Asserting the bytes rather than the mime type is what catches a
        // conversion that silently passed the HEIC through with a JPEG label on it.
        XCTAssertEqual(Array(decoded.prefix(2)), [0xFF, 0xD8], "not a JPEG")
    }

    /// The prose is the only place a timestamp can live — MCP's image block has no field for one —
    /// so a result whose text does not date the picture is a screenshot with no provenance.
    func testTheTextSaysHowOldTheFrameIsAndWhichWindowItIs() throws {
        let store = try makeStore()
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - 4, appName: "Figma", windowTitle: "Onboarding — v3",
                imagePath: try writeFrameImage(named: "figma.heic")))

        let text = try look(nil, store).text

        XCTAssertTrue(text.contains("Figma"), text)
        XCTAssertTrue(text.contains("Onboarding — v3"), text)
        XCTAssertTrue(text.contains("effectively live"), "a 4-second-old frame is live: \(text)")
    }

    /// The failure this guards is a model reporting "the layout is fixed" from a picture taken
    /// before the fix. An old frame usually means an idle screen, but it can mean capture stopped,
    /// and the reader is told to check rather than to assume either.
    func testAnOldFrameIsLabelledOldAndWarnsAgainstReadingItAsCurrent() throws {
        let store = try makeStore()
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - (Tools.idleFrameGrace + 300), appName: "Safari",
                imagePath: try writeFrameImage(named: "old.heic")))

        let text = try look(nil, store).text

        XCTAssertTrue(text.contains("minutes ago"), text)
        XCTAssertTrue(text.contains("look again"), "no instruction to re-check a stale frame: \(text)")
    }

    // MARK: - Redaction survives the move to pixels

    /// **The rule that makes serving screenshots safe at all.** `Redaction.scrub` has only ever
    /// touched text; the picture beside a scrubbed OCR string still shows the token in full. The
    /// marker the scrub leaves behind is the evidence, and it costs the picture rather than the
    /// moment.
    func testAFrameWhoseTextWasRedactedComesBackWithNoPicture() throws {
        let store = try makeStore()
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - 3, appName: "Terminal",
                ocrText: "export OPENAI_API_KEY=\(Redaction.marker)",
                imagePath: try writeFrameImage(named: "secret.heic")))

        let output = try look(nil, store)

        XCTAssertTrue(output.images.isEmpty, "a redacted frame's screenshot was served")
        XCTAssertTrue(output.text.contains("credential"), output.text)
        XCTAssertTrue(
            output.text.contains("redaction working"),
            "withholding must not read as a broken capture: \(output.text)")
        // The moment itself is not lost — only the pixels are.
        XCTAssertTrue(output.text.contains("Terminal"), output.text)
    }

    /// The accessibility column and the OCR column see different halves of a window and fail in
    /// opposite directions, so a credential caught in either one has to withhold the picture.
    func testRedactionInTheAccessibilityTextAlsoWithholdsThePicture() throws {
        let store = try makeStore()
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - 3, appName: "Arc", ocrText: "sign in",
                imagePath: try writeFrameImage(named: "ax.heic"),
                axText: "token: \(Redaction.marker)"))

        XCTAssertTrue(try look(nil, store).images.isEmpty)
    }

    // MARK: - Nothing to look at is a fact, not an error

    /// Retention deletes frame files while their rows survive, so a row pointing at nothing is
    /// routine. It must not fail the call, and it must not silently return a pictureless result
    /// that reads as "the screen was blank".
    func testAFrameWhoseFileIsGoneExplainsItselfInsteadOfFailing() throws {
        let store = try makeStore()
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - 10, appName: "Slack", ocrText: "standup at 10",
                imagePath: root.appendingPathComponent("deleted.heic").path))

        let output = try look(nil, store)

        XCTAssertTrue(output.images.isEmpty)
        XCTAssertTrue(output.text.contains("no longer on disk"), output.text)
        XCTAssertTrue(output.text.contains("standup at 10"), "the surviving text was dropped too: \(output.text)")
    }

    func testAnEmptyStoreSaysNothingWasCapturedRatherThanFailing() throws {
        let output = try look(nil, try makeStore())

        XCTAssertTrue(output.images.isEmpty)
        XCTAssertTrue(output.text.contains("No screen capture"), output.text)
        XCTAssertTrue(
            output.text.contains("never") || output.text.contains("not recorded"),
            "an empty answer must not read as an empty life: \(output.text)")
    }

    /// An `app` filter that matched nothing, on a Mac that was recording, is a fact about the
    /// filter. Reporting it as "nothing was captured" sends the reader to `status` to investigate
    /// a recorder that is working fine.
    func testAnAppFilterThatMatchesNothingBlamesTheFilter() throws {
        let store = try makeStore()
        _ = try store.insertFrame(
            Frame(
                capturedAt: ContextTime.now - 5, appName: "Xcode",
                imagePath: try writeFrameImage(named: "xcode.heic")))

        let text = try look(["app": "Photoshop"], store).text

        XCTAssertTrue(text.contains("not the recording"), text)
        XCTAssertTrue(text.contains("Photoshop"), text)
        // The frame that does exist is named and dated rather than described as live capture: on a
        // Mac whose screen grant died days ago, "the screen was being captured then" is false.
        XCTAssertTrue(text.contains("Xcode"), "the frame that did exist was not named: \(text)")
    }

    // MARK: - Arguments

    /// `at` is a lookup backwards. Answering "what was on screen at 2pm" with a 2:40pm frame is not
    /// a stale answer, it is a different question.
    func testAtNeverReturnsAFrameFromAfterTheMomentAsked() throws {
        let store = try makeStore()
        let noon = 1_785_600_000.0
        _ = try store.insertFrame(
            Frame(capturedAt: noon, appName: "Notes", imagePath: try writeFrameImage(named: "then.heic")))
        _ = try store.insertFrame(
            Frame(capturedAt: noon + 3600, appName: "Mail", imagePath: try writeFrameImage(named: "later.heic")))

        let iso = ISO8601DateFormatter()
        let text = try look(["at": .string(iso.string(from: Date(timeIntervalSince1970: noon + 60)))], store).text

        XCTAssertTrue(text.contains("Notes"), text)
        XCTAssertFalse(text.contains("Mail"), "a frame from after the moment asked for: \(text)")
    }

    /// Every image costs a large slice of the reply. Three is the most that has ever answered a
    /// question, and an unbounded `count` is how one call swallows the whole turn.
    func testCountIsBoundedAndOrdersNewestFirst() throws {
        let store = try makeStore()
        for index in 0..<6 {
            _ = try store.insertFrame(
                Frame(
                    capturedAt: ContextTime.now - Double(index + 1), appName: "App\(index)",
                    imagePath: try writeFrameImage(named: "f\(index).heic")))
        }

        let output = try look(["count": 99], store)

        XCTAssertEqual(output.images.count, 3)
        let first = try XCTUnwrap(output.text.range(of: "App0"))
        let second = try XCTUnwrap(output.text.range(of: "App1"))
        XCTAssertTrue(first.lowerBound < second.lowerBound, "not newest-first: \(output.text)")
    }

    func testAnUnreadableAtArgumentIsRejectedRatherThanIgnored() throws {
        XCTAssertThrowsError(try look(["at": "the day before the thing"], try makeStore()))
    }
}

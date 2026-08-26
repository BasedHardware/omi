import ContextCore
import Foundation
import XCTest

@testable import ContextApp

/// The shape of what `ScreenActivityUploader` actually puts on the wire.
///
/// This exists because the backend's screen-activity store has no date type in it at all: it writes
/// `row["timestamp"]` into Firestore verbatim and then answers every range query by **string**
/// comparison against `strftime('%Y-%m-%d %H:%M:%S.000')` boundaries
/// (`backend/database/screen_activity.py`). A timestamp is therefore not "a time in some agreed
/// encoding" — it is a sort key, and the only encoding that sorts correctly beside the rows the Omi
/// desktop app writes is the one GRDB uses to persist a `Date`: `yyyy-MM-dd HH:mm:ss.SSS` in UTC.
///
/// Asserted through `drain()` and the injected transport rather than against the formatter, because
/// what matters is the bytes in the request body. A future refactor that moves the formatting
/// somewhere else still has to face these assertions.
final class ScreenActivityWireFormatTests: XCTestCase {

    /// `2026-08-14 12:08:49.500` UTC, chosen with a fractional half-second so a formatter that drops
    /// milliseconds fails here rather than passing on a round number.
    private static let capturedAt: Double = 1_786_709_329.5
    private static let expectedTimestamp = "2026-08-14 12:08:49.500"

    /// **The regression test.** Uploaded rows carry the backend's storage format, not RFC-3339.
    ///
    /// Against the code as it shipped this fails with `2026-08-14T12:08:49Z`: a `T` where the space
    /// belongs, a `Z` the backend never writes, and no milliseconds.
    @MainActor
    func testAnUploadedRowCarriesTheBackendsStorageTimestampFormat() async throws {
        let sent = try await uploadOneFrame()
        let row = try Self.onlyRow(of: sent)

        XCTAssertEqual(
            row.timestamp, Self.expectedTimestamp,
            "the backend stores this string verbatim and sorts by it — the separator is the contract")
    }

    /// What the format is *for*, stated as the query the backend actually runs.
    ///
    /// A day filter builds `'YYYY-MM-DD 00:00:00.000'` and `'YYYY-MM-DD 23:59:59.999'` and compares
    /// with `>=` / `<=` — lexicographically. `'T'` is 0x54 and `' '` is 0x20, so an RFC-3339 stamp
    /// sorts above *every* string the backend can build for that day: it falls outside the upper
    /// bound of its own date, and above every row the Omi desktop app wrote that day. That is the
    /// live symptom this pins — 71 Omi rows from 04:57Z followed by all 64 of ours through 12:08Z,
    /// with the two devices never interleaving.
    @MainActor
    func testAnUploadedRowFallsInsideTheDayFilterTheBackendBuildsForIt() async throws {
        let sent = try await uploadOneFrame()
        let row = try Self.onlyRow(of: sent)

        // Exactly the two bounds `get_screen_activity` derives from a `datetime` for 2026-08-14.
        let dayStart = "2026-08-14 00:00:00.000"
        let dayEnd = "2026-08-14 23:59:59.999"
        XCTAssertTrue(
            row.timestamp >= dayStart && row.timestamp <= dayEnd,
            "\(row.timestamp) has to fall inside its own day's filter, which is a string comparison")

        // And the ordering against a neighbouring device's row, which is the part a same-day
        // `start_date` alone would not have caught.
        let omiDesktopRowLaterThatDay = "2026-08-14 13:00:00.000"
        XCTAssertLessThan(
            row.timestamp, omiDesktopRowLaterThatDay,
            "sorting beside the Omi desktop app's rows is the whole reason for this format")

        // The shape the bug had, kept as the counter-example so this test says why it exists.
        XCTAssertGreaterThan(
            "2026-08-14T12:08:49Z", dayEnd,
            "an RFC-3339 stamp sorts past the end of its own day — that was the defect")
    }

    // MARK: - Helpers

    /// One frame in, one drain, and the request body it produced.
    @MainActor
    private func uploadOneFrame() async throws -> Data {
        let fixture = try TemporaryUploadStore()
        let frameId = try fixture.seedFrame(capturedAt: Self.capturedAt)
        let store = fixture.store

        let sent = SentBody()
        let uploader = ScreenActivityUploader(
            isAirgapped: { false },
            isSignedIn: { true },
            openStore: { store },
            authHeaders: { _ in ["Authorization": "Bearer test"] },
            transport: { request in
                sent.value = request.httpBody
                return (
                    Data("{\"synced\":1,\"last_id\":\(frameId)}".utf8),
                    HTTPURLResponse(
                        url: request.url ?? URL(string: "https://example.invalid")!,
                        statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!
                )
            },
            defaults: fixture.defaults)

        let outcome = await uploader.drain()
        XCTAssertEqual(outcome, .caughtUp)

        // `XCTUnwrap`, never `XCTSkip`: a drain that sent nothing has to fail this suite rather than
        // quietly excuse itself, or a filter change that stops uploading altogether reads as green.
        return try XCTUnwrap(sent.value, "the drain sent nothing, so there is no wire format to assert")
    }

    /// The one row of the envelope, decoded. Decoding the envelope rather than string-matching the
    /// JSON keeps this a test about the payload and not about key order.
    private static func onlyRow(of body: Data) throws -> WireRow {
        let envelope = try JSONDecoder().decode(WireEnvelope.self, from: body)
        XCTAssertEqual(envelope.rows.count, 1, "one seeded frame is one uploaded row")
        return try XCTUnwrap(envelope.rows.first)
    }

    /// The reader's half of the uploader's private `Encodable` wire types.
    private struct WireEnvelope: Decodable {
        let rows: [WireRow]
    }

    private struct WireRow: Decodable {
        let id: Int64
        let timestamp: String
        let appName: String
        let windowTitle: String
        let ocrText: String
    }

    /// A class so the transport closure and the test body share one value rather than a copy.
    private final class SentBody: @unchecked Sendable {
        var value: Data?
    }

    /// A throwaway database and `UserDefaults` suite, so a test never reads the developer's own
    /// captures and never moves the real sync cursor.
    private final class TemporaryUploadStore {
        let root: URL
        let store: ContextStore
        let defaults: UserDefaults
        private let suiteName: String

        init() throws {
            root = URL(fileURLWithPath: NSTemporaryDirectory())
                .appendingPathComponent("wire-format-store-\(UUID().uuidString)", isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            store = try ContextStore(url: root.appendingPathComponent("context.db"))
            suiteName = "wire-format-tests-\(UUID().uuidString)"
            defaults = UserDefaults(suiteName: suiteName) ?? .standard
        }

        @discardableResult
        func seedFrame(capturedAt: Double) throws -> Int64 {
            try store.insertFrame(
                Frame(
                    capturedAt: capturedAt,
                    appName: "Notes",
                    windowTitle: "Untitled",
                    ocrText: "a line of text that was on the user's screen"))
        }

        deinit {
            defaults.removePersistentDomain(forName: suiteName)
            try? FileManager.default.removeItem(at: root)
        }
    }
}

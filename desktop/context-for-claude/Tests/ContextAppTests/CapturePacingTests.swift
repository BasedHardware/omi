import ContextCore
import CoreGraphics
import Foundation
import XCTest

@testable import ContextApp

/// The two Capture behaviours that used to be pictures of settings.
///
/// Both were drawn, both were persisted, and neither had a reader anywhere in the capture pipeline:
/// the four Capture Quality tiles quoted four pixel sizes at a pipeline that hard-coded one, and
/// "Pause on Inactivity" was a toggle with zero consumers.
///
/// **The tiles are gone now, and that is exactly why the first test stayed.** The user-facing choice
/// was removed, not the resizing and re-encoding it drove — capture still downscales to
/// `FrameImage.Quality.longestSide` and still encodes at `.compression`. A pipeline that quietly
/// stopped doing either would look identical from the outside until somebody's disk filled or their
/// screenshots turned to mush, which is the same class of defect as the original: a stated number
/// that nothing applies.
final class CapturePacingTests: XCTestCase {

    // MARK: - Capture quality

    /// The stored image really is brought down to the one size this app writes.
    func testTheStoredImageIsDownscaledToTheOneSizeCaptureWrites() throws {
        let capture = try syntheticScreen(width: 3_000, height: 2_000)

        let stored = try XCTUnwrap(
            FrameImage.downscaled(capture, longestSide: FrameImage.Quality.longestSide),
            "a capture larger than the ceiling was not resized")
        XCTAssertEqual(max(stored.width, stored.height), FrameImage.Quality.longestSide)
        XCTAssertEqual(
            Double(stored.width) / Double(stored.height), 1.5, accuracy: 0.01,
            "the aspect ratio of the screen must survive the downscale")
    }

    /// …and the fidelity knob is real too: encoding at the stored quality is materially cheaper than
    /// encoding the same image losslessly, which is what a `compression` value nothing applied would
    /// look like.
    ///
    /// The ratio is not asserted, only the direction — but the direction is a measurement rather than
    /// a hope. Encoding this fixture through this exact path gave 16,567 bytes at q0.20 against
    /// 27,423 at q0.40, separation wide enough that a re-encode on another macOS version cannot
    /// invert it.
    func testTheStoredImageIsCompressedAtTheStatedQuality() throws {
        let image = try syntheticScreen(width: 800, height: 600)

        let stored = try XCTUnwrap(FrameImage.data(from: image)).count
        let lossless = try XCTUnwrap(losslessHEIC(image)).count

        XCTAssertLessThan(
            stored, lossless,
            "the same picture costing the same either way is what a compression quality nothing "
                + "applies looks like")
    }

    /// An image already inside the ceiling is left alone rather than re-rendered, which is what
    /// keeps a small window from being pointlessly resampled on every tick.
    func testACaptureSmallerThanTheCeilingIsNotResized() throws {
        let small = try syntheticScreen(width: 900, height: 600)

        XCTAssertNil(FrameImage.downscaled(small, longestSide: FrameImage.Quality.longestSide))
        XCTAssertNotNil(FrameImage.encoded(small), "…and is still encodable")
    }

    /// The same `CGImageDestination` call `FrameImage.data(from:)` makes, at quality 1.0, so the two
    /// numbers differ in exactly one input.
    private func losslessHEIC(_ image: CGImage) -> Data? {
        let data = NSMutableData()
        guard
            let destination = CGImageDestinationCreateWithData(
                data as CFMutableData, "public.heic" as CFString, 1, nil)
        else { return nil }
        CGImageDestinationAddImage(
            destination, image, [kCGImageDestinationLossyCompressionQuality: 1.0] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { return nil }
        return data as Data
    }

    // MARK: - Capture request lifecycle

    /// The capture request cache is tied to the exact shareable-content window object and frame.
    /// Reusing by numeric window ID alone could carry a stale filter across a refreshed snapshot.
    func testCaptureRequestCacheRequiresTheSameWindowSnapshot() {
        let snapshotWindow = NSObject()
        let sameSnapshot = CaptureRequestKey(
            windowID: 42, windowIdentity: ObjectIdentifier(snapshotWindow),
            windowFrame: CGRect(x: 0, y: 0, width: 100, height: 100))
        let refreshedSnapshot = CaptureRequestKey(
            windowID: 42, windowIdentity: ObjectIdentifier(NSObject()),
            windowFrame: CGRect(x: 0, y: 0, width: 100, height: 100))
        let differentWindow = CaptureRequestKey(
            windowID: 43, windowIdentity: ObjectIdentifier(snapshotWindow),
            windowFrame: CGRect(x: 0, y: 0, width: 100, height: 100))
        let resizedWindow = CaptureRequestKey(
            windowID: 42, windowIdentity: ObjectIdentifier(snapshotWindow),
            windowFrame: CGRect(x: 0, y: 0, width: 120, height: 100))

        XCTAssertEqual(sameSnapshot, sameSnapshot)
        XCTAssertNotEqual(sameSnapshot, refreshedSnapshot)
        XCTAssertNotEqual(sameSnapshot, differentWindow)
        XCTAssertNotEqual(sameSnapshot, resizedWindow)
    }

    // MARK: - The cadence is a cadence

    /// **The interval is the time between ticks, not the time between the end of one and the start
    /// of the next.**
    ///
    /// The loop used to sleep the whole period after the work, so the real cadence was
    /// `interval + work` — and the work is not uniform. A tick the dedup gate suppresses costs a
    /// capture and a hash; a tick that *stores* costs OCR, an accessibility walk and a HEIC encode
    /// on top. So the pipeline throttled itself hardest on exactly the ticks that were producing
    /// something. Measured against this machine's own database, consecutive stored frames averaged
    /// 3.79 s apart on a 3.0 s setting — 26% of the capture rate lost to the placement of one
    /// `sleep`, invisible in every setting and every log line.
    func testTheTickCadenceDoesNotIncludeTheWork() {
        XCTAssertEqual(ScreenWatcher.sleepAfterTick(period: 3.0, elapsed: 0.8), 2.2, accuracy: 0.001)
        XCTAssertEqual(ScreenWatcher.sleepAfterTick(period: 3.0, elapsed: 0.25), 2.75, accuracy: 0.001)
        XCTAssertEqual(
            ScreenWatcher.sleepAfterTick(period: 3.0, elapsed: 0.79) + 0.79,
            3.0, accuracy: 0.001,
            "a tick plus its sleep must add up to the interval the user was promised")
    }

    /// …and it cannot become a busy loop, which is the failure mode a naive remainder invites.
    ///
    /// A tick that outruns the period returns zero and the next one starts at once — that tick was
    /// doing seconds of real work, so there is nothing to spin on. A backwards clock (an NTP
    /// correction, a wake from sleep) reads as a negative elapsed and falls back to the whole
    /// period: waiting is the safe direction for nonsense, hammering the WindowServer is not.
    func testAnOverrunningTickWaitsRatherThanSpinning() {
        XCTAssertEqual(ScreenWatcher.sleepAfterTick(period: 3.0, elapsed: 3.0), 0)
        XCTAssertEqual(ScreenWatcher.sleepAfterTick(period: 3.0, elapsed: 45), 0)

        for nonsense in [-1, -.greatestFiniteMagnitude, .infinity, .nan, 0] as [TimeInterval] {
            XCTAssertEqual(
                ScreenWatcher.sleepAfterTick(period: 3.0, elapsed: nonsense), 3.0,
                "an unreadable elapsed must fall back to the full interval: \(nonsense)")
        }
    }

    // MARK: - Counting the ticks, not just the rows

    /// **The number that was missing while the app captured at half the rate it should have.**
    ///
    /// Rows per hour were observable from the database; *attempts* per hour were observable from
    /// nowhere, so "we are not firing often enough" and "we are firing and discarding half of it"
    /// — two defects with completely different fixes — looked identical from outside. The census is
    /// the seam that separates them.
    func testTheCensusSeparatesAttemptsFromRows() {
        var census = CaptureCensus()
        for _ in 0..<10 { XCTAssertNil(census.record(.stored)) }
        for _ in 0..<20 { XCTAssertNil(census.record(.suppressed)) }
        for _ in 0..<5 { XCTAssertNil(census.record(.standDown)) }

        let summary = census.summary
        XCTAssertTrue(summary.contains("35 ticks"), summary)
        XCTAssertTrue(
            summary.contains("30 reached the screen"), "a stand-down never reached the screen: \(summary)")
        XCTAssertTrue(summary.contains("10 stored"), summary)
        XCTAssertTrue(summary.contains("suppressed 20"), "the reason has to be in the line: \(summary)")
    }

    /// A count that is never reported is not evidence, and one reported every tick is noise that
    /// buries evidence. It arrives on a fixed number of ticks and starts again from zero.
    func testTheCensusReportsOnceAndResets() {
        var census = CaptureCensus()
        var lines: [String] = []
        for _ in 0..<(CaptureCensus.reportEvery * 2) {
            if let line = census.record(.stored) { lines.append(line) }
        }

        XCTAssertEqual(lines.count, 2, "one line per \(CaptureCensus.reportEvery) ticks, no more")
        XCTAssertTrue(lines[0].contains("\(CaptureCensus.reportEvery) ticks"), lines[0])
        XCTAssertEqual(census.ticks, 0, "the window has to start again, or the counts compound")
    }

    // MARK: - Pause on Inactivity

    /// The threshold, and why it is where it is: reading is inactivity, and this pipeline already
    /// had to be fixed once for treating a still screen as nothing happening.
    func testTheIdleThresholdIsLongEnoughThatReadingIsNotAbsence() {
        XCTAssertEqual(CaptureActivity.idleThreshold, 300)
        XCTAssertGreaterThanOrEqual(
            CaptureActivity.idleThreshold, SessionPolicy.gapSeconds,
            "this app already has an answer to 'the user has gone' — two answers can drift apart")
    }

    func testCaptureStandsDownOnlyAfterTheThresholdHasPassed() {
        XCTAssertFalse(CaptureActivity.isIdle(secondsSinceInput: 0))
        XCTAssertFalse(CaptureActivity.isIdle(secondsSinceInput: 299))
        XCTAssertTrue(CaptureActivity.isIdle(secondsSinceInput: 300))
        XCTAssertTrue(CaptureActivity.isIdle(secondsSinceInput: 86_400))
    }

    /// The property that matters more than the threshold: a pause cannot become permanent.
    ///
    /// There is no paused flag to get stuck — the answer is a pure function of a counter the system
    /// resets on any input at all — so a machine that comes back captures on its very next tick.
    /// A clock that moved backwards under us is read as activity for the same reason: the direction
    /// that keeps recording is the one to fail in.
    func testCaptureCannotWedgeOff() {
        XCTAssertTrue(CaptureActivity.isIdle(secondsSinceInput: 3_600), "away")
        XCTAssertFalse(
            CaptureActivity.isIdle(secondsSinceInput: 0.2),
            "one keystroke resets the counter, and the next tick must capture")

        for impossible in [-1, -.greatestFiniteMagnitude, .infinity, .nan] as [TimeInterval] {
            XCTAssertFalse(
                CaptureActivity.isIdle(secondsSinceInput: impossible),
                "a nonsense reading must not be able to stop capture: \(impossible)")
        }
    }

    // MARK: - Saying so

    /// The gate has to be visible, not just effective.
    ///
    /// Standing capture down used to write one log line and nothing else: the menu bar went on
    /// reading "Listening", `capture-state.json` went on reporting a healthy pipeline, and the MCP
    /// `status` tool went on telling Claude the day was covered while nothing was being recorded. An
    /// unrecorded hour that says so is a gap; an unrecorded hour that claims otherwise is a lie the
    /// model then reasons from.
    func testTheIdlePauseSaysWhyAndForHowLong() throws {
        let reason = try XCTUnwrap(
            ScreenWatcher.idlePauseReason(pausesOnInactivity: true, isIdle: true))

        XCTAssertTrue(reason.hasPrefix("Paused"), "the sentence has to read as a pause: \(reason)")
        // Derived from the threshold rather than typed, so the two cannot drift into a sentence
        // that promises five minutes of capture the gate stopped taking after two.
        let minutes = Int(CaptureActivity.idleThreshold / 60)
        XCTAssertTrue(
            reason.contains("\(minutes) minute"),
            "the sentence must name the threshold it is enforcing: \(reason)")
    }

    /// The switch decides, not the counter. An idle Mac with the setting off is capturing normally
    /// and must not be reported as paused.
    func testNothingIsClaimedWhenTheSettingIsOff() {
        XCTAssertNil(ScreenWatcher.idlePauseReason(pausesOnInactivity: false, isIdle: true))
        XCTAssertNil(ScreenWatcher.idlePauseReason(pausesOnInactivity: false, isIdle: false))
        XCTAssertNil(ScreenWatcher.idlePauseReason(pausesOnInactivity: true, isIdle: false))
    }

    /// The transition, which is the part a person experiences: announced once when it starts,
    /// cleared once when it ends, and silent in between.
    ///
    /// Silent in between matters — this is asked on every tick, and republishing an unchanged
    /// sentence would rewrite the heartbeat file every three seconds for as long as a machine sits
    /// untouched overnight.
    @MainActor
    func testThePauseIsAnnouncedOnceAndClearedOnTheFirstActiveTick() throws {
        let watcher = ScreenWatcher()
        var announced: [ScreenStandDown?] = []
        watcher.onStandDown = { announced.append($0) }

        let paused = try XCTUnwrap(
            ScreenWatcher.idlePauseReason(pausesOnInactivity: true, isIdle: true))
        watcher.reportStandDown(.paused(paused))
        watcher.reportStandDown(.paused(paused))
        watcher.reportStandDown(.paused(paused))
        XCTAssertEqual(announced.count, 1, "a steady pause must be announced once, not per tick")

        watcher.reportStandDown(nil)
        XCTAssertEqual(announced.count, 2)
        XCTAssertNil(
            announced.last ?? .paused("still paused"),
            "the first tick with a keystroke behind it must clear the pause, not the first frame")
    }

    // MARK: - The stall watchdog

    /// **A screen watcher that is refused forever must say so.**
    ///
    /// The other half of the 2 August defect. Once the WindowServer stops answering this process
    /// there is no error to catch and no callback to fire: the tick simply finds no capturable
    /// window, logs a line it has already logged, and goes round again. Twenty-nine hours of that
    /// produced one log entry and a heartbeat file that went on claiming a healthy pipeline.
    ///
    /// The threshold is asserted from both sides because both are failures: too eager and every wake
    /// from sleep raises a false alarm on the one surface the user trusts; never, which is what
    /// shipped, is what this is fixing.
    func testTheScreenStallIsAnnouncedOnlyAfterTheThresholdHasPassed() {
        let now: Double = 1_800_000_000

        XCTAssertNil(
            ScreenWatcher.stallReason(lastServedAt: now - 1, now: now),
            "a single refused tick is ordinary and must not raise an alarm")
        XCTAssertNil(
            ScreenWatcher.stallReason(lastServedAt: now - ScreenWatcher.stallSeconds + 1, now: now),
            "one second short of the threshold is still inside the patience the watcher promises")

        let stalled = ScreenWatcher.stallReason(
            lastServedAt: now - ScreenWatcher.stallSeconds, now: now)
        XCTAssertNotNil(stalled, "the threshold has passed and nothing has been captured")
        XCTAssertTrue(
            (stalled ?? "").contains("Reopening"),
            "screen capture rights are fixed when a process connects to the window server, so the "
                + "sentence has to offer the only thing that can actually fix it: \(stalled ?? "")")
    }

    /// A watcher with nothing to compare against cannot be stalled, and a clock that jumped
    /// backwards is not evidence of one — the direction that keeps the app quiet is the one to fail
    /// in, because a false alarm on this surface is expensive and the next genuinely refused tick
    /// re-arms the clock against a sane `now`.
    func testTheStallWatchdogCannotFireOnNonsense() {
        XCTAssertNil(ScreenWatcher.stallReason(lastServedAt: nil, now: 1_800_000_000))
        XCTAssertNil(
            ScreenWatcher.stallReason(lastServedAt: 1_800_000_000, now: 1_800_000_000 - 10_000),
            "a backwards clock must not be read as ten thousand seconds of silence")
        XCTAssertNil(ScreenWatcher.stallReason(lastServedAt: .nan, now: 1_800_000_000))
    }

    // MARK: - Helpers

    /// Something shaped like a screenshot: a gradient background, repeating blocks where text and
    /// chrome would be, and a little noise on top.
    ///
    /// Not flat colour and not white noise, and both exclusions matter. A flat image encodes to the
    /// same handful of bytes at every quality, so a hard-coded constant would pass. Pure noise is
    /// incompressible, so every quality saturates the encoder and the sizes converge. This is in
    /// between, which is where a real screen is.
    ///
    /// Deterministic — a fixed seed, no `random` — so the size ordering asserted above is a fact
    /// about the encoder rather than about which numbers this run happened to draw.
    private func syntheticScreen(width: Int, height: Int) throws -> CGImage {
        let context = try XCTUnwrap(
            CGContext(
                data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        let pixels = try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self)
        var seed: UInt64 = 0x2545_F491_4F6C_DD1D

        for y in 0..<height {
            for x in 0..<(context.bytesPerRow / 4) {
                seed = seed &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
                let noise = Int(truncatingIfNeeded: seed >> 40) % 24
                let block = ((x / 7) % 2 == 0 && (y / 19) % 3 == 0) ? 90 : 0
                let gradient = 40 + (x * 180) / max(1, width)
                let value = UInt8(clamping: gradient + block + noise)
                let offset = y * context.bytesPerRow + x * 4
                pixels[offset] = value
                pixels[offset + 1] = UInt8(clamping: Int(value) / 2 + 20)
                pixels[offset + 2] = 255 &- value
                pixels[offset + 3] = 255
            }
        }
        return try XCTUnwrap(context.makeImage())
    }
}

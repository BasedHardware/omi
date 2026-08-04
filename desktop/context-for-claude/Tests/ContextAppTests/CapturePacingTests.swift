import ContextCore
import CoreGraphics
import Foundation
import XCTest

@testable import ContextApp

/// The two Capture settings that used to be pictures of settings.
///
/// Both were drawn, both were persisted, and neither had a reader anywhere in the capture pipeline:
/// the four Capture Quality tiles quoted four pixel sizes at a pipeline that hard-coded one, and
/// "Pause on Inactivity" was a toggle with zero consumers. A control the pipeline does not consult
/// is a decoration, so these assert the pipeline consulting them.
final class CapturePacingTests: XCTestCase {

    // MARK: - Capture Quality

    /// The tile's stated resolution is the resolution stored. This is the whole defect: picking
    /// **Smallest** stored exactly what **Best Quality** stored.
    func testTheSelectedTileDecidesHowLargeTheStoredImageIs() throws {
        let capture = try syntheticScreen(width: 3_000, height: 2_000)

        for quality in CaptureQuality.allCases {
            let stored = try XCTUnwrap(
                FrameImage.downscaled(capture, longestSide: quality.longestSide),
                "\(quality.title) did not resize a capture larger than its own ceiling")
            XCTAssertEqual(
                max(stored.width, stored.height), quality.longestSide,
                "\(quality.title) promises \(quality.longestSide) px on the longest side")
            XCTAssertEqual(
                Double(stored.width) / Double(stored.height), 1.5, accuracy: 0.01,
                "the aspect ratio of the screen must survive the downscale")
        }
    }

    /// …and the fidelity knob is real too, isolated from the size knob by encoding one identical
    /// image at every point on the scale.
    ///
    /// The expected sizes are not asserted, only their order — but the order is a measurement rather
    /// than a hope. Encoding this fixture through this exact path gave 27,423 / 16,567 / 14,218 /
    /// 10,252 bytes for Best / Default / Compact / Smallest, which is separation wide enough that a
    /// re-encode on another macOS version cannot invert it.
    func testTheSelectedTileDecidesHowHardTheStoredImageIsCompressed() throws {
        let image = try syntheticScreen(width: 800, height: 600)
        let ordered: [CaptureQuality] = [.best, .standard, .compact, .smallest]

        let sizes = try ordered.map { try XCTUnwrap(FrameImage.data(from: image, quality: $0)).count }

        for index in 1..<ordered.count {
            XCTAssertGreaterThan(
                sizes[index - 1], sizes[index],
                "\(ordered[index - 1].title) did not store more than \(ordered[index].title) — the "
                    + "same picture coming out the same size at two tiles is what a hard-coded "
                    + "compression quality looks like")
        }
    }

    /// An image already inside the ceiling is left alone rather than re-rendered, which is what
    /// keeps a small window from being pointlessly resampled on every tick.
    func testACaptureSmallerThanTheCeilingIsNotResized() throws {
        let small = try syntheticScreen(width: 900, height: 600)

        XCTAssertNil(FrameImage.downscaled(small, longestSide: CaptureQuality.best.longestSide))
        XCTAssertNotNil(FrameImage.encoded(small, quality: .best), "…and is still encodable")
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

import XCTest

@testable import Omi_Computer

/// Regression coverage for the agent-VM database upload log. The compression
/// ratio was computed inline as `compressedSize * 100 / originalSize` (UInt64);
/// a 0-byte or unreadable `omi.db` yields `originalSize == 0` yet still passes
/// the `fileExists` guard and gzips to a non-empty stub, so execution reached the
/// division and trapped on unsigned integer divide-by-zero, crashing the app on
/// launch for signed-in users. `compressionPercent` now guards the divisor.
final class AgentVMCompressionRatioTests: XCTestCase {

    func testZeroOriginalSizeReturnsZeroInsteadOfTrapping() {
        // Before the fix this line traps (UInt64 division by zero) and crashes.
        XCTAssertEqual(AgentVMService.compressionPercent(compressed: 20, original: 0), 0)
        XCTAssertEqual(AgentVMService.compressionPercent(compressed: 0, original: 0), 0)
    }

    func testTypicalCompressionRatios() {
        XCTAssertEqual(AgentVMService.compressionPercent(compressed: 25, original: 100), 25)
        XCTAssertEqual(AgentVMService.compressionPercent(compressed: 50, original: 200), 25)
        // Whole-number (integer) percent, matching the original log semantics.
        XCTAssertEqual(AgentVMService.compressionPercent(compressed: 1, original: 3), 33)
    }

    func testCompressedLargerThanOriginalIsNotClamped() {
        // gzip on tiny inputs can exceed the original; the log just reports > 100%.
        XCTAssertEqual(AgentVMService.compressionPercent(compressed: 40, original: 20), 200)
    }
}

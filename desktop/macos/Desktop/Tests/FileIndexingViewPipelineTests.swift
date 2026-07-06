import XCTest

final class FileIndexingViewPipelineTests: XCTestCase {
    func testSkipCancelsPipelineBeforeMarkingFileIndexingComplete() throws {
        let source = try fileIndexingViewSource()
        guard let skipRange = source.range(of: "private func skip()") else {
            return XCTFail("FileIndexingView.skip() must exist")
        }
        guard
            let cancelRange = source.range(
                of: "pipelineTask?.cancel()",
                range: skipRange.lowerBound..<source.endIndex),
            let markCompleteRange = source.range(
                of: "UserDefaults.standard.set(true, forKey: \"hasCompletedFileIndexing\")",
                range: skipRange.lowerBound..<source.endIndex)
        else {
            return XCTFail("Skip must cancel the pipeline and preserve the completion flag")
        }

        XCTAssertLessThan(cancelRange.lowerBound, markCompleteRange.lowerBound)
    }

    func testFileScanFailureResetIgnoresCancelledPipeline() throws {
        let source = try fileIndexingViewSource()
        guard let scanRange = source.range(of: "let scanSucceeded = await runFileScanning()") else {
            return XCTFail("FileIndexingView must await the file scan result")
        }
        guard
            let cancellationGuardRange = source.range(
                of: "guard !Task.isCancelled else { return }",
                range: scanRange.lowerBound..<source.endIndex),
            let resetRange = source.range(
                of: "UserDefaults.standard.set(false, forKey: \"hasCompletedFileIndexing\")",
                range: scanRange.lowerBound..<source.endIndex)
        else {
            return XCTFail("Failed scans must not reset completion after pipeline cancellation")
        }

        XCTAssertLessThan(cancellationGuardRange.lowerBound, resetRange.lowerBound)
    }

    private func fileIndexingViewSource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/FileIndexing/FileIndexingView.swift")
        return try String(contentsOf: sourceURL, encoding: .utf8)
    }
}

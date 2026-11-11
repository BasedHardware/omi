import XCTest

@testable import ContextApp

final class ModelPoolTests: XCTestCase {
    func testOnboardingWarmupAndFirstCaptureReuseOneLoadedModel() async throws {
        let loader = RecordingModelLoader()
        let pool = ModelPool<ModelToken> { _, _ in
            await loader.load()
        }

        // This is onboarding's prepareModels path: it completes before the first capture starts.
        let warmed = try await pool.models(version: .v2)

        // This is the first Transcriber.start path. It must use the cached result, not invoke the
        // CoreML loader again.
        let firstCapture = try await pool.models(version: .v2)

        let loadCount = await loader.loadCount
        XCTAssertEqual(loadCount, 1)
        XCTAssertEqual(warmed, firstCapture)
    }
}

private struct ModelToken: Equatable, Sendable {
    let id: UUID
}

private actor RecordingModelLoader {
    private(set) var loadCount = 0

    func load() -> ModelToken {
        loadCount += 1
        return ModelToken(id: UUID())
    }
}

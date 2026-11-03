import Foundation
import XCTest

@testable import Omi_Computer

private actor CaptureGapDecoder {
  private var counts: [Int] = []
  private let filterFirst: Bool

  init(filterFirst: Bool = false) { self.filterFirst = filterFirst }

  func transcribe(_ samples: [Float]) -> LocalTranscriptionService.WindowTranscript {
    counts.append(samples.count)
    return .init(
      text: filterFirst && counts.count == 1 ? "." : "window \(counts.count)", confidence: 1, rtfx: 1)
  }

  func sampleCounts() -> [Int] { counts }
}

@MainActor
final class LocalTranscriptionCaptureGapTests: XCTestCase {
  private func speech() -> Data {
    [Int16](repeating: 1600, count: 16000).withUnsafeBufferPointer { Data(buffer: $0) }
  }

  func testFinishDeliversEveryBufferedGapWindowBeforeReturning() async {
    let decoder = CaptureGapDecoder()
    var received: [TranscriptionService.BackendSegment] = []
    // A prepared decoder exercises the real buffer/finish/delivery path without models or a pump.
    let service = LocalTranscriptionService(
      transcribeWindow: { await decoder.transcribe($0) }, onSegments: { received += $0 })
    service.appendAudio(speech())
    let off = Date(timeIntervalSince1970: 1001)
    service.setCapturePaused(true, at: off)
    service.setCapturePaused(false, at: off.addingTimeInterval(150))
    service.appendAudio(speech())

    await service.finish()

    XCTAssertEqual(received.map(\.text), ["window 1", "window 2"])
    XCTAssertEqual(received.map(\.start), [0, 151])
    XCTAssertEqual(received.map(\.end), [1, 152])
    let counts = await decoder.sampleCounts()
    XCTAssertEqual(counts, [16000, 16000], "no synthetic silence and no dropped post-gap speech")
    service.appendAudio(speech())
    await service.finish()
    XCTAssertEqual(received.count, 2, "a retired service cannot accept or re-emit audio")
  }

  func testFilteredPreGapTranscriptDoesNotStopFinalDraining() async {
    let decoder = CaptureGapDecoder(filterFirst: true)
    var received: [TranscriptionService.BackendSegment] = []
    let service = LocalTranscriptionService(
      transcribeWindow: { await decoder.transcribe($0) }, onSegments: { received += $0 })
    service.appendAudio(speech())
    let off = Date(timeIntervalSince1970: 1001)
    service.setCapturePaused(true, at: off)
    service.setCapturePaused(false, at: off.addingTimeInterval(150))
    service.appendAudio(speech())

    await service.finish()

    XCTAssertEqual(received.map(\.text), ["window 2"])
    XCTAssertEqual(received.map(\.start), [151])
    let counts = await decoder.sampleCounts()
    XCTAssertEqual(counts, [16000, 16000])
  }
}

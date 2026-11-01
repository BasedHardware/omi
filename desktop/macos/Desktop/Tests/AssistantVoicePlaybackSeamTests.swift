import XCTest

@testable import Omi_Computer

@MainActor
final class AssistantVoicePlaybackSeamTests: XCTestCase {

  private func silentWAV(sampleCount: Int = 800) -> Data {
    var data = Data()
    let dataSize = UInt32(sampleCount)
    let byteRate = UInt32(8000)
    data.append(contentsOf: "RIFF".utf8)
    data.append(contentsOf: withUnsafeBytes(of: UInt32(36 + dataSize).littleEndian) { $0 })
    data.append(contentsOf: "WAVE".utf8)
    data.append(contentsOf: "fmt ".utf8)
    data.append(contentsOf: withUnsafeBytes(of: UInt32(16).littleEndian) { $0 })
    data.append(contentsOf: withUnsafeBytes(of: UInt16(1).littleEndian) { $0 })
    data.append(contentsOf: withUnsafeBytes(of: UInt16(1).littleEndian) { $0 })
    data.append(contentsOf: withUnsafeBytes(of: byteRate.littleEndian) { $0 })
    data.append(contentsOf: withUnsafeBytes(of: byteRate.littleEndian) { $0 })
    data.append(contentsOf: withUnsafeBytes(of: UInt16(1).littleEndian) { $0 })
    data.append(contentsOf: withUnsafeBytes(of: UInt16(8).littleEndian) { $0 })
    data.append(contentsOf: "data".utf8)
    data.append(contentsOf: withUnsafeBytes(of: dataSize.littleEndian) { $0 })
    data.append(contentsOf: [UInt8](repeating: 128, count: sampleCount))
    return data
  }

  func testRealtimeAcknowledgementCacheIsScopedToTheExactSessionVoice() throws {
    let phrase = RealtimeSlowToolAcknowledgementKind.deeperThinking.phrases[0]
    let url = FloatingBarVoicePlaybackService.realtimeSlowToolAcknowledgementCacheURL(
      kind: .deeperThinking, text: phrase, voiceID: "Kore", instructions: "")
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    let wav = silentWAV()
    try wav.write(to: url)
    defer { try? FileManager.default.removeItem(at: url) }

    XCTAssertEqual(
      FloatingBarVoicePlaybackService.cachedRealtimeSlowToolAcknowledgementAudio(
        kind: .deeperThinking, text: phrase, voiceID: "Kore", instructions: ""),
      wav)
    XCTAssertNil(
      FloatingBarVoicePlaybackService.cachedRealtimeSlowToolAcknowledgementAudio(
        kind: .deeperThinking, text: phrase, voiceID: "Charon", instructions: ""))
    XCTAssertNil(
      FloatingBarVoicePlaybackService.cachedRealtimeSlowToolAcknowledgementAudio(
        kind: .deeperThinking, text: phrase, voiceID: "ZzNoSuchVoiceSeamTest", instructions: ""))
  }

  func testHeldPreviewCannotPlayAfterRealOutputStarts() async throws {
    let service = FloatingBarVoicePlaybackService.shared
    var realOutputBusy = false
    var started: [Data] = []
    let gate = _SampleGate()
    service.voiceSampleSynthesizer = { _ in
      await gate.markEntered()
      await gate.waitOpen()
      return Data([1, 2, 3, 4])
    }
    service.voiceSampleBusyProbe = { realOutputBusy }
    service.voiceSampleStarter = { started.append($0) }
    defer {
      service.voiceSampleSynthesizer = nil
      service.voiceSampleBusyProbe = nil
      service.voiceSampleStarter = nil
      service.stop()
    }

    let task = Task { try await service.playVoiceSample(voiceID: "Kore") }
    await gate.waitEntered()
    realOutputBusy = true
    await gate.open()

    do {
      try await task.value
      XCTFail("preview must not start once real output owns the speaker")
    } catch {
      XCTAssertTrue(error is VoiceSampleUnavailable)
    }
    XCTAssertTrue(started.isEmpty)
    XCTAssertFalse(service.voiceSampleActive)
  }

  func testClosedPreviewNeverPlaysLate() async throws {
    let service = FloatingBarVoicePlaybackService.shared
    var started: [Data] = []
    let gate = _SampleGate()
    service.voiceSampleSynthesizer = { _ in
      await gate.markEntered()
      await gate.waitOpen()
      return Data([1, 2, 3, 4])
    }
    service.voiceSampleStarter = { started.append($0) }
    defer {
      service.voiceSampleSynthesizer = nil
      service.voiceSampleBusyProbe = nil
      service.voiceSampleStarter = nil
      service.stop()
    }

    let task = Task { try await service.playVoiceSample(voiceID: "Kore") }
    await gate.waitEntered()
    service.stopVoiceSample()
    await gate.open()

    do {
      try await task.value
      XCTFail("a cancelled preview must not start late")
    } catch {
      XCTAssertTrue(error is CancellationError)
    }
    XCTAssertTrue(started.isEmpty)
    XCTAssertFalse(service.voiceSampleActive)
  }
}

private actor _SampleGate {
  private var entered = false
  private var isOpen = false
  private var enteredContinuations: [CheckedContinuation<Void, Never>] = []
  private var openContinuations: [CheckedContinuation<Void, Never>] = []

  func markEntered() {
    entered = true
    for c in enteredContinuations { c.resume() }
    enteredContinuations = []
  }

  func waitEntered() async {
    if entered { return }
    await withCheckedContinuation { enteredContinuations.append($0) }
  }

  func waitOpen() async {
    if isOpen { return }
    await withCheckedContinuation { openContinuations.append($0) }
  }

  func open() {
    isOpen = true
    for c in openContinuations { c.resume() }
    openContinuations = []
  }
}

import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class PushToTalkSpeechGateTests: XCTestCase {
  func testHubSpeechGateRejectsSilence() {
    let audio = pcm16k(seconds: 1.0) { _ in 0 }

    XCTAssertFalse(PushToTalkManager.hubTurnHasSpeech(pcm16k: audio))
  }

  func testHubSpeechGateRejectsBroadbandNoise() {
    var state: UInt64 = 0x1234_abcd
    let audio = pcm16k(seconds: 1.0) { _ in
      state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
      let normalized = Double(Int64(bitPattern: state >> 16) % 20001 - 10000) / 10000.0
      return Int16(max(-12000, min(12000, Int(normalized * 12000))))
    }

    XCTAssertFalse(PushToTalkManager.hubTurnHasSpeech(pcm16k: audio))
  }

  func testHubSpeechGateRejectsTooShortVoicedAudio() {
    let audio = sinePCM16k(seconds: 0.12, frequency: 220, amplitude: 3500)

    XCTAssertFalse(PushToTalkManager.hubTurnHasSpeech(pcm16k: audio))
  }

  // Synthetic tones keep the frame math deterministic; real-speech fixture tests below
  // are the evidence for short/quiet admission behavior.
  func testHubSpeechGateAcceptsClearShortReply() {
    let audio = sinePCM16k(seconds: 0.42, frequency: 220, amplitude: 3500)

    XCTAssertTrue(PushToTalkManager.hubTurnHasSpeech(pcm16k: audio))
  }

  func testHubSpeechGateAcceptsSustainedVoicedAudio() {
    let audio = sinePCM16k(seconds: 0.7, frequency: 220, amplitude: 3500)

    XCTAssertTrue(PushToTalkManager.hubTurnHasSpeech(pcm16k: audio))
  }

  func testSpeechLikeProfileRejectsNoiseEvenWhenRmsIsHigh() {
    let voicedTone = sinePCM16k(seconds: 0.7, frequency: 220, amplitude: 3500)
    let voiced = PushToTalkManager.speechLikeAudioSeconds(pcm16k: voicedTone)

    var state: UInt64 = 0xbeef
    let noise = pcm16k(seconds: 0.7) { _ in
      state = state &* 2_862_933_555_777_941_757 &+ 3_037_000_493
      return Int16(Int(state % 24001) - 12000)
    }
    let noisy = PushToTalkManager.speechLikeAudioSeconds(pcm16k: noise)

    XCTAssertGreaterThanOrEqual(voiced.speechLike, 0.16)
    XCTAssertLessThan(noisy.speechLike, 0.16)
  }

  func testHubSpeechGateAcceptsKnownRealSpeechFixture() throws {
    let pcm = try realSpeechFixturePCM()
    XCTAssertTrue(PushToTalkManager.hubTurnHasSpeech(pcm16k: pcm))
  }

  func testHubSpeechGateAcceptsQuietShortKnownRealSpeechFixture() throws {
    // This is a real LibriSpeech utterance, scaled to a quiet/far-microphone level.
    // The window is intentionally shorter than the 750ms short-turn branch; keep this
    // regression grounded in speech rather than the synthetic tone fixtures below.
    let pcm = try realSpeechFixturePCM()
    let sampleRate = 16_000
    let start = Int(0.14 * Double(sampleRate)) * 2
    let end = start + Int(0.5 * Double(sampleRate)) * 2
    let shortSpeech = Data(pcm[start..<end])
    let quietSpeech = scalePCM16(shortSpeech, gain: 0.25)
    let profile = PushToTalkManager.speechLikeAudioSeconds(pcm16k: quietSpeech)

    XCTAssertEqual(profile.total, 0.5, accuracy: 0.001)
    XCTAssertGreaterThanOrEqual(profile.speechLike, 0.22)
    XCTAssertTrue(PushToTalkManager.hubTurnHasSpeech(pcm16k: quietSpeech))
  }

  private func sinePCM16k(seconds: Double, frequency: Double, amplitude: Double) -> Data {
    pcm16k(seconds: seconds) { sampleIndex in
      let t = Double(sampleIndex) / 16000.0
      return Int16((sin(2 * Double.pi * frequency * t) * amplitude).rounded())
    }
  }

  private func pcm16k(seconds: Double, sample: (Int) -> Int16) -> Data {
    let sampleCount = Int((seconds * 16000).rounded())
    var data = Data(capacity: sampleCount * 2)
    for i in 0..<sampleCount {
      var value = sample(i).littleEndian
      withUnsafeBytes(of: &value) { data.append(contentsOf: $0) }
    }
    return data
  }

  private func realSpeechFixturePCM() throws -> Data {
    var repositoryRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<4 { repositoryRoot.deleteLastPathComponent() }
    let url = repositoryRoot.appendingPathComponent(
      "backend/testing/release_fixtures/transcription-release-probe.wav")
    let wav = try Data(contentsOf: url)
    var offset = 12
    while offset + 8 <= wav.count {
      let chunkID = String(decoding: wav[offset..<(offset + 4)], as: UTF8.self)
      let chunkSize =
        Int(wav[offset + 4])
        | (Int(wav[offset + 5]) << 8)
        | (Int(wav[offset + 6]) << 16)
        | (Int(wav[offset + 7]) << 24)
      if chunkID == "data" {
        let start = offset + 8
        let end = min(wav.count, start + chunkSize)
        return Data(wav[start..<end])
      }
      offset += 8 + chunkSize + (chunkSize % 2)
    }
    throw NSError(
      domain: "PushToTalkSpeechGateTests", code: 1,
      userInfo: [NSLocalizedDescriptionKey: "WAV data chunk missing"])
  }

  private func scalePCM16(_ data: Data, gain: Double) -> Data {
    var output = Data(capacity: data.count)
    data.withUnsafeBytes { raw in
      let bytes = raw.bindMemory(to: UInt8.self)
      guard bytes.count >= 2 else { return }
      for offset in stride(from: 0, to: bytes.count - 1, by: 2) {
        let bits = UInt16(bytes[offset]) | (UInt16(bytes[offset + 1]) << 8)
        let sample = Int16(bitPattern: bits)
        var value = Int16((Double(sample) * gain).rounded()).littleEndian
        withUnsafeBytes(of: &value) { output.append(contentsOf: $0) }
      }
    }
    return output
  }
}

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
}

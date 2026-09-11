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

    guard wav.count >= 12 else {
      throw fixtureError("WAV header truncated: expected 12 bytes, found \(wav.count)")
    }
    guard String(decoding: wav[0..<4], as: UTF8.self) == "RIFF" else {
      throw fixtureError("WAV header invalid: RIFF signature missing")
    }
    guard String(decoding: wav[8..<12], as: UTF8.self) == "WAVE" else {
      throw fixtureError("WAV header invalid: WAVE signature missing")
    }

    var offset = 12
    var foundPCM16Mono16kFormat = false
    while offset < wav.count {
      guard wav.count - offset >= 8 else {
        throw fixtureError(
          "WAV chunk header truncated at byte \(offset): expected 8 bytes, found \(wav.count - offset)"
        )
      }
      let chunkID = String(decoding: wav[offset..<(offset + 4)], as: UTF8.self)
      let chunkSize =
        Int(wav[offset + 4])
        | (Int(wav[offset + 5]) << 8)
        | (Int(wav[offset + 6]) << 16)
        | (Int(wav[offset + 7]) << 24)
      let payloadStart = offset + 8
      guard chunkSize <= wav.count - payloadStart else {
        throw fixtureError(
          "WAV \(chunkID) chunk truncated at byte \(payloadStart): declared \(chunkSize) bytes, "
            + "found \(wav.count - payloadStart)"
        )
      }
      let payloadEnd = payloadStart + chunkSize

      if chunkID == "fmt " {
        guard chunkSize >= 16 else {
          throw fixtureError(
            "WAV fmt chunk truncated: expected at least 16 bytes, found \(chunkSize)"
          )
        }
        let audioFormat = Int(wav[payloadStart]) | (Int(wav[payloadStart + 1]) << 8)
        let channelCount = Int(wav[payloadStart + 2]) | (Int(wav[payloadStart + 3]) << 8)
        let sampleRate =
          Int(wav[payloadStart + 4])
          | (Int(wav[payloadStart + 5]) << 8)
          | (Int(wav[payloadStart + 6]) << 16)
          | (Int(wav[payloadStart + 7]) << 24)
        let blockAlign = Int(wav[payloadStart + 12]) | (Int(wav[payloadStart + 13]) << 8)
        let bitsPerSample = Int(wav[payloadStart + 14]) | (Int(wav[payloadStart + 15]) << 8)
        guard audioFormat == 1, channelCount == 1, sampleRate == 16_000, blockAlign == 2,
          bitsPerSample == 16
        else {
          throw fixtureError(
            "WAV fmt unsupported: expected PCM16 mono at 16 kHz "
              + "(format=1, channels=1, sampleRate=16000, blockAlign=2, bitsPerSample=16), "
              + "found format=\(audioFormat), channels=\(channelCount), sampleRate=\(sampleRate), "
              + "blockAlign=\(blockAlign), bitsPerSample=\(bitsPerSample)"
          )
        }
        foundPCM16Mono16kFormat = true
      } else if chunkID == "data" {
        guard foundPCM16Mono16kFormat else {
          throw fixtureError("WAV data chunk appeared before a valid PCM16 mono 16 kHz fmt chunk")
        }
        guard chunkSize.isMultiple(of: 2) else {
          throw fixtureError(
            "WAV data chunk truncated: PCM16 payload has odd byte count \(chunkSize)"
          )
        }
        return Data(wav[payloadStart..<payloadEnd])
      }

      let paddedEnd = payloadEnd + (chunkSize % 2)
      guard paddedEnd <= wav.count else {
        throw fixtureError(
          "WAV \(chunkID) chunk padding truncated at byte \(payloadEnd): expected one pad byte"
        )
      }
      offset = paddedEnd
    }
    throw fixtureError(
      foundPCM16Mono16kFormat
        ? "WAV data chunk missing after valid PCM16 mono 16 kHz fmt chunk"
        : "WAV data chunk missing: valid PCM16 mono 16 kHz fmt chunk not found"
    )
  }

  private func fixtureError(_ message: String) -> NSError {
    NSError(
      domain: "PushToTalkSpeechGateTests",
      code: 1,
      userInfo: [NSLocalizedDescriptionKey: message]
    )
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

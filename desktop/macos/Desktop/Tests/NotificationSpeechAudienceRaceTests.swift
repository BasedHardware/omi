import XCTest

@testable import Omi_Computer

/// A notification accepted for a private room must not be heard by a call that starts
/// while its speech is still being generated.
@MainActor
final class NotificationSpeechAudienceRaceTests: XCTestCase {
  private final class Room: @unchecked Sendable {
    var othersCanHear = false
  }

  private struct SynthesisFailed: Error {}

  override func tearDown() async throws {
    FloatingBarVoicePlaybackService.shared.oneShotSynthesizer = nil
    FloatingBarVoicePlaybackService.shared.stop()
  }

  func testTheAudienceHandedToThePlayerIsReadLive() {
    let room = Room()
    var audience: (() -> Bool)?
    let speaker = NotificationSpeechOnDelivery(
      text: "Call dad tonight", speak: { _, allows in audience = allows }, othersCanHearNow: { room.othersCanHear })

    speaker.notificationWasPresented()
    XCTAssertEqual(audience?(), true)

    room.othersCanHear = true
    XCTAssertEqual(audience?(), false, "a call starting after presentation must revoke the audience")
  }

  func testSpeechSynthesizedAfterACallStartsNeverPlays() async {
    let room = Room()
    let service = FloatingBarVoicePlaybackService.shared
    let (synthesized, done) = AsyncStream<Void>.makeStream()
    service.oneShotSynthesizer = { _, _, _ in
      await MainActor.run { room.othersCanHear = true }
      done.finish()
      return Self.silentWAV()
    }

    service.speakOneShot("Private reminder", audienceAllows: { !room.othersCanHear })
    await landed(synthesized)

    XCTAssertTrue(room.othersCanHear)
    XCTAssertFalse(service.isSpeaking, "synthesized audio must not start once others can hear")
  }

  func testSystemVoiceFallbackAfterACallStartsNeverSpeaks() async {
    let room = Room()
    let service = FloatingBarVoicePlaybackService.shared
    let (synthesized, done) = AsyncStream<Void>.makeStream()
    service.oneShotSynthesizer = { _, _, _ in
      await MainActor.run { room.othersCanHear = true }
      done.finish()
      throw SynthesisFailed()
    }

    service.speakOneShot("Private reminder", audienceAllows: { !room.othersCanHear })
    await landed(synthesized)

    XCTAssertTrue(room.othersCanHear)
    XCTAssertFalse(service.isSpeaking, "the system-voice fallback must not speak once others can hear")
  }

  /// Wait for the fake synthesis to finish, then yield so its main-actor completion
  /// runs. The audio below lasts 5 s, so anything that started is still speaking when
  /// the assertion runs.
  private func landed(_ synthesized: AsyncStream<Void>) async {
    for await _ in synthesized {}
    for _ in 0..<20 { await Task.yield() }
  }

  private nonisolated static func silentWAV(sampleCount: Int = 40_000) -> Data {
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
}

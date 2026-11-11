import XCTest

@testable import Omi_Computer

/// A notification accepted for a private room must not be heard by a call that starts
/// while its speech is still being generated or handed to a fallback voice.
@MainActor
final class NotificationSpeechAudienceRaceTests: XCTestCase {
  private typealias Outcome = FloatingBarVoicePlaybackService.OneShotAudienceOutcome

  private final class Room: @unchecked Sendable {
    var othersCanHear = false
  }

  private struct SynthesisFailed: Error {}

  private var service: FloatingBarVoicePlaybackService { .shared }

  override func tearDown() async throws {
    service.oneShotSynthesizer = nil
    service.oneShotAudienceObserver = nil
    service.stop()
  }

  /// The decided outcome of the next audience-gated one-shot, awaited rather than timed.
  private func nextOutcome(_ start: () -> Void) async -> Outcome? {
    let (outcomes, sink) = AsyncStream<Outcome>.makeStream()
    service.oneShotAudienceObserver = { sink.yield($0) }
    start()
    for await outcome in outcomes { return outcome }
    return nil
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

  func testSpeechSynthesizedAfterACallStartsIsWithheld() async {
    let room = Room()
    service.oneShotSynthesizer = { _, _, _ in
      await MainActor.run { room.othersCanHear = true }
      return Self.silentWAV()
    }

    let outcome = await nextOutcome {
      service.speakOneShot("Private reminder", audienceAllows: { !room.othersCanHear })
    }

    XCTAssertEqual(outcome, .withheld)
    XCTAssertFalse(service.isSpeaking, "nothing started, and no synthesis is left pending")
  }

  func testAFailedSynthesisAfterACallStartsNeverFallsBackToSpeech() async {
    let room = Room()
    service.oneShotSynthesizer = { _, _, _ in
      await MainActor.run { room.othersCanHear = true }
      throw SynthesisFailed()
    }

    let outcome = await nextOutcome {
      service.speakOneShot("Private reminder", audienceAllows: { !room.othersCanHear })
    }

    XCTAssertEqual(outcome, .withheld)
    XCTAssertFalse(service.isSpeaking)
  }

  func testAPlayerFailureAfterTheCallStartsNeverFallsBackToSpeech() async {
    // The audience is private when synthesis returns and changes before the player's
    // system-voice fallback: the second read is the one that must hold.
    var reads = 0
    service.oneShotSynthesizer = { _, _, _ in Data("not audio".utf8) }

    let outcome = await nextOutcome {
      service.speakOneShot(
        "Private reminder",
        audienceAllows: {
          reads += 1
          return reads == 1
        })
    }

    XCTAssertEqual(outcome, .withheld)
    XCTAssertEqual(reads, 2, "checked after synthesis and again before the fallback")
    XCTAssertFalse(service.isSpeaking)
  }

  func testAStoppedSynthesisThatFinishesLateNeverPlays() async {
    let (release, open) = AsyncStream<Void>.makeStream()
    service.oneShotSynthesizer = { _, _, _ in
      for await _ in release {}
      return Self.silentWAV()
    }

    let outcome = await nextOutcome {
      service.speakOneShot("Private reminder", audienceAllows: { true })
      service.stop()  // another output takes over before the audio arrives
      open.finish()
    }

    XCTAssertEqual(outcome, .droppedStale)
    XCTAssertFalse(service.isSpeaking)
  }

  func testAPrivateRoomStillHearsTheNotification() async {
    service.oneShotSynthesizer = { _, _, _ in Self.silentWAV() }

    let outcome = await nextOutcome {
      service.speakOneShot("Private reminder", audienceAllows: { true })
    }

    // A machine with no audio output can refuse the player and fall back to the system
    // voice; either way the notification was admitted, never withheld.
    XCTAssertTrue([.played, .fellBackToSystemVoice].contains(outcome), String(describing: outcome))
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

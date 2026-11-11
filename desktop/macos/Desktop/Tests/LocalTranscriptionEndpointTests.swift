import XCTest

@testable import Omi_Computer

/// Pins the pause detection that closes an on-device transcription window early.
///
/// Before it, a window only closed on the fixed 10 s boundary, so a spoken command waited
/// for wherever it landed in that window — measured live at 1.1 s, 6.2 s and 7.7 s for three
/// identical utterances. That was the wake word's entire latency on Apple Silicon.
final class LocalTranscriptionEndpointTests: XCTestCase {
  private let sampleRate = 16000
  private let tailSamples = 9600  // 0.6s
  private let minSamples = 16000  // 1.0s

  private func speech(_ seconds: Double, level: Float = 0.05) -> [Float] {
    // Alternating sign keeps the mean near zero while holding RMS at `level`.
    (0..<Int(Double(sampleRate) * seconds)).map { $0.isMultiple(of: 2) ? level : -level }
  }

  private func silence(_ seconds: Double) -> [Float] {
    [Float](repeating: 0, count: Int(Double(sampleRate) * seconds))
  }

  private func isEndpointed(_ buffer: [Float]) -> Bool {
    LocalTranscriptionService.isEndpointed(buffer, tailSamples: tailSamples, minSamples: minSamples)
  }

  func testSpeechFollowedByAPauseClosesTheWindow() {
    XCTAssertTrue(isEndpointed(speech(2.0) + silence(0.7)))
  }

  func testSpeechStillRunningDoesNotClose() {
    XCTAssertFalse(isEndpointed(speech(2.7)))
  }

  func testPauseShorterThanTheTailDoesNotClose() {
    XCTAssertFalse(isEndpointed(speech(2.0) + silence(0.3)))
  }

  /// A buffer of pure silence must not drain: it would spend an inference on nothing and
  /// advance the emitted-seconds cursor past audio no one spoke.
  func testSilenceAloneDoesNotClose() {
    XCTAssertFalse(isEndpointed(silence(5.0)))
  }

  /// A blip shorter than the minimum utterance is noise, not a command.
  func testTooShortToBeAnUtteranceDoesNotClose() {
    XCTAssertFalse(isEndpointed(speech(0.2) + silence(0.7)))
  }

  /// The minimum is a second of *voiced* audio, not a second of buffer. A long mostly-quiet
  /// window with one blip in it is what Parakeet answers with a hallucinated word — live, a
  /// 1.1 s window at rms 0.0067 came back "Yeah."
  func testBlipInAMostlyQuietWindowDoesNotClose() {
    XCTAssertFalse(isEndpointed(silence(2.0) + speech(0.3) + silence(2.0) + silence(0.7)))
  }

  /// Speech broken by short gaps still adds up to an utterance.
  func testVoicedAudioAccumulatesAcrossShortGaps() {
    XCTAssertTrue(isEndpointed(speech(0.6) + silence(0.2) + speech(0.6) + silence(0.7)))
  }

  /// Room tone sits under the noise floor `drain` already uses, so it reads as a pause
  /// rather than holding the window open until the 10 s boundary.
  func testRoomToneUnderTheNoiseFloorCountsAsAPause() {
    XCTAssertTrue(isEndpointed(speech(2.0) + speech(0.7, level: 0.001)))
  }

  func testEmptyBufferDoesNotClose() {
    XCTAssertFalse(isEndpointed([]))
  }

  // MARK: - Leading-silence trim

  private func leadingSilence(_ buffer: [Float]) -> Int {
    LocalTranscriptionService.leadingSilenceSamples(buffer, chunk: sampleRate / 10, keep: 2)
  }

  /// Quiet ahead of the first speech is dropped, less two chunks of lead-in, so the 10 s cap
  /// is spent on speech instead of filling partway through a sentence.
  func testSilenceBeforeSpeechIsTrimmedWithLeadIn() {
    XCTAssertEqual(leadingSilence(silence(3.0) + speech(2.0)), (30 - 2) * (sampleRate / 10))
  }

  func testBufferOpeningWithSpeechIsNotTrimmed() {
    XCTAssertEqual(leadingSilence(speech(2.0)), 0)
  }

  /// Less lead-in than we keep means nothing to trim — never clip the first phoneme.
  func testSilenceShorterThanTheLeadInIsKept() {
    XCTAssertEqual(leadingSilence(silence(0.15) + speech(2.0)), 0)
  }

  /// Only quiet *before* any speech is trimmed; the scan stops at the first speech chunk, so
  /// a pause between two utterances stays in the window.
  func testPauseBetweenUtterancesIsNotTrimmed() {
    let buffer = speech(1.0) + silence(2.0) + speech(1.0)
    XCTAssertEqual(leadingSilence(buffer), 0)
  }

  // MARK: - A pause measured against the room

  /// Background measured live with people talking nearby: the quietest 100 ms of microphone
  /// audio stayed between 0.0041 and 0.0057 RMS for two minutes.
  private let noisyRoomLevel: Float = 0.006

  private func frames(_ level: Float, count: Int) -> [Float] {
    [Float](repeating: level, count: count)
  }

  private func noisyRoomFloor() -> Float {
    LocalTranscriptionService.quietFloor(recentFrameRMS: frames(noisyRoomLevel, count: 100))
  }

  /// The live failure. Against the fixed floor a room this noisy never contains a pause, so
  /// every microphone window ran the full 10 s.
  func testFixedFloorFindsNoPauseInANoisyRoom() {
    XCTAssertFalse(isEndpointed(speech(1.0, level: noisyRoomLevel) + speech(2.0) + speech(0.7, level: noisyRoomLevel)))
  }

  func testPauseInANoisyRoomClosesAgainstTheRoomsFloor() {
    let buffer = speech(1.0, level: noisyRoomLevel) + speech(2.0) + speech(0.7, level: noisyRoomLevel)
    XCTAssertTrue(
      LocalTranscriptionService.isEndpointed(
        buffer, tailSamples: tailSamples, minSamples: minSamples, floor: noisyRoomFloor()))
  }

  func testSpeechStillRunningInANoisyRoomDoesNotClose() {
    let buffer = speech(1.0, level: noisyRoomLevel) + speech(2.7)
    XCTAssertFalse(
      LocalTranscriptionService.isEndpointed(
        buffer, tailSamples: tailSamples, minSamples: minSamples, floor: noisyRoomFloor()))
  }

  /// The hallucination guard still holds when the floor rises: a blip is not an utterance.
  func testBlipInANoisyRoomDoesNotClose() {
    let buffer =
      speech(2.0, level: noisyRoomLevel) + speech(0.3) + speech(2.7, level: noisyRoomLevel)
    XCTAssertFalse(
      LocalTranscriptionService.isEndpointed(
        buffer, tailSamples: tailSamples, minSamples: minSamples, floor: noisyRoomFloor()))
  }

  func testRoomNoiseAheadOfSpeechIsTrimmedWithLeadIn() {
    let buffer = speech(3.0, level: noisyRoomLevel) + speech(2.0)
    XCTAssertEqual(
      LocalTranscriptionService.leadingSilenceSamples(
        buffer, chunk: sampleRate / 10, keep: 2, floor: noisyRoomFloor()),
      (30 - 2) * (sampleRate / 10))
  }

  /// A low percentile of the history, so speech in it does not lift the floor.
  func testQuietFloorIgnoresSpeechInTheHistory() {
    let floor = LocalTranscriptionService.quietFloor(
      recentFrameRMS: frames(0.05, count: 70) + frames(noisyRoomLevel, count: 30))
    XCTAssertEqual(floor, noisyRoomLevel * LocalTranscriptionService.roomNoiseMargin, accuracy: 0.0001)
  }

  /// A quiet room keeps exactly the floor it had before.
  func testQuietRoomKeepsTheFixedFloor() {
    let floor = LocalTranscriptionService.quietFloor(recentFrameRMS: frames(0.001, count: 100))
    XCTAssertEqual(floor, LocalTranscriptionService.speechFloor)
  }

  /// Digital silence (the system-audio lane between sounds) keeps it too.
  func testDigitalSilenceKeepsTheFixedFloor() {
    XCTAssertEqual(
      LocalTranscriptionService.quietFloor(recentFrameRMS: frames(0, count: 100)),
      LocalTranscriptionService.speechFloor)
  }

  func testLoudRoomCannotMakeSpeechCountAsQuiet() {
    let floor = LocalTranscriptionService.quietFloor(recentFrameRMS: frames(0.05, count: 100))
    XCTAssertEqual(floor, LocalTranscriptionService.maximumQuietFloor)
  }

  func testTooLittleHistoryKeepsTheFixedFloor() {
    let floor = LocalTranscriptionService.quietFloor(
      recentFrameRMS: frames(noisyRoomLevel, count: LocalTranscriptionService.minimumRoomLevelFrames - 1))
    XCTAssertEqual(floor, LocalTranscriptionService.speechFloor)
  }
}

import XCTest

@testable import Omi_Computer

/// Pins who the on-device transcriber calls "You" once speaker embeddings replace the old
/// mic-is-always-the-user rule. Embeddings are synthetic: each voice is a unit axis plus a
/// little deterministic noise, so distinct voices are orthogonal (distance 1.0) and repeats
/// of one voice stay well inside the match threshold.
final class LocalSpeakerRegistryTests: XCTestCase {
  private typealias Lane = LocalTranscriptionLane
  private typealias Resolution = LocalSpeakerRegistry.Resolution

  private var noiseState: UInt64 = 0x9E37_79B9_7F4A_7C15

  private func voice(_ axis: Int) -> [Float] {
    var vector = [Float](repeating: 0, count: 256)
    vector[axis] = 1
    for i in vector.indices {
      noiseState = noiseState &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
      let unit = Float(noiseState >> 40) / Float(1 << 24)  // 0..<1
      vector[i] += (unit - 0.5) * 0.02
    }
    return vector
  }

  private func hear(
    _ registry: inout LocalSpeakerRegistry,
    _ axis: Int,
    lane: Lane = .microphone,
    seconds: Double = 3,
    rms: Float = 0.02
  ) -> LocalSpeakerRegistry.Outcome {
    let outcome = registry.observe(
      LocalSpeakerRegistry.Observation(embedding: voice(axis), durationSeconds: seconds, loudness: rms, lane: lane))
    XCTAssertNotNil(outcome)
    return outcome
      ?? LocalSpeakerRegistry.Outcome(
        resolution: Resolution(speakerId: -1, isUser: false), relabels: [:], voiceprintsToPersist: [],
        nearestDistance: .infinity)
  }

  private func userUpdate(_ outcome: LocalSpeakerRegistry.Outcome) -> VoiceprintUpdate? {
    outcome.voiceprintsToPersist.first { $0.personId == nil }
  }

  func testFirstMicVoiceIsYouAndASecondMicVoiceIsAnotherSpeaker() {
    var registry = LocalSpeakerRegistry()

    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
    let other = hear(&registry, 1)
    XCTAssertEqual(other.resolution, Resolution(speakerId: 1, isUser: false))
    XCTAssertGreaterThan(other.nearestDistance, 0.9, "orthogonal voices are a full unit apart")
    XCTAssertTrue(other.relabels.isEmpty, "an equally loud, equally long rival does not displace the user")
    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertEqual(hear(&registry, 1).resolution, Resolution(speakerId: 1, isUser: false))
    XCTAssertEqual(registry.clusters.count, 2)
  }

  func testSystemAudioVoiceIsNeverYouAndItsMicEchoSharesItsId() {
    var registry = LocalSpeakerRegistry()

    XCTAssertEqual(
      hear(&registry, 1, lane: .systemAudio, seconds: 8).resolution, Resolution(speakerId: 1, isUser: false))
    let user = hear(&registry, 0)
    XCTAssertEqual(user.resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertTrue(user.relabels.isEmpty, "a brand-new cluster has no earlier segments to move")
    // The remote voice bleeding from the speakers into the mic is the same person, not "You".
    XCTAssertEqual(
      hear(&registry, 1, lane: .microphone, seconds: 2).resolution, Resolution(speakerId: 1, isUser: false))
    XCTAssertEqual(hear(&registry, 2, lane: .systemAudio).resolution, Resolution(speakerId: 2, isUser: false))
  }

  func testDominantMicVoiceTakesOverAndEarlierSegmentsAreRelabeled() {
    var registry = LocalSpeakerRegistry()

    // A quiet voice far from the mic opens the conversation and is provisionally "You".
    XCTAssertEqual(hear(&registry, 1, seconds: 2, rms: 0.005).resolution, Resolution(speakerId: 0, isUser: true))
    // The Mac's owner, close and loud, out-scores it: the two swap public ids.
    let owner = hear(&registry, 0, seconds: 4, rms: 0.02)
    XCTAssertEqual(owner.resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertEqual(owner.relabels, [0: Resolution(speakerId: 1, isUser: false)])
    XCTAssertEqual(hear(&registry, 1, seconds: 2, rms: 0.005).resolution, Resolution(speakerId: 1, isUser: false))
    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
  }

  func testStoredVoiceprintIdentifiesYouEvenWhenSomeoneElseSpeaksFirstAndMore() {
    var registry = LocalSpeakerRegistry(userVoiceprint: voice(0), userIsEnrolled: true)

    XCTAssertEqual(hear(&registry, 1, seconds: 10, rms: 0.05).resolution, Resolution(speakerId: 1, isUser: false))
    let user = hear(&registry, 0, seconds: 2, rms: 0.005)
    XCTAssertEqual(user.resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertTrue(registry.userIsConfirmed)
    // A confirmed identity is not up for grabs, however much the other person talks.
    XCTAssertEqual(hear(&registry, 1, seconds: 120, rms: 0.05).resolution, Resolution(speakerId: 1, isUser: false))
    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
  }

  func testStaleVoiceprintFallsBackToTheDominantMicVoiceAfterTheGracePeriod() {
    var registry = LocalSpeakerRegistry(userVoiceprint: voice(7))

    XCTAssertEqual(hear(&registry, 0, seconds: 10).resolution, Resolution(speakerId: 1, isUser: false))
    XCTAssertEqual(hear(&registry, 0, seconds: 10).resolution, Resolution(speakerId: 1, isUser: false))
    let promoted = hear(&registry, 0, seconds: 10)
    XCTAssertEqual(promoted.resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertEqual(promoted.relabels, [1: Resolution(speakerId: 0, isUser: true)])
    XCTAssertFalse(registry.userIsConfirmed)
  }

  func testVoiceprintIsHandedBackOnceTheUserHasSpokenEnough() throws {
    var registry = LocalSpeakerRegistry()

    for _ in 0..<3 {
      let outcome = hear(&registry, 0, seconds: 5)
      XCTAssertNil(userUpdate(outcome), "15 s is not enough to persist")
    }
    let update = try XCTUnwrap(userUpdate(hear(&registry, 0, seconds: 5)))
    XCTAssertEqual(update.embedding.count, 256)
    XCTAssertLessThan(LocalSpeakerRegistry.cosineDistance(update.embedding, voice(0)), 0.05)
    XCTAssertFalse(update.isEnrolled, "a bootstrap guess is remembered as a guess, not a confirmed identity")
    XCTAssertNil(userUpdate(hear(&registry, 0, seconds: 5)), "re-persist only after another minute")
  }

  /// The learned print from a previous session identifies the user early but does not lock them
  /// in: the live session that motivated this had stored the *other* person as "You".
  func testALearnedVoiceprintStillYieldsToADominantMicVoice() {
    var registry = LocalSpeakerRegistry(userVoiceprint: voice(1), userIsEnrolled: false)

    XCTAssertEqual(hear(&registry, 1, seconds: 3, rms: 0.005).resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertFalse(registry.userIsConfirmed)
    let owner = hear(&registry, 0, seconds: 6, rms: 0.03)
    XCTAssertEqual(owner.resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertEqual(owner.relabels, [0: Resolution(speakerId: 1, isUser: false)])
  }

  func testThisIsMeMovesTheUserLabelAndRemembersAnEnrolledVoice() throws {
    var registry = LocalSpeakerRegistry()
    XCTAssertEqual(hear(&registry, 1).resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 1, isUser: false))

    let result = try XCTUnwrap(registry.markAsUser(speakerId: 1))
    XCTAssertEqual(
      result.relabels,
      [0: Resolution(speakerId: 1, isUser: false), 1: Resolution(speakerId: 0, isUser: true)])
    XCTAssertTrue(result.persist.isEnrolled)
    XCTAssertNil(result.persist.personId)
    XCTAssertLessThan(LocalSpeakerRegistry.cosineDistance(result.persist.embedding, voice(0)), 0.05)
    XCTAssertTrue(registry.userIsConfirmed)
    // Locked: however much the other voice talks now, it stays Speaker 1.
    XCTAssertEqual(hear(&registry, 1, seconds: 200, rms: 0.05).resolution, Resolution(speakerId: 1, isUser: false))
    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
  }

  func testNamingASpeakerTeachesTheirVoiceForTheNextSession() throws {
    var registry = LocalSpeakerRegistry()
    _ = hear(&registry, 0)
    XCTAssertEqual(hear(&registry, 1, seconds: 4).resolution, Resolution(speakerId: 1, isUser: false))

    let named = try XCTUnwrap(registry.assignPerson("person-anna", toSpeakerId: 1))
    XCTAssertEqual(named.relabels, [1: Resolution(speakerId: 1, isUser: false, personId: "person-anna")])
    let update = try XCTUnwrap(named.persist)
    XCTAssertEqual(update.personId, "person-anna")
    XCTAssertTrue(update.isEnrolled)
    XCTAssertEqual(
      hear(&registry, 1).resolution, Resolution(speakerId: 1, isUser: false, personId: "person-anna"))
    XCTAssertNil(registry.assignPerson("person-anna", toSpeakerId: 0), "the user is never a named person")

    // Next session: Anna is recognised the moment she speaks.
    var next = LocalSpeakerRegistry(knownVoices: [
      .init(personId: nil, embedding: voice(0), isEnrolled: true),
      .init(personId: "person-anna", embedding: update.embedding, isEnrolled: true),
    ])
    XCTAssertEqual(
      hear(&next, 1, lane: .systemAudio, seconds: 4).resolution,
      Resolution(speakerId: 1, isUser: false, personId: "person-anna"))
    XCTAssertEqual(hear(&next, 0).resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertTrue(next.userIsConfirmed, "an enrolled user print confirms on match")
  }

  func testPushToTalkEnrollmentIdentifiesALiveSpeakerAsTheUser() throws {
    var registry = LocalSpeakerRegistry()
    XCTAssertEqual(hear(&registry, 1, seconds: 8, rms: 0.03).resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertEqual(hear(&registry, 0, seconds: 3, rms: 0.01).resolution, Resolution(speakerId: 1, isUser: false))

    let enrolled = try XCTUnwrap(registry.enrollUser(embedding: voice(0), speechSeconds: 3))
    XCTAssertEqual(
      enrolled.relabels,
      [0: Resolution(speakerId: 1, isUser: false), 1: Resolution(speakerId: 0, isUser: true)])
    XCTAssertTrue(enrolled.persist.isEnrolled)
    XCTAssertTrue(registry.userIsConfirmed)
    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
  }

  func testForgettingTheUserVoiceReopensTheBootstrap() {
    var registry = LocalSpeakerRegistry(userVoiceprint: voice(0), userIsEnrolled: true)
    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertTrue(registry.userIsConfirmed)
    registry.forgetVoice(personId: nil)
    XCTAssertFalse(registry.userIsConfirmed)
    XCTAssertNil(registry.knownUserVoice)
  }

  func testClusterCapJoinsTheNearestVoiceInsteadOfGrowing() {
    var config = LocalSpeakerRegistry.Config()
    config.maxClusters = 2
    var registry = LocalSpeakerRegistry(config: config)

    _ = hear(&registry, 0)
    _ = hear(&registry, 1)
    let third = hear(&registry, 2)
    XCTAssertEqual(registry.clusters.count, 2)
    XCTAssertTrue([0, 1].contains(third.resolution.speakerId))
  }

  /// A 1.7 s echo fragment produced a phantom "Speaker 4" live; short windows may only join.
  func testShortWindowJoinsTheNearestVoiceInsteadOfOpeningACluster() {
    var registry = LocalSpeakerRegistry()

    XCTAssertEqual(hear(&registry, 0).resolution, Resolution(speakerId: 0, isUser: true))
    XCTAssertEqual(
      hear(&registry, 1, lane: .systemAudio, seconds: 6).resolution, Resolution(speakerId: 1, isUser: false))
    let fragment = hear(&registry, 5, lane: .microphone, seconds: 1.7)
    XCTAssertEqual(registry.clusters.count, 2)
    XCTAssertTrue([0, 1].contains(fragment.resolution.speakerId))
    // A full-length window of that voice still gets its own id.
    XCTAssertEqual(hear(&registry, 5, seconds: 3).resolution, Resolution(speakerId: 2, isUser: false))
  }

  func testUnusableEmbeddingIsIgnored() {
    var registry = LocalSpeakerRegistry()
    let zero = registry.observe(
      LocalSpeakerRegistry.Observation(
        embedding: [Float](repeating: 0, count: 256), durationSeconds: 3, loudness: 0.02, lane: .microphone))
    XCTAssertNil(zero)
    XCTAssertTrue(registry.clusters.isEmpty)
    XCTAssertEqual(LocalSpeakerRegistry.cosineDistance([1, 0], [0, 1]), 1, accuracy: 1e-6)
    XCTAssertEqual(LocalSpeakerRegistry.cosineDistance([1, 0], [2, 0]), 0, accuracy: 1e-6)
  }

  func testResolutionLabelMatchesBackendFormat() {
    XCTAssertEqual(Resolution(speakerId: 0, isUser: true).speakerLabel, "SPEAKER_00")
    XCTAssertEqual(Resolution(speakerId: 12, isUser: false).speakerLabel, "SPEAKER_12")
  }
}

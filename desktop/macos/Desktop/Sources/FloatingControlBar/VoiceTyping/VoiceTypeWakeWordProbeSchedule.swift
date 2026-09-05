import Foundation

/// When, during a hold, the opening of the turn is decoded once to listen for
/// the wake word.
///
/// Nothing is typed while the key is held, so this is not about latency. It is
/// about spend and about feedback: a dictation on the realtime-hub route would
/// otherwise stream every minute of the hold to a model whose answer is going
/// to be cancelled, and the user would get no sign that "type" was heard until
/// the paste. Probes fire at the voiced-byte thresholds below (five attempts
/// through ~2.3 s of voice), scheduled by *voiced* audio rather than by time —
/// a locked turn can open with seconds of room tone — and each decodes only
/// the first few seconds, so the cost is bounded however long the hold.
///
/// The probe is advisory. The closing transcript decides the turn on its own,
/// so a missed or misheard probe costs nothing but the early hub release.
struct VoiceTypeWakeWordProbeSchedule: Equatable {

  /// Voiced bytes (16 kHz s16le) at which each probe runs. The first fires as
  /// soon as there is enough voice for "type" plus the start of the next word
  /// — the claim needs a word after the wake word — so the notch turns red
  /// right after the user says "type". The rest are quick retries in case the
  /// on-device model misheard the opening, spaced so a claim usually lands
  /// under a second of speech.
  static let voicedByteThresholds = [
    Int(0.45 * 32_000), Int(0.7 * 32_000), Int(1.0 * 32_000), Int(1.5 * 32_000), Int(2.3 * 32_000),
  ]
  /// The most audio a probe decodes. The wake word opens the utterance; the
  /// rest of a long hold is not needed to find it.
  static let maxProbeBytes = 6 * 32_000

  private(set) var voicedBytes = 0
  private(set) var probesTaken = 0
  private(set) var isDecided = false
  /// Audio not yet a whole 20 ms window. The microphone delivers whatever
  /// the CoreAudio IOProc hands it — ~342 bytes per chunk on a 48 kHz
  /// device — and a chunk smaller than a window measures as no voice at all.
  /// Live, that meant no probe ever ran on a real hold. Windows are cut
  /// across chunk boundaries instead.
  private var pending = Data()
  private static let windowBytes = 640

  /// Feeds one mic chunk. Returns true while a probe is due — it stays due,
  /// chunk after chunk, until `beginProbe` takes it. The caller can only run
  /// one decode at a time, and a slow model load must not silently spend the
  /// slots that fall while it is busy: the probe that was due simply runs on
  /// the first chunk after the decoder is free.
  mutating func observe(chunk: Data) -> Bool {
    guard !isDecided, probesTaken < Self.voicedByteThresholds.count else { return false }
    pending.append(chunk)
    let whole = (pending.count / Self.windowBytes) * Self.windowBytes
    if whole > 0 {
      voicedBytes += VoiceTypeAudioTrim.speechBytes(in: Data(pending.prefix(whole)))
      pending = Data(pending.dropFirst(whole))
    }
    return isProbeDue
  }

  var isProbeDue: Bool {
    !isDecided && probesTaken < Self.voicedByteThresholds.count
      && voicedBytes >= Self.voicedByteThresholds[probesTaken]
  }

  /// The caller is starting the probe that is due. Consumes the slot.
  mutating func beginProbe() {
    guard isProbeDue else { return }
    probesTaken += 1
  }

  /// The question is settled either way (claimed, rejected, or blocked); no
  /// further probes.
  mutating func decide() {
    isDecided = true
  }

  mutating func reset() {
    self = VoiceTypeWakeWordProbeSchedule()
  }
}

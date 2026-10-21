/// Saved audio that covers much less than the conversation it belongs to.
///
/// A phone recording can end up with a few seconds of stored audio under a
/// transcript that runs for minutes (#19243). The player then shows the short
/// length as if it were the whole recording, which reads as a broken file.
/// This decides when the player should say so instead.
library;

/// Saved audio below this share of the conversation counts as partial.
const double partialAudioMaxCoverage = 0.9;

/// Ignore shortfalls smaller than this: trailing silence trimmed from a file
/// or a transcript that outruns the last chunk by a few seconds is normal.
const double partialAudioMinShortfallSeconds = 10;

bool savedAudioIsPartial({required double savedSeconds, required double conversationSeconds}) {
  if (!savedSeconds.isFinite || !conversationSeconds.isFinite) return false;
  if (savedSeconds <= 0 || conversationSeconds <= 0) return false;
  final shortfall = conversationSeconds - savedSeconds;
  return shortfall >= partialAudioMinShortfallSeconds && savedSeconds < conversationSeconds * partialAudioMaxCoverage;
}

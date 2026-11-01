/// The outcome of one pendant question, independent of the currently open chat.
enum VoiceQuestionFailure { noSpeech, busy, quota, unavailable }

class VoiceQuestionResult {
  const VoiceQuestionResult.answered(this.answer, {this.question}) : failure = null;
  const VoiceQuestionResult.failed(this.failure)
      : answer = null,
        question = null;

  final String? answer;
  final String? question;
  final VoiceQuestionFailure? failure;
}

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';

/// What "finish this capture" ended in. Every entry point (the live page's Finish, Home's Wrap Up,
/// the record button's stop) gets one of these, never a bare null, and presents it with
/// `presentFinishOutcome` (ux-contract §17).
sealed class FinishOutcome {
  const FinishOutcome();

  /// The Process Now answer, classified. [heardSomething] is whether the page showed the reader
  /// anything (transcript, photos, preview lines) when they tapped.
  static FinishOutcome fromProcess(InProgressProcessOutcome outcome, {required bool heardSomething}) {
    final conversation = outcome.response?.conversation;
    if (conversation == null) {
      return switch (outcome.absence) {
        // A 200 with no conversation: the server deleted it as empty (too short to keep).
        ProcessAbsence.emptyBody => const FinishDiscarded(),
        // No in-progress conversation: it was already finalized (closed on the server's side).
        ProcessAbsence.notFound => const FinishNothingNew(alreadySaved: true),
        ProcessAbsence.transport || null => const FinishFailed(FinishFailure.noAnswer),
      };
    }
    if (conversation.discarded) return const FinishDiscarded();
    if (conversation.v3?.recording == true) {
      // The recording answered still in progress: the server had nothing of it to process. With
      // words on the page that is not "nothing": the audio has not reached the server yet.
      if (conversation.status == ConversationStatus.in_progress) {
        return heardSomething ? const FinishNotReceived() : const FinishNothingNew();
      }
      return FinishProcessing(conversation.id);
    }
    return FinishOpened(conversation);
  }
}

/// The server made the conversation: open it.
final class FinishOpened extends FinishOutcome {
  const FinishOpened(this.conversation);
  final ServerConversation conversation;
}

/// The server admitted the recording; its conversation is being made. Open the processing page.
final class FinishProcessing extends FinishOutcome {
  const FinishProcessing(this.recordingId);
  final String recordingId;
}

/// Nothing new since the last Finish (or the server had already saved it: [alreadySaved]).
final class FinishNothingNew extends FinishOutcome {
  const FinishNothingNew({this.alreadySaved = false});
  final bool alreadySaved;
}

/// The server kept nothing: the recording was too short or had no speech.
final class FinishDiscarded extends FinishOutcome {
  const FinishDiscarded();
}

/// The page showed words, but the server has none of them yet (a pendant's audio still on its way).
/// The recording carries on and is processed when the audio arrives.
final class FinishNotReceived extends FinishOutcome {
  const FinishNotReceived();
}

/// A phone Transcribe Later recording: it was saved on the phone and uploads on its own; its row on
/// Home is where it lives until then.
final class FinishSavedForLater extends FinishOutcome {
  const FinishSavedForLater();
}

enum FinishFailure {
  /// Offline, a timeout or a server error: no answer, nothing processed.
  noAnswer,

  /// Something in the app threw.
  exception,
}

/// Nothing was processed. The caller keeps what the reader made on screen and offers Try Again,
/// which sends it again.
final class FinishFailed extends FinishOutcome {
  const FinishFailed(this.reason);
  final FinishFailure reason;
}

/// Thrown by `finishCaptureWithOutcome` when the finish made no Process Now request: a phone
/// Transcribe Later recording, which is saved on the phone and uploads on its own.
class FinishMadeNoRequest extends StateError {
  FinishMadeNoRequest() : super('capture did not request live processing');
}

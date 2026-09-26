/// Honest speech-profile enroll telemetry (#12765).
///
/// `Onboarding Step Speech Profile Completed` used to fire on All Done even
/// when the upload failed or the user skipped. These events are the ones
/// that mean a voiceprint actually did or did not land.
enum SpeechProfileEnrollEvent { skipped, uploadSucceeded, uploadFailed, embeddingStored }

String speechProfileEnrollEventName(SpeechProfileEnrollEvent event) {
  switch (event) {
    case SpeechProfileEnrollEvent.skipped:
      return 'Speech Profile Skipped';
    case SpeechProfileEnrollEvent.uploadSucceeded:
      return 'Speech Profile Upload Succeeded';
    case SpeechProfileEnrollEvent.uploadFailed:
      return 'Speech Profile Upload Failed';
    case SpeechProfileEnrollEvent.embeddingStored:
      return 'Speech Profile Embedding Stored';
  }
}

/// All Done / continue is not enroll success. Keep a separate step event so
/// funnel charts stop treating `profileCompleted` as a stored voiceprint.
const String speechProfileContinuedEventName = 'Onboarding Step Speech Profile Continued';

import 'package:omi/backend/schema/message_event.dart';

/// Connection-scoped UI state. Counts are server persistence receipts, never
/// elapsed time or locally retained frames.
class LiveHeldAudioState {
  String? sessionId;
  int heldSeconds = 0;
  int resetAt = 0;
  bool paused = false;

  void reset() {
    sessionId = null;
    heldSeconds = 0;
    resetAt = 0;
    paused = false;
  }

  bool apply(SttCapLiveHeldEvent event) {
    if (event.sessionId.isEmpty || event.heldSeconds < 0) return false;
    if (sessionId != null && sessionId != event.sessionId) return false;
    sessionId = event.sessionId;
    heldSeconds = event.heldSeconds;
    resetAt = event.resetAt;
    paused = event.paused;
    return true;
  }
}

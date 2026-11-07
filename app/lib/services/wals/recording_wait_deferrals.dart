/// Owns the per-recording wait a `record_capture_pending` 503 asks for.
///
/// The server holds one conversation's WALs until its registered record can
/// prove coverage. This keeps only that conversation's WALs out of the drain
/// for the body's `retry_after_seconds`, never the account, so every other
/// recording keeps uploading. In memory only: a restart re-probes at once, and
/// the WAL itself stays pending with its retry budget untouched.
class RecordingWaitDeferrals {
  RecordingWaitDeferrals(this._now);

  /// Upper bound on one server-requested wait, so a bad value cannot strand a WAL.
  static const int maxWaitSeconds = 300;

  final DateTime Function() _now;
  final Map<String, DateTime> _until = {};

  void defer(String? conversationId, int? seconds) {
    if (conversationId == null || seconds == null || seconds <= 0) return;
    _until[conversationId] = _now().add(Duration(seconds: seconds.clamp(1, maxWaitSeconds)));
  }

  bool isWaiting(String? conversationId) {
    if (conversationId == null) return false;
    final until = _until[conversationId];
    if (until == null) return false;
    if (!until.isAfter(_now())) {
      _until.remove(conversationId);
      return false;
    }
    return true;
  }
}

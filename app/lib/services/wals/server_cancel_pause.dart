import 'package:shared_preferences/shared_preferences.dart';

/// Whether the server's owner-cancel kill switch (`SYNC_JOB_OWNER_CANCEL_ENABLED`) was last seen off.
///
/// The phone learns it only from the server's own answer: a 503 `sync_job_cancel_disabled` pauses
/// for [pauseLength], and any other answer from the cancel endpoint clears it. While paused, deleting
/// an uploaded recording still records its tombstone (the cancel is retried once the switch is back
/// on), but the confirmation must not promise the server copy is erased now.
class ServerCancelPause {
  ServerCancelPause._();

  static final ServerCancelPause instance = ServerCancelPause._();
  static const preferencesKey = 'walServerCancelPausedUntil';
  static const pauseLength = Duration(hours: 1);

  DateTime Function() now = DateTime.now;
  int _pausedUntil = 0;
  bool _loaded = false;

  bool get paused => _pausedUntil > now().millisecondsSinceEpoch ~/ 1000;

  Future<void> load() async {
    if (_loaded) return;
    _loaded = true;
    try {
      _pausedUntil = (await SharedPreferences.getInstance()).getInt(preferencesKey) ?? 0;
    } on Exception {
      _pausedUntil = 0; // Unknown: the switch ships on.
    }
  }

  Future<void> pause() => _store(now().add(pauseLength).millisecondsSinceEpoch ~/ 1000);

  Future<void> clear() => _pausedUntil == 0 ? Future<void>.value() : _store(0);

  Future<void> _store(int until) async {
    _pausedUntil = until;
    _loaded = true;
    try {
      await (await SharedPreferences.getInstance()).setInt(preferencesKey, until);
    } on Exception {
      // The in-memory answer still holds for this session.
    }
  }

  /// Tests only.
  void reset({int pausedUntil = 0}) {
    _pausedUntil = pausedUntil;
    _loaded = true;
    now = DateTime.now;
  }
}

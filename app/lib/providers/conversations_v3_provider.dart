import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations_v3.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';

typedef ConversationsLiveFetcher = Future<ApiResult<api.ConversationsLiveRead>> Function();

/// The server's per-user switch for recordings and conversations (v3), and the conversation in
/// progress.
///
/// [v3] true means the new Home: a flat list of conversations with the live one on top, and no episode
/// calls. False, a 404 or no answer yet means today's Home runs untouched. The last answer is kept per
/// account so a cold start opens on the right Home; a different account never inherits it.
class ConversationsV3Provider extends ChangeNotifier {
  ConversationsV3Provider({ConversationsLiveFetcher? fetchLive, String Function()? uid, String? cachedUid})
      : _fetchLive = fetchLive ?? api.getConversationsLive,
        _uid = uid ?? (() => SharedPreferencesUtil().uid) {
    final cached = cachedUid ?? _readCachedUid();
    _owner = _uid();
    _v3 = cached.isNotEmpty && cached == _owner;
  }

  /// Home re-reads the live conversation this often while it is on screen.
  static const pollInterval = Duration(seconds: 15);

  static const _prefKey = 'conversationsV3Uid';

  final ConversationsLiveFetcher _fetchLive;
  final String Function() _uid;

  String _owner = '';
  bool _v3 = false;
  ServerConversation? _live;
  Future<void>? _reading;
  Timer? _poll;
  int _watchers = 0;
  bool _disposed = false;

  bool get v3 => _v3 && _owner == _uid();

  ServerConversation? get live => v3 ? _live : null;

  static String _readCachedUid() {
    try {
      return SharedPreferencesUtil().getString(_prefKey);
    } catch (_) {
      return '';
    }
  }

  void _remember(bool on) {
    // The cache only shortens a cold start; the live read stays authoritative.
    try {
      unawaited(SharedPreferencesUtil().saveString(_prefKey, on ? _owner : '').catchError((_) => false));
    } catch (_) {}
  }

  void _ensureOwner() {
    final uid = _uid();
    if (uid == _owner) return;
    _owner = uid;
    _v3 = false;
    _live = null;
    _reading = null;
  }

  /// One read of the switch and the live conversation; concurrent callers share it.
  Future<void> refresh() {
    _ensureOwner();
    return _reading ??= _read().whenComplete(() => _reading = null);
  }

  Future<void> _read() async {
    final owner = _owner;
    final result = await _fetchLive();
    if (_disposed || owner != _uid()) return;
    final wasV3 = _v3;
    final wasLive = _live;
    switch (result) {
      case ApiSuccess(:final data):
        _v3 = data.v3;
        _live = data.v3 ? data.conversation : null;
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        // An older server: today's Home.
        _v3 = false;
        _live = null;
      case ApiFailure():
        // Offline or a server error: keep the last answer.
        return;
    }
    if (wasV3 != _v3) _remember(_v3);
    if (wasV3 != _v3 || !_sameLive(wasLive, _live)) notifyListeners();
  }

  static bool _sameLive(ServerConversation? a, ServerConversation? b) {
    if (a == null || b == null) return a == b;
    return a.id == b.id &&
        a.structured.title == b.structured.title &&
        a.v3?.tileState == b.v3?.tileState &&
        a.finishedAt == b.finishedAt &&
        a.transcriptSegments.length == b.transcriptSegments.length;
  }

  /// Home calls this while it is on screen; pair each call with [unwatch].
  void watch() {
    _watchers++;
    if (_poll != null) return;
    unawaited(refresh());
    _poll = Timer.periodic(pollInterval, (_) => unawaited(refresh()));
  }

  void unwatch() {
    if (_watchers > 0) _watchers--;
    if (_watchers > 0) return;
    _poll?.cancel();
    _poll = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _poll?.cancel();
    super.dispose();
  }
}

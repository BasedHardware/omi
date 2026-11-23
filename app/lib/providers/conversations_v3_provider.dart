// The per-user recordings-and-conversations (v3) switch and the live conversation, read from
// GET /v1/conversations/live; it decides between the v3 Home and today's episode Home.

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations_v3.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/services/capture/optimistic_processing.dart';

typedef ConversationsLiveFetcher = Future<ApiResult<api.ConversationsLiveRead>> Function();

/// The server's per-user switch for recordings and conversations (v3), and the conversation in
/// progress.
///
/// [v3] true means the new Home: a flat list of conversations with the live one on top, and no episode
/// calls. False or a 404 means today's Home runs untouched. Until the first answer ([resolved] false)
/// the app makes neither episode nor feed calls, so a v3 account never makes one. The last answer is
/// kept per account, so after the first launch a cold start knows at once; a different account never
/// inherits it.
class ConversationsV3Provider extends ChangeNotifier {
  /// [cached] is the remembered answer, `<uid>:1` or `<uid>:0`; tests pass it, the app reads it.
  ConversationsV3Provider({ConversationsLiveFetcher? fetchLive, String Function()? uid, String? cached})
      : _fetchLive = fetchLive ?? api.getConversationsLive,
        _uid = uid ?? (() => SharedPreferencesUtil().uid) {
    final remembered = cached ?? _readCached();
    _owner = _uid();
    if (_owner.isNotEmpty && remembered == '$_owner:1') {
      _v3 = true;
      _resolved = true;
    } else if (_owner.isNotEmpty && remembered == '$_owner:0') {
      _resolved = true;
    }
  }

  /// Home re-reads the live conversation this often while it is on screen.
  static const pollInterval = Duration(seconds: 15);

  static const _prefKey = 'conversationsV3Answer';

  final ConversationsLiveFetcher _fetchLive;
  final String Function() _uid;

  String _owner = '';
  bool _v3 = false;
  bool _resolved = false;
  ServerConversation? _live;
  Future<void>? _reading;
  ServerConversation? _finishRow;
  String? _finishRecordingId;
  String? _finishLiveId;
  bool _suppressListening = false;
  bool _finishAccepted = false;
  bool _finishExpired = false;
  Timer? _finishExpiry;

  bool get finishFeedbackEnabled => v3 && !const bool.fromEnvironment('OMI_V3_FINISH_FEEDBACK_OFF');
  ServerConversation? get finishRow => finishFeedbackEnabled && !_finishExpired ? _finishRow : null;

  bool get suppressListeningAfterFinish => finishFeedbackEnabled && _suppressListening;

  void startManualFinish(ServerConversation row, String? recordingId, {String? liveConversationId}) {
    if (!finishFeedbackEnabled) return;
    _clearManualFinish();
    _finishRow = row;
    _suppressListening = true;
    _finishRecordingId = recordingId;
    final live = _live;
    if (live != null &&
        (live.id == liveConversationId ||
            live.id == recordingId ||
            (recordingId != null && live.v3?.recordingIds.contains(recordingId) == true))) {
      _finishLiveId = live.id;
    }
    _armFinishExpiry();
    notifyListeners();
  }

  bool settleManualFinish(ServerConversation row, ServerConversation? result) {
    if (!finishFeedbackEnabled || !identical(_finishRow, row)) return false;
    if (result == null || result.discarded || result.status == ConversationStatus.in_progress) {
      _clearManualFinish();
    } else {
      _finishAccepted = true;
      _finishExpired = false;
      _suppressListening = true;
      _armFinishExpiry();
      _finishRecordingId = result.id;
      if (result.v3?.recording != true) {
        _finishLiveId = result.id;
      } else if (_live?.v3?.recordingIds.contains(result.id) == true) {
        _finishLiveId ??= _live!.id;
      }
    }
    notifyListeners();
    return true;
  }

  bool finishHasSuccessor(Iterable<ServerConversation> rows) =>
      _finishAccepted &&
      rows.any(
        (row) =>
            row.v3?.recording != true &&
            row.v3?.homeHidden != true &&
            !row.isHiddenFromDefaultList &&
            row.v3?.tileState != ConversationTileState.failed &&
            row.status != ConversationStatus.failed &&
            row.v3?.tileState != ConversationTileState.live &&
            row.status != ConversationStatus.in_progress &&
            (row.id == _finishLiveId ||
                (_finishLiveId == null &&
                    _finishRecordingId != null &&
                    (row.v3?.recordingIds.contains(_finishRecordingId) == true ||
                        row.v3?.recordingPieces.any(
                              (piece) => piece.recordingId == _finishRecordingId,
                            ) ==
                            true))),
      );

  void acknowledgeManualFinish(ServerConversation row) {
    if (!identical(finishRow, row)) return;
    _clearManualFinish(keepClosedLive: true);
    notifyListeners();
  }

  void _armFinishExpiry() {
    _finishExpiry?.cancel();
    _finishExpiry = Timer(OptimisticProcessingPlaceholder.timeout, () {
      _finishExpired = true;
      _suppressListening = false;
      notifyListeners();
    });
  }

  void _clearManualFinish({bool keepClosedLive = false}) {
    _finishExpiry?.cancel();
    _finishRow = null;
    _finishRecordingId = null;
    if (!keepClosedLive) _finishLiveId = null;
    _suppressListening = false;
    _finishAccepted = false;
    _finishExpired = false;
  }

  Future<void> refreshAfterManualFinish() async {
    final owner = _owner;
    await _reading?.then<void>((_) {}, onError: (Object _) {});
    if (owner != _uid()) return;
    if (!_disposed && finishFeedbackEnabled) await refresh();
  }

  Timer? _poll;
  bool Function()? _pollWhen;
  bool Function()? _rowsPending;
  Future<void> Function()? _refreshRows;
  int _watchers = 0;
  bool _disposed = false;

  bool get v3 => _v3 && _owner == _uid();

  /// The server has answered for this account (now or on an earlier launch).
  bool get resolved => _resolved && _owner == _uid();

  /// Episode and Home-feed reads wait for this: off for a v3 account, and until the first answer.
  bool get suppressesLegacy => !resolved || v3;

  ServerConversation? get live =>
      v3 && ((_finishExpired && !_finishAccepted) || _live?.id != _finishLiveId) ? _live : null;

  @visibleForTesting
  bool get polling => _poll != null;

  static String _readCached() {
    try {
      return SharedPreferencesUtil().getString(_prefKey);
    } catch (_) {
      return '';
    }
  }

  void _remember(bool on) {
    // The cache only shortens a cold start; the live read stays authoritative.
    try {
      unawaited(SharedPreferencesUtil().saveString(_prefKey, '$_owner:${on ? 1 : 0}').catchError((_) => false));
    } catch (_) {}
  }

  void _ensureOwner() {
    final uid = _uid();
    if (uid == _owner) return;
    _clearManualFinish();
    _owner = uid;
    _v3 = false;
    _resolved = false;
    _live = null;
    _reading = null;
  }

  /// One read of the switch and the live conversation; concurrent callers share it.
  Future<void> refresh() {
    _ensureOwner();
    final pending = _reading;
    if (pending != null) return pending;
    final read = _read();
    _reading = read;
    // Only this read clears its slot: an account switch may already have started the next one.
    return read.whenComplete(() {
      if (identical(_reading, read)) _reading = null;
    });
  }

  Future<void> _read() async {
    final owner = _owner;
    final result = await _fetchLive();
    if (_disposed || owner != _uid()) return;
    final wasV3 = _v3;
    final wasResolved = _resolved;
    final wasLive = _live;
    switch (result) {
      case ApiSuccess(:final data):
        _v3 = data.v3;
        _live = data.v3 ? data.conversation : null;
        if (_live != null &&
            _live!.id != _finishLiveId &&
            (_finishRecordingId == null || _live!.v3?.recordingIds.contains(_finishRecordingId) != true)) {
          _suppressListening = false;
          if (_finishRow == null) _finishLiveId = null;
        }
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        // An older server: today's Home.
        _v3 = false;
        _live = null;
      case ApiFailure(:final problem) when !_resolved && (problem.statusCode ?? 0) >= 500:
        // The first answer is a server error: run today's Home rather than holding episodes and the
        // feed back for every account. Not remembered, so the next read decides again.
        _v3 = false;
        _live = null;
        _resolved = true;
        notifyListeners();
        return;
      case ApiFailure():
        // Offline, or a later failure: keep the last answer.
        return;
    }
    _resolved = true;
    if (wasV3 != _v3 || !wasResolved) _remember(_v3);
    if (wasV3 != _v3 || !wasResolved || !_sameLive(wasLive, _live)) notifyListeners();
  }

  static bool _sameLive(ServerConversation? a, ServerConversation? b) {
    if (a == null || b == null) return a == b;
    return a.id == b.id &&
        a.structured.title == b.structured.title &&
        a.v3?.tileState == b.v3?.tileState &&
        a.v3?.homeHidden == b.v3?.homeHidden &&
        a.startedAt == b.startedAt &&
        a.finishedAt == b.finishedAt &&
        a.transcriptSegments.length == b.transcriptSegments.length;
  }

  /// Home calls this while it is on screen; pair each call with [unwatch]. A tick is skipped while
  /// [when] says Home is covered (a pushed page). While [rowsPending] says a listed conversation is
  /// still transcribing or writing its summary, each tick also runs [refreshRows], so its row moves
  /// on to done without a pull-to-refresh (X7).
  void watch({bool Function()? when, bool Function()? rowsPending, Future<void> Function()? refreshRows}) {
    _watchers++;
    if (when != null) _pollWhen = when;
    if (rowsPending != null) _rowsPending = rowsPending;
    if (refreshRows != null) _refreshRows = refreshRows;
    if (_poll != null) return;
    unawaited(refresh());
    _poll = Timer.periodic(pollInterval, (_) => tick());
  }

  /// One poll: the live conversation, and the list while a row is mid-pipeline.
  @visibleForTesting
  void tick() {
    if (_pollWhen?.call() == false) return;
    unawaited(refresh());
    final refreshRows = _refreshRows;
    if (v3 && refreshRows != null && (_rowsPending?.call() ?? false)) {
      unawaited(refreshRows().catchError((Object _) {}));
    }
  }

  /// Whether any of [conversations] is still transcribing or writing its summary.
  static bool anyMidPipeline(Iterable<ServerConversation> conversations) => conversations.any((c) {
        final tile = c.v3?.tileState;
        return tile == ConversationTileState.transcribing || tile == ConversationTileState.writing;
      });

  void unwatch() {
    if (_watchers > 0) _watchers--;
    if (_watchers > 0) return;
    _poll?.cancel();
    _poll = null;
    _pollWhen = null;
    _rowsPending = null;
    _refreshRows = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _clearManualFinish();
    _poll?.cancel();
    super.dispose();
  }
}

// The per-user recordings-and-conversations (v3) switch and the live conversation, read from
// GET /v1/conversations/live; it decides between the v3 Home and today's episode Home.

import 'dart:async';

import 'package:clock/clock.dart';
import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations.dart' show ConversationByIdResult, waitForConversationSummary;
import 'package:omi/backend/http/api/conversations_v3.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/providers/summary_wait_after_end.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/utils/conversations/early_title.dart';

typedef ConversationsLiveFetcher = Future<ApiResult<api.ConversationsLiveRead>> Function();

/// One answer of the waiting requests sent after a conversation is ended (reliability experiment
/// `fast_end_feedback`): the conversation as the server returned it, and whether its summary is stored.
typedef SummaryWaitAnswer = ({String conversationId, ConversationByIdResult result, bool settled});

typedef SummaryWaitRequest = Future<({ConversationByIdResult result, bool settled})> Function(String conversationId,
    {bool untilOutline});

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
  ConversationsV3Provider(
      {ConversationsLiveFetcher? fetchLive,
      String Function()? uid,
      String? cached,
      SummaryWaitRequest? summaryWait,
      bool Function()? summaryWaitEnabled})
      : _fetchLive = fetchLive ?? api.getConversationsLive,
        _uid = uid ?? (() => SharedPreferencesUtil().uid) {
    _summaryWait = SummaryWaitAfterEnd(
      wait: summaryWait ?? waitForConversationSummary,
      enabled: summaryWaitEnabled,
      active: (_) => !_disposed && v3,
      apply: _applySummaryAnswer,
    );
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
  // Reliability experiment end_open_conversation: the End time of a finish the server stored before its
  // conversation existed. No id names that conversation; it will carry this instant.
  DateTime? _finishCutAt;
  // An accepted finish that reached its deadline: Home reads the list once.
  bool _reconcileOnHome = false;

  // Counts manual finishes the server did not accept, so a latched End can be retried.
  int _finishFailures = 0;
  int get finishFailures => _finishFailures;

  bool takeHomeReconcile() {
    final due = _reconcileOnHome;
    _reconcileOnHome = false;
    return due;
  }

  bool _suppressListening = false;
  String? _finishCaptureId;
  bool _finishAccepted = false;
  bool _finishExpired = false;
  Timer? _finishExpiry;
  Timer? _finishDeadline;

  bool get finishFeedbackEnabled => v3 && !const bool.fromEnvironment('OMI_V3_FINISH_FEEDBACK_OFF');
  ServerConversation? get finishRow => finishFeedbackEnabled && !_finishExpired ? _finishRow : null;

  bool suppressListeningAfterFinish(String? captureId) =>
      finishFeedbackEnabled && _suppressListening && _finishCaptureId == captureId;

  // --- Reliability experiment instant_live_text: the Listening row returns on speech after the End ---

  DateTime? _finishStartedAt;
  bool _listeningResumed = false;

  /// When the End that hides Home's Listening row for [captureId] was pressed; null while nothing is hidden.
  DateTime? listeningSuppressedSince(String? captureId) =>
      suppressListeningAfterFinish(captureId) ? _finishStartedAt : null;

  /// The phone's own recogniser heard words spoken after that End: Home shows the Listening row again,
  /// and the End's later acceptance does not hide it a second time. Returns whether anything changed.
  bool resumeListeningAfterFinish(String? captureId) {
    if (!suppressListeningAfterFinish(captureId)) return false;
    _suppressListening = false;
    _listeningResumed = true;
    notifyListeners();
    return true;
  }

  void startManualFinish(ServerConversation row, String? recordingId, {String? liveConversationId, String? captureId}) {
    if (!finishFeedbackEnabled) return;
    _clearManualFinish();
    _finishRow = row;
    _suppressListening = true;
    _finishStartedAt = clock.now();
    _finishCaptureId = captureId;
    _finishRecordingId = recordingId;
    _finishLiveId = liveConversationId;
    _bindFinishToLive();
    _armFinishExpiry();
    _finishDeadline = Timer(const Duration(minutes: 20), () {
      _reconcileOnHome = _finishAccepted;
      _clearManualFinish(keepClosedLive: _finishAccepted);
      notifyListeners();
    });
    notifyListeners();
  }

  bool settleManualFinish(ServerConversation row, ServerConversation? result,
      {bool alreadyClosed = false, DateTime? endStoredAt}) {
    if (!finishFeedbackEnabled || !identical(_finishRow, row)) return false;
    final accepted =
        result == null ? alreadyClosed : !result.discarded && result.status != ConversationStatus.in_progress;
    if (!accepted) {
      _finishFailures++;
      _clearManualFinish();
    } else {
      _finishAccepted = true;
      _finishExpired = false;
      _suppressListening = !_listeningResumed;
      if (result == null && endStoredAt != null) {
        // The End is stored but nothing names its conversation, and there may never be one (nothing was
        // said before the End). The row keeps the limit it started with instead of waiting 20 minutes.
        _finishCutAt = endStoredAt;
      } else {
        _finishExpiry?.cancel();
      }
      if (result != null) {
        _finishRecordingId = result.id;
        if (result.v3?.recording != true) {
          _finishLiveId = result.id;
        }
      } else if (row is OptimisticProcessingConversation) {
        // A 404 has no active recording pointer and cannot confirm that a summary exists.
        _finishRecordingId ??= row.targetConversationId;
      }
      _bindFinishToLive();
    }
    notifyListeners();
    return true;
  }

  // Only infer the window from a matching source when Finish did not name it.
  void _bindFinishToLive() {
    final live = _live;
    final recordingId = _finishRecordingId;
    if (_finishLiveId == null &&
        live != null &&
        recordingId != null &&
        (live.id == recordingId || live.v3?.recordingIds.contains(recordingId) == true)) {
      _finishLiveId = live.id;
    }
  }

  /// A visible successor can take over the row while its summary is pending.
  bool finishHasSuccessor(Iterable<ServerConversation> visibleRows) => _matchesFinish(visibleRows);

  ServerConversation? finishTerminalMatch(Iterable<ServerConversation> rows) {
    if (!_finishAccepted) return null;
    for (final row in rows) {
      if (row.v3?.recording == true) continue;
      final terminal = switch (row.v3?.tileState) {
        ConversationTileState.done || ConversationTileState.failed => true,
        null => row.status == ConversationStatus.completed ||
            row.status == ConversationStatus.failed ||
            row.homeStep == 'failed',
        _ => false,
      };
      if (terminal && _matchesFinishRow(row)) return row;
    }
    return null;
  }

  bool _matchesFinish(Iterable<ServerConversation> rows) => rows.any(_matchesFinishRow);

  /// The conversation a stored End closed carries that End's instant, whatever recordings it was made from.
  bool _closedByStoredEnd(ServerConversation row) {
    final sent = _finishCutAt;
    final closedAt = row.v3?.manualCutAt;
    return _finishAccepted &&
        sent != null &&
        closedAt != null &&
        closedAt.difference(sent).abs() <= const Duration(milliseconds: 2);
  }

  bool _matchesFinishRow(ServerConversation row) =>
      row.v3?.tileState != ConversationTileState.live &&
      row.status != ConversationStatus.in_progress &&
      (row.id == _finishLiveId ||
          _closedByStoredEnd(row) ||
          (_finishAccepted &&
              _finishLiveId == null &&
              _finishRecordingId != null &&
              (row.id == _finishRecordingId ||
                  row.v3?.recordingIds.contains(_finishRecordingId) == true ||
                  row.v3?.recordingPieces.any(
                        (piece) => piece.recordingId == _finishRecordingId,
                      ) ==
                      true)));

  bool acknowledgeManualFinish(ServerConversation row) {
    if (!_finishAccepted || !identical(finishRow, row)) return false;
    _clearManualFinish(keepClosedLive: true);
    notifyListeners();
    return true;
  }

  void _armFinishExpiry() {
    _finishExpiry?.cancel();
    _finishExpiry = Timer(OptimisticProcessingPlaceholder.timeout, () {
      if (_finishAccepted) {
        // Only a stored End with no conversation yet keeps this timer after acceptance. None came: the
        // row goes, and Home reads its list once in case the conversation is there under another id.
        _reconcileOnHome = true;
        _clearManualFinish();
      } else {
        _finishExpired = true;
        _suppressListening = false;
      }
      notifyListeners();
    });
  }

  void _clearManualFinish({bool keepClosedLive = false}) {
    _finishExpiry?.cancel();
    _finishDeadline?.cancel();
    _listeningResumed = false;
    _finishRow = null;
    _finishRecordingId = null;
    _finishCutAt = null;
    if (!keepClosedLive) {
      _finishLiveId = null;
      _finishCaptureId = null;
      _suppressListening = false;
    }
    _finishAccepted = false;
    _finishExpired = false;
  }

  Future<void> refreshAfterManualFinish() async {
    final owner = _owner;
    await _reading?.then<void>((_) {}, onError: (Object _) {});
    if (owner != _uid()) return;
    if (!_disposed && finishFeedbackEnabled) await refresh();
  }

  // --- Reliability experiment fast_end_feedback: the outline, then the summary, on waiting requests ---

  late final SummaryWaitAfterEnd _summaryWait;
  final StreamController<SummaryWaitAnswer> _summaryAnswers = StreamController<SummaryWaitAnswer>.broadcast();
  Future<void> Function()? _summaryRowsFallback;
  void Function(ServerConversation row)? _summaryShowRow;

  /// Each answer of the waiting requests, for a page that shows that conversation.
  Stream<SummaryWaitAnswer> get summaryAnswers => _summaryAnswers.stream;

  /// The account's open conversation as of the last live read, whatever the finish bookkeeping shows.
  String? get openConversationId => _live?.id;

  /// The open conversation made from [recordingId], when the last live read knows it.
  String? liveWindowIdFor(String recordingId) {
    final live = _live;
    if (live == null) return null;
    return live.id == recordingId || live.v3?.recordingIds.contains(recordingId) == true ? live.id : null;
  }

  /// Every way of ending a conversation calls this once the conversation is known. Sends the two
  /// waiting requests for [conversationId]; each answer goes to [summaryAnswers] and re-reads Home's
  /// live conversation and its recent rows ([refreshRows] when Home is not watching). Returns whether
  /// a run started: false when the experiment is off, this account is not on v3, the id is unknown,
  /// or a run for this conversation is already open.
  ///
  /// Reliability experiment early_title_icon: an answer that carries the conversation with its title
  /// and emoji fixed, summary still to come ([titledBeforeSummary]), is also handed to [showRow], so
  /// Home lists it at once in place of its Processing row, whatever a bounded row re-read covers.
  bool awaitSummaryAfterEnd(String? conversationId,
      {Future<void> Function()? refreshRows, void Function(ServerConversation row)? showRow}) {
    if (!v3) return false;
    if (refreshRows != null) _summaryRowsFallback = refreshRows;
    if (showRow != null) _summaryShowRow = showRow;
    return _summaryWait.start(conversationId);
  }

  Future<void> _applySummaryAnswer(String conversationId, ConversationByIdResult result,
      {required bool settled}) async {
    if (_disposed) return;
    final row = result.item;
    if (row != null && titledBeforeSummary(row)) _summaryShowRow?.call(row);
    _summaryAnswers.add((conversationId: conversationId, result: result, settled: settled));
    unawaited(refresh().catchError((Object _) {}));
    final rows = _refreshRows ?? _summaryRowsFallback;
    if (rows != null) unawaited(rows().catchError((Object _) {}));
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
        if (_finishRow != null) _bindFinishToLive();
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
        a.discarded == b.discarded &&
        a.v3?.tileState == b.v3?.tileState &&
        a.v3?.homeHidden == b.v3?.homeHidden &&
        listEquals(a.v3?.recordingIds, b.v3?.recordingIds) &&
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

  /// How long a row may sit mid-pipeline and still drive Home's periodic re-read. An older stuck
  /// row updates on pull-to-refresh and when the app reopens; it must not keep the list re-reading.
  static const pendingRefreshWindow = Duration(hours: 1);

  /// The rows of [conversations] mid-pipeline whose last activity is within [pendingRefreshWindow].
  static Iterable<ServerConversation> recentlyMidPipeline(Iterable<ServerConversation> conversations, DateTime now) =>
      conversations.where((c) {
        final tile = c.v3?.tileState;
        if (tile != ConversationTileState.transcribing && tile != ConversationTileState.writing) return false;
        return now.difference(c.finishedAt ?? c.startedAt ?? c.createdAt) < pendingRefreshWindow;
      });

  /// Where a bounded re-read of recent rows starts: the earliest creation among [touched] (rows known
  /// to be changing), never later than [pendingRefreshWindow] ago and never earlier than a day ago.
  static DateTime recentRefreshSince(Iterable<DateTime> touched, DateTime now) {
    var since = now.subtract(pendingRefreshWindow);
    for (final at in touched) {
      if (at.isBefore(since)) since = at;
    }
    final floor = now.subtract(const Duration(days: 1));
    return (since.isBefore(floor) ? floor : since).subtract(const Duration(minutes: 2));
  }

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
    unawaited(_summaryAnswers.close());
    super.dispose();
  }
}

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/episodes.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/live_start_anchor.dart';

typedef EpisodeLiveFetcher = Future<ApiResult<EpisodeRead>> Function();
typedef EpisodeLookupFetcher = Future<ApiResult<EpisodeRead>> Function(String conversationId);
typedef EpisodeWrapUpCall = Future<ApiResult<Episode>> Function(String episodeId, {String? conversationId});
typedef EpisodeDismissCall = Future<ApiResult<Episode>> Function(String episodeId, String itemId);

/// The server's episodes overlay, as the app shows it: the live episode (Home's first row and the
/// live episode page) and the episode a finished conversation belongs to (its Moments section).
///
/// [enabled] is the server capability. It starts false and stays false on a 404 or an
/// `enabled: false` answer, so an older or switched-off server keeps today's per-conversation UI.
class EpisodeProvider extends ChangeNotifier {
  EpisodeProvider({
    EpisodeLiveFetcher? fetchLive,
    EpisodeLookupFetcher? lookup,
    EpisodeWrapUpCall? wrapUp,
    EpisodeDismissCall? dismiss,
    DateTime Function()? clock,
  })  : _fetchLive = fetchLive ?? api.getLiveEpisode,
        _lookup = lookup ?? api.getEpisodeForConversation,
        _wrapUp = wrapUp ?? api.wrapUpEpisode,
        _dismiss = dismiss ?? api.dismissEpisodeItem,
        _clock = clock ?? DateTime.now;

  final EpisodeLiveFetcher _fetchLive;
  final EpisodeLookupFetcher _lookup;
  final EpisodeWrapUpCall _wrapUp;
  final EpisodeDismissCall _dismiss;
  final DateTime Function() _clock;

  /// How often a watcher (Home's live row, the live page) re-reads the live episode.
  static const pollInterval = Duration(seconds: 30);

  /// Until a live episode shows up, a watcher re-reads sooner: the server opens one at the first
  /// words, and the row should switch to it (and hide its fragments) within seconds, not half a minute.
  static const pendingPollInterval = Duration(seconds: 10);

  /// The quick re-reads stop after this long without an episode (a pendant worn in silence), so
  /// quiet wear costs the normal cadence; an episode closing re-arms them for the next stretch.
  static const pendingPollWindow = Duration(minutes: 3);

  /// One stable start for every surface's running length (Home row, live page, device page).
  final LiveStartAnchor liveAnchor = LiveStartAnchor();

  bool _enabled = false;
  bool get enabled => _enabled;

  Episode? _live;
  Episode? get live => _ownerUid == SharedPreferencesUtil().uid ? _live : null;

  // A live endpoint returning null does not delete the episode or its members. Keep the
  // last snapshot reachable while its authoritative conversation lookup catches up.
  Episode? _previous;

  /// "Open previous" is the shortcut to the episode just closed, not a standing bookmark:
  /// past this window from the episode's last activity its members are ordinary history
  /// rows again, so Home's link retires instead of pointing at yesterday.
  static const previousExpiry = Duration(hours: 12);

  Episode? get previous {
    final episode = _ownerUid == SharedPreferencesUtil().uid ? _previous : null;
    if (episode == null) return null;
    final closedAt = episode.stateUpdatedAt ?? episode.lastActivityAt;
    return _clock().difference(closedAt) < previousExpiry ? episode : null;
  }

  String _ownerUid = SharedPreferencesUtil().uid;

  void _ensureOwner() {
    final uid = SharedPreferencesUtil().uid;
    if (_ownerUid == uid) return;
    _ownerUid = uid;
    _generation++;
    _enabled = false;
    _pendingSince = null;
    _live = null;
    _previous = null;
    _recoveryAttemptedAt = null;
    _lastLiveRead = null;
    _waitingSince = _clock();
    _captureId = null;
    _previousBeforeCapture = null;
    _byConversation.clear();
    _cachedAt.clear();
    _lookups.clear();
    _ended.clear();
    liveAnchor.clear();
  }

  DateTime? _lastLiveRead;
  late DateTime _waitingSince = _clock();
  String? _captureId;
  String? _previousBeforeCapture;
  static const notesWaitLimit = Duration(minutes: 3);
  static const notesStaleLimit = Duration(minutes: 5);

  bool notesUnavailable({DateTime? captureStart, String? captureId}) {
    _ensureOwner();
    final time = now();
    if (captureId != null && captureId != _captureId) {
      if (_captureId != null) {
        _previousBeforeCapture = _previous?.id;
      }
      _waitingSince = captureStart ?? time;
      _captureId = captureId;
    }
    final episode = _live;
    if (episode == null) {
      final since = captureStart != null && captureStart.isBefore(_waitingSince) ? captureStart : _waitingSince;
      return (_previous != null && _previous!.id != _previousBeforeCapture) || time.difference(since) >= notesWaitLimit;
    }
    final firstSeen = episode.startedAt.isBefore(_waitingSince) ? episode.startedAt : _waitingSince;
    if (episode.bullets.isEmpty && time.difference(firstSeen) >= notesWaitLimit) return true;
    return (_lastLiveRead != null && time.difference(_lastLiveRead!) >= notesWaitLimit) ||
        time.difference(episode.stateUpdatedAt ?? episode.startedAt) >= notesStaleLimit;
  }

  void _remember(Episode episode) {
    if (_ownerUid != SharedPreferencesUtil().uid ||
        (_previous != null && episode.startedAt.isBefore(_previous!.startedAt))) {
      return;
    }
    _previous = episode;
    _savePointer('previousEpisodeConversation', episode);
  }

  void _savePointer(String name, Episode episode) {
    final uid = SharedPreferencesUtil().uid;
    if (uid.isNotEmpty && episode.conversationIds.isNotEmpty) {
      unawaited(SharedPreferencesUtil().saveString('$name:$uid', episode.conversationIds.last));
    }
  }

  // Bypass the detail cache: that cache may still describe the member's live episode.
  Future<void> recoverPrevious([String? conversationId]) async {
    _ensureOwner();
    final uid = SharedPreferencesUtil().uid;
    final id =
        conversationId ?? (uid.isEmpty ? '' : SharedPreferencesUtil().getString('previousEpisodeConversation:$uid'));
    if (id.isEmpty || _recovering.contains(id)) return;
    _recovering.add(id);
    try {
      final result = await _lookup(id);
      if (_disposed || uid != SharedPreferencesUtil().uid) return;
      if (result case ApiSuccess(:final data)) {
        final episode = data.episode;
        if (episode != null && !episode.live && episode.id != _live?.id) {
          _remember(episode);
          _cacheEpisode(id, episode, recovered: true);
          for (final member in episode.conversationIds) {
            _cacheEpisode(member, episode, recovered: true);
          }
          notifyListeners();
        }
      }
    } finally {
      _recovering.remove(id);
    }
  }

  final Set<String> _recovering = {};

  /// Pointer recovery is how a cold Home finds the episode that closed while nothing was
  /// watching. Without a brake, every quiet poll (10–30 s) would re-read both pointers for
  /// as long as they resolve to nothing; once per window is enough, and an episode closing
  /// on screen still recovers at once through [_acceptLive] and the Home link.
  static const recoveryRetryInterval = Duration(minutes: 5);
  DateTime? _recoveryAttemptedAt;

  void _recoverFromPointers() {
    if (_previous != null && _live != null) return;
    final now = _clock();
    if (_recoveryAttemptedAt != null && now.difference(_recoveryAttemptedAt!) < recoveryRetryInterval) return;
    _recoveryAttemptedAt = now;
    if (_previous == null) unawaited(recoverPrevious());
    if (_live != null) return;
    final uid = SharedPreferencesUtil().uid;
    if (uid.isNotEmpty) {
      unawaited(recoverPrevious(SharedPreferencesUtil().getString('lastLiveEpisodeConversation:$uid')));
    }
  }

  void _acceptLive(Episode? episode, {bool recover = true}) {
    final old = _live;
    final next = episode != null && episode.live && !_ended.contains(episode.id) ? episode : null;
    if (old != null && old.id != next?.id) {
      _remember(old);
      if (recover && old.conversationIds.isNotEmpty) unawaited(recoverPrevious(old.conversationIds.last));
    }
    if (episode != null && !episode.live) _remember(episode);
    if (next != null && old?.id != next.id) {
      _waitingSince = _clock();
      _previousBeforeCapture = null;
    }
    _live = next;
    if (next != null) _savePointer('lastLiveEpisodeConversation', next);
    _lastLiveRead = _clock();
  }

  final Map<String, Episode?> _byConversation = {};
  final Map<String, DateTime> _cachedAt = {};

  // Closure can precede member finalization. A recovered closed snapshot is not immutable.
  static const episodeCacheTtl = pollInterval;

  void _cacheEpisode(String conversationId, Episode? episode, {bool recovered = false}) {
    _byConversation[conversationId] = episode;
    // Render recovered notes immediately, but always revalidate when opening member details.
    if (recovered) {
      _cachedAt.remove(conversationId);
    } else {
      _cachedAt[conversationId] = _clock();
    }
  }

  final Map<String, Future<Episode?>> _lookups = {};
  int _watchers = 0;
  Timer? _poll;
  int _generation = 0;
  bool _wrappingUp = false;
  bool get wrappingUp => _wrappingUp;

  /// Episodes the person ended. Until the server closes one at once, it can still read as live for
  /// a few minutes; it must never come back as the live row.
  final Set<String> _ended = {};

  DateTime now() => _clock();

  /// Re-reads the live episode. A failed read keeps what was shown; a 404 means no episodes here.
  Future<void> refreshLive() async {
    _ensureOwner();
    final uid = _ownerUid;
    final generation = ++_generation;
    final result = await _fetchLive();
    if (generation != _generation || _disposed || uid != SharedPreferencesUtil().uid) return;
    switch (result) {
      case ApiSuccess(:final data):
        _enabled = data.enabled;
        final episode = data.episode;
        _acceptLive(episode);
        _recoverFromPointers();
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        _enabled = false;
        _live = null;
      case ApiFailure():
        return;
    }
    _reschedule();
    notifyListeners();
  }

  DateTime? _pendingSince;
  bool _disposed = false;

  Duration get _interval {
    if (!_enabled || _live != null) {
      _pendingSince = null;
      return pollInterval;
    }
    final since = _pendingSince ??= _clock();
    return _clock().difference(since) < pendingPollWindow ? pendingPollInterval : pollInterval;
  }

  Duration? _scheduled;

  void _reschedule() {
    if (_disposed || _watchers == 0 || _scheduled == _interval) return;
    _poll?.cancel();
    _scheduled = _interval;
    _poll = Timer.periodic(_interval, (_) => unawaited(refreshLive()));
  }

  /// The conversations a live episode stands for on Home; they reappear as rows once it closes.
  Set<String> get liveConversationIds => _enabled && live != null ? live!.conversationIds.toSet() : const {};

  /// The episode [conversationId] belongs to. Coalesce reads and keep only a short-lived cache:
  /// finalization can add moments even after the episode closes and another one starts.
  Future<Episode?> episodeFor(String conversationId) {
    _ensureOwner();
    final uid = _ownerUid;
    final cachedAt = _cachedAt[conversationId];
    if (_byConversation.containsKey(conversationId) &&
        cachedAt != null &&
        _clock().difference(cachedAt) < episodeCacheTtl) {
      return Future.value(_byConversation[conversationId]);
    }
    return _lookups[conversationId] ??= _lookup(conversationId).then((result) {
      if (_disposed || uid != SharedPreferencesUtil().uid) return null;
      _lookups.remove(conversationId);
      switch (result) {
        case ApiSuccess(:final data):
          _enabled = data.enabled || _enabled;
          _cacheEpisode(conversationId, data.episode);
          notifyListeners();
          return data.episode;
        case ApiFailure():
          return null;
      }
    });
  }

  Episode? cachedEpisodeFor(String conversationId) =>
      _ownerUid == SharedPreferencesUtil().uid ? _byConversation[conversationId] : null;

  /// Starts polling while at least one live surface is on screen.
  void watch() {
    _watchers++;
    if (_watchers == 1) {
      unawaited(refreshLive());
      _scheduled = _interval;
      _poll = Timer.periodic(_interval, (_) => unawaited(refreshLive()));
    }
  }

  void unwatch() {
    if (_watchers == 0) return;
    _watchers--;
    if (_watchers == 0) {
      _poll?.cancel();
      _poll = null;
      _scheduled = null;
    }
  }

  /// "Wrap up now": closes the live episode once [conversationId] (the capture being finished) has
  /// its notes. The row leaves Home right away.
  Future<bool> wrapUp({String? conversationId}) async {
    _ensureOwner();
    final uid = _ownerUid;
    final episode = _live;
    if (episode == null || _wrappingUp) return false;
    _wrappingUp = true;
    notifyListeners();
    try {
      final result = await _wrapUp(episode.id, conversationId: conversationId);
      if (_disposed || uid != SharedPreferencesUtil().uid) return false;
      if (result case ApiSuccess(:final data)) {
        _remember(data);
        _live = data.live && conversationId == null ? data : null;
        return true;
      }
      return false;
    } finally {
      _wrappingUp = false;
      notifyListeners();
    }
  }

  /// The person ended the live conversation (Wrap up, a pendant double-tap, Finish): the live
  /// episode closes at once and the next one counts from now. The ended conversation shows as a
  /// processing row; its notes and items still reach the closed episode on the server.
  void onLiveFinalized() {
    _ensureOwner();
    final now = _clock();
    liveAnchor.restart(now);
    final episode = _live;
    if (episode != null) {
      _remember(episode);
      _ended.add(episode.id);
      _live = null;
      // Without a conversation id the server closes the episode immediately; a repeat is a no-op.
      unawaited(_wrapUp(episode.id));
    }
    _waitingSince = now;
    _pendingSince = null;
    _reschedule();
    notifyListeners();
  }

  /// Undo on a captured item: hidden at once, dismissed on the server; restored if that fails.
  Future<bool> dismissItem(String itemId) async {
    final episode = _live;
    if (episode == null) return false;
    _live = episode.copyWith(
      items: [
        for (final item in episode.items) item.id == itemId ? item.withStatus(EpisodeItemStatus.dismissed) : item,
      ],
    );
    notifyListeners();
    final result = await _dismiss(episode.id, itemId);
    if (result is ApiSuccess<Episode>) {
      if (_live?.id == result.data.id) _live = result.data;
      notifyListeners();
      return true;
    }
    if (_live?.id == episode.id) _live = episode;
    notifyListeners();
    return false;
  }

  /// Test and render seam: show [episode] as the live one without a request.
  @visibleForTesting
  void debugSetLive(Episode? episode, {bool enabled = true, Map<String, Episode?> byConversation = const {}}) {
    _enabled = enabled;
    _acceptLive(episode, recover: false);
    for (final entry in byConversation.entries) {
      _cacheEpisode(entry.key, entry.value);
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _poll?.cancel();
    super.dispose();
  }
}

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/episodes.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/live_start_anchor.dart';
import 'package:omi/providers/conversation_provider.dart';

typedef EpisodeLiveFetcher = Future<ApiResult<EpisodeRead>> Function();
typedef EpisodeLookupFetcher = Future<ApiResult<EpisodeRead>> Function(String conversationId);
typedef EpisodeDetailFetcher = Future<ApiResult<Episode>> Function(String episodeId);
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
    Future<ApiResult<EpisodePageRead>> Function(DateTime, DateTime, {String? cursor})? fetchPage,
    EpisodeLookupFetcher? lookup,
    EpisodeDetailFetcher? detail,
    EpisodeWrapUpCall? wrapUp,
    EpisodeDismissCall? dismiss,
    DateTime Function()? clock,
  })  : _fetchLive = fetchLive ?? api.getLiveEpisode,
        _fetchPage = fetchPage ?? api.getEpisodes,
        _lookup = lookup ?? api.getEpisodeForConversation,
        _detail = detail ?? api.getEpisode,
        _wrapUp = wrapUp ?? api.wrapUpEpisode,
        _dismiss = dismiss ?? api.dismissEpisodeItem,
        _clock = clock ?? DateTime.now;

  final Future<ApiResult<EpisodePageRead>> Function(DateTime, DateTime, {String? cursor}) _fetchPage;
  List<Episode> _homeEpisodes = const [];
  List<Episode> get homeEpisodes => enabled && _ownerUid == SharedPreferencesUtil().uid ? _homeEpisodes : const [];
  String? _homeKey;
  DateTime? _homeReadAt;
  DateTime? _homeFrom;
  DateTime? _homeTo;
  Timer? _homeHold;
  // Backoff step only; backend-call budgets below never reset when held episodes change.
  int _homeHoldAttempts = 0;
  final _homeHoldEpisodeCalls = <String, Map<String, int>>{};
  final _homeHoldWindowCalls = <String, int>{};
  int _homeGeneration = 0;
  Future<bool>? _homeRead;
  String? _homeReadingKey;

  ConversationProvider? _homeConversations;
  Set<String> _hiddenHomeMembers = {};
  Object? _homeVisibilityRows;
  int _homeVisibilityCount = -1;
  int _homePendingCount = -1;
  Set<String> get hiddenHomeMembers => _ownerUid == SharedPreferencesUtil().uid ? _hiddenHomeMembers : const {};

  /// Retain the local delete fence after the conversation provider retires its in-flight
  /// tombstone. An older episode snapshot must not resurrect that member. Undo/failure
  /// restores it to the conversation list, which releases this projection-only fence.
  void observeHomeConversations(ConversationProvider provider) {
    if (identical(provider, _homeConversations)) return;
    _homeConversations?.removeListener(_syncHomeVisibility);
    _homeConversations = provider;
    provider.heldHomeEpisodes = () => {
          for (final episode in homeEpisodes)
            if (episode.live ||
                (episode.composed &&
                    episode.members
                            .where(
                              (m) => !_hiddenHomeMembers.contains(m.id) && !provider.memoriesToDelete.containsKey(m.id),
                            )
                            .length >=
                        2))
              episode.id: episode.members
                  .where((m) => !_hiddenHomeMembers.contains(m.id) && !provider.memoriesToDelete.containsKey(m.id))
                  .toList(),
        };
    _homeVisibilityRows = null;
    provider.addListener(_syncHomeVisibility);
    _syncHomeVisibility();
  }

  void _syncHomeVisibility() {
    final provider = _homeConversations;
    if (provider == null || _disposed) return;
    // Delete/settlement/Undo changes pending or loaded length; refreshes replace the list.
    // Every unrelated high-frequency notify returns before walking membership.
    if (identical(_homeVisibilityRows, provider.conversations) &&
        _homeVisibilityCount == provider.conversations.length &&
        _homePendingCount == provider.memoriesToDelete.length) {
      return;
    }
    _homeVisibilityRows = provider.conversations;
    _homeVisibilityCount = provider.conversations.length;
    _homePendingCount = provider.memoriesToDelete.length;
    _ensureOwner();
    if (_hiddenHomeMembers.isEmpty && provider.memoriesToDelete.isEmpty) return;
    final pending = provider.memoriesToDelete.keys.toSet();
    final restored = provider.conversations.map((c) => c.id).toSet();
    final hidden = {..._hiddenHomeMembers, ...pending}
      ..removeWhere((id) => !pending.contains(id) && restored.contains(id));
    if (setEquals(hidden, _hiddenHomeMembers)) return;
    _hiddenHomeMembers = hidden;
    _openedEpisodes.removeWhere((_, episode) => episode.conversationIds.any(hidden.contains));
    _byConversation.removeWhere((_, episode) => episode?.conversationIds.any(hidden.contains) ?? false);
    notifyListeners();
  }

  void invalidateHome() {
    _openedEpisodes.clear();
    _byConversation.clear();
    _cachedAt.clear();
    _opening.clear();
    _openTokens.clear();
    _homeHold?.cancel();
    _homeReadingKey = null;
    _homeReadAt = null;
    _homeFrom = null;
    _homeTo = null;
    _homeGeneration++;
  }

  void _closedOnHome(String episodeId) {
    // Keep the just-closed row grouped while the authoritative read catches up.
    _homeEpisodes = [for (final e in _homeEpisodes) e.id == episodeId ? e.copyWith(live: false) : e];
    invalidateHome();
  }

  /// Load all pages atomically. False means failure/incomplete membership, not a ready empty overlay.
  Future<bool> refreshHome(DateTime from, DateTime to, {bool force = false, bool bootstrap = false}) {
    _ensureOwner();
    return _refreshHome(from, to, force: force, bootstrap: bootstrap);
  }

  Future<bool> _refreshHome(
    DateTime from,
    DateTime to, {
    required bool force,
    required bool bootstrap,
    Set<String>? heldIds,
  }) {
    final key = '$_ownerUid|$from|$to|$bootstrap';
    if (!force && key == _homeReadingKey && _homeRead != null) return _homeRead!;
    final read = _readHome(from, to, force: force, bootstrap: bootstrap, heldIds: heldIds);
    _homeReadingKey = key;
    _homeRead = read;
    return read.whenComplete(() {
      if (identical(_homeRead, read)) {
        _homeRead = null;
        _homeReadingKey = null;
      }
    });
  }

  Future<bool> _readHome(
    DateTime from,
    DateTime to, {
    required bool force,
    required bool bootstrap,
    Set<String>? heldIds,
  }) async {
    if (!_enabled && !bootstrap) return false;
    final key = '${from.toIso8601String()}|${to.toIso8601String()}';
    if (!force &&
        _homeReadAt != null &&
        _clock().difference(_homeReadAt!) < pollInterval &&
        _homeFrom != null &&
        _homeTo != null &&
        !from.isBefore(_homeFrom!) &&
        !to.isAfter(_homeTo!)) {
      return true;
    }
    _homeHold?.cancel();
    _homeKey = key;
    final generation = ++_homeGeneration;
    final uid = _ownerUid;
    final collected = <String, Episode>{};
    final cursors = <String>{};
    String? cursor;
    final episodeCalls = _homeHoldEpisodeCalls.putIfAbsent(uid, () => {});
    final windowKey = '$uid|$key';
    do {
      if (heldIds != null) {
        if ((_homeHoldWindowCalls[windowKey] ?? 0) >= homeHoldWindowCalls ||
            heldIds.any((id) => (episodeCalls[id] ?? 0) >= homeHoldAttempts)) {
          break;
        }
        // Charge before dispatch, including failed/stale reads, to every episode this read serves.
        _homeHoldWindowCalls[windowKey] = (_homeHoldWindowCalls[windowKey] ?? 0) + 1;
        for (final id in heldIds) {
          episodeCalls[id] = (episodeCalls[id] ?? 0) + 1;
        }
      }
      final result = await _fetchPage(from, to, cursor: cursor);
      if (_disposed ||
          generation != _homeGeneration ||
          uid != SharedPreferencesUtil().uid ||
          (!_enabled && !bootstrap)) {
        return false;
      }
      if (result case ApiSuccess(:final data)) {
        if (!data.enabled) {
          _enabled = false;
          _live = null;
          _homeEpisodes = const [];
          notifyListeners();
          return true;
        }
        _enabled = true;
        for (final episode in data.episodes) {
          collected[episode.id] = _ended.contains(episode.id) ? episode.copyWith(live: false) : episode;
        }
        cursor = data.nextCursor;
        if (cursor != null && !cursors.add(cursor)) return false;
      } else {
        _holdHome(from, to, key, generation);
        return false;
      }
    } while (cursor != null && (heldIds == null || !heldIds.every(collected.containsKey)));
    // A bounded hold read may stop mid-window. Preserve membership and update only its targets.
    _homeEpisodes = heldIds == null
        ? collected.values.toList()
        : [
            for (final episode in _homeEpisodes)
              heldIds.contains(episode.id) ? collected[episode.id] ?? episode : episode,
          ];
    _homeFrom = from;
    _homeTo = to;
    _homeReadAt = _clock();
    notifyListeners();
    _holdHome(from, to, key, generation);
    return true;
  }

  /// Nothing else rebuilds Home while a finished episode waits, so re-read until it settles.
  /// Budgets survive settlement, new episodes, invalidation and range revisits. Each timer can
  /// fetch only the remaining budget: at most 10 backend calls per held episode in total and
  /// 20 per user/window over this provider's lifetime, plus ordinary explicit Home loads.
  /// One initial P-page load plus all automatic retries costs at most P + 20 calls.
  void _holdHome(DateTime from, DateTime to, String key, int generation) {
    if (generation != _homeGeneration) return;
    _homeHold?.cancel();
    final now = _clock();
    final episodeCalls = _homeHoldEpisodeCalls.putIfAbsent(_ownerUid, () => {});
    final held = _homeEpisodes.where(
      (e) => e.members.length != 1 && (e.awaitingSummary(now) || _homeHeldByProcessingMember(e)),
    );
    final eligible = held.where((e) => (episodeCalls[e.id] ?? 0) < homeHoldAttempts).toList();
    if (eligible.isEmpty || (_homeHoldWindowCalls['$_ownerUid|$key'] ?? 0) >= homeHoldWindowCalls) {
      _homeHoldAttempts = 0;
      return;
    }
    final backoff = _homeHoldAttempts > 4 ? 4 : _homeHoldAttempts;
    final seconds = pollInterval.inSeconds << backoff;
    final delay = eligible.any((e) => e.awaitingSummary(now))
        ? pollInterval
        : Duration(seconds: seconds > homeHoldMaxDelay.inSeconds ? homeHoldMaxDelay.inSeconds : seconds);
    _homeHoldAttempts++;
    final ids = eligible.map((e) => e.id).toSet();
    _homeHold = Timer(delay, () {
      _ensureOwner();
      if (key == _homeKey && generation == _homeGeneration) {
        unawaited(_refreshHome(from, to, force: true, bootstrap: false, heldIds: ids));
      }
    });
  }

  /// A closed episode needs another read while a member is still processing: Home's pending hold
  /// keeps the uncomposed copy on screen until a read brings the composed one.
  bool _homeHeldByProcessingMember(Episode episode) {
    if (episode.live || episode.composed || episode.members.length == 1) return false;
    final processing = _homeConversations?.processingConversations;
    return processing != null && processing.any((c) => episode.conversationIds.contains(c.id));
  }

  @visibleForTesting
  void debugSetHomeEpisodes(List<Episode> episodes) {
    _homeEpisodes = episodes;
    _homeReadAt = _clock();
    notifyListeners();
  }

  final EpisodeLiveFetcher _fetchLive;
  final EpisodeLookupFetcher _lookup;
  final EpisodeDetailFetcher _detail;
  final Map<String, Episode> _openedEpisodes = {};
  Episode? openedEpisode(String id) => _ownerUid == SharedPreferencesUtil().uid ? _openedEpisodes[id] : null;
  final EpisodeWrapUpCall _wrapUp;
  final EpisodeDismissCall _dismiss;
  final DateTime Function() _clock;

  /// How often a watcher (Home's live row, the live page) re-reads the live episode.
  static const pollInterval = Duration(seconds: 30);

  /// Hard backend-call budgets for automatic held-episode reads, including failed page fetches.
  static const homeHoldAttempts = 10;
  static const homeHoldWindowCalls = 20;
  static const homeHoldMaxDelay = Duration(minutes: 5);

  /// Until a live episode shows up, a watcher re-reads sooner: the server opens one at the first
  /// words, and the row should switch to it (and hide its fragments) within seconds, not half a minute.
  static const pendingPollInterval = Duration(seconds: 10);

  /// The quick re-reads stop after this long without an episode (a pendant worn in silence), so
  /// quiet wear costs the normal cadence; an episode closing re-arms them for the next stretch.
  static const pendingPollWindow = Duration(minutes: 3);

  /// One stable start for every surface's running length (Home row, live page, device page).
  final LiveStartAnchor liveAnchor = LiveStartAnchor();

  bool _enabled = false;
  bool get enabled => _enabled && _ownerUid == SharedPreferencesUtil().uid;

  Episode? _live;
  Episode? get live => _ownerUid == SharedPreferencesUtil().uid ? _live : null;

  // A live endpoint returning null does not delete the episode or its members. Keep the
  // last snapshot reachable while its authoritative conversation lookup catches up.
  Episode? _previous;

  /// "Open previous" is the shortcut to the episode just closed, not a standing bookmark:
  /// past this window from the episode's last activity the shortcut retires. Closed
  /// episodes remain in the Home history projection.
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
    _homeEpisodes = const [];
    _homeHold?.cancel();
    _homeHoldAttempts = 0;
    _hiddenHomeMembers = {};
    _homeVisibilityRows = null;
    _homeKey = null;
    _homeReadAt = null;
    _homeFrom = null;
    _homeTo = null;
    _homeGeneration++;
    _byConversation.clear();
    _openedEpisodes.clear();
    _opening.clear();
    _openTokens.clear();
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
      _closedOnHome(old.id);
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

  /// The conversations the existing live row stands for on Home.
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

  static const openComposePolls = 8;
  static const openComposePollInterval = Duration(seconds: 5);
  static const openComposeReadTimeout = Duration(seconds: 4);
  final Map<String, Future<Episode?>> _opening = {};
  final Map<String, Object> _openTokens = {};

  /// One read per open, with at most eight more reads only while the server says
  /// notes are deferred. Concurrent opens coalesce; leaving the page cancels polling.
  Future<Episode?> openEpisode(String episodeId) {
    _ensureOwner();
    if (_disposed || episodeId.isEmpty) return Future.value(null);
    final existing = _opening[episodeId];
    if (existing != null) return existing;
    final token = Object();
    _openTokens[episodeId] = token;
    final future = _readOpened(episodeId, token).whenComplete(() {
      if (identical(_openTokens[episodeId], token)) {
        _opening.remove(episodeId);
        _openTokens.remove(episodeId);
      }
    });
    _opening[episodeId] = future;
    return future;
  }

  void cancelOpenEpisode(String episodeId) {
    _openTokens.remove(episodeId);
    _opening.remove(episodeId);
  }

  Future<Episode?> _readOpened(String episodeId, Object token) async {
    final uid = _ownerUid;
    bool active() => !_disposed && uid == SharedPreferencesUtil().uid && identical(_openTokens[episodeId], token);
    final deadline = _clock().add(const Duration(seconds: 45));
    Episode? episode;
    for (var attempt = 0; attempt <= openComposePolls && active(); attempt++) {
      if (attempt > 0) {
        await Future<void>.delayed(openComposePollInterval);
        if (!active() || !_clock().isBefore(deadline)) break;
      }
      ApiResult<Episode> result;
      try {
        final remaining = deadline.difference(_clock());
        if (remaining <= Duration.zero) break;
        result = await _detail(
          episodeId,
        ).timeout(remaining < openComposeReadTimeout ? remaining : openComposeReadTimeout);
      } on TimeoutException {
        break;
      }
      if (!active()) return null;
      if (result is! ApiSuccess<Episode>) break;
      episode = result.data;
      _mergeOpened(episode);
      if (episode.live || !episode.composeDeferred) break;
    }
    return episode;
  }

  void _mergeOpened(Episode episode) {
    _openedEpisodes.remove(episode.id);
    _openedEpisodes[episode.id] = episode;
    if (_openedEpisodes.length > 16) _openedEpisodes.remove(_openedEpisodes.keys.first);
    for (final id in episode.conversationIds) {
      _byConversation[id] = episode;
      _cachedAt[id] = _clock();
    }
    notifyListeners();
  }

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
        _acceptLive(data.live && conversationId == null ? data : null, recover: false);
        _remember(data);
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
      _closedOnHome(episode.id);
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
    _homeHold?.cancel();
    _disposed = true;
    _homeConversations?.removeListener(_syncHomeVisibility);
    _poll?.cancel();
    super.dispose();
  }
}

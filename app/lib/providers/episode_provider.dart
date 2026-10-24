import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/episodes.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
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
  Episode? get live => _live;

  final Map<String, Episode?> _byConversation = {};
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
    final generation = ++_generation;
    final result = await _fetchLive();
    if (generation != _generation || _disposed) return;
    switch (result) {
      case ApiSuccess(:final data):
        _enabled = data.enabled;
        final episode = data.episode;
        _live = episode != null && _ended.contains(episode.id) ? null : episode;
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
  Set<String> get liveConversationIds => _enabled && _live != null ? _live!.conversationIds.toSet() : const {};

  /// The episode [conversationId] belongs to, read once per conversation and cached.
  Future<Episode?> episodeFor(String conversationId) {
    if (_byConversation.containsKey(conversationId)) return Future.value(_byConversation[conversationId]);
    return _lookups[conversationId] ??= _lookup(conversationId).then((result) {
      _lookups.remove(conversationId);
      switch (result) {
        case ApiSuccess(:final data):
          _enabled = data.enabled || _enabled;
          _byConversation[conversationId] = data.episode;
          notifyListeners();
          return data.episode;
        case ApiFailure():
          return null;
      }
    });
  }

  Episode? cachedEpisodeFor(String conversationId) => _byConversation[conversationId];

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
    final episode = _live;
    if (episode == null || _wrappingUp) return false;
    _wrappingUp = true;
    notifyListeners();
    try {
      final result = await _wrapUp(episode.id, conversationId: conversationId);
      if (result case ApiSuccess(:final data)) {
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
    final now = _clock();
    liveAnchor.restart(now);
    final episode = _live;
    if (episode != null) {
      _ended.add(episode.id);
      _live = null;
      // Without a conversation id the server closes the episode immediately; a repeat is a no-op.
      unawaited(_wrapUp(episode.id));
    }
    _pendingSince = null;
    _reschedule();
    notifyListeners();
  }

  /// Undo on a captured item: hidden at once, dismissed on the server; restored if that fails.
  Future<bool> dismissItem(String itemId) async {
    final episode = _live;
    if (episode == null) return false;
    _live = episode.copyWith(items: [
      for (final item in episode.items) item.id == itemId ? item.withStatus(EpisodeItemStatus.dismissed) : item,
    ]);
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
    _live = episode;
    _byConversation.addAll(byConversation);
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _poll?.cancel();
    super.dispose();
  }
}

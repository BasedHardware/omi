// Bounded Home card paging, warming and legacy preparation coordination.
// Account generations fence cached shells, mutations and late network responses.
import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/home_feed_cache.dart';
import 'package:omi/backend/http/api/home_feed.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/providers/conversation_provider.dart';

typedef HomeFeedFetcher = Future<ApiResult<HomeFeedPage>> Function({String? cursor});

/// One flight per account/query generation, bounded seven-day warming, cursor-only continuation.
class HomeFeedProvider extends ChangeNotifier {
  HomeFeedProvider(
      {HomeFeedFetcher? fetch,
      Future<ApiResult<HomeFeedPreparation>> Function()? prepare,
      String Function()? owner,
      HomeFeedCache? cache,
      DateTime Function()? now})
      : _fetch = fetch ?? HomeFeedApi().page,
        _prepare = prepare ?? (() => HomeFeedApi().prepare()),
        _owner = owner ?? (() => SharedPreferencesUtil().uid),
        _cache = cache ?? HomeFeedCache(),
        _now = now ?? DateTime.now;
  ConversationProvider? _observedSource;
  void Function(String, bool)? _sourceCallback;
  final HomeFeedFetcher _fetch;
  final Future<ApiResult<HomeFeedPreparation>> Function() _prepare;
  Timer? _prepareTimer;
  int _prepareCalls = 0, _prepareFailures = 0;
  DateTime? _prepareUntil;
  bool preparationReady = false;
  String? _serverGeneration;
  bool _reconcileRequested = false;
  int _reconcileRestarts = 0;
  bool preparing = false;
  final String Function() _owner;
  final HomeFeedCache _cache;
  final DateTime Function() _now;
  static const maxCards = 350, maxWarmRequests = 8, maxBytes = 512 * 1024;
  String _uid = '';
  int _generation = 0, _bytes = 0;
  bool _disposed = false, _hasMore = true, _active = true, _needsRefresh = true;
  List<HomeFeedCard> _items = const [];
  List<HomeFeedCard> get items => _owner() == _uid ? _items : const [];
  String? _cursor;
  Future<void>? _flight;
  bool get loading => _flight != null;
  Future<void>? _starting;
  final Set<String> _pendingDeletes = {};
  bool initialized = false, unsupported = false, truncated = false;
  ApiProblem? problem;
  bool get hasMore => _hasMore;
  bool get partial => truncated || problem != null;
  Future<void> retry() =>
      _reconcileRequested ? reconcileLoadedWindow() : (_needsRefresh || _cursor == null ? refresh() : loadMore());

  void setActive(bool active) {
    if (_active == active && _uid == _owner()) return;
    final resuming = !_active && active && _uid == _owner();
    _active = active;
    if (!active) _items = [for (final card in _items) card.withoutText()];
    _generation++;
    _prepareTimer?.cancel();
    _starting = null;
    _flight = null;
    if (_uid != _owner()) {
      _items = const [];
      _pendingDeletes.clear();
      _cursor = null;
      _needsRefresh = true;
      _hasMore = true;
      _bytes = 0;
      problem = null;
      _serverGeneration = null;
      _reconcileRequested = false;
      _reconcileRestarts = 0;
      _prepareUntil = null;
      _prepareFailures = 0;
      preparationReady = false;
      truncated = false;
      _prepareCalls = 0;
      preparing = false;
      initialized = false;
      unsupported = false;
      _uid = _owner();
    }
    if (active && preparing) _schedulePreparation(_generation, _uid);
    if (resuming && initialized && !unsupported) unawaited(reconcileLoadedWindow());
    if (!_disposed) notifyListeners();
  }

  void observeConversations(ConversationProvider source) {
    if (identical(source, _observedSource)) return;
    if (identical(_observedSource?.homeCardSourceChanged, _sourceCallback)) {
      _observedSource?.homeCardSourceChanged = null;
    }
    _observedSource = source;
    source.homeCardSourceChanged = _sourceCallback = (id, pending) {
      if (_disposed) return;
      if (id.isEmpty) {
        final oldOwner = _uid;
        _generation++;
        _items = const [];
        _pendingDeletes.clear();
        _flight = null;
        _starting = null;
        initialized = false;
        unsupported = false;
        problem = null;
        truncated = false;
        _prepareTimer?.cancel();
        _prepareCalls = 0;
        unawaited(_cache.write(oldOwner, const [], () => true));
        notifyListeners();
        return;
      }
      if (pending) {
        _pendingDeletes.add(id);
      } else {
        _pendingDeletes.remove(id);
      }
      _generation++;
      _flight = null;
      _items = [
        for (final card in _items)
          if (card.detailId != id || card.kind == 'episode') (card.kind == 'episode' ? card.withoutText() : card)
      ];
      unawaited(_persist(_generation, _uid));
      notifyListeners();
      if (!pending && _active && _uid == _owner()) unawaited(reconcileLoadedWindow());
    };
  }

  Future<void> start() {
    if (_uid != _owner()) setActive(_active);
    if (_starting != null) return _starting!;
    final future = _start();
    _starting = future;
    return future.whenComplete(() {
      if (identical(_starting, future)) _starting = null;
    });
  }

  Future<void> _start() async {
    final uid = _owner();
    if (uid.isEmpty || _disposed || !_active) return;
    if (_uid == uid && initialized) return;
    _uid = uid;
    final generation = ++_generation;
    final cached = await _cache.read(uid);
    if (!_current(generation, uid)) return;
    _items = [for (final card in cached) card.withoutText()];
    notifyListeners(); // cached first frame never waits for I/O
    await refresh();
  }

  bool _current(int generation, String uid) => !_disposed && _active && generation == _generation && uid == _owner();
  Future<void> refresh() {
    if (_uid != _owner()) setActive(_active);
    if (_disposed || !_active) return Future.value();
    if (_flight != null) return _flight!;
    _uid = _owner();
    _reconcileRestarts = 0;
    if (unsupported && preparing) {
      _prepareFailures = 0;
      _prepareCalls = 0;
      _prepareUntil = DateTime.now().add(const Duration(minutes: 10));
    }
    _cursor = null;
    _hasMore = true;
    _bytes = 0;
    _needsRefresh = true;
    return _read(replace: true).then((_) {
      if (problem == null && !unsupported) unawaited(warm());
    });
  }

  Future<void> loadMore() {
    if (_flight != null) return _flight!;
    if (!_active || !_hasMore || _disposed || unsupported || !initialized) return Future.value();
    if (_needsRefresh) return refresh();
    return _read(replace: false);
  }

  Future<void> warm() async {
    final generation = _generation;
    for (var request = 1; request < maxWarmRequests && generation == _generation && _active; request++) {
      if (!_hasMore ||
          problem != null ||
          _items.length >= maxCards ||
          _bytes >= maxBytes ||
          (_items.isNotEmpty && !_items.last.sortAt.isAfter(_now().subtract(const Duration(days: 7))))) {
        return;
      }
      await loadMore();
    }
  }

  Future<void> _read({required bool replace}) {
    final generation = _generation, uid = _uid, requested = _cursor;
    late final Future<void> flight;
    flight = () async {
      ApiResult<HomeFeedPage> result;
      try {
        // Defer injected synchronous work until the flight identity is installed.
        result = await Future<ApiResult<HomeFeedPage>>.sync(() => _fetch(cursor: requested));
      } on TimeoutException {
        result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
      } on IOException {
        result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
      }

      if (!_current(generation, uid)) return;
      initialized = true;
      if (result is ApiFailure<HomeFeedPage>) {
        await _handleFailure(result.problem, generation, uid, replace: replace);
        return;
      }
      final page = (result as ApiSuccess<HomeFeedPage>).data;
      if (!replace && _serverGeneration != null && _serverGeneration != page.generation) {
        _items = [for (final card in _items) card.withoutText()];
        _serverGeneration = page.generation;
        _reconcileRequested = true;
        await _persist(generation, uid);
        return;
      }
      _serverGeneration = page.generation;
      problem = null;
      unsupported = false;
      truncated = page.truncated;
      _needsRefresh = false;
      final merged = <String, HomeFeedCard>{
        if (!replace)
          for (final c in _items) c.id: c
      };
      for (final card in page.items) {
        if (_pendingDeletes.contains(card.detailId)) continue;
        merged[card.id] = card.kind == 'episode' && _pendingDeletes.isNotEmpty ? card.withoutText() : card;
      }
      _items = merged.values.toList()..sort((a, b) => b.sortAt.compareTo(a.sortAt));
      _bytes += page.items.fold<int>(0, (n, c) => n + c.title.length * 4 + c.preview.length * 4 + 256);
      if ((page.hasMore || page.truncated) && (page.nextCursor == null || page.nextCursor == requested)) {
        problem = const ApiProblem(ApiProblemKind.decode);
        return;
      }
      _cursor = page.nextCursor;
      _hasMore = page.hasMore || page.truncated; // a partial response never manufactures history exhaustion
      await _persist(generation, uid);
    }()
        .whenComplete(() {
      if (!_disposed && identical(_flight, flight)) {
        _flight = null;
        notifyListeners();
        if (_reconcileRequested && _reconcileRestarts++ < 2) {
          _reconcileRequested = false;
          unawaited(reconcileLoadedWindow());
        }
      }
    });
    _flight = flight;
    notifyListeners();
    return flight;
  }

  Future<void> _handleFailure(ApiProblem failure, int generation, String uid, {required bool replace}) async {
    problem = failure;
    preparing = failure.statusCode == 409 && failure.detail == 'home_feed_preparation_required';
    // A serving rollback must restore compatibility even after cards were adopted.
    // Dirty coverage after adoption keeps redacted geometry until reconciliation;
    // the legacy provider may still hold text from before a remote deletion.
    unsupported = failure.kind == ApiProblemKind.notFound || (replace && _serverGeneration == null && preparing);
    if (unsupported) {
      recordFallback(const ApiFallbackEvent(reason: ApiFallbackReason.error, outcome: ApiFallbackOutcome.degraded));
    }
    if (preparing) {
      _items = [for (final card in _items) card.withoutText()];
      await _persist(generation, uid);
      _schedulePreparation(generation, uid);
      return;
    }
    final view =
        presentApiResult<List<HomeFeedCard>>(ApiFailure(failure), previous: _items, isEmpty: (value) => value.isEmpty);
    if (view.data == null) {
      _items = const [];
      await _persist(generation, uid);
    }
  }

  /// Revalidate the entire loaded window after a known source mutation. Keeping redacted
  /// episode shells until this commit preserves the scrolled reader's row geometry.
  Future<void> reconcileLoadedWindow() {
    if (_flight != null) return _flight!;
    if (_disposed || !_active) return Future.value();
    final generation = _generation, uid = _uid, target = _items.length;
    final done = Completer<void>();
    _flight = done.future;
    Future<void>(() async {
      var cursor = <String?>[null];
      final collected = <String, HomeFeedCard>{};
      var bytes = 0;
      String? acceptedGeneration;
      for (var request = 0; request < maxWarmRequests; request++) {
        ApiResult<HomeFeedPage> result;
        try {
          result = await _fetch(cursor: cursor.last);
        } on TimeoutException {
          result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
        } on IOException {
          result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
        }
        if (!_current(generation, uid)) return;
        if (result is ApiFailure<HomeFeedPage>) {
          await _handleFailure(result.problem, generation, uid, replace: true);
          return;
        }
        final page = (result as ApiSuccess<HomeFeedPage>).data;
        if (acceptedGeneration != null && acceptedGeneration != page.generation) {
          problem = const ApiProblem(ApiProblemKind.server, detail: 'home_feed_changed');
          _reconcileRequested = true;
          return;
        }
        acceptedGeneration = page.generation;
        for (final card in page.items) {
          if (_pendingDeletes.contains(card.detailId)) continue;
          collected[card.id] = card.kind == 'episode' && _pendingDeletes.isNotEmpty ? card.withoutText() : card;
          bytes += card.title.length * 4 + card.preview.length * 4 + 256;
        }
        if ((page.hasMore || page.truncated) && (page.nextCursor == null || cursor.contains(page.nextCursor))) {
          problem = const ApiProblem(ApiProblemKind.decode);
          return;
        }
        _cursor = page.nextCursor;
        _hasMore = page.hasMore || page.truncated;
        truncated = page.truncated;
        if (!_hasMore || collected.length >= target || collected.length >= maxCards || bytes >= maxBytes) break;
        cursor.add(page.nextCursor);
      }
      if (!_current(generation, uid)) return;
      _items = collected.values.toList()..sort((a, b) => b.sortAt.compareTo(a.sortAt));
      _needsRefresh = false;
      _serverGeneration = acceptedGeneration;
      problem = null;
      await _persist(generation, uid);
    }).catchError((Object error, StackTrace stack) {
      if (_current(generation, uid)) problem = const ApiProblem(ApiProblemKind.decode);
    }).whenComplete(() {
      if (!_disposed && identical(_flight, done.future)) {
        _flight = null;
        notifyListeners();
      }
      done.complete();
    });
    return done.future;
  }

  void continuePreparation() {
    if (!preparing || !_active) return;
    if (_prepareUntil == null ||
        _prepareCalls >= 60 ||
        _prepareFailures >= 3 ||
        DateTime.now().isAfter(_prepareUntil!)) {
      _prepareUntil = DateTime.now().add(const Duration(minutes: 10));
      _prepareCalls = 0;
      _prepareFailures = 0;
    }
    _schedulePreparation(_generation, _uid);
  }

  void _schedulePreparation(int generation, String uid) {
    _prepareUntil ??= DateTime.now().add(const Duration(minutes: 10));
    if (_prepareCalls >= 60 ||
        _prepareFailures >= 3 ||
        DateTime.now().isAfter(_prepareUntil!) ||
        !_current(generation, uid)) {
      return;
    }
    _prepareTimer?.cancel();
    _prepareTimer =
        Timer(Duration(seconds: _prepareCalls > 0 && _prepareCalls % 3 == 0 ? 30 : (1 << _prepareFailures)), () async {
      if (!_current(generation, uid)) return;
      _prepareCalls++;
      ApiResult<HomeFeedPreparation> result;
      try {
        result = await _prepare();
      } on TimeoutException {
        _prepareFailures++;
        _schedulePreparation(generation, uid);
        return;
      } on IOException {
        _prepareFailures++;
        _schedulePreparation(generation, uid);
        return;
      }
      if (!_current(generation, uid)) return;
      if (result is ApiFailure<HomeFeedPreparation>) {
        _prepareFailures++;
        _schedulePreparation(generation, uid);
        return;
      }
      if (result is ApiSuccess<HomeFeedPreparation>) {
        _prepareFailures = 0;
        if (result.data.ready) {
          // Keep the compatible history/scroll position for this opening. The next explicit refresh adopts cards.
          preparing = false;
          preparationReady = true;
          if (!unsupported) {
            _reconcileRestarts = 0;
            if (_flight == null) {
              unawaited(reconcileLoadedWindow());
            } else {
              _reconcileRequested = true;
            }
          }
          notifyListeners();
        } else if (result.data.hasMore) {
          _schedulePreparation(generation, uid);
        }
      }
    });
  }

  Future<void> _persist(int generation, String uid) =>
      _cache.write(uid, _items.take(maxCards).toList(), () => _current(generation, uid));
  @override
  void dispose() {
    _disposed = true;
    if (identical(_observedSource?.homeCardSourceChanged, _sourceCallback)) {
      _observedSource?.homeCardSourceChanged = null;
    }
    _prepareTimer?.cancel();
    _generation++;
    super.dispose();
  }
}

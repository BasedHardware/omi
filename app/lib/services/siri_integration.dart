import 'dart:async';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/env/env.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/analytics/registry/events.g.dart' as siri_events;
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Small test seam for the conversation capture path used by Siri's foreground
/// Start/Stop actions. Production resolves these callbacks from CaptureProvider.
typedef SiriListeningCapture = ({
  Future<void> Function() start,
  Future<bool> Function() stop,
  String? Function() source,
  bool Function() deviceConnected,
  bool Function() phoneBatchRecording,
  bool Function() deviceBatchRecording,
});

typedef SiriMemoryPageFetcher = Future<GetMemoriesResult> Function({
  required int limit,
  required int offset,
  String? cursor,
});

/// The native index receives projections only after Dart's authoritative state
/// has accepted a fetch or mutation. All methods are inert on Android.
class SiriIntegration extends SiriEventsApi {
  SiriIntegration._()
      : _host = SiriIndexApi(),
        _isIOS = Platform.isIOS,
        _testSessionConfig = null,
        _testListeningCapture = null,
        _testMemoryPageFetcher = null;

  /// Inject a Pigeon host for hermetic projection and account fencing tests.
  SiriIntegration.forTest(SiriIndexApi host, String uid,
      {SiriSessionConfig Function(User, IdTokenResult, int)? sessionConfig,
      SiriListeningCapture? listeningCapture,
      SiriMemoryPageFetcher? memoryPageFetcher,
      bool coldStart = false})
      : _host = host,
        _isIOS = true,
        _testSessionConfig = sessionConfig,
        _testListeningCapture = listeningCapture,
        _testMemoryPageFetcher = memoryPageFetcher,
        _uid = coldStart ? null : uid,
        _nativeGeneration = coldStart ? null : 0;
  static final instance = SiriIntegration._();
  @visibleForTesting
  static SiriIntegration? testInstance;
  static SiriIntegration get current => testInstance ?? instance;
  final SiriIndexApi _host;
  final bool _isIOS;
  final SiriSessionConfig Function(User, IdTokenResult, int)? _testSessionConfig;
  final SiriListeningCapture? _testListeningCapture;
  final SiriMemoryPageFetcher? _testMemoryPageFetcher;
  void installEvents() {
    if (_isIOS) SiriEventsApi.setUp(this);
  }

  int _accountGeneration = 0;
  int? _nativeGeneration;
  Future<void> _nativeTail = Future<void>.value();
  String? _uid;

  Future<T> _nativeOperation<T>(Future<T> Function() operation) {
    final result = _nativeTail.then((_) => operation());
    _nativeTail = result.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return result;
  }

  Future<void> accountChanged(User? user) async {
    if (!_isIOS) return;
    final generation = ++_accountGeneration;
    final uid = user?.uid;
    if (uid != null && _nativeGeneration == null) {
      try {
        final savedGeneration = await _nativeOperation(() => _host.generationForOwner(uid));
        if (generation != _accountGeneration) return;
        if (savedGeneration != null) {
          _uid = uid;
          _nativeGeneration = savedGeneration;
        }
      } catch (error) {
        Logger.debug('Siri owner resume failed: $error');
        return; // An uncertain owner must not trigger a destructive startup wipe.
      }
    }
    if (uid == null || uid != _uid || _nativeGeneration == null) {
      _uid = null;
      _nativeGeneration = null;
      try {
        final nativeGeneration = await _nativeOperation(_host.wipe);
        if (generation == _accountGeneration) _nativeGeneration = nativeGeneration;
      } catch (error) {
        Logger.debug('Siri wipe failed: $error');
        return; // Never bind another account while the old snapshot remains.
      }
    }
    if (uid == null || generation != _accountGeneration) return;
    _uid = uid;
    await refreshSession(user!);
  }

  Future<void> refreshSession(User user) async {
    if (!_isIOS) return;
    if (user.uid != _uid) {
      await accountChanged(user);
      return;
    }
    final generation = _accountGeneration;
    final nativeGeneration = _nativeGeneration;
    if (nativeGeneration == null) return;
    try {
      final tokenResult = await user.getIdTokenResult();
      final token = tokenResult.token;
      if (generation != _accountGeneration || user.uid != _uid) return;
      final config = _testSessionConfig?.call(user, tokenResult, nativeGeneration) ??
          (() {
            final platform = PlatformManager.instance;
            return SiriSessionConfig(
              uid: user.uid,
              generation: nativeGeneration,
              baseUrl: Env.apiBaseUrl ?? '',
              profile: Env.profile.name,
              appVersion: platform.appVersion,
              appBuild: platform.appBuild,
              deviceIdHash: platform.deviceIdHash,
              token: token,
              tokenExpiresAtMs: tokenResult.expirationTime?.millisecondsSinceEpoch,
            );
          })();
      await _nativeOperation(() async {
        if (generation != _accountGeneration || user.uid != _uid || nativeGeneration != _nativeGeneration) return;
        await _host.publishSessionConfig(config);
      });
      if (generation == _accountGeneration && user.uid == _uid) await _flushTelemetry();
    } catch (error) {
      Logger.debug('Siri session mirror failed: $error');
    }
  }

  Future<void> upsertConversations(List<ServerConversation> rows) async {
    final uid = _uid;
    if (!_isIOS || uid == null) return;
    try {
      await _host.upsertConversations(uid, _conversationProjection(rows));
    } catch (error) {
      Logger.debug('Siri conversation index failed: $error');
    }
  }

  /// The caller proves whether the server response is complete or covers a
  /// newest-page time window. An incremental mutation must use upsert instead.
  Future<void> reconcileConversations(List<ServerConversation> rows, {DateTime? coveredAfter}) async {
    final uid = _uid;
    if (!_isIOS || uid == null) return;
    try {
      await _host.reconcileConversations(uid, _conversationProjection(rows), coveredAfter?.millisecondsSinceEpoch);
    } catch (error) {
      Logger.debug('Siri conversation reconciliation failed: $error');
    }
  }

  List<SiriConversation> _conversationProjection(List<ServerConversation> rows) {
    final cutoff = DateTime.now().subtract(const Duration(days: 180));
    final newest = List<ServerConversation>.of(rows)
      ..sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    return newest
        .where((row) =>
            row.id.isNotEmpty &&
            row.status == ConversationStatus.completed &&
            !row.discarded &&
            !row.deleted &&
            (row.startedAt ?? row.createdAt).isAfter(cutoff))
        .take(2000)
        .map((row) => SiriConversation(
              id: row.id,
              title: row.structured.title,
              summary: row.structured.overview,
              startedAtMs: (row.startedAt ?? row.createdAt).millisecondsSinceEpoch,
              updatedAtMs: (row.finishedAt ?? row.createdAt).millisecondsSinceEpoch,
            ))
        .toList();
  }

  Future<void> upsertMemories(List<Memory> rows) async {
    final uid = _uid;
    if (!_isIOS || uid == null) return;
    try {
      await _host.upsertMemories(uid, _memoryProjection(rows));
    } catch (error) {
      Logger.debug('Siri memory index failed: $error');
    }
  }

  /// Only a complete, owner-wide and unfiltered traversal may call this.
  Future<void> reconcileMemories(List<Memory> rows) async {
    final uid = _uid;
    if (!_isIOS || uid == null) return;
    try {
      await _host.reconcileMemories(uid, _memoryProjection(rows));
    } catch (error) {
      Logger.debug('Siri memory reconciliation failed: $error');
    }
  }

  List<SiriMemory> _memoryProjection(List<Memory> rows) {
    final now = DateTime.now();
    final newest = List<Memory>.of(rows)..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return newest
        .where((row) =>
            row.id.isNotEmpty &&
            !row.deleted &&
            (row.invalidAt == null || row.invalidAt!.isAfter(now)) &&
            (row.ledgerStatus == null || row.ledgerStatus == 'active') &&
            (row.supersededBy == null || row.supersededBy!.isEmpty) &&
            row.userReview != false)
        .take(5000)
        .map((row) => SiriMemory(
              id: row.id,
              content: row.content,
              createdAtMs: row.createdAt.millisecondsSinceEpoch,
              expiresAtMs: row.invalidAt?.millisecondsSinceEpoch,
            ))
        .toList();
  }

  /// The normal Memories view can be useful-now or device filtered. Read the
  /// owner-wide all view separately before removing any absent private item.
  /// A failed, truncated or capped traversal remains additive only.
  Future<void> refreshAuthoritativeMemories() async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    const limit = 100;
    const maxPages = 50;
    final rows = <Memory>[];
    final seen = <String>{};
    var offset = 0;
    String? cursor;
    var complete = false;
    try {
      for (var page = 0; page < maxPages; page++) {
        final result =
            await (_testMemoryPageFetcher?.call(limit: limit, offset: cursor == null ? offset : 0, cursor: cursor) ??
                getMemoriesResult(
                  limit: limit,
                  offset: cursor == null ? offset : 0,
                  cursor: cursor,
                  view: MemoryReadView.all,
                  forceView: true,
                ));
        if (_uid != uid || _accountGeneration != generation) return;
        if (!result.ok || result.truncated) break;
        rows.addAll(result.memories.where((row) => seen.add(row.id)));
        if (result.nextCursor != null) {
          if (result.nextCursor == cursor) break;
          cursor = result.nextCursor;
          continue;
        }
        if (cursor != null || result.memories.length < limit) {
          complete = true;
          break;
        }
        offset += result.memories.length;
      }
    } catch (error) {
      Logger.debug('Siri authoritative memory fetch failed: $error');
      return;
    }
    if (_uid != uid || _accountGeneration != generation) return;
    if (complete) {
      await reconcileMemories(rows);
    } else if (rows.isNotEmpty) {
      await upsertMemories(rows);
    }
  }

  Future<void> upsertTasks(List<ActionItemWithMetadata> rows) async {
    final uid = _uid;
    if (!_isIOS || uid == null) return;
    try {
      await _host.upsertTasks(uid, _taskProjection(rows));
    } catch (error) {
      Logger.debug('Siri task index failed: $error');
    }
  }

  /// Only a completed unfiltered task traversal may call this. An active-only
  /// result cannot remove recent completed tasks from the native snapshot.
  Future<void> reconcileTasks(List<ActionItemWithMetadata> rows, {required bool includeCompleted}) async {
    final uid = _uid;
    if (!_isIOS || uid == null) return;
    try {
      await _host.reconcileTasks(uid, _taskProjection(rows), includeCompleted);
    } catch (error) {
      Logger.debug('Siri task reconciliation failed: $error');
    }
  }

  List<SiriTask> _taskProjection(List<ActionItemWithMetadata> rows) {
    final cutoff = DateTime.now().subtract(const Duration(days: 30));
    return rows
        .where((row) => row.id.isNotEmpty && (!row.completed || (row.completedAt?.isAfter(cutoff) ?? false)))
        .map((row) => SiriTask(
              id: row.id,
              title: row.description,
              completed: row.completed,
              createdAtMs: (row.createdAt ?? DateTime.now()).millisecondsSinceEpoch,
              dueAtMs: row.dueAt?.millisecondsSinceEpoch,
              completedAtMs: row.completedAt?.millisecondsSinceEpoch,
            ))
        .toList();
  }

  Future<void> delete(String type, String id) async {
    final uid = _uid;
    if (!_isIOS || uid == null) return;
    try {
      await _host.deleteEntities(uid, type, [id]);
    } catch (error) {
      Logger.debug('Siri index delete failed: $error');
    }
  }

  Future<bool> isEnabled() async {
    if (!_isIOS) return false;
    return _host.isEnabled();
  }

  Future<void> setEnabled(bool enabled) async {
    if (!_isIOS) return;
    await _host.setEnabled(enabled);
  }

  Future<String?> takePendingRoute() async => _isIOS ? _host.takePendingRoute() : null;

  @override
  void memoryCreated(String id) {
    final context = globalNavigatorKey.currentContext;
    if (context != null) unawaited(context.read<MemoriesProvider>().loadMemories());
  }

  @override
  void taskChanged(String id) {
    final context = globalNavigatorKey.currentContext;
    if (context != null) unawaited(context.read<ActionItemsProvider>().fetchActionItems());
  }

  @override
  Future<bool> openRoute(String route) => HomeNavigation.openRoute(route);

  @override
  Future<void> setListening(bool enabled) async {
    final capture = _testListeningCapture ??
        (() {
          final context = globalNavigatorKey.currentContext;
          if (context == null) throw StateError('Omi is not ready');
          final provider = context.read<CaptureProvider>();
          final device = context.read<DeviceProvider>();
          return (
            start: () async {
              await provider.streamRecording();
            },
            stop: () => provider.stopStreamRecording(),
            source: () => provider.liveCaptureSource,
            deviceConnected: () => device.isConnected,
            phoneBatchRecording: () => provider.isPhoneMicBatchRecording,
            deviceBatchRecording: () => provider.isPendantBatchRecording,
          );
        })();
    if (enabled) {
      if (capture.deviceConnected() &&
          (capture.deviceBatchRecording() || (capture.source() != null && capture.source() != 'phone'))) {
        throw PlatformException(
            code: 'device_already_listening', message: 'Omi is already listening from your device.');
      }
      if (capture.source() == 'phone' || capture.phoneBatchRecording()) return;
      await capture.start();
    } else {
      if (capture.source() != 'phone' && !capture.phoneBatchRecording()) {
        throw StateError('Phone conversation capture is not recording');
      }
      if (!await capture.stop()) throw StateError('Phone conversation capture did not stop');
    }
  }

  Future<void> setCurrentScreen(String route, String? id) async {
    if (_isIOS) await _host.setCurrentScreen(route, id);
  }

  Future<void> donateUiAction(String type, String id) async {
    final uid = _uid;
    if (!_isIOS || uid == null || id.isEmpty) return;
    try {
      await _host.donateAction(uid, type, id);
    } catch (error) {
      Logger.debug('Siri donation failed: $error');
    }
  }

  Future<void> _flushTelemetry() async {
    final rows = await _host.takeTelemetry();
    for (final row in rows) {
      if (row.kind == 'intent') {
        final intents = siri_events.SiriIntentPerformedIntent.values.where((value) => value.name == row.intent);
        if (intents.isEmpty) continue;
        final outcomes = siri_events.SiriIntentPerformedOutcome.values.where((value) => value.name == row.outcome);
        const TypedEvents().emit(siri_events.SiriIntentPerformed(
          intent: intents.first,
          platform: siri_events.SiriIntentPerformedPlatform.ios,
          outcome: outcomes.isEmpty ? siri_events.SiriIntentPerformedOutcome.server : outcomes.first,
          latencyMs: row.latencyMs,
          invokedVia: siri_events.SiriIntentPerformedInvokedVia.unknown,
        ));
      } else if (row.kind == 'index') {
        final outcomes = siri_events.SiriIndexRebuiltOutcome.values.where((value) => value.name == row.outcome);
        const TypedEvents().emit(siri_events.SiriIndexRebuilt(
          platform: siri_events.SiriIndexRebuiltPlatform.ios,
          entityCounts: row.entityCounts,
          durationMs: row.latencyMs,
          outcome: outcomes.isEmpty ? siri_events.SiriIndexRebuiltOutcome.server : outcomes.first,
        ));
      }
    }
  }
}

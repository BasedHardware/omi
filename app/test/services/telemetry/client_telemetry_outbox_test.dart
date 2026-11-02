import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/services/telemetry/client_telemetry_flags.dart';
import 'package:omi/services/telemetry/client_telemetry_outbox.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:shared_preferences/shared_preferences.dart';

String _id(int n) => '00000000-0000-4000-8000-${n.toString().padLeft(12, '0')}';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime now;

  /// controllable monotonic clock: advances with `now` so anchor math works in tests
  int monotonicMs = 0;
  late int ids;
  late MemoryTelemetryStore store;
  late List<Duration> delays;
  late List<({String ownerId, bool forceRefresh, String body})> posts;
  late List<TelemetryHttpResult> script;
  late ClientTelemetry telemetry;

  String currentOwner = 'owner-a';
  String? tokenFor(String ownerId, {bool refresh = false}) => ownerId == currentOwner ? 'token-$ownerId' : null;

  ClientTelemetry build({int maxObservations = 1000, int maxBytes = 1024 * 1024, Random? random}) {
    final outbox = ClientTelemetryOutbox(
      store: store,
      clock: () => now,
      newId: () => _id(++ids),
      tokenFor: (ownerId, {required bool forceRefresh}) async => tokenFor(ownerId, refresh: forceRefresh),
      post: ({required ownerId, required token, required body, required timeout}) async {
        posts.add((ownerId: ownerId, forceRefresh: token.contains('refresh'), body: body));
        if (script.isEmpty) return const TelemetryHttpResult.timeout();
        return script.removeAt(0);
      },
      delay: (duration) async {
        delays.add(duration);
      },
      random: random ?? Random(1),
      maxObservations: maxObservations,
      maxBytes: maxBytes,
    );
    return ClientTelemetry(
      outbox: outbox,
      clock: () => now,
      monotonicElapsedMs: () => monotonicMs,
      newId: () => _id(++ids),
      armFlushTimer: false,
    )
      ..ownerId = (() => currentOwner)
      ..platform = (() => 'ios')
      ..channel = (() => 'production');
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    ClientTelemetryFlags.debugReset();
    ClientTelemetryFlags.migrationEnabledOverride = true;
    now = DateTime.utc(2026, 10, 12, 12);
    monotonicMs = 0;
    ids = 0;
    store = MemoryTelemetryStore();
    delays = [];
    posts = [];
    script = [];
    currentOwner = 'owner-a';
    telemetry = build();
  });

  tearDown(ClientTelemetryFlags.debugReset);

  UploadMirror mirror({
    required String attemptId,
    required String phase,
    required String source,
    int? latencyMs,
    int? httpStatus,
    String? failureClass,
    String? jobId,
  }) =>
      UploadMirror(
        attemptId: attemptId,
        phase: phase,
        source: source,
        occurredAt: now,
        latencyMs: latencyMs,
        httpStatus: httpStatus,
        failureClass: failureClass,
        jobId: jobId,
      );

  Future<void> uploadAttempt({
    required String attemptId,
    required String source,
    String? terminal,
    int? latencyMs,
    int? httpStatus,
    String? failureClass,
    String? jobId,
    DateTime? laterAt,
  }) async {
    telemetry.observeUpload(mirror(attemptId: attemptId, phase: 'started', source: source));
    await telemetry.settled;
    if (terminal == null) return;
    now = now.add(Duration(milliseconds: latencyMs ?? 0));
    telemetry.observeUpload(
      mirror(
        attemptId: attemptId,
        phase: terminal,
        source: source,
        latencyMs: latencyMs,
        httpStatus: httpStatus,
        failureClass: failureClass,
        jobId: jobId,
      ),
    );
    await telemetry.settled;
    if (laterAt != null && jobId != null) {
      now = laterAt;
      telemetry.observeUploadDurableCompleted(jobId: jobId, confirmedAt: now);
      await telemetry.settled;
    }
  }

  test('fixture parity matches legacy upload counts and latency buckets', () async {
    final started = now;
    await uploadAttempt(attemptId: _id(101), source: 'phone', terminal: 'completed', latencyMs: 120, httpStatus: 200);
    await uploadAttempt(
      attemptId: _id(102),
      source: 'pendant',
      terminal: 'accepted',
      latencyMs: 80,
      httpStatus: 202,
      jobId: 'job-done',
    );
    final durableAt = now.subtract(const Duration(milliseconds: 80)).add(const Duration(milliseconds: 5000));
    now = durableAt;
    telemetry.observeUploadDurableCompleted(jobId: 'job-done', confirmedAt: durableAt);
    await telemetry.settled;
    now = started;
    await uploadAttempt(
        attemptId: _id(103),
        source: 'phone',
        terminal: 'accepted',
        latencyMs: 40,
        httpStatus: 202,
        jobId: 'job-pending');
    now = started;
    await uploadAttempt(
      attemptId: _id(104),
      source: 'unknown',
      terminal: 'failed',
      latencyMs: 50,
      httpStatus: 504,
      failureClass: 'timeout',
    );
    now = started;
    await uploadAttempt(attemptId: _id(105), source: 'sdcard', terminal: 'deferred', latencyMs: 30, httpStatus: 429);
    now = started;
    await uploadAttempt(attemptId: _id(106), source: 'phone');

    telemetry.noteProcessingVisible('conv-1');
    now = now.add(const Duration(milliseconds: 1500));
    monotonicMs += 1500;
    telemetry.noteProcessingRowLeft(id: 'conv-1', lifecycleOk: true, lifecycleStatus: 'completed');
    telemetry.noteProcessingVisible('conv-2');
    now = now.add(const Duration(milliseconds: 800));
    monotonicMs += 800;
    telemetry.noteProcessingRowLeft(id: 'conv-2', lifecycleOk: true, lifecycleStatus: 'failed');
    telemetry.noteProcessingVisible('conv-3');
    telemetry.noteProcessingRowLeft(id: 'conv-3', lifecycleOk: true, lifecycleStatus: 'in_progress');
    telemetry.noteProcessingVisible('conv-4');
    telemetry.noteProcessingRowLeft(id: 'conv-4', lifecycleOk: false, lifecycleStatus: null);
    telemetry.noteProcessingRowLeft(id: 'never-visible', lifecycleOk: true, lifecycleStatus: 'completed');
    await telemetry.settled;

    telemetry.observeIngress(
      generation: 'g1',
      phase: 'subscribing',
      reason: 'none',
      subscriptionConfirmed: false,
      recoveryOutcome: 'none',
      recoverySpent: false,
      reconnectSpent: false,
    );
    telemetry.observeIngress(
      generation: 'g1',
      phase: 'subscribing',
      reason: 'none',
      subscriptionConfirmed: false,
      recoveryOutcome: 'none',
      recoverySpent: false,
      reconnectSpent: false,
    );
    telemetry.observeIngress(
      generation: 'g1',
      phase: 'actionRequired',
      reason: 'no_audio',
      subscriptionConfirmed: true,
      recoveryOutcome: 'failed',
      recoverySpent: true,
      reconnectSpent: false,
    );
    telemetry.observeIngress(
      generation: 'g2',
      phase: 'not-a-phase',
      reason: 'not-a-reason',
      subscriptionConfirmed: false,
      recoveryOutcome: 'nope',
      recoverySpent: false,
      reconnectSpent: true,
    );
    telemetry.observeWedge(operationId: _id(201), phase: 'detected', trigger: 'zero_byte_streak', outcome: 'pending');
    telemetry.observeWedge(
      operationId: _id(201),
      phase: 'resolved',
      trigger: 'zero_byte_streak',
      outcome: 'recovered',
      latencyMs: 1000,
    );
    telemetry.observeDeviceSession(
      operationId: _id(301),
      analyticsVendor: 'omi',
      duration: const Duration(milliseconds: 1500),
      reason: 'manual',
      hciReasonCode: 8,
      intentional: true,
    );
    telemetry.observeDeviceSession(
      operationId: _id(302),
      analyticsVendor: 'limitless',
      duration: const Duration(milliseconds: 2000),
      reason: 'remote_device_terminated',
      hciReasonCode: 300,
      intentional: false,
    );
    await telemetry.settled;

    final pending = telemetry.outbox.pending('owner-a');
    final receipt = _receipt(pending,
        disappeared: telemetry.disappearedWithoutTerminal, suppressed: telemetry.ingressDuplicatesSuppressed);
    final fixture = File('test/fixtures/client_telemetry_parity_receipt.txt').readAsStringSync().trim();
    expect(receipt, fixture);
    expect(receipt, contains('canary_acceptance=pending'));
    expect(receipt, contains('http_202_labeled_completed=false'));
    expect(pending.where((observation) => observation.attributes.containsKey('owner_id')), isEmpty);
  });

  test('account swap does not reattribute and logout purges that owner', () async {
    telemetry.observeUpload(mirror(attemptId: _id(1), phase: 'started', source: 'phone'));
    await telemetry.settled;
    currentOwner = 'owner-b';
    telemetry.onOwnerChanged(previous: 'owner-a', next: 'owner-b');
    telemetry.observeUpload(mirror(attemptId: _id(2), phase: 'started', source: 'phone'));
    await telemetry.settled;
    telemetry.outbox.post = ({required ownerId, required token, required body, required timeout}) async {
      posts.add((ownerId: ownerId, forceRefresh: false, body: body));
      final batchId = RegExp(r'"batch_id":"([^"]+)"').firstMatch(body)!.group(1);
      return TelemetryHttpResult.http(
        statusCode: 200,
        body: '{"schema_version":1,"batch_id":"$batchId","accepted_count":1,"duplicate_count":0}',
      );
    };
    telemetry.outbox.flush(onlyOwner: 'owner-b');
    await telemetry.settled;
    expect(posts.single.ownerId, 'owner-b');
    expect(telemetry.outbox.pending('owner-a'), hasLength(1));
    expect(telemetry.outbox.pending('owner-b'), isEmpty);

    currentOwner = '';
    telemetry.onOwnerChanged(previous: 'owner-a', next: null);
    await telemetry.settled;
    expect(telemetry.outbox.pending('owner-a'), isEmpty);
    expect(telemetry.outbox.dropCounts('owner-a')['logout'], 1);
  });

  test('timeout retries, duplicate acknowledgement, and restart keep event ids', () async {
    telemetry.observeUpload(mirror(attemptId: _id(1), phase: 'started', source: 'phone'));
    await telemetry.settled;
    final eventId = telemetry.outbox.pending('owner-a').single.eventId;
    var timedOut = false;
    telemetry.outbox.tokenFor = (ownerId, {required bool forceRefresh}) async {
      if (timedOut || ownerId != 'owner-a') return null;
      return 'token-owner-a';
    };
    telemetry.outbox.post = ({required ownerId, required token, required body, required timeout}) async {
      timedOut = true;
      posts.add((ownerId: ownerId, forceRefresh: false, body: body));
      return const TelemetryHttpResult.timeout();
    };
    telemetry.outbox.flush(onlyOwner: 'owner-a');
    await telemetry.settled;
    expect(telemetry.outbox.pending('owner-a').single.attempts, 1);
    expect(telemetry.outbox.pending('owner-a').single.eventId, eventId);

    final restarted = build();
    script.add(
      TelemetryHttpResult.http(
        statusCode: 200,
        body: '{"schema_version":1,"batch_id":"placeholder","accepted_count":0,"duplicate_count":1}',
      ),
    );
    // The restarted outbox mints its own batch id. Replace the scripted body after the first post
    // by answering from the request body instead.
    script.clear();
    restarted.outbox.post = ({required ownerId, required token, required body, required timeout}) async {
      posts.add((ownerId: ownerId, forceRefresh: false, body: body));
      final batchId = RegExp(r'"batch_id":"([^"]+)"').firstMatch(body)!.group(1);
      return TelemetryHttpResult.http(
        statusCode: 200,
        body: '{"schema_version":1,"batch_id":"$batchId","accepted_count":0,"duplicate_count":1}',
      );
    };
    restarted.outbox.flush(onlyOwner: 'owner-a');
    await restarted.settled;
    expect(posts.last.body, contains(eventId));
    expect(restarted.outbox.pending('owner-a'), isEmpty);
  });

  test('401 refreshes the same owner once and a foreign token is not reused', () async {
    telemetry.observeUpload(mirror(attemptId: _id(1), phase: 'started', source: 'phone'));
    await telemetry.settled;
    var refreshes = 0;
    telemetry.outbox.tokenFor = (ownerId, {required bool forceRefresh}) async {
      if (ownerId != 'owner-a') return null;
      if (forceRefresh) refreshes++;
      return forceRefresh ? 'token-owner-a-refreshed' : 'token-owner-a';
    };
    var calls = 0;
    telemetry.outbox.post = ({required ownerId, required token, required body, required timeout}) async {
      calls++;
      posts.add((ownerId: ownerId, forceRefresh: token.endsWith('refreshed'), body: body));
      if (calls == 1) return TelemetryHttpResult.http(statusCode: 401, body: '');
      final batchId = RegExp(r'"batch_id":"([^"]+)"').firstMatch(body)!.group(1);
      return TelemetryHttpResult.http(
        statusCode: 200,
        body: '{"schema_version":1,"batch_id":"$batchId","accepted_count":1,"duplicate_count":0}',
      );
    };
    telemetry.outbox.flush(onlyOwner: 'owner-a');
    await telemetry.settled;
    expect(refreshes, 1);
    expect(posts, hasLength(2));
    expect(posts.last.forceRefresh, isTrue);
    expect(posts.every((post) => post.ownerId == 'owner-a'), isTrue);
    expect(telemetry.outbox.pending('owner-a'), isEmpty);
  });

  test('permanent 409 and exhausted timeouts drop with a visible reason', () async {
    telemetry.observeUpload(mirror(attemptId: _id(1), phase: 'started', source: 'phone'));
    await telemetry.settled;
    script.add(TelemetryHttpResult.http(statusCode: 409, body: ''));
    telemetry.outbox.flush(onlyOwner: 'owner-a');
    await telemetry.settled;
    expect(telemetry.outbox.pending('owner-a'), isEmpty);
    expect(telemetry.outbox.dropCounts('owner-a')['conflict'], 1);

    telemetry.observeUpload(mirror(attemptId: _id(2), phase: 'started', source: 'phone'));
    await telemetry.settled;
    telemetry.outbox.flush(onlyOwner: 'owner-a');
    await telemetry.settled;
    expect(telemetry.outbox.pending('owner-a'), isEmpty);
    expect(telemetry.outbox.dropCounts('owner-a')['attempts_exhausted'], 1);
    expect(delays.length, ClientTelemetrySchema.maxAttempts - 1);
  });

  test('long Retry-After parks inside the TTL and a short one is honored', () async {
    telemetry.observeUpload(mirror(attemptId: _id(1), phase: 'started', source: 'phone'));
    await telemetry.settled;
    script.add(TelemetryHttpResult.http(statusCode: 429, body: '', retryAfterHeader: '10'));
    telemetry.outbox.flush(onlyOwner: 'owner-a');
    await telemetry.settled;
    expect(delays, contains(const Duration(seconds: 10)));

    delays.clear();
    script.add(TelemetryHttpResult.http(statusCode: 429, body: '', retryAfterHeader: '400'));
    telemetry.observeUpload(mirror(attemptId: _id(2), phase: 'started', source: 'phone'));
    await telemetry.settled;
    telemetry.outbox.flush(onlyOwner: 'owner-a');
    await telemetry.settled;
    expect(delays, isEmpty);
    expect(telemetry.outbox.pending('owner-a'), isNotEmpty);
    final parked = telemetry.outbox.pending('owner-a').where((observation) => observation.notBefore != null);
    expect(parked, isNotEmpty);
    final sent = posts.length;
    now = now.add(const Duration(seconds: 30));
    telemetry.outbox.flush(onlyOwner: 'owner-a');
    await telemetry.settled;
    expect(posts, hasLength(sent));
  });

  test('overflow drops the oldest observation and expired rows are explained', () async {
    telemetry = build(maxObservations: 2, maxBytes: 1024 * 1024);
    for (var n = 1; n <= 3; n++) {
      telemetry.observeUpload(mirror(attemptId: _id(n), phase: 'started', source: 'phone'));
    }
    await telemetry.settled;
    expect(telemetry.outbox.pending('owner-a'), hasLength(2));
    expect(telemetry.outbox.dropCounts('owner-a')['overflow_count'], 1);
    expect(telemetry.outbox.pending('owner-a').map((observation) => observation.attributes['attempt_id']),
        isNot(contains(_id(1))));

    now = now.add(const Duration(hours: 25));
    telemetry.observeUpload(mirror(attemptId: _id(4), phase: 'started', source: 'phone'));
    await telemetry.settled;
    expect(telemetry.outbox.dropCounts('owner-a')['expired'], greaterThan(0));
    expect(telemetry.outbox.pending('owner-a').map((observation) => observation.attributes['attempt_id']), [_id(4)]);
  });

  test('byte overflow drops the oldest stored observation', () async {
    telemetry = build(maxBytes: 300);
    telemetry.observeUpload(mirror(attemptId: _id(1), phase: 'started', source: 'phone'));
    telemetry.observeUpload(mirror(attemptId: _id(2), phase: 'started', source: 'phone'));
    await telemetry.settled;
    expect(telemetry.outbox.dropCounts('owner-a')['overflow_bytes'], greaterThan(0));
    expect(telemetry.outbox.pending('owner-a').length, lessThan(2));
  });

  test('202 is accepted and only a later confirmation is completed', () async {
    now = DateTime.utc(2026, 10, 12, 15);
    final gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      fairUseStatusLoader: () async => null,
      attemptIdFactory: () => _id(9),
      clock: () => now,
      clientTelemetry: telemetry,
      uploader: (files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        now = now.add(const Duration(milliseconds: 80));
        return UploadFilesResult.queued('job-202');
      },
      telemetryEmitter: (_, __) {},
    );
    await gate.upload(const [], telemetrySource: 'pendant');
    await telemetry.settled;
    final phases = telemetry.outbox.pending('owner-a').map((observation) => observation.attributes['phase']).toList();
    expect(phases, ['started', 'accepted']);
    expect(phases, isNot(contains('completed')));
    now = now.add(const Duration(milliseconds: 4920));
    telemetry.observeUploadDurableCompleted(jobId: 'job-202', confirmedAt: now);
    await telemetry.settled;
    final completed = telemetry.outbox
        .pending('owner-a')
        .where((observation) => observation.attributes['phase'] == 'completed')
        .single;
    expect(completed.attributes['latency_ms'], 5000);
    expect(completed.attributes['attempt_id'], _id(9));
  });

  test('paced 429 defers and pre-arrival admission emits nothing', () async {
    now = DateTime.utc(2026, 10, 12, 16);
    final events = <String>[];
    final gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      fairUseStatusLoader: () async => null,
      attemptIdFactory: () => _id(8),
      clock: () => now,
      clientTelemetry: telemetry,
      telemetryEmitter: (name, _) => events.add(name),
      uploader: (files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        now = now.add(const Duration(milliseconds: 30));
        throw SyncRateLimitedException(
            kind: SyncRateLimitKind.backendCapacity,
            retryAfterSeconds: 60,
            reasonCode: 'backfill_paced',
            statusCode: 429);
      },
    );
    await expectLater(gate.upload(const [], telemetrySource: 'sdcard'), throwsA(isA<SyncRateLimitedException>()));
    await telemetry.settled;
    expect(events, [RecordingUploadTelemetry.startedEvent]);
    expect(
      telemetry.outbox.pending('owner-a').map((observation) => observation.attributes['phase']),
      ['started', 'deferred'],
    );

    final before = telemetry.outbox.pending('owner-a').length;
    await expectLater(gate.upload(const []), throwsA(isA<SyncRateLimitedException>()));
    await telemetry.settled;
    expect(telemetry.outbox.pending('owner-a'), hasLength(before));
  });

  test('client-visible processing uses the row anchor and ignores disappearance', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed)], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.completed), ok: true),
      isSignedIn: () => true,
    )..clientTelemetry = telemetry;
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));
    now = now.add(const Duration(milliseconds: 1500));
    monotonicMs += 1500;
    await provider.forceRefreshConversations();
    await telemetry.settled;
    final processing = telemetry.outbox
        .pending('owner-a')
        .where((observation) => observation.family == 'conversation_processing')
        .single;
    expect(processing.attributes['outcome'], 'completed');
    expect(processing.attributes['latency_basis'], 'processing_observed');
    expect(processing.attributes['latency_ms'], 1500);

    final disappearing = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async => (item: null, ok: true),
      isSignedIn: () => true,
    )..clientTelemetry = telemetry;
    addTearDown(disappearing.dispose);
    disappearing.addProcessingConversation(_conversation('c2', status: ConversationStatus.processing));
    await disappearing.forceRefreshConversations();
    await telemetry.settled;
    expect(
      telemetry.outbox.pending('owner-a').where((observation) => observation.attributes['outcome'] == 'completed'),
      hasLength(1),
    );
    expect(telemetry.disappearedWithoutTerminal, 1);
  });

  test('one hundred wedge observations flush one batch without an explicit flush', () async {
    final sent = <int>[];
    telemetry.outbox.post = ({required ownerId, required token, required body, required timeout}) async {
      final count = RegExp(r'"event_id"').allMatches(body).length;
      sent.add(count);
      final batchId = RegExp(r'"batch_id":"([^"]+)"').firstMatch(body)!.group(1);
      return TelemetryHttpResult.http(
        statusCode: 200,
        body: '{"schema_version":1,"batch_id":"$batchId","accepted_count":$count,"duplicate_count":0}',
      );
    };
    for (var n = 1; n <= 99; n++) {
      telemetry.observeWedge(
        operationId: _id(3000 + n),
        phase: 'detected',
        trigger: 'zero_bytes',
        outcome: 'pending',
      );
    }
    await telemetry.settled;
    expect(sent, isEmpty);
    expect(telemetry.outbox.pending('owner-a'), hasLength(99));
    telemetry.observeWedge(operationId: _id(3100), phase: 'detected', trigger: 'zero_bytes', outcome: 'pending');
    await telemetry.settled;
    expect(sent, [100]);
    expect(telemetry.outbox.pending('owner-a'), isEmpty);
  });

  test('missing channel is a recorded drop and does not latch the ingress tuple', () async {
    telemetry.channel = () => null;
    telemetry.observeIngress(
      generation: 'g-missing',
      phase: 'flowing',
      reason: 'none',
      subscriptionConfirmed: true,
      recoveryOutcome: 'none',
      recoverySpent: false,
      reconnectSpent: false,
    );
    await telemetry.settled;
    expect(telemetry.outbox.dropCounts('owner-a')['context_unavailable'], 1);
    expect(telemetry.outbox.pending('owner-a'), isEmpty);
    telemetry.channel = () => 'production';
    telemetry.observeIngress(
      generation: 'g-missing',
      phase: 'flowing',
      reason: 'none',
      subscriptionConfirmed: true,
      recoveryOutcome: 'none',
      recoverySpent: false,
      reconnectSpent: false,
    );
    await telemetry.settled;
    expect(telemetry.outbox.pending('owner-a'), hasLength(1));
    expect(telemetry.ingressDuplicatesSuppressed, 0);
  });

  test('file store reloads the same event after a restart', () async {
    final directory = await Directory.systemTemp.createTemp('client-telemetry-outbox');
    addTearDown(() async {
      if (directory.existsSync()) directory.deleteSync(recursive: true);
    });
    final first = ClientTelemetryOutbox(
      store: FileTelemetryStore(() async => directory),
      clock: () => now,
      newId: () => _id(++ids),
    );
    await first.add(
      ClientTelemetryObservation(
        ownerId: 'owner-a',
        eventId: _id(7),
        occurredAt: now,
        platform: 'ios',
        channel: 'production',
        family: 'upload',
        attributes: {'attempt_id': _id(7), 'phase': 'started', 'source': 'phone', 'operation_id': _id(8)},
        enqueuedAt: now,
        attempts: 2,
      ),
    );
    final restarted = ClientTelemetryOutbox(
      store: FileTelemetryStore(() async => directory),
      clock: () => now,
      newId: () => _id(++ids),
    );
    restarted.flush(onlyOwner: 'owner-a');
    await restarted.settled;
    final pending = restarted.pending('owner-a').single;
    expect(pending.eventId, _id(7));
    expect(pending.attempts, 2);
    expect(File('${directory.path}/client_telemetry_outbox.json').existsSync(), isTrue);
    expect(File('${directory.path}/client_telemetry_outbox.json.tmp').existsSync(), isFalse);
  });
}

ServerConversation _conversation(String id, {required ConversationStatus status}) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 10, 12),
      structured: Structured('Title', 'Overview'),
      status: status,
    );

String _receipt(List<ClientTelemetryObservation> pending, {required int disappeared, required int suppressed}) {
  final upload = pending.where((observation) => observation.family == 'upload').toList();
  final byAttempt = <String, List<ClientTelemetryObservation>>{};
  for (final observation in upload) {
    byAttempt.putIfAbsent(observation.attributes['attempt_id'] as String, () => []).add(observation);
  }
  var syncCompleted = 0;
  var laterCompleted = 0;
  var pendingAccepted = 0;
  final requestLatency = <int>[];
  final laterLatency = <int>[];
  for (final observations in byAttempt.values) {
    final phases = observations.map((observation) => observation.attributes['phase']).toSet();
    final accepted = observations.where((observation) => observation.attributes['phase'] == 'accepted');
    final completed = observations.where((observation) => observation.attributes['phase'] == 'completed');
    if (phases.contains('accepted') && phases.contains('completed')) {
      laterCompleted++;
      pendingAccepted += 0;
      requestLatency.add(accepted.single.attributes['latency_ms'] as int);
      laterLatency.add(completed.single.attributes['latency_ms'] as int);
    } else if (phases.contains('completed')) {
      syncCompleted++;
      requestLatency.add(completed.single.attributes['latency_ms'] as int);
    } else if (phases.contains('accepted')) {
      pendingAccepted++;
      requestLatency.add(accepted.single.attributes['latency_ms'] as int);
    } else {
      for (final observation in observations) {
        final latency = observation.attributes['latency_ms'];
        if (latency is int) requestLatency.add(latency);
      }
    }
  }
  int phaseCount(String phase) => upload.where((observation) => observation.attributes['phase'] == phase).length;
  final allLatency = [...requestLatency, ...laterLatency];
  final buckets = ClientTelemetrySchema.histogramBuckets(allLatency);
  String bucket(Object le) => buckets.firstWhere((entry) => entry['le_seconds'] == le)['count'].toString();
  final processing = pending.where((observation) => observation.family == 'conversation_processing').toList();
  final ingress = pending.where((observation) => observation.family == 'capture_ingress').toList();
  final wedge = pending.where((observation) => observation.family == 'capture_wedge').toList();
  final sessions = pending.where((observation) => observation.family == 'device_session').toList();
  final conservation = phaseCount('started') ==
      syncCompleted +
          phaseCount('accepted') +
          phaseCount('failed') +
          phaseCount('deferred') +
          byAttempt.values
              .where((observations) => observations.length == 1 && observations.single.attributes['phase'] == 'started')
              .length;
  final labeled202 = upload.any(
    (observation) => observation.attributes['phase'] == 'completed' && observation.attributes['http_status'] == 202,
  );
  return [
    'client_telemetry_parity_receipt schema=1',
    'canary_acceptance=pending',
    'migration_flag_default=off',
    'posthog_retirement_flag_default=off',
    'upload_started=${phaseCount('started')}',
    'upload_request_completed=$syncCompleted',
    'upload_accepted=${phaseCount('accepted')}',
    'upload_failed=${phaseCount('failed')}',
    'upload_deferred=${phaseCount('deferred')}',
    'upload_unresolved=${byAttempt.values.where((observations) => observations.length == 1 && observations.single.attributes['phase'] == 'started').length}',
    'upload_accepted_completed=$laterCompleted',
    'upload_pending_accepted=$pendingAccepted',
    'conservation_ok=$conservation',
    'legacy_posthog_started=6',
    'legacy_posthog_completed=3',
    'legacy_posthog_failed=1',
    'legacy_completed_equals_sync_completed_plus_accepted=${syncCompleted + phaseCount('accepted') == 3}',
    'legacy_failed_equals_failed=${phaseCount('failed') == 1}',
    'upload_request_terminal_latency_count=${requestLatency.length}',
    'upload_request_terminal_latency_sum_ms=${requestLatency.fold<int>(0, (sum, value) => sum + value)}',
    'upload_later_completed_latency_count=${laterLatency.length}',
    'upload_later_completed_latency_sum_ms=${laterLatency.fold<int>(0, (sum, value) => sum + value)}',
    'upload_latency_count=${allLatency.length}',
    'upload_latency_sum_ms=${allLatency.fold<int>(0, (sum, value) => sum + value)}',
    'bucket_le_0.05=${bucket(0.05)}',
    'bucket_le_0.1=${bucket(0.1)}',
    'bucket_le_0.25=${bucket(0.25)}',
    'bucket_le_0.5=${bucket(0.5)}',
    'bucket_le_1=${bucket(1)}',
    'bucket_le_2=${bucket(2)}',
    'bucket_le_5=${bucket(5)}',
    'bucket_le_10=${bucket(10)}',
    'bucket_le_30=${bucket(30)}',
    'bucket_le_60=${bucket(60)}',
    'bucket_le_120=${bucket(120)}',
    'bucket_le_300=${bucket(300)}',
    'bucket_le_900=${bucket(900)}',
    'bucket_le_3600=${bucket(3600)}',
    'bucket_le_86400=${bucket(86400)}',
    'bucket_le_inf=${bucket('+Inf')}',
    'processing_completed=${processing.where((observation) => observation.attributes['outcome'] == 'completed').length}',
    'processing_failed=${processing.where((observation) => observation.attributes['outcome'] == 'failed').length}',
    'processing_disappeared_without_terminal=$disappeared',
    'processing_latency_sum_ms=${processing.fold<int>(0, (sum, observation) => sum + (observation.attributes['latency_ms'] as int? ?? 0))}',
    'ingress_observations=${ingress.length}',
    'ingress_duplicate_suppressed=$suppressed',
    'ingress_action_required=${ingress.where((observation) => observation.attributes['phase'] == 'action_required').length}',
    'ingress_unknown_phase=${ingress.where((observation) => observation.attributes['phase'] == 'unknown').length}',
    'wedge_detected=${wedge.where((observation) => observation.attributes['phase'] == 'detected').length}',
    'wedge_resolved_recovered=${wedge.where((observation) => observation.attributes['outcome'] == 'recovered').length}',
    'device_session=${sessions.length}',
    'device_session_duration_sum_ms=${sessions.fold<int>(0, (sum, observation) => sum + (observation.attributes['duration_ms'] as int))}',
    'device_session_hci_leaked=${sessions.where((observation) => observation.attributes['hci_reason_code'] == 300).length}',
    'http_202_labeled_completed=$labeled202',
    'collector_deployment=pending',
    'seven_day_canary=pending',
  ].join('\n');
}

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:omi/services/telemetry/client_telemetry_schema.dart';

typedef TelemetryDelay = Future<void> Function(Duration duration);
typedef TelemetryToken = Future<String?> Function(String ownerId, {required bool forceRefresh});
typedef TelemetryPost = Future<TelemetryHttpResult> Function({
  required String ownerId,
  required String token,
  required String body,
  required Duration timeout,
});

class TelemetryHttpResult {
  const TelemetryHttpResult._({
    required this.kind,
    this.statusCode,
    this.retryAfter,
    this.batchId,
    this.ackSchemaVersion,
    this.acceptedCount,
    this.duplicateCount,
  });

  const TelemetryHttpResult.network() : this._(kind: TelemetryHttpKind.network);
  const TelemetryHttpResult.timeout() : this._(kind: TelemetryHttpKind.timeout);

  factory TelemetryHttpResult.http({
    required int statusCode,
    String? body,
    String? retryAfterHeader,
  }) {
    Duration? retryAfter;
    final parsed = int.tryParse(retryAfterHeader?.trim() ?? '');
    if (parsed != null && parsed >= 0) retryAfter = Duration(seconds: parsed);
    if (statusCode == 200 && body != null) {
      try {
        final decoded = jsonDecode(body);
        if (decoded is Map) {
          return TelemetryHttpResult._(
            kind: TelemetryHttpKind.ok,
            statusCode: statusCode,
            batchId: decoded['batch_id'] as String?,
            ackSchemaVersion: decoded['schema_version'] as int?,
            acceptedCount: decoded['accepted_count'] as int?,
            duplicateCount: decoded['duplicate_count'] as int?,
          );
        }
      } catch (_) {}
      return TelemetryHttpResult._(kind: TelemetryHttpKind.retryable, statusCode: statusCode);
    }
    if (statusCode == 408 || statusCode == 429 || statusCode >= 500) {
      return TelemetryHttpResult._(kind: TelemetryHttpKind.retryable, statusCode: statusCode, retryAfter: retryAfter);
    }
    // sol blocker: only a genuine auth rejection (401) may force a token
    // refresh; 403 is an authorization failure a refresh cannot fix.
    if (statusCode == 401) {
      return TelemetryHttpResult._(kind: TelemetryHttpKind.unauthorized, statusCode: statusCode);
    }
    if (statusCode == 403) {
      return TelemetryHttpResult._(kind: TelemetryHttpKind.permanent, statusCode: statusCode);
    }
    if (statusCode == 409) {
      return TelemetryHttpResult._(kind: TelemetryHttpKind.conflict, statusCode: statusCode);
    }
    return TelemetryHttpResult._(kind: TelemetryHttpKind.permanent, statusCode: statusCode);
  }

  final TelemetryHttpKind kind;
  final int? statusCode;
  final Duration? retryAfter;
  final String? batchId;
  /** sol blocker: ack `schema_version`; a mismatched ack is retryable, not success. */
  final int? ackSchemaVersion;
  final int? acceptedCount;
  final int? duplicateCount;
}

enum TelemetryHttpKind { ok, network, timeout, retryable, unauthorized, conflict, permanent }

class AcceptedUploadJob {
  AcceptedUploadJob({
    required this.ownerId,
    required this.attemptId,
    required this.operationId,
    required this.source,
    required this.startedAt,
  });

  final String ownerId;
  final String attemptId;
  final String operationId;
  final String source;
  final DateTime startedAt;

  Map<String, Object?> toJson() => {
        'owner_id': ownerId,
        'attempt_id': attemptId,
        'operation_id': operationId,
        'source': source,
        'started_at': startedAt.toUtc().toIso8601String(),
      };

  static AcceptedUploadJob? fromJson(Map<String, Object?> json) {
    try {
      return AcceptedUploadJob(
        ownerId: json['owner_id'] as String,
        attemptId: json['attempt_id'] as String,
        operationId: json['operation_id'] as String,
        source: json['source'] as String,
        startedAt: DateTime.parse(json['started_at'] as String).toUtc(),
      );
    } catch (_) {
      return null;
    }
  }
}

abstract class ClientTelemetryStore {
  Future<Map<String, dynamic>?> read();
  Future<void> write(Map<String, dynamic> document);
}

class MemoryTelemetryStore implements ClientTelemetryStore {
  Map<String, dynamic>? document;

  @override
  Future<Map<String, dynamic>?> read() async {
    if (document == null) return null;
    return jsonDecode(jsonEncode(document)) as Map<String, dynamic>;
  }

  @override
  Future<void> write(Map<String, dynamic> document) async {
    this.document = jsonDecode(jsonEncode(document)) as Map<String, dynamic>;
  }
}

/// JSON document on local disk. A failed read starts empty; a failed write
/// leaves the in-memory outbox intact for the next persist.
class FileTelemetryStore implements ClientTelemetryStore {
  FileTelemetryStore(this._directory);

  final Future<Directory> Function() _directory;

  Future<File> _file() async {
    final directory = await _directory();
    return File('${directory.path}/client_telemetry_outbox.json');
  }

  @override
  Future<Map<String, dynamic>?> read() async {
    try {
      final file = await _file();
      if (!await file.exists()) return null;
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
    } catch (_) {}
    return null;
  }

  @override
  Future<void> write(Map<String, dynamic> document) async {
    final file = await _file();
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(jsonEncode(document), flush: true);
    await temporary.rename(file.path);
  }
}

/// Per-owner durable outbox. Transport failures stay inside this type.
class ClientTelemetryOutbox {
  ClientTelemetryOutbox({
    required this.store,
    required this.clock,
    required this.newId,
    this.tokenFor,
    this.post,
    TelemetryDelay? delay,
    Random? random,
    this.maxObservations = ClientTelemetrySchema.maxOutboxObservations,
    this.maxBytes = ClientTelemetrySchema.maxOutboxBytes,
  })  : _delay = delay ?? ((duration) => Future<void>.delayed(duration)),
        _random = random ?? Random();

  ClientTelemetryStore store;

  /// Swaps persistence before the first load. A loaded outbox keeps its store
  /// so an in-flight owner is not silently rebound.
  void attachStore(ClientTelemetryStore next) {
    if (_loaded) return;
    store = next;
  }

  final DateTime Function() clock;
  final String Function() newId;
  TelemetryToken? tokenFor;
  TelemetryPost? post;
  final TelemetryDelay _delay;
  final Random _random;
  final int maxObservations;
  final int maxBytes;

  final Map<String, List<ClientTelemetryObservation>> _owners = {};
  final Map<String, Map<String, int>> _drops = {};
  final Map<String, Map<String, AcceptedUploadJob>> _acceptedJobs = {};
  Future<void> _tail = Future<void>.value();
  bool _loaded = false;
  bool _flushing = false;

  /// Completes after work scheduled during an in-flight callback, including the
  /// batch flush a full outbox arms from inside enqueue.
  Future<void> get settled async {
    while (true) {
      final current = _tail;
      await current;
      if (identical(current, _tail)) return;
    }
  }

  void schedule(Future<void> Function() operation) {
    _tail = _tail.then((_) => operation()).catchError((Object _) {});
  }

  Map<String, int> dropCounts(String ownerId) => Map<String, int>.from(_drops[ownerId] ?? const {});

  List<ClientTelemetryObservation> pending(String ownerId) => List<ClientTelemetryObservation>.from(
        _owners[ownerId] ?? const [],
      );

  AcceptedUploadJob? acceptedJob(String jobId) {
    for (final jobs in _acceptedJobs.values) {
      final job = jobs[jobId];
      if (job != null) return job;
    }
    return null;
  }

  void rememberAcceptedJob(String jobId, AcceptedUploadJob job) {
    schedule(() => saveAcceptedJob(jobId, job));
  }

  Future<void> saveAcceptedJob(String jobId, AcceptedUploadJob job) async {
    await _ensureLoaded();
    final jobs = _acceptedJobs.putIfAbsent(job.ownerId, () => {});
    jobs[jobId] = job;
    _trimAcceptedJobs(job.ownerId);
    await _persist();
  }

  Future<void> add(ClientTelemetryObservation observation) async {
    await _ensureLoaded();
    _enqueueNow(observation);
    await _persist();
    _maybeFlushFull(observation.ownerId);
  }

  Future<void> recordDrop(String ownerId, String reason) async {
    await _ensureLoaded();
    _addDrop(ownerId, reason, 1);
    await _persist();
  }

  void completeAcceptedJob({
    required String jobId,
    required ClientTelemetryObservation Function(AcceptedUploadJob job) build,
  }) {
    schedule(() async {
      await _ensureLoaded();
      final job = takeAcceptedJob(jobId);
      if (job == null) return;
      _enqueueNow(build(job));
      await _persist();
      _maybeFlushFull(job.ownerId);
    });
  }

  AcceptedUploadJob? takeAcceptedJob(String jobId) {
    for (final entry in _acceptedJobs.entries) {
      final job = entry.value.remove(jobId);
      if (job != null) return job;
    }
    return null;
  }

  void enqueue(ClientTelemetryObservation observation) {
    schedule(() async {
      await _ensureLoaded();
      _enqueueNow(observation);
      await _persist();
      _maybeFlushFull(observation.ownerId);
    });
  }

  void purgeOwner(String ownerId, {required String reason}) {
    schedule(() async {
      await _ensureLoaded();
      final pending = _owners.remove(ownerId) ?? const <ClientTelemetryObservation>[];
      if (pending.isNotEmpty) _addDrop(ownerId, reason, pending.length);
      _acceptedJobs.remove(ownerId);
      await _persist();
    });
  }

  void flush({String? onlyOwner}) {
    schedule(() => _flush(onlyOwner: onlyOwner));
  }

  /// sol blocker: lets the rearming timer stop only when the outbox is
  /// genuinely empty for the owner (or every owner when null). Mirrors the
  /// last queued state on a completer so the caller can await it.
  Future<bool> hasPending({String? onlyOwner}) {
    final completer = Completer<bool>();
    schedule(() async {
      try {
        await _ensureLoaded();
        final pending = onlyOwner != null
            ? (_owners[onlyOwner] ?? const <ClientTelemetryObservation>[]).isNotEmpty
            : _owners.values.any((observations) => observations.isNotEmpty);
        if (!completer.isCompleted) completer.complete(pending);
      } catch (error) {
        if (!completer.isCompleted) completer.complete(false);
      }
    });
    return completer.future;
  }

  Future<void> _ensureLoaded() async {
    if (_loaded) return;
    _loaded = true;
    final document = await store.read();
    if (document == null) return;
    final owners = document['owners'];
    if (owners is! Map) return;
    owners.forEach((ownerKey, rawOwner) {
      if (rawOwner is! Map) return;
      final ownerId = ownerKey.toString();
      final observations = <ClientTelemetryObservation>[];
      final rawObservations = rawOwner['observations'];
      if (rawObservations is List) {
        for (final raw in rawObservations) {
          if (raw is Map) {
            final parsed = ClientTelemetryObservation.fromJson(Map<String, Object?>.from(raw));
            if (parsed != null) observations.add(parsed);
          }
        }
      }
      _owners[ownerId] = observations;
      final drops = <String, int>{};
      final rawDrops = rawOwner['drops'];
      if (rawDrops is Map) {
        rawDrops.forEach((key, value) {
          if (value is int) drops[key.toString()] = value;
        });
      }
      _drops[ownerId] = drops;
      final jobs = <String, AcceptedUploadJob>{};
      final rawJobs = rawOwner['accepted_jobs'];
      if (rawJobs is Map) {
        rawJobs.forEach((key, value) {
          if (value is Map) {
            final job = AcceptedUploadJob.fromJson(Map<String, Object?>.from(value));
            if (job != null) jobs[key.toString()] = job;
          }
        });
      }
      _acceptedJobs[ownerId] = jobs;
    });
  }

  void _enqueueNow(ClientTelemetryObservation observation) {
    final now = clock().toUtc();
    if (observation.occurredAt.isAfter(now.add(ClientTelemetrySchema.maxFutureSkew))) {
      _addDrop(observation.ownerId, 'future_timestamp', 1);
      return;
    }
    if (now.difference(observation.occurredAt) > ClientTelemetrySchema.maxOutboxAge ||
        now.difference(observation.enqueuedAt) > ClientTelemetrySchema.maxOutboxAge) {
      _addDrop(observation.ownerId, 'expired', 1);
      return;
    }
    if (!_contextValid(observation) || observation.wireBytes > ClientTelemetrySchema.maxObservationBytes) {
      _addDrop(observation.ownerId, 'invalid_observation', 1);
      return;
    }
    final queue = _owners.putIfAbsent(observation.ownerId, () => []);
    queue.add(observation);
    _trim(observation.ownerId, now);
  }

  bool _contextValid(ClientTelemetryObservation observation) {
    if (!ClientTelemetrySchema.platforms.contains(observation.platform)) return false;
    if (!ClientTelemetrySchema.channels.contains(observation.channel)) return false;
    if (!ClientTelemetrySchema.isUuid(observation.eventId)) return false;
    return true;
  }

  void _trim(String ownerId, DateTime now) {
    final queue = _owners[ownerId];
    if (queue == null) return;
    queue.removeWhere((observation) {
      final expired = now.difference(observation.enqueuedAt) > ClientTelemetrySchema.maxOutboxAge ||
          now.difference(observation.occurredAt) > ClientTelemetrySchema.maxOutboxAge;
      if (expired) _addDrop(ownerId, 'expired', 1);
      return expired;
    });
    while (queue.length > maxObservations) {
      queue.removeAt(0);
      _addDrop(ownerId, 'overflow_count', 1);
    }
    while (_ownerBytes(ownerId) > maxBytes && queue.isNotEmpty) {
      queue.removeAt(0);
      _addDrop(ownerId, 'overflow_bytes', 1);
    }
    _trimAcceptedJobs(ownerId);
  }

  void _trimAcceptedJobs(String ownerId) {
    final jobs = _acceptedJobs[ownerId];
    if (jobs == null) return;
    while (jobs.length > maxObservations) {
      jobs.remove(jobs.keys.first);
      _addDrop(ownerId, 'accepted_job_overflow', 1);
    }
  }

  int _ownerBytes(String ownerId) {
    var bytes = 0;
    for (final observation in _owners[ownerId] ?? const <ClientTelemetryObservation>[]) {
      bytes += observation.wireBytes;
    }
    return bytes;
  }

  void _maybeFlushFull(String ownerId) {
    if (tokenFor == null || post == null) return;
    if ((_owners[ownerId]?.length ?? 0) >= ClientTelemetrySchema.maxObservationsPerBatch) {
      flush(onlyOwner: ownerId);
    }
  }

  void _addDrop(String ownerId, String reason, int count) {
    final drops = _drops.putIfAbsent(ownerId, () => {});
    drops[reason] = (drops[reason] ?? 0) + count;
  }

  Future<void> _persist() async {
    final owners = <String, Object?>{};
    final ownerIds = {..._owners.keys, ..._drops.keys, ..._acceptedJobs.keys};
    for (final ownerId in ownerIds) {
      owners[ownerId] = {
        'observations': [for (final observation in _owners[ownerId] ?? const []) observation.toJson()],
        'drops': _drops[ownerId] ?? <String, int>{},
        'accepted_jobs': {
          for (final entry in (_acceptedJobs[ownerId] ?? const <String, AcceptedUploadJob>{}).entries)
            entry.key: entry.value.toJson(),
        },
      };
    }
    await store.write({'schema_version': ClientTelemetrySchema.schemaVersion, 'owners': owners});
  }

  Future<void> _flush({String? onlyOwner}) async {
    if (_flushing) return;
    _flushing = true;
    try {
      await _ensureLoaded();
      final now = clock().toUtc();
      for (final ownerId in _owners.keys.toList()) {
        _trim(ownerId, now);
      }
      final ownerId = onlyOwner;
      if (ownerId == null) return;
      await _flushOwner(ownerId);
      await _persist();
    } finally {
      _flushing = false;
    }
  }

  Future<void> _flushOwner(String ownerId) async {
    final tokenFor = this.tokenFor;
    final post = this.post;
    if (tokenFor == null || post == null) return;
    final queue = _owners[ownerId];
    if (queue == null || queue.isEmpty) return;
    final now = clock().toUtc();
    final ready =
        queue.where((observation) => observation.notBefore == null || !observation.notBefore!.isAfter(now)).toList();
    final batch = <ClientTelemetryObservation>[];
    var bytes = ClientTelemetrySchema.utf8Length('{"schema_version":1,"batch_id":"","observations":[]}');
    for (final observation in ready) {
      if (batch.length >= ClientTelemetrySchema.maxObservationsPerBatch) break;
      final next = bytes + observation.wireBytes + 1;
      if (batch.isNotEmpty && next > ClientTelemetrySchema.maxRequestBytes) break;
      if (observation.wireBytes > ClientTelemetrySchema.maxObservationBytes) {
        queue.remove(observation);
        _addDrop(ownerId, 'invalid_observation', 1);
        continue;
      }
      batch.add(observation);
      bytes = next;
    }
    if (batch.isEmpty) return;
    final batchId = newId();
    final body = ClientTelemetrySchema.canonicalJson({
      'schema_version': ClientTelemetrySchema.schemaVersion,
      'batch_id': batchId,
      'observations': [for (final observation in batch) jsonDecode(observation.wire)],
    });
    if (ClientTelemetrySchema.utf8Length(body) > ClientTelemetrySchema.maxRequestBytes) {
      _addDrop(ownerId, 'invalid_observation', batch.length);
      queue.removeWhere(batch.contains);
      return;
    }

    var refreshed = false;
    var forceRefresh = false;
    while (true) {
      final attempts = batch.fold<int>(0, (maxAttempts, observation) => max(maxAttempts, observation.attempts));
      if (attempts >= ClientTelemetrySchema.maxAttempts) {
        queue.removeWhere(batch.contains);
        _addDrop(ownerId, 'attempts_exhausted', batch.length);
        return;
      }
      final token = await tokenFor(ownerId, forceRefresh: forceRefresh);
      forceRefresh = false;
      if (token == null || token.isEmpty) {
        if (refreshed) {
          queue.removeWhere(batch.contains);
          _addDrop(ownerId, 'unauthorized', batch.length);
          await _persist();
        }
        return;
      }
      // sol blocker: claim the attempt BEFORE the network call. A crash after
      // transmission would otherwise skip the increment and the five-attempt
      // budget would never consume the event.
      for (final observation in batch) {
        observation.attempts += 1;
      }
      await _persist();
      TelemetryHttpResult result;
      try {
        result = await post(ownerId: ownerId, token: token, body: body, timeout: ClientTelemetrySchema.requestTimeout);
      } catch (_) {
        result = const TelemetryHttpResult.network();
      }
      // sol blocker: validate the ack schema version and reject negative
      // counts even when they happen to sum to the batch length.
      final ackValid = result.kind == TelemetryHttpKind.ok &&
          result.ackSchemaVersion == ClientTelemetrySchema.schemaVersion &&
          result.batchId == batchId &&
          result.acceptedCount != null &&
          result.duplicateCount != null &&
          result.acceptedCount! >= 0 &&
          result.duplicateCount! >= 0 &&
          result.acceptedCount! + result.duplicateCount! == batch.length;
      if (ackValid) {
        final sent = batch.map((observation) => observation.eventId).toSet();
        queue.removeWhere((observation) => sent.contains(observation.eventId));
        return;
      }
      if (result.kind == TelemetryHttpKind.ok) {
        // A 200 with a malformed/negative ack is retryable, not a success.
        if (batch.every((observation) => observation.attempts >= ClientTelemetrySchema.maxAttempts)) {
          queue.removeWhere(batch.contains);
          _addDrop(ownerId, 'attempts_exhausted', batch.length);
        }
        return;
      }
      if (result.kind == TelemetryHttpKind.unauthorized) {
        if (refreshed) {
          queue.removeWhere(batch.contains);
          _addDrop(ownerId, 'unauthorized', batch.length);
          return;
        }
        refreshed = true;
        forceRefresh = true;
        continue;
      }
      if (result.kind == TelemetryHttpKind.conflict) {
        queue.removeWhere(batch.contains);
        _addDrop(ownerId, 'conflict', batch.length);
        return;
      }
      if (result.kind == TelemetryHttpKind.permanent) {
        queue.removeWhere(batch.contains);
        _addDrop(ownerId, 'permanent_${result.statusCode ?? '4xx'}', batch.length);
        return;
      }
      final retryAfter = result.retryAfter;
      if (retryAfter != null && retryAfter > ClientTelemetrySchema.maxRetryAfter) {
        final parkUntil = clock().toUtc().add(retryAfter);
        for (final observation in batch) {
          observation.notBefore = parkUntil;
        }
        return;
      }
      if (batch.every((observation) => observation.attempts >= ClientTelemetrySchema.maxAttempts)) {
        queue.removeWhere(batch.contains);
        _addDrop(ownerId, 'attempts_exhausted', batch.length);
        return;
      }
      final capIndex = min(batch.first.attempts - 1, ClientTelemetrySchema.retryDelayCapsMs.length - 1);
      final capMs = ClientTelemetrySchema.retryDelayCapsMs[capIndex < 0 ? 0 : capIndex];
      final jitterMs = (_random.nextDouble() * capMs).floor();
      final retryAfterMs = retryAfter?.inMilliseconds ?? 0;
      final waitMs = max(jitterMs, min(retryAfterMs, ClientTelemetrySchema.maxRetryAfter.inMilliseconds));
      await _delay(Duration(milliseconds: waitMs));
    }
  }
}

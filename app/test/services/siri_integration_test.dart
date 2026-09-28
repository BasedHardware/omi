import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/services/siri_integration.dart';

class RecordingSiriHost extends SiriIndexApi {
  String? owner;
  List<SiriConversation> conversations = [];
  List<SiriMemory> memories = [];
  bool reconciledMemories = false;
  List<SiriTask> tasks = [];
  String? deletedType;
  List<String> deletedIds = [];

  @override
  Future<void> upsertConversations(String uid, List<SiriConversation> rows) async {
    owner = uid;
    conversations = rows;
  }

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> rows) async {
    owner = uid;
    memories = rows;
  }

  @override
  Future<void> reconcileMemories(String uid, List<SiriMemory> rows) async {
    reconciledMemories = true;
    owner = uid;
    memories = rows;
  }

  @override
  Future<void> upsertTasks(String uid, List<SiriTask> rows) async {
    owner = uid;
    tasks = rows;
  }

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async {
    owner = uid;
    deletedType = type;
    deletedIds = ids;
  }
}

class _RaceToken implements IdTokenResult {
  @override
  String? get token => 'fake-token';
  @override
  DateTime? get expirationTime => DateTime.now().add(const Duration(minutes: 5));
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RaceUser implements User {
  @override
  String get uid => 'owner-race';
  @override
  Future<IdTokenResult> getIdTokenResult([bool forceRefresh = false]) async => _RaceToken();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RaceHost extends SiriIndexApi {
  final publishStarted = Completer<void>();
  final releasePublish = Completer<void>();
  String? owner;
  int generation = 0;
  final events = <String>[];

  @override
  Future<void> publishSessionConfig(SiriSessionConfig config) async {
    publishStarted.complete();
    await releasePublish.future;
    events.add('publish');
    owner = config.uid;
  }

  @override
  Future<void> prepareForSignOut() async {
    events.add('pending-wipe');
    owner = null;
  }

  @override
  Future<int> wipe() async {
    owner = null;
    return ++generation;
  }

  @override
  Future<List<SiriTelemetryRecord>> takeTelemetry() async => [];
}

class _ColdOwnerHost extends SiriIndexApi {
  _ColdOwnerHost(this.owner);
  String? owner;
  int generation = 7;
  int wipes = 0;
  int publications = 0;

  @override
  Future<int?> generationForOwner(String uid) async => owner == uid ? generation : null;

  @override
  Future<int> wipe() async {
    wipes++;
    owner = null;
    return ++generation;
  }

  @override
  Future<void> publishSessionConfig(SiriSessionConfig config) async {
    expect(config.generation, generation);
    owner = config.uid;
    publications++;
  }

  @override
  Future<List<SiriTelemetryRecord>> takeTelemetry() async => [];
}

void main() {
  test('iOS reindex callbacks do not bypass the owner-fenced Spotlight queue', () {
    final source = File('ios/Runner/SiriIntegration/SiriEntities.swift').readAsStringSync();
    for (final name in ['ConversationQuery', 'MemoryQuery', 'TaskQuery']) {
      final start = source.indexOf('struct $name: IndexedEntityQuery');
      expect(start, greaterThanOrEqualTo(0), reason: name);
      final end = source.indexOf('\n}', start);
      final query = source.substring(start, end);
      expect(query.contains('CSSearchableIndex(name:'), isFalse, reason: name);
      expect(query.contains('SiriSnapshotStore.shared.reindex'), isTrue, reason: name);
    }
  });
  TestWidgetsFlutterBinding.ensureInitialized();
  final now = DateTime.now();

  test('cold launch with the same owner retains the native index and generation', () async {
    final host = _ColdOwnerHost('owner-race');
    final siri = SiriIntegration.forTest(host, 'owner-race',
        coldStart: true,
        sessionConfig: (user, token, generation) => SiriSessionConfig(
            uid: user.uid,
            generation: generation,
            baseUrl: 'http://127.0.0.1:8977',
            profile: 'local_dev',
            appVersion: 'test',
            appBuild: '0',
            deviceIdHash: 'test',
            token: token.token,
            tokenExpiresAtMs: token.expirationTime?.millisecondsSinceEpoch));

    await siri.accountChanged(_RaceUser());
    expect(host.wipes, 0);
    expect(host.owner, 'owner-race');
    expect(host.publications, 1);
  });

  test('cold launch with a changed owner wipes the prior index before binding', () async {
    final host = _ColdOwnerHost('old-owner');
    final siri = SiriIntegration.forTest(host, 'owner-race',
        coldStart: true,
        sessionConfig: (user, token, generation) => SiriSessionConfig(
            uid: user.uid,
            generation: generation,
            baseUrl: 'http://127.0.0.1:8977',
            profile: 'local_dev',
            appVersion: 'test',
            appBuild: '0',
            deviceIdHash: 'test',
            token: token.token,
            tokenExpiresAtMs: token.expirationTime?.millisecondsSinceEpoch));

    await siri.accountChanged(_RaceUser());
    expect(host.wipes, 1);
    expect(host.owner, 'owner-race');
    expect(host.publications, 1);
  });

  test('Siri Start and Stop use conversation capture and finalize the phone session', () async {
    final calls = <String>[];
    String? source;
    final siri = SiriIntegration.forTest(RecordingSiriHost(), 'owner-capture', listeningCapture: (
      start: () async {
        calls.add('streamRecording');
        source = 'phone';
      },
      stop: () async {
        calls.add('stopStreamRecording');
        source = null;
        return true;
      },
      source: () => source,
      deviceConnected: () => false,
      phoneBatchRecording: () => false,
      deviceBatchRecording: () => false,
      phonePaused: () => false,
    ));

    await siri.setListening(true);
    await siri.setListening(false);
    expect(calls, ['streamRecording', 'stopStreamRecording']);
  });

  test('Siri Start does not report success for paused phone stream or batch capture', () async {
    for (final batch in [false, true]) {
      var starts = 0;
      final siri = SiriIntegration.forTest(RecordingSiriHost(), 'owner-paused', listeningCapture: (
        start: () async {
          starts++;
        },
        stop: () async => true,
        source: () => 'phone',
        deviceConnected: () => false,
        phoneBatchRecording: () => batch,
        deviceBatchRecording: () => false,
        phonePaused: () => true,
      ));
      await expectLater(siri.setListening(true),
          throwsA(isA<PlatformException>().having((error) => error.code, 'code', 'capture_paused')));
      expect(starts, 0);
    }
  });

  test('Siri Start reports an already-streaming BLE device without opening phone capture', () async {
    var phoneStarts = 0;
    final siri = SiriIntegration.forTest(RecordingSiriHost(), 'owner-device', listeningCapture: (
      start: () async {
        phoneStarts++;
      },
      stop: () async => true,
      source: () => 'omi',
      deviceConnected: () => true,
      phoneBatchRecording: () => false,
      deviceBatchRecording: () => false,
      phonePaused: () => false,
    ));

    await expectLater(siri.setListening(true),
        throwsA(isA<PlatformException>().having((error) => error.code, 'code', 'device_already_listening')));
    expect(phoneStarts, 0);
  });

  test('connected idle device does not block phone conversation capture', () async {
    var phoneStarts = 0;
    final siri = SiriIntegration.forTest(RecordingSiriHost(), 'owner-device', listeningCapture: (
      start: () async {
        phoneStarts++;
      },
      stop: () async => true,
      source: () => null,
      deviceConnected: () => true,
      phoneBatchRecording: () => false,
      deviceBatchRecording: () => false,
      phonePaused: () => false,
    ));

    await siri.setListening(true);
    expect(phoneStarts, 1);
  });

  test('Siri Stop reports nothing to stop with a typed listening outcome', () async {
    final siri = SiriIntegration.forTest(RecordingSiriHost(), 'owner-stop', listeningCapture: (
      start: () async {},
      stop: () async => true,
      source: () => null,
      deviceConnected: () => false,
      phoneBatchRecording: () => false,
      deviceBatchRecording: () => false,
      phonePaused: () => false,
    ));
    await expectLater(siri.setListening(false),
        throwsA(isA<PlatformException>().having((error) => error.code, 'code', 'nothing_to_stop')));
  });

  test('sign-out ordered after an in-flight native session publication', () async {
    final host = _RaceHost();
    final siri = SiriIntegration.forTest(host, 'owner-race',
        sessionConfig: (user, token, generation) => SiriSessionConfig(
              uid: user.uid,
              generation: generation,
              baseUrl: 'http://127.0.0.1:8977',
              profile: 'local_dev',
              appVersion: 'test',
              appBuild: '0',
              deviceIdHash: 'test',
              token: token.token,
              tokenExpiresAtMs: token.expirationTime?.millisecondsSinceEpoch,
            ));
    final signingIn = siri.accountChanged(_RaceUser());
    await host.publishStarted.future.timeout(const Duration(seconds: 5));
    final signingOut = siri.accountChanged(null);
    host.releasePublish.complete();
    await Future.wait([signingIn, signingOut]);
    expect(host.owner, isNull);
  });

  test('pre-sign-out marker waits for prior publication and fences its owner', () async {
    final host = _RaceHost();
    final siri = SiriIntegration.forTest(host, 'owner-race',
        sessionConfig: (user, token, generation) => SiriSessionConfig(
            uid: user.uid,
            generation: generation,
            baseUrl: 'http://127.0.0.1:8977',
            profile: 'local_dev',
            appVersion: 'test',
            appBuild: '0',
            deviceIdHash: 'test',
            token: token.token,
            tokenExpiresAtMs: token.expirationTime?.millisecondsSinceEpoch));
    final signingIn = siri.accountChanged(_RaceUser());
    await host.publishStarted.future.timeout(const Duration(seconds: 5));
    final preparing = siri.prepareForSignOut();
    expect(host.events, isEmpty);
    host.releasePublish.complete();
    await Future.wait([signingIn, preparing]);
    expect(host.events, ['publish', 'pending-wipe']);
    expect(host.owner, isNull);
  });

  test('conversation projection sorts newest and excludes old or unfinished rows', () async {
    final host = RecordingSiriHost();
    final siri = SiriIntegration.forTest(host, 'owner-a');
    ServerConversation conversation(String id, int ageDays,
            {ConversationStatus status = ConversationStatus.completed}) =>
        ServerConversation(
          id: id,
          createdAt: now.subtract(Duration(days: ageDays)),
          structured: Structured('Title $id', 'Summary $id'),
          status: status,
        );

    await siri.upsertConversations([
      conversation('older', 10),
      conversation('unfinished', 1, status: ConversationStatus.processing),
      conversation('too-old', 181),
      conversation('newest', 1),
    ]);

    expect(host.owner, 'owner-a');
    expect(host.conversations.map((row) => row.id), ['newest', 'older']);
    expect(host.conversations.first.title, 'Title newest');
    await siri.upsertConversations([conversation('newest', 1, status: ConversationStatus.processing)]);
    expect(host.deletedType, 'conversation');
    expect(host.deletedIds, ['newest']);
  });

  test('memory projection sorts newest and drops expired or deleted rows', () async {
    final host = RecordingSiriHost();
    final siri = SiriIntegration.forTest(host, 'owner-b');
    Memory memory(String id, int ageDays,
            {bool deleted = false,
            DateTime? invalidAt,
            DateTime? expiresAt,
            MemoryLayer? layer = MemoryLayer.longTerm}) =>
        Memory(
          id: id,
          uid: 'owner-b',
          content: 'Content $id',
          category: MemoryCategory.manual,
          createdAt: now.subtract(Duration(days: ageDays)),
          updatedAt: now,
          visibility: MemoryVisibility.private,
          deleted: deleted,
          invalidAt: invalidAt,
          expiresAt: expiresAt,
          layer: layer,
          layerIsExplicit: true,
        );

    await siri.upsertMemories([
      memory('older', 10),
      memory('expired', 2, invalidAt: now.subtract(const Duration(days: 1))),
      memory('compat-expired', 2, expiresAt: now.subtract(const Duration(days: 1))),
      memory('deleted', 1, deleted: true),
      memory('archived', 0, layer: MemoryLayer.archive),
      memory('newest', 0, expiresAt: now.add(const Duration(days: 1)), invalidAt: now.add(const Duration(days: 2))),
    ]);

    expect(host.owner, 'owner-b');
    expect(host.memories.map((row) => row.id), ['newest', 'older']);
    expect(host.memories.first.content, 'Content newest');
    expect(host.memories.first.expiresAtMs, now.add(const Duration(days: 1)).millisecondsSinceEpoch);
    await siri.upsertMemories([memory('newest', 0, layer: MemoryLayer.archive)]);
    expect(host.deletedType, 'memory');
    expect(host.deletedIds, ['newest']);
  });

  test('old-owner memory rows cannot clear the new owner snapshot', () async {
    final host = RecordingSiriHost();
    final siri = SiriIntegration.forTest(host, 'owner-b');
    await siri.reconcileMemories([
      Memory(
        id: 'old-owner-memory',
        uid: 'owner-a',
        content: 'Private',
        category: MemoryCategory.manual,
        createdAt: now,
        updatedAt: now,
        visibility: MemoryVisibility.private,
      )
    ]);
    expect(host.reconciledMemories, isFalse);
  });

  test('task projection keeps active tasks and recent completions with owner UID', () async {
    final host = RecordingSiriHost();
    final siri = SiriIntegration.forTest(host, 'owner-c');
    ActionItemWithMetadata task(String id, bool completed, DateTime? completedAt) => ActionItemWithMetadata(
          id: id,
          description: 'Task $id',
          completed: completed,
          createdAt: now.subtract(const Duration(days: 45)),
          completedAt: completedAt,
        );

    await siri.upsertTasks([
      task('active', false, null),
      task('recent', true, now.subtract(const Duration(days: 1))),
      task('expired', true, now.subtract(const Duration(days: 31))),
    ]);
    expect(host.owner, 'owner-c');
    expect(host.tasks.map((row) => row.id), ['active', 'recent']);
    expect(host.tasks.last.completed, isTrue);

    await siri.upsertTasks([task('active', false, null).copyWith(status: 'cancelled')]);
    expect(host.deletedType, 'task');
    expect(host.deletedIds, ['active']);

    await siri.delete('task', 'active');
    expect(host.owner, 'owner-c');
    expect(host.deletedType, 'task');
    expect(host.deletedIds, ['active']);
  });

  test('Siri eligibility decision table covers every private-state field', () {
    final date = now.subtract(const Duration(days: 1));
    Memory memory({
      bool deleted = false,
      bool dismissed = false,
      bool locked = false,
      bool siriVisibilityValid = true,
      bool? userReview,
      MemoryLayer? layer = MemoryLayer.longTerm,
      bool layerIsExplicit = true,
      DateTime? invalidAt,
      String? ledgerStatus,
      String? supersededBy,
    }) =>
        Memory(
          id: 'memory',
          uid: 'owner',
          content: 'Visible',
          category: MemoryCategory.manual,
          createdAt: date,
          updatedAt: now,
          visibility: MemoryVisibility.private,
          deleted: deleted,
          isDismissed: dismissed,
          isLocked: locked,
          siriVisibilityValid: siriVisibilityValid,
          userReview: userReview,
          layer: layer,
          layerIsExplicit: layerIsExplicit,
          invalidAt: invalidAt,
          ledgerStatus: ledgerStatus,
          supersededBy: supersededBy,
        );
    final memoryCases = <(String, Memory, bool)>[
      ('eligible', memory(), true),
      ('empty id', memory()..id = '', false),
      ('missing tier', memory(layer: null, layerIsExplicit: false), true),
      ('unproven tier', memory(layerIsExplicit: false), true),
      ('deleted', memory(deleted: true), false),
      ('dismissed', memory(dismissed: true), false),
      ('locked', memory(locked: true), false),
      ('rejected', memory(userReview: false), false),
      ('archive', memory(layer: MemoryLayer.archive), false),
      ('expired', memory(invalidAt: date), false),
      ('superseded status', memory(ledgerStatus: 'superseded'), false),
      ('superseded target', memory(supersededBy: 'replacement'), false),
      ('unknown visibility', memory(siriVisibilityValid: false), false),
    ];
    for (final (name, row, expected) in memoryCases) {
      expect(siriMemoryIsIndexable(row, now), expected, reason: name);
    }
    expect(Memory.fromJson(memory(dismissed: true).toJson()).isDismissed, isTrue,
        reason: 'wire dismissal must survive the Dart adapter');

    ServerConversation conversation({
      String id = 'conversation',
      bool deleted = false,
      bool discarded = false,
      bool locked = false,
      bool siriVisibilityValid = true,
      ConversationStatus status = ConversationStatus.completed,
      DateTime? createdAt,
    }) =>
        ServerConversation(
          id: id,
          createdAt: createdAt ?? date,
          structured: Structured('Title', 'Summary'),
          deleted: deleted,
          discarded: discarded,
          isLocked: locked,
          siriVisibilityValid: siriVisibilityValid,
          status: status,
        );
    final conversationCases = <(String, ServerConversation, bool)>[
      ('eligible', conversation(), true),
      ('empty id', conversation(id: ''), false),
      ('deleted', conversation(deleted: true), false),
      ('discarded', conversation(discarded: true), false),
      ('locked', conversation(locked: true), false),
      ('processing', conversation(status: ConversationStatus.processing), false),
      ('aged', conversation(createdAt: now.subtract(const Duration(days: 181))), false),
      ('unknown visibility', conversation(siriVisibilityValid: false), false),
    ];
    for (final (name, row, expected) in conversationCases) {
      expect(siriConversationIsIndexable(row, now), expected, reason: name);
    }

    final malformedMemory = Memory.fromJson({...memory().toJson(), 'visibility': 'future-value'});
    expect(malformedMemory.visibility, MemoryVisibility.public,
        reason: 'ordinary Memories UI keeps its pre-Siri fallback');
    expect(siriMemoryIsIndexable(malformedMemory, now), isFalse);
    final malformedConversation =
        ServerConversation.fromJson({...conversation().toJson(), 'visibility': 'future-value'});
    expect(malformedConversation.visibility, ConversationVisibility.private_,
        reason: 'ordinary Conversations UI keeps its pre-Siri fallback');
    expect(siriConversationIsIndexable(malformedConversation, now), isFalse);

    ActionItemWithMetadata task({
      String id = 'task',
      bool completed = false,
      bool locked = false,
      String status = 'active',
      String? supersededBy,
      DateTime? completedAt,
    }) =>
        ActionItemWithMetadata(
          id: id,
          description: 'Visible',
          createdAt: date,
          completed: completed,
          completedAt: completedAt,
          isLocked: locked,
          status: status,
          supersededBy: supersededBy,
        );
    final taskCases = <(String, ActionItemWithMetadata, bool)>[
      ('eligible', task(), true),
      (
        'omitted status wire default',
        ActionItemWithMetadata.fromJson({
          'id': 'legacy-task',
          'description': 'Legacy task',
          'completed': false,
        }),
        true
      ),
      ('empty id', task(id: ''), false),
      ('locked', task(locked: true), false),
      ('cancelled', task(status: 'cancelled'), false),
      ('unknown status', task(status: 'processing'), false),
      ('superseded', task(supersededBy: 'replacement'), false),
      ('recent completion', task(completed: true, completedAt: date), true),
      ('old completion', task(completed: true, completedAt: now.subtract(const Duration(days: 31))), false),
    ];
    for (final (name, row, expected) in taskCases) {
      expect(siriTaskIsIndexable(row, now), expected, reason: name);
    }
    expect(siriMemoryIsIndexable(memory(), now, owner: 'other-owner'), false, reason: 'account owner');
  });
}

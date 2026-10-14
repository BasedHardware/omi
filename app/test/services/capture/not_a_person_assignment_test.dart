import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';

class _Actions extends NoopCaptureExternalActions {
  int created = 0;
  int assigned = 0;
  @override
  Future<Person?> createPerson(String name) async {
    created++;
    return null;
  }

  @override
  Future<bool> assignSpeaker(String id, List<String> ids, String person, {int? speakerId}) async {
    assigned++;
    return true;
  }
}

class _Ble implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

TranscriptSegment _segment(String id) => TranscriptSegment(
    id: id, text: 'TV', speaker: 'SPEAKER_04', isUser: true, personId: null, start: 0, end: 2, translations: []);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'deviceMuted': true});
    await SharedPreferencesUtil.init();
  });
  test('same-conversation refresh reapplies exclusions to stale speaker labels', () async {
    final controller = CaptureController(
      externalActions: _Actions(),
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async => true,
    );
    addTearDown(() async {
      controller.dispose();
      await controller.lifetime.close();
    });
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1'), _segment('s2')],
      ),
    );
    final staleSnapshot = ServerConversation(
      id: 'c',
      createdAt: DateTime(2026),
      structured: Structured('TV', 'TV'),
      transcriptSegments: [
        // Stale *non-manual* labels (auto/cached) are still re-blanked: the
        // receipt projects exclusions as unlabeled, so any non-manual label
        // for an excluded speaker predates the exclusion.
        _segment('s1')..speakerLabelSource = 'auto',
        _segment('s2')
          ..isUser = false
          ..personId = 'p1'
          ..speakerLabelSource = 'auto',
      ],
    );
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);

    controller.applyInProgressConversation(staleSnapshot);

    expect(controller.segments.map((s) => s.id), ['s1', 's2']);
    for (final segment in controller.segments) {
      expect(segment.isUser, isFalse);
      expect(segment.personId, isNull);
      expect(segment.speakerLabelSource, isNull);
    }
  });

  test('a newer manual positive label survives a same-conversation refresh', () async {
    final controller = CaptureController(
      externalActions: _Actions(),
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async => true,
    );
    addTearDown(() async {
      controller.dispose();
      await controller.lifetime.close();
    });
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1')],
      ),
    );
    // The local exclusion commits, then another client assigns the speaker to
    // a person: the refreshed snapshot carries the newer manual positive.
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);
    final newerPositive = ServerConversation(
      id: 'c',
      createdAt: DateTime(2026),
      structured: Structured('TV', 'TV'),
      transcriptSegments: [
        _segment('s1')
          ..isUser = false
          ..personId = 'p1'
          ..speakerLabelSource = 'manual',
      ],
    );

    controller.applyInProgressConversation(newerPositive);

    expect(controller.segments.single.personId, 'p1');
    expect(controller.segments.single.speakerLabelSource, 'manual');
  });
  test('exclusion clears the cluster, skips person creation, suppresses suggestions and is reversible', () async {
    final actions = _Actions();
    final calls = <List<String>>[];
    var succeeds = true;
    final controller = CaptureController(
      externalActions: actions,
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async {
        expect(id, 'c');
        calls.add(ids);
        return succeeds;
      },
    );
    addTearDown(() async {
      controller.dispose();
      await controller.lifetime.close();
    });
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1'), _segment('s2')],
      ),
    );
    final suggestion = SpeakerLabelSuggestionEvent(speakerId: 4, personId: '', personName: 'Sam', segmentId: 's2');
    controller.suggestionsBySegmentId['s2'] = suggestion;
    succeeds = false;
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isFalse);
    expect(controller.segments.first.isUser, isTrue);
    expect(controller.suggestionsBySegmentId, isNotEmpty);
    succeeds = true;
    for (var i = 0; i < 2; i++) {
      expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);
      expect(controller.segments.every((s) => !s.isUser && s.personId == null && s.speakerLabelSource == null), isTrue);
      expect(controller.suggestionsBySegmentId, isEmpty);
      controller.onMessageEventReceived(suggestion);
      expect(controller.suggestionsBySegmentId, isEmpty);
    }
    expect(calls.every((ids) => ids.length == 2), isTrue);
    expect(actions.created, 0);
    expect(actions.assigned, 0);
    controller.onSegmentReceived([_segment('later')]);
    await Future<void>.delayed(Duration.zero);
    expect(controller.segments.every((s) => !s.isUser && s.personId == null), isTrue);
    for (final person in ['p1', 'user']) {
      expect(
        await controller.assignSpeakerToConversation(4, person, 'Sam', ['s1', 's2'], applyToSpeaker: true),
        isTrue,
      );
      expect(
        controller.segments.every(
          (s) => s.isUser == (person == 'user') && s.personId == (person == 'user' ? null : person),
        ),
        isTrue,
      );
    }
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'next',
        createdAt: DateTime(2026),
        structured: Structured('next', 'next'),
        transcriptSegments: [_segment('s2')..isUser = false],
      ),
    );
    controller.onMessageEventReceived(suggestion);
    expect(controller.suggestionsBySegmentId, isNotEmpty);
  });
  test('a newer manual positive label from the server retires the local exclusion', () async {
    var reconcileSnapshots = <ServerConversation>[];
    late final CaptureController controller;
    controller = CaptureController(
      externalActions: _Actions(),
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async => true,
      inProgressConversationLoader: () async {
        // The authoritative snapshot decides: no queued snapshot means the
        // persisted receipt still projects the exclusion as unlabeled; a
        // queued snapshot models another surface's manual positive having
        // won server-side.
        if (reconcileSnapshots.isEmpty) return;
        controller.applyInProgressConversation(reconcileSnapshots.removeAt(0));
      },
    );
    addTearDown(() async {
      CaptureController.exclusionReconcileDelay = const Duration(milliseconds: 300);
      controller.dispose();
      await controller.lifetime.close();
    });
    CaptureController.exclusionReconcileDelay = Duration.zero;
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1'), _segment('s2')],
      ),
    );
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);
    expect(controller.segments.every((s) => !s.isUser && s.personId == null), isTrue);

    // A manual positive label arrives on the incremental socket path. The
    // socket carries no assignment generation, so the label alone must not
    // retire the exclusion: a stale pre-exclusion label would otherwise
    // resurrect the old identity and re-enable suggestions the backend still
    // rejects. Keep the exclusion; the reconcile refresh finds the persisted
    // receipt still excluding the voice (no queued snapshot) and changes
    // nothing.
    controller.onSegmentReceived([
      _segment('s2')
        ..isUser = false
        ..personId = 'p9'
        ..speakerLabelSource = 'manual',
    ]);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);

    // The exclusion still owns the voice: the stale label is blanked and the
    // suggestion stays suppressed.
    final conflicted = controller.segments.firstWhere((s) => s.id == 's2');
    expect(conflicted.isUser, isFalse);
    expect(conflicted.personId, isNull);
    final suppressedSuggestion =
        SpeakerLabelSuggestionEvent(speakerId: 4, personId: '', personName: 'Sam', segmentId: 's1');
    controller.onMessageEventReceived(suppressedSuggestion);
    expect(controller.suggestionsBySegmentId, isEmpty);

    // Another manual-positive flush arrives; this time the authoritative
    // snapshot carries the newer persisted manual positive, so the exclusion
    // retires and the label survives.
    reconcileSnapshots.add(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [
          _segment('s1')..isUser = false,
          _segment('s2')
            ..isUser = false
            ..personId = 'p9'
            ..speakerLabelSource = 'manual',
        ],
      ),
    );
    controller.onSegmentReceived([
      _segment('s2')
        ..isUser = false
        ..personId = 'p9'
        ..speakerLabelSource = 'manual',
    ]);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    final updated = controller.segments.firstWhere((s) => s.id == 's2');
    expect(updated.personId, 'p9');
    expect(updated.speakerLabelSource, 'manual');

    // The retired exclusion no longer suppresses suggestions for the speaker.
    final suggestion = SpeakerLabelSuggestionEvent(speakerId: 4, personId: '', personName: 'Sam', segmentId: 's1');
    controller.onMessageEventReceived(suggestion);
    expect(controller.suggestionsBySegmentId, isNotEmpty);

    // An automatic label must not retire a fresh exclusion, and never reaches
    // the reconcile path: only a manual positive can query the snapshot.
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);
    controller.onSegmentReceived([
      _segment('s2')
        ..isUser = false
        ..personId = 'p8'
        ..speakerLabelSource = 'auto',
    ]);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    final autoLabeled = controller.segments.firstWhere((s) => s.id == 's2');
    expect(autoLabeled.isUser, isFalse);
    expect(autoLabeled.personId, isNull);
  });

  test('a refresh requested before the exclusion acknowledgement cannot retire it', () async {
    final controller = CaptureController(
      externalActions: _Actions(),
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async => true,
    );
    addTearDown(() async {
      controller.dispose();
      await controller.lifetime.close();
    });
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1')],
      ),
    );
    // The refresh's HTTP request starts *before* the exclusion is
    // acknowledged: its response may still carry the pre-exclusion manual
    // label when it installs later.
    final requestEpoch = controller.debugSnapshotEpoch;
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);
    expect(controller.debugSnapshotEpoch, greaterThan(requestEpoch));

    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [
          _segment('s1')
            ..isUser = false
            ..personId = 'p1'
            ..speakerLabelSource = 'manual',
        ],
      ),
      requestEpoch: requestEpoch,
    );

    // The stale request's snapshot may not resurrect the retired label: the
    // exclusion survives and re-blanks it.
    final segment = controller.segments.single;
    expect(segment.isUser, isFalse);
    expect(segment.personId, isNull);
    expect(segment.speakerLabelSource, isNull);
    final suggestion = SpeakerLabelSuggestionEvent(speakerId: 4, personId: '', personName: 'Sam', segmentId: 's1');
    controller.onMessageEventReceived(suggestion);
    expect(controller.suggestionsBySegmentId, isEmpty);
  });

  test('a session change during the reconcile delay cancels the refresh install', () async {
    var loads = 0;
    late final CaptureController controller;
    final owner = CaptureSessionOwner(
      coordinator: RecordingTransferCoordinator(
        reconcile: () async {},
        discover: () async {},
        refreshPending: () async {},
        drain: () async => const RecordingTransferDrainResult.skipped(),
        autoUploadEnabled: () => false,
      ),
      startForeground: () async {},
      stopForeground: () async {},
    );
    controller = CaptureController(
      externalActions: _Actions(),
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async => true,
      sessionOwner: owner,
      inProgressConversationLoader: () async {
        loads++;
      },
    );
    addTearDown(() async {
      CaptureController.exclusionReconcileDelay = const Duration(milliseconds: 300);
      controller.dispose();
      await controller.lifetime.close();
    });
    CaptureController.exclusionReconcileDelay = Duration.zero;
    controller.testSessionStartSeconds = 1000; // an active capture session
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1')],
      ),
    );
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);

    // A manual-positive socket flush schedules the reconcile refresh, then
    // the capture recording is replaced before the delay elapses.
    controller.onSegmentReceived([
      _segment('s1')
        ..isUser = false
        ..personId = 'p1'
        ..speakerLabelSource = 'manual',
    ]);
    owner.replaceSession('next-recording'); // per-recording identity rolled
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);

    // The cancelled reconcile must not have run its load.
    expect(loads, 0);
  });

  test('a sequential phone-mic restart with an unchanged activeCaptureSessionId still fences the reconcile', () async {
    // Regression for the per-recording-identity fence: activeCaptureSessionId
    // is documented to stay identical across sequential phone-mic captures,
    // so the old session-id fence could install the previous capture's
    // snapshot into the new session. The owner token must differ.
    var loads = 0;
    late final CaptureController controller;
    final owner = CaptureSessionOwner(
      coordinator: RecordingTransferCoordinator(
        reconcile: () async {},
        discover: () async {},
        refreshPending: () async {},
        drain: () async => const RecordingTransferDrainResult.skipped(),
        autoUploadEnabled: () => false,
      ),
      startForeground: () async {},
      stopForeground: () async {},
    );
    controller = CaptureController(
      externalActions: _Actions(),
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async => true,
      sessionOwner: owner,
      inProgressConversationLoader: () async {
        loads++;
      },
    );
    addTearDown(() async {
      CaptureController.exclusionReconcileDelay = const Duration(milliseconds: 300);
      controller.dispose();
      await controller.lifetime.close();
    });
    CaptureController.exclusionReconcileDelay = Duration.zero;
    controller.testSessionStartSeconds = 1000;
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1')],
      ),
    );
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);

    controller.onSegmentReceived([
      _segment('s1')
        ..isUser = false
        ..personId = 'p1'
        ..speakerLabelSource = 'manual',
    ]);
    // Phone-mic stop/next-start keeps _sessionStartSeconds, so
    // activeCaptureSessionId is unchanged — but the recording rolled.
    expect(controller.activeCaptureSessionId, 'live-1000');
    owner.replaceSession('next-recording');
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(loads, 0);
  });

  test('a conflict arriving mid-refresh queues a follow-up reconcile', () async {
    var loads = 0;
    final gate = Completer<void>();
    late final CaptureController controller;
    controller = CaptureController(
      externalActions: _Actions(),
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async => true,
      inProgressConversationLoader: () async {
        loads++;
        if (loads == 1) await gate.future; // second conflict lands mid-GET
      },
    );
    addTearDown(() async {
      CaptureController.exclusionReconcileDelay = const Duration(milliseconds: 300);
      controller.dispose();
      await controller.lifetime.close();
    });
    CaptureController.exclusionReconcileDelay = Duration.zero;
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1')],
      ),
    );
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);

    // First conflict starts the refresh; its GET is still in flight...
    controller.onSegmentReceived([
      _segment('s1')
        ..isUser = false
        ..personId = 'p1'
        ..speakerLabelSource = 'manual',
    ]);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(loads, 1);

    // ...when a second speaker's conflict arrives and must queue a follow-up.
    controller.onSegmentReceived([
      _segment('s2')
        ..isUser = false
        ..personId = 'p2'
        ..speakerLabelSource = 'manual',
    ]);
    gate.complete();
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    // The queued follow-up ran: the second conflict was not discarded.
    expect(loads, 2);
  });
}

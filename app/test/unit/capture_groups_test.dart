import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/capture_group.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/capture_group_separation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_meta.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/conversations/capture_groups.dart';

final _t0 = DateTime(2026, 9, 23, 13, 57);

CaptureGroup _meeting({String primary = 'desktop'}) => CaptureGroup(
      id: 'event-1',
      primaryId: primary,
      revision: 2,
      members: [
        CaptureGroupMember(
            id: 'desktop', source: 'desktop', startedAt: _t0, finishedAt: _t0.add(const Duration(minutes: 62))),
        CaptureGroupMember(
          id: 'pendant-2',
          source: 'omi',
          startedAt: _t0.add(const Duration(minutes: 31)),
          finishedAt: _t0.add(const Duration(minutes: 34)),
        ),
        CaptureGroupMember(
          id: 'pendant-1',
          source: 'omi',
          startedAt: _t0.add(const Duration(minutes: 2)),
          finishedAt: _t0.add(const Duration(minutes: 30)),
        ),
      ],
    );

ServerConversation _row(String id, {CaptureGroup? group, int minute = 0}) => ServerConversation(
      id: id,
      createdAt: _t0.add(Duration(minutes: minute + 10)),
      startedAt: _t0.add(Duration(minutes: minute)),
      finishedAt: _t0.add(Duration(minutes: minute + 10)),
      structured: Structured(id, ''),
      source: ConversationSource.omi,
      captureGroup: group,
    );

TranscriptSegment _segment(String text, {bool user = false, int speaker = 0, String? personId}) => TranscriptSegment(
      id: text,
      text: text,
      speaker: 'SPEAKER_0$speaker',
      isUser: user,
      personId: personId,
      start: 0,
      end: 1,
      translations: const [],
    );

void main() {
  group('capture group wire', () {
    test('decodes membership and survives the cache round trip', () {
      final json = _row('desktop').toJson()
        ..['capture_group'] = {
          'id': 'event-1',
          'primary_id': 'desktop',
          'revision': 3,
          'members': [
            {'id': 'desktop', 'source': 'desktop', 'started_at': '2026-09-23T20:57:00Z'},
            {'id': 'pendant-1', 'source': 'omi'},
          ],
        };
      final decoded = ServerConversation.fromJson(json);
      expect(decoded.captureGroup!.primaryId, 'desktop');
      expect(decoded.captureGroup!.revision, 3);
      expect(decoded.captureGroup!.members.map((m) => m.source), ['desktop', 'omi']);
      expect(
          decoded.captureGroup!.members.first.startedAt!.isAtSameMomentAs(DateTime.utc(2026, 9, 23, 20, 57)), isTrue);

      final cached = ServerConversation.fromJson(decoded.toJson());
      expect(cached.captureGroup!.members.map((m) => m.id), ['desktop', 'pendant-1']);
      expect(ServerConversation.fromJson(_row('solo').toJson()).captureGroup, isNull);
    });
  });

  group('collapse (one row per recorded event)', () {
    test('the loaded primary represents its group, in list order', () {
      final rows = [
        _row('pendant-2', group: _meeting()),
        _row('other'),
        _row('desktop', group: _meeting()),
        _row('pendant-1', group: _meeting()),
      ];
      expect(CaptureGroupPresentation.collapse(rows).map((c) => c.id), ['other', 'desktop']);
      expect(CaptureGroupPresentation.collapsedAwayIds(rows), {'pendant-1', 'pendant-2'});
    });

    test('an unloaded primary falls back to the first loaded member', () {
      final rows = [_row('pendant-1', group: _meeting()), _row('pendant-2', group: _meeting())];
      expect(CaptureGroupPresentation.collapse(rows).map((c) => c.id), ['pendant-1']);
    });

    test('a lone loaded member is never hidden', () {
      final rows = [_row('pendant-1', group: _meeting()), _row('other')];
      expect(CaptureGroupPresentation.collapse(rows).map((c) => c.id), ['pendant-1', 'other']);
      expect(CaptureGroupPresentation.collapsedAwayIds(rows), isEmpty);
    });

    test('distinct sources follow server member order', () {
      expect(CaptureGroupPresentation.distinctSources(_row('desktop', group: _meeting())), ['desktop', 'omi']);
      expect(CaptureGroupPresentation.distinctSources(_row('solo')), isEmpty);
    });
  });

  group('recordings of one event', () {
    test('lists every member in start order and marks the open one', () {
      final recordings = CaptureGroupPresentation.recordings(_row('pendant-1', group: _meeting()));
      expect(recordings.map((r) => r.id), ['desktop', 'pendant-1', 'pendant-2']);
      expect(recordings.where((r) => r.isCurrent).map((r) => r.id), ['pendant-1']);
    });

    test('a membership that has not caught up still lists the open conversation', () {
      const group = CaptureGroup(id: 'e', primaryId: 'desktop', members: [CaptureGroupMember(id: 'desktop')]);
      final recordings = CaptureGroupPresentation.recordings(_row('late', group: group));
      expect(recordings.map((r) => r.id), containsAll(['desktop', 'late']));
      expect(recordings.singleWhere((r) => r.isCurrent).id, 'late');
    });

    test('a group of one is just a conversation', () {
      const group = CaptureGroup(id: 'e', primaryId: 'solo', members: [CaptureGroupMember(id: 'solo')]);
      expect(CaptureGroupPresentation.recordings(_row('solo', group: group)), isEmpty);
      expect(CaptureGroupPresentation.recordings(_row('solo')), isEmpty);
    });

    test('opening a member prefers the loaded row and fetches otherwise', () async {
      final fetched = <String>[];
      Future<ServerConversation?> fetch(String id) async {
        fetched.add(id);
        return _row(id);
      }

      final loaded = [_row('pendant-1', group: _meeting())];
      expect(await CaptureGroupPresentation.resolveMember('pendant-1', loaded: loaded, fetch: fetch), same(loaded[0]));
      expect(
          (await CaptureGroupPresentation.resolveMember('pendant-2', loaded: loaded, fetch: fetch))!.id, 'pendant-2');
      expect(fetched, ['pendant-2']);
    });
  });

  group('header people summary', () {
    test('names the first two, then how many more', () {
      expect(ConversationDetailMeta.peopleSummary(['You']), 'You');
      expect(ConversationDetailMeta.peopleSummary(['You', 'Dana']), 'You, Dana');
      expect(ConversationDetailMeta.peopleSummary(['You', 'Dana', 'Speaker 2', 'Speaker 3']), 'You, Dana +2');
      expect(ConversationDetailMeta.peopleSummary(const []), '');
    });

    test('participants put the owner first, then first appearance, by name when known', () {
      final people = ConversationDetailMeta.participants(
        [
          _segment('a', speaker: 2),
          _segment('b', user: true),
          _segment('c', speaker: 1, personId: 'p-dana'),
          _segment('d', speaker: 2),
          _segment('e', speaker: 3, personId: 'p-unknown'),
        ],
        you: 'You',
        speaker: (id) => 'Speaker ${id + 1}',
        personName: (id) => id == 'p-dana' ? 'Dana' : null,
      );
      expect(people, ['You', 'Speaker 3', 'Dana', 'Speaker 4']);
    });
  });

  group('separation flow', () {
    test('success reloads, then returns to idle', () async {
      final calls = <String>[];
      final controller = CaptureGroupSeparationController(separate: (id) async {
        calls.add('separate $id');
        return CaptureGroupSeparationResult.separated;
      });
      addTearDown(controller.dispose);
      final phases = <CaptureGroupSeparationPhase>[];
      controller.addListener(() => phases.add(controller.phase));

      final ok = await controller.separate('pendant-2', reload: () async => calls.add('reload'));

      expect(ok, isTrue);
      expect(calls, ['separate pendant-2', 'reload']);
      expect(phases, [CaptureGroupSeparationPhase.separating, CaptureGroupSeparationPhase.idle]);
    });

    test('an already-separated recording still reloads the stale membership', () async {
      var reloaded = false;
      final controller =
          CaptureGroupSeparationController(separate: (_) async => CaptureGroupSeparationResult.unchanged);
      addTearDown(controller.dispose);
      expect(await controller.separate('x', reload: () async => reloaded = true), isTrue);
      expect(reloaded, isTrue);
    });

    test('failure keeps the membership, reports which recording, and never reloads', () async {
      var reloaded = false;
      final controller = CaptureGroupSeparationController(separate: (_) async => CaptureGroupSeparationResult.failed);
      addTearDown(controller.dispose);

      expect(await controller.separate('pendant-2', reload: () async => reloaded = true), isFalse);
      expect(reloaded, isFalse);
      expect(controller.phase, CaptureGroupSeparationPhase.failed);
      expect(controller.recordingId, 'pendant-2');

      controller.reset();
      expect(controller.phase, CaptureGroupSeparationPhase.idle);
    });

    test('one separation at a time', () async {
      final gate = <Future<void>>[];
      final controller = CaptureGroupSeparationController(separate: (_) async {
        await Future<void>.delayed(const Duration(milliseconds: 5));
        return CaptureGroupSeparationResult.separated;
      });
      addTearDown(controller.dispose);
      gate.add(controller.separate('a', reload: () async {}));
      expect(controller.isBusy, isTrue);
      expect(await controller.separate('b', reload: () async {}), isFalse);
      await Future.wait(gate);
      expect(controller.isBusy, isFalse);
    });
  });

  group('conversation list', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('shows one row per event and keeps every server row loaded', () async {
      final provider = ConversationProvider(
        conversationListFetcher: () async => (
          items: [
            _row('pendant-2', group: _meeting(), minute: 31),
            _row('desktop', group: _meeting()),
            _row('pendant-1', group: _meeting(), minute: 2),
            _row('other', minute: 90),
          ],
          ok: true,
        ),
        isSignedIn: () => true,
      );
      addTearDown(provider.dispose);
      provider.showShortConversations = true;

      await provider.forceRefreshConversations();

      expect(provider.displayedConversations.map((c) => c.id), ['other', 'desktop']);
      expect(provider.conversations, hasLength(4));
      expect(provider.loadedConversationById('pendant-1')?.id, 'pendant-1');
    });

    test('a row hidden behind its event leaves the merge selection', () {
      final provider = ConversationProvider(isSignedIn: () => true);
      addTearDown(provider.dispose);
      provider.showShortConversations = true;
      provider.conversations = [_row('pendant-1', group: _meeting(), minute: 2), _row('other', minute: 90)];
      provider.groupConversationsByDate();
      provider.enterSelectionMode();
      provider.toggleConversationSelection('pendant-1');
      provider.toggleConversationSelection('other');

      // The primary arrives on a later page: pendant-1 now hides behind it.
      provider.conversations = [...provider.conversations, _row('desktop', group: _meeting())];
      provider.groupConversationsByDate();

      expect(provider.displayedConversations.map((c) => c.id), ['other', 'desktop']);
      expect(provider.selectedConversationIds, {'other'});
    });
  });
}

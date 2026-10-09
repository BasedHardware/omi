import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/services/proactivity/proactivity_outbox.dart';

GeneratedProactivityFeedItem feedItem({
  String id = 'item-1',
  String producer = 'future_producer',
  String feedback = 'none',
}) =>
    GeneratedProactivityFeedItem(
      id: id,
      producer: producer,
      title: 'Revisit Your Commitment',
      body: 'Your saved task is ready to revisit.',
      createdAt: '2026-10-03T09:00:00Z',
      acted: false,
      dismissed: false,
      feedback: feedback,
      target: const GeneratedProactivityTarget(kind: 'action_item', id: 'task-1'),
    );

GeneratedProactivityFeedResponse feedResponse({
  bool enabled = true,
  List<GeneratedProactivityFeedItem> items = const [],
  bool hasMore = false,
  String nextCursor = '',
}) =>
    GeneratedProactivityFeedResponse(
      enabled: enabled,
      items: items,
      hasMore: hasMore,
      nextCursor: nextCursor,
      serverTime: '2026-10-03T09:01:00Z',
    );

const outcomeSuccess = ApiSuccess(
  GeneratedProactivityOutcomeResponse(itemId: 'item-1', recorded: true, negative: false, acted24h: false),
);

class OutcomeHarness {
  OutcomeHarness({OutcomeSender? send, Duration retryDelay = const Duration(hours: 1)}) {
    outbox = ProactivityOutbox(
      read: () => saved,
      write: (value) async {
        saved = value;
      },
      send: (id, event) async {
        events.add(event);
        return send == null ? outcomeSuccess : await send(id, event);
      },
      surface: () => 'ios',
      ownerIsCurrent: (uid) => uid == owner,
      track: (action, channel, surface) => analytics.add({'action': action, 'channel': channel, 'surface': surface}),
      retryDelay: retryDelay,
    );
  }
  String saved = '';
  String? owner = 'owner-a';
  late final ProactivityOutbox outbox;
  final events = <GeneratedProactivityOutcomeRequest>[];
  final analytics = <Map<String, String>>[];
  Future<void> bind([String? uid = 'owner-a']) async {
    owner = uid;
    await outbox.bindOwner(uid);
  }
}

import 'package:omi/backend/schema/conversation.dart';

/// Each server omission has an exact snapshot held by this client. Keep that
/// snapshot in the local source list so replacing an overlay cannot orphan it.
List<ServerConversation> retainSuppressedHomeMembers(
    List<ServerConversation> returned, Map<String, ServerConversation> held, Iterable<String> suppressedIds) {
  final present = returned.map((c) => c.id).toSet();
  return [
    ...returned,
    for (final id in suppressedIds)
      if (held[id] case final member? when present.add(id)) member,
  ];
}

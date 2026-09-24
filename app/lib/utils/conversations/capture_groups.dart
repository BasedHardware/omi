import 'package:omi/backend/schema/conversation.dart';

/// One device's recording of the event a conversation belongs to.
class CaptureRecording {
  final String id;

  /// Wire source string (`desktop`, `omi`, `phone`, `apple_watch`, ...).
  final String? source;
  final DateTime? startedAt;
  final DateTime? finishedAt;

  /// The recording whose detail is on screen.
  final bool isCurrent;

  const CaptureRecording({
    required this.id,
    required this.source,
    required this.startedAt,
    required this.finishedAt,
    required this.isCurrent,
  });
}

/// One list row per recorded event, and the recordings behind it.
///
/// Mirrors desktop's `CaptureGroupPresentation` (BasedHardware/omi#17281); the
/// shared vectors live in `contracts/parity/capture_group_collapse.json`.
abstract final class CaptureGroupPresentation {
  /// One row per capture group, built only from [conversations] (the rows the
  /// client has loaded and would otherwise show), keeping their order.
  ///
  /// The representative is the member whose id is the group's `primary_id`
  /// when it is loaded, otherwise the first loaded member in list order. A
  /// member whose group has no other loaded member is shown as itself:
  /// grouping may hide a duplicate, never a conversation.
  static List<ServerConversation> collapse(List<ServerConversation> conversations) {
    final representatives = _representativeIds(conversations);
    if (representatives.isEmpty) return conversations;
    return conversations.where((conversation) {
      final groupId = conversation.captureGroup?.id;
      final representative = groupId == null ? null : representatives[groupId];
      return representative == null || representative == conversation.id;
    }).toList();
  }

  /// Ids in [conversations] that [collapse] hides behind their event's row.
  static Set<String> collapsedAwayIds(List<ServerConversation> conversations) {
    final shown = collapse(conversations).map((conversation) => conversation.id).toSet();
    return conversations.map((conversation) => conversation.id).where((id) => !shown.contains(id)).toSet();
  }

  /// Group id -> the member shown for it, for groups with two or more loaded members.
  static Map<String, String> _representativeIds(List<ServerConversation> conversations) {
    final loaded = <String, List<ServerConversation>>{};
    for (final conversation in conversations) {
      final groupId = conversation.captureGroup?.id;
      if (groupId != null) (loaded[groupId] ??= []).add(conversation);
    }
    final result = <String, String>{};
    for (final entry in loaded.entries) {
      final members = entry.value;
      if (members.length < 2) continue;
      final primary = members.where((member) => member.id == member.captureGroup?.primaryId).firstOrNull;
      result[entry.key] = (primary ?? members.first).id;
    }
    return result;
  }

  /// Distinct wire sources that recorded [conversation]'s event, in the order
  /// the server lists members. Empty when no other device recorded it.
  static List<String> distinctSources(ServerConversation conversation) {
    final seen = <String>[];
    for (final member in conversation.captureGroup?.members ?? const []) {
      final source = member.source ?? 'unknown';
      if (!seen.contains(source)) seen.add(source);
    }
    return seen;
  }

  /// The recordings to list on [conversation]'s detail, in the order they started.
  ///
  /// Empty unless the event has another recording: a group of one is just a
  /// conversation. Built from the server's membership rather than the loaded
  /// list, so a member the list has not paged in is still listed.
  static List<CaptureRecording> recordings(ServerConversation conversation) {
    final group = conversation.captureGroup;
    if (group == null) return const [];
    final seen = <String>{};
    final recordings = <CaptureRecording>[
      for (final member in group.members)
        if (seen.add(member.id))
          CaptureRecording(
            id: member.id,
            source: member.source,
            startedAt: member.startedAt,
            finishedAt: member.finishedAt,
            isCurrent: member.id == conversation.id,
          ),
    ];
    // A membership that has not caught up with this conversation still lists it.
    if (!seen.contains(conversation.id)) {
      recordings.add(CaptureRecording(
        id: conversation.id,
        source: conversation.source?.name,
        startedAt: conversation.startedAt,
        finishedAt: conversation.finishedAt,
        isCurrent: true,
      ));
    }
    if (recordings.length < 2) return const [];
    recordings.sort((a, b) {
      final left = a.startedAt;
      final right = b.startedAt;
      if (left != null && right != null && left != right) return left.compareTo(right);
      if (left == null && right != null) return 1;
      if (left != null && right == null) return -1;
      return a.id.compareTo(b.id);
    });
    return recordings;
  }

  /// Opens a member by id: the loaded row when the client has it, otherwise a fetch.
  static Future<ServerConversation?> resolveMember(
    String id, {
    required Iterable<ServerConversation> loaded,
    required Future<ServerConversation?> Function(String id) fetch,
  }) async {
    for (final conversation in loaded) {
      if (conversation.id == id) return conversation;
    }
    return fetch(id);
  }
}

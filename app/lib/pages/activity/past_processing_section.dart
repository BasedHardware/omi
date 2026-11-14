import 'package:clock/clock.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Merge the filter-independent server view with loaded Home rows. A newer
/// finished conversation wins over a stale pending snapshot immediately.
List<ServerConversation> pastProcessingConversations({
  required List<PendingWorkItem> pending,
  required Iterable<ServerConversation> conversations,
  List<Episode> episodes = const [],
  Set<String> attentionIds = const {},
  DateTime? now,
}) {
  final today = localHomeDay(now ?? clock.now());
  final byId = <String, ServerConversation>{};
  for (final item in pending) {
    if (item.kind != 'conversation' || item.startedAt == null) continue;
    for (final id in item.conversationIds) {
      byId[id] = ServerConversation(
        id: id,
        createdAt: item.startedAt!,
        startedAt: item.startedAt,
        structured: Structured('', ''),
        homeStep: item.homeStep ?? (item.state != 'summarizing' ? 'transcribing' : 'writing_notes'),
      );
    }
  }
  for (final conversation in conversations) {
    byId[conversation.id] = conversation;
  }
  // An episode can still owe its composed notes after every member finished.
  // Use Home's own projection so hiding that older row never strands its links.
  final rows = buildHomeRows(byId.values.toList(), episodes,
      enabled: episodes.isNotEmpty, groupAwaitingTranscript: true, now: now);
  for (final row in rows) {
    if (!row.isProcessing || !row.day.isBefore(today) || row.episode == null) continue;
    final members = row.episode!.members.isNotEmpty
        ? row.episode!.members
        : [
            for (final id in row.episodeConversationIds)
              if (byId[id] != null) byId[id]!
          ];
    for (final member in members) {
      if (member.deleted || member.discarded || member.isLocked) continue;
      byId[member.id] = ServerConversation(
        id: member.id,
        createdAt: member.createdAt,
        startedAt: member.startedAt,
        structured: member.structured,
        homeStep: row.step == HomeStep.transcribing ? 'transcribing' : 'writing_notes',
      );
    }
  }
  return byId.values.where((c) {
    final step = homeStepOf(c);
    return !attentionIds.contains(c.id) &&
        (step == HomeStep.transcribing || step == HomeStep.writingNotes) &&
        localHomeDay(c.startedAt ?? c.createdAt).isBefore(today);
  }).toList()
    ..sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
}

/// Projected failures (including an expired Home wait) have no ledger item yet.
/// Loaded rows override pending/episode snapshots; ledger items render once in
/// the existing Needs attention list and keep their keyed retry policy.
List<ServerConversation> failedActivityConversations({
  required List<PendingWorkItem> pending,
  required Iterable<ServerConversation> conversations,
  List<Episode> episodes = const [],
  Set<String> attentionIds = const {},
}) {
  final byId = <String, ServerConversation>{
    for (final item in pending)
      if (item.kind == 'conversation' && item.homeStep == 'failed' && item.startedAt != null)
        for (final id in item.conversationIds)
          id: ServerConversation(
              id: id,
              createdAt: item.startedAt!,
              startedAt: item.startedAt,
              structured: Structured('', ''),
              homeStep: 'failed'),
    for (final episode in episodes)
      for (final member in episode.members) member.id: member,
    for (final c in conversations) c.id: c,
  };
  return byId.values
      .where((c) => !attentionIds.contains(c.id) && !c.deleted && !c.discarded && isFailedHomeConversation(c))
      .toList()
    ..sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
}

/// The bell's Activity page keeps older work reachable until it finishes.
class PastProcessingSection extends StatelessWidget {
  const PastProcessingSection({super.key, required this.conversations, this.openConversation});

  final List<ServerConversation> conversations;
  final Future<void> Function(BuildContext, String)? openConversation;

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty) return const SizedBox.shrink();
    final l = context.l10n;
    final dates = OmiDateFormat.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.md, bottom: OmiSpacing.md),
      child: OmiSettingsGroup(
        key: const Key('activity_past_processing'),
        header: l.wrappedProcessingDefault,
        children: [
          for (final c in conversations)
            OmiSettingsRow(
              key: ValueKey('activity_processing_${c.id}'),
              leading: Icon(Icons.hourglass_empty, color: OmiColors.textSecondary),
              title: homeStepOf(c) == HomeStep.transcribing ? l.homeStepTranscribing : l.episodeWritingNotes,
              subtitle: '${dates.dayHeader((c.startedAt ?? c.createdAt).toLocal())} · '
                  '${dates.time((c.startedAt ?? c.createdAt).toLocal())}',
              onTap: () => (openConversation ?? _open)(context, c.id),
            ),
        ],
      ),
    );
  }

  static Future<void> _open(BuildContext context, String id) => openChatBlockConversation(context, conversationId: id);
}

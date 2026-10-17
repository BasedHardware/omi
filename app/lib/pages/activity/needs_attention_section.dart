import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Work that could not finish, at the top of Activity: conversations the server gave up summarizing
/// (with Try Again) and recordings that could not be processed (opening Offline Sync, which owns
/// their retry). Home never shows these; the bell's warning dot points here.
class NeedsAttentionSection extends StatelessWidget {
  const NeedsAttentionSection({super.key, required this.store, this.syncProvider, this.openConversation});

  final PendingWorkStore store;

  /// Injectable for tests; defaults to the app provider when one is in scope.
  final SyncProvider? syncProvider;

  /// Injectable for tests; defaults to opening the conversation detail page.
  final Future<void> Function(BuildContext context, String conversationId)? openConversation;

  /// Whether the section draws anything for this state.
  static bool hasContent(PendingWorkStore store, SyncProvider? sync) =>
      store.attention.isNotEmpty || _recordingCount(sync) > 0;

  static int _recordingCount(SyncProvider? sync) =>
      sync == null ? 0 : groupRecordingBlocks(SyncPendingWork.attention(sync)).length;

  @override
  Widget build(BuildContext context) {
    final sync = syncProvider ?? context.watch<SyncProvider?>();
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        if (!hasContent(store, sync)) return const SizedBox.shrink();
        final l = context.l10n;
        final dates = OmiDateFormat.of(context);
        final recordings = _recordingCount(sync);
        final retryable = store.attention.where((i) => i.retryable && i.retryState == AttentionRetryState.none);
        return Column(
          key: const Key('activity_needs_attention'),
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.md, 0, OmiSpacing.xxs),
              child: Row(
                children: [
                  Expanded(
                    child: Semantics(
                      header: true,
                      child: Text(
                        l.activityNeedsAttention.toUpperCase(),
                        style: OmiType.footnote
                            .copyWith(fontWeight: FontWeight.w600, color: OmiColors.warning, letterSpacing: 0.4),
                      ),
                    ),
                  ),
                  if (retryable.length > 1)
                    OmiButton.tertiary(
                      key: const Key('activity_retry_all'),
                      label: l.activityRetryAll,
                      onPressed: store.retryAll,
                    ),
                ],
              ),
            ),
            Material(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.xlAll,
              clipBehavior: Clip.antiAlias,
              child: Column(
                children: [
                  for (final (index, item) in store.attention.indexed) ...[
                    if (index > 0) Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
                    _AttentionRow(
                      key: ValueKey('activity_attention_${item.id}'),
                      title: item.title ?? l.attentionSummaryFailed,
                      subtitle: [
                        if (item.title != null) l.attentionSummaryFailed,
                        if (item.startedAt != null) dates.time(item.startedAt!.toLocal()),
                      ].join(' · '),
                      busy: item.retryState == AttentionRetryState.inProgress,
                      onRetry: item.retryable && item.retryState == AttentionRetryState.none
                          ? () => store.retry(item)
                          : null,
                      onTap: item.conversationId == null
                          ? null
                          : () => (openConversation ?? _openConversation)(context, item.conversationId!),
                    ),
                  ],
                  if (recordings > 0) ...[
                    if (store.attention.isNotEmpty)
                      Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
                    _AttentionRow(
                      key: const Key('activity_attention_recordings'),
                      title: l.syncCardNeedsAttention(recordings),
                      subtitle: l.syncDetailsTitle,
                      busy: false,
                      onRetry: null,
                      onTap: () => openOfflineSyncDetails(context, sync!),
                    ),
                  ],
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  static Future<void> _openConversation(BuildContext context, String conversationId) async {
    await openChatBlockConversation(context, conversationId: conversationId);
  }
}

class _AttentionRow extends StatelessWidget {
  const _AttentionRow({
    super.key,
    required this.title,
    required this.subtitle,
    required this.busy,
    required this.onRetry,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final bool busy;
  final VoidCallback? onRetry;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 10, 14),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              alignment: Alignment.center,
              child: Icon(Icons.warning_amber_rounded, size: 18, color: OmiColors.warning),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.body, maxLines: 2, overflow: TextOverflow.ellipsis),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(subtitle, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                  ],
                ],
              ),
            ),
            if (busy)
              const Padding(
                padding: EdgeInsetsDirectional.only(start: OmiSpacing.xs, end: OmiSpacing.xs),
                child: OmiSpinner(size: OmiSpinnerSize.small),
              )
            else if (onRetry != null)
              OmiButton.secondary(
                label: context.l10n.tryAgain,
                onPressed: onRetry,
                size: OmiButtonSize.compact,
              )
            else if (onTap != null)
              Icon(Icons.chevron_right, color: OmiColors.textTertiary),
          ],
        ),
      ),
    );
  }
}

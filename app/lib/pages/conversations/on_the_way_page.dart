import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// Recordings on their way to becoming conversations, opened from Home's
/// pending row. It lists conversations-to-be by how close they are to done;
/// device storage, retries and past syncs stay on the Offline Sync page behind
/// Sync Details.
class OnTheWayPage extends StatelessWidget {
  const OnTheWayPage({super.key, this.syncProvider, this.multiFileSync});

  /// Injectable for tests and the visual audit; defaults to the app provider.
  final SyncProvider? syncProvider;

  /// Injectable Sync Details routing for tests and the visual audit.
  final bool? multiFileSync;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Consumer<SyncProvider>(
      builder: (context, sync, child) {
        final p = syncProvider ?? sync;
        final processing = context.watch<ConversationProvider?>()?.processingConversations ?? const [];
        final almostReady = <_PendingItem>[
          for (final c in processing)
            _PendingItem(
              start: c.startedAt ?? c.createdAt,
              seconds: c.getDurationInSeconds(),
              label: l.processing,
              step: 3,
            ),
          for (final block in groupRecordingBlocks(SyncPendingWork.uploaded(p)))
            _PendingItem.block(block, label: l.transcribing, step: 2),
        ];
        final syncing = [
          for (final block in groupRecordingBlocks(SyncPendingWork.syncing(p)))
            _PendingItem.block(block, label: _syncingLabel(block, l), step: 1),
        ];

        final attentionCount = groupRecordingBlocks(SyncPendingWork.attention(p)).length;
        final Widget body;
        if (almostReady.isEmpty && syncing.isEmpty) {
          body = OmiEmptyState(icon: Icons.check_circle_outline, title: l.allRecordingsSynced);
        } else {
          body = ListView(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
            children: [
              if (almostReady.isNotEmpty) ...[
                _SectionHeader(label: l.onTheWayAlmostReady),
                _Group(items: almostReady),
              ],
              if (syncing.isNotEmpty) ...[
                _SectionHeader(label: l.syncingStatus),
                _Group(items: syncing),
              ],
              const SizedBox(height: OmiSpacing.lg),
              Material(
                key: const Key('on_the_way_sync_details'),
                color: OmiColors.surface1,
                borderRadius: OmiRadius.xlAll,
                child: InkWell(
                  borderRadius: OmiRadius.xlAll,
                  onTap: () => openOfflineSyncDetails(context, p, multiFileSync: multiFileSync),
                  child: Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.md, 14, 10, 14),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(l.syncDetailsTitle, style: OmiType.body),
                              // Refused recordings stay one tap away, never on Home.
                              if (attentionCount > 0) ...[
                                const SizedBox(height: 3),
                                Text(
                                  l.syncCardNeedsAttention(attentionCount),
                                  style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                                ),
                              ],
                            ],
                          ),
                        ),
                        Icon(Icons.chevron_right, color: OmiColors.textTertiary),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        }
        return Scaffold(
          appBar: AppBar(leading: const OmiBackButton(), title: Text(l.onTheWayTitle)),
          body: body,
        );
      },
    );
  }

  static String _syncingLabel(RecordingBlock block, AppLocalizations l) {
    final onDevice = walIsOnDevice(block.representative);
    final moving = block.state == WalSyncDisplayState.syncing;
    if (onDevice) return moving ? l.syncCardDownloadingTitle : l.syncStatusOnDevice;
    return moving ? l.syncCardUploadingTitle : l.syncStatusWaiting;
  }
}

class _PendingItem {
  const _PendingItem({required this.start, required this.seconds, required this.label, required this.step});

  _PendingItem.block(RecordingBlock block, {required this.label, required this.step})
      : start = DateTime.fromMillisecondsSinceEpoch(block.startSeconds * 1000),
        seconds = block.seconds;

  final DateTime start;
  final int seconds;
  final String label;

  /// 1: still syncing, 2: transcribing, 3: writing the conversation.
  final int step;
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.xs),
      child: Semantics(
        header: true,
        child: Text(
          label.toUpperCase(),
          style: OmiType.footnote
              .copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary, letterSpacing: 0.4),
        ),
      ),
    );
  }
}

class _Group extends StatelessWidget {
  const _Group({required this.items});

  final List<_PendingItem> items;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final dates = OmiDateFormat.of(context);
    return Container(
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
      child: Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0) Divider(height: 1, thickness: 1, indent: OmiSpacing.md, color: OmiColors.surface2),
            Semantics(
              label: '${dates.time(items[i].start)}, ${OmiDuration.compact(items[i].seconds, l)}, ${items[i].label}',
              excludeSemantics: true,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            items[i].seconds > 0
                                ? '${dates.time(items[i].start)} · ${OmiDuration.compact(items[i].seconds, l)}'
                                : dates.time(items[i].start),
                            style: OmiType.body,
                          ),
                          const SizedBox(height: 3),
                          Text(items[i].label, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                        ],
                      ),
                    ),
                    _Steps(step: items[i].step),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Three short bars: synced, transcribed, written.
class _Steps extends StatelessWidget {
  const _Steps({required this.step});

  final int step;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 1; i <= 3; i++)
          Container(
            margin: const EdgeInsetsDirectional.only(start: 4),
            width: 14,
            height: 4,
            decoration: BoxDecoration(
              color: i <= step ? OmiColors.accent : OmiColors.surface3,
              borderRadius: OmiRadius.pillAll,
            ),
          ),
      ],
    );
  }
}

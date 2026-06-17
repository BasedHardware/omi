import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/wal_item_detail/wal_item_detail_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// A row in the conversations list for an unsynced local recording (a WAL captured
/// in offline/batch mode). Unlike a conversation it has no title/icon yet — it just
/// shows the recording's time + duration, its sync status, and an inline play/pause
/// button that decodes and plays the local audio on device. Tapping the row opens
/// the WAL detail page (upload, share, etc.).
class RecordingListItem extends StatelessWidget {
  final Wal wal;

  const RecordingListItem({super.key, required this.wal});

  String _formatDuration(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  (Color, String) _status(BuildContext context, bool hasError) {
    final l = context.l10n;
    if (wal.isSyncing) return (Colors.grey.shade300, l.syncStatusBackingUp);
    if (hasError) return (Colors.redAccent, l.failedStatus);
    switch (wal.syncDisplayState) {
      case WalSyncDisplayState.synced:
        return (Colors.grey.shade500, l.syncStatusConversationCreated);
      case WalSyncDisplayState.uploaded:
        return (Colors.grey.shade400, l.syncStatusUploaded);
      case WalSyncDisplayState.retrying:
        return (Colors.orangeAccent, l.syncStatusRetrying);
      case WalSyncDisplayState.failed:
        return (Colors.redAccent, l.syncStatusFailed);
      case WalSyncDisplayState.corrupted:
        return (Colors.redAccent, l.syncStatusFileUnavailable);
      case WalSyncDisplayState.waiting:
      case WalSyncDisplayState.syncing:
        return (Colors.grey.shade500, l.syncStatusWaiting);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, _) {
        final hasError = syncProvider.failedWal?.id == wal.id;
        final (statusColor, statusLabel) = _status(context, hasError);
        final isPlaying = syncProvider.isWalPlaying(wal.id);
        final dt = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000);
        final timeStr = dateTimeFormat('h:mm a', dt, locale: Localizations.localeOf(context).languageCode);

        return Padding(
          padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
          child: Container(
            width: double.maxFinite,
            decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(24.0)),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(24.0),
              child: Dismissible(
                key: ValueKey('rec_${wal.filePath ?? wal.id}'),
                direction: wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  color: Colors.red,
                  padding: const EdgeInsets.only(right: 20),
                  child: const Icon(Icons.delete, color: Colors.white),
                ),
                onDismissed: (_) => syncProvider.deleteWal(wal),
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (context) => WalItemDetailPage(wal: wal)),
                    );
                  },
                  child: Padding(
                    padding: const EdgeInsetsDirectional.symmetric(horizontal: 16, vertical: 18),
                    child: Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: Colors.deepPurple.withValues(alpha: 0.18),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.graphic_eq, color: Colors.deepPurpleAccent, size: 20),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '$timeStr · ${_formatDuration(wal.seconds)}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                              ),
                              const SizedBox(height: 3),
                              Text(
                                statusLabel,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(color: statusColor, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 10),
                        GestureDetector(
                          onTap: () => syncProvider.toggleWalPlayback(wal),
                          child: Container(
                            width: 44,
                            height: 44,
                            decoration: BoxDecoration(
                              color: Colors.deepPurpleAccent.withValues(alpha: 0.15),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              isPlaying ? Icons.pause : Icons.play_arrow,
                              color: Colors.deepPurpleAccent,
                              size: 24,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

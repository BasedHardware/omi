import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/sync_confirmation.dart';
import 'local_storage_page.dart';
import 'private_cloud_sync_page.dart';
import 'synced_conversations_page.dart';
import 'wal_item_detail/wal_item_detail_page.dart';

Widget _buildFaIcon(IconData icon, {double size = 18, Color color = const Color(0xFF8E8E93)}) {
  return Padding(
    padding: const EdgeInsets.only(left: 2, top: 1),
    child: FaIcon(icon, size: size, color: color),
  );
}

class WalListItem extends StatelessWidget {
  final DateTime date;
  final int walIdx;
  final Wal wal;

  const WalListItem({super.key, required this.wal, required this.date, required this.walIdx});

  double _calcProgress(Wal wal) {
    if (!wal.isSyncing || wal.syncStartedAt == null) return 0.0;
    if (wal.storageTotalBytes <= 0) return 0.0;
    return (wal.storageOffset / wal.storageTotalBytes).clamp(0.0, 1.0);
  }

  String _formatEta(int seconds) {
    if (seconds < 60) return '${seconds}s';
    if (seconds < 3600) return '${seconds ~/ 60}m ${seconds % 60}s';
    return '${seconds ~/ 3600}h ${(seconds % 3600) ~/ 60}m';
  }

  String? _sourceLabel(BuildContext context) {
    if (wal.storage == WalStorage.sdcard) return context.l10n.sdCard;
    if (wal.originalStorage == WalStorage.sdcard) return context.l10n.fromSd;
    if (wal.storage == WalStorage.flashPage || wal.originalStorage == WalStorage.flashPage) {
      return context.l10n.limitless;
    }
    return null;
  }

  (Color, String) _rowStatus(BuildContext context, bool hasError) {
    final l = context.l10n;
    if (wal.isSyncing) {
      return (Colors.grey.shade300, l.syncStatusBackingUp);
    }
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

  Widget _trailing(BuildContext context, SyncProvider syncProvider, bool hasError) {
    if (wal.isSyncing) {
      return const SizedBox(
        width: 16,
        height: 16,
        child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent)),
      );
    }
    final st = wal.syncDisplayState;
    if (hasError || st == WalSyncDisplayState.failed || st == WalSyncDisplayState.retrying) {
      return GestureDetector(
        onTap: () => syncProvider.syncWal(wal),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          decoration: BoxDecoration(
            color: Colors.deepPurpleAccent.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(100),
          ),
          child: Text(context.l10n.retry,
              style: const TextStyle(color: Colors.deepPurpleAccent, fontSize: 13, fontWeight: FontWeight.w500)),
        ),
      );
    }
    return FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final hasError = syncProvider.failedWal?.id == wal.id;
        final (statusColor, statusLabel) = _rowStatus(context, hasError);
        final timeStr = dateTimeFormat('h:mm a', DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000));
        final duration = secondsToHumanReadable(wal.seconds, context);
        final source = _sourceLabel(context);
        final showBar = wal.isSyncing &&
            wal.status != WalStatus.synced &&
            wal.syncStartedAt != null &&
            wal.storage != WalStorage.flashPage;

        return Container(
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
          child: Dismissible(
            key: Key(wal.id),
            direction: wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
            confirmDismiss: (direction) {
              final uploading = wal.syncDisplayState == WalSyncDisplayState.uploaded;
              return OmiConfirmDialog.show(
                context,
                title: uploading ? context.l10n.deleteWhileProcessingTitle : context.l10n.deleteRecording,
                message: uploading ? context.l10n.deleteWhileProcessingMessage : context.l10n.thisCannotBeUndone,
                confirmLabel: context.l10n.delete,
                confirmColor: Colors.red,
              );
            },
            background: Container(
              alignment: Alignment.centerRight,
              padding: const EdgeInsets.only(right: 20.0),
              color: Colors.red,
              child: const Icon(Icons.delete, color: Colors.white),
            ),
            onDismissed: (direction) {
              ServiceManager.instance().wal.getSyncs().deleteWal(wal);
            },
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {
                Navigator.of(context).push(MaterialPageRoute(builder: (context) => WalItemDetailPage(wal: wal)));
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                source != null ? '$timeStr · $duration · $source' : '$timeStr · $duration',
                                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
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
                        _trailing(context, syncProvider, hasError),
                      ],
                    ),
                    if (showBar) ...[
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(2),
                              child: LinearProgressIndicator(
                                value: _calcProgress(wal),
                                backgroundColor: const Color(0xFF3C3C43),
                                color: Colors.deepPurpleAccent,
                                minHeight: 3,
                              ),
                            ),
                          ),
                          if (wal.syncSpeedKBps != null && wal.syncSpeedKBps! > 0) ...[
                            const SizedBox(width: 12),
                            Text('${wal.syncSpeedKBps!.toStringAsFixed(1)} KB/s',
                                style: TextStyle(color: Colors.grey.shade500, fontSize: 11)),
                          ],
                        ],
                      ),
                      if (wal.syncEtaSeconds != null && wal.syncEtaSeconds! > 0) ...[
                        const SizedBox(height: 4),
                        Text(context.l10n.etaLabel(_formatEta(wal.syncEtaSeconds!)),
                            style: TextStyle(color: Colors.grey.shade600, fontSize: 11)),
                      ],
                    ],
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class SyncPage extends StatefulWidget {
  const SyncPage({super.key});

  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<SyncProvider>().refreshWals();
    });
  }

  Widget _buildSettingsItem({
    required IconData icon,
    required String title,
    String? status,
    VoidCallback? onTap,
  }) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        child: Row(
          children: [
            FaIcon(icon, color: const Color(0xFF8E8E93), size: 18),
            const SizedBox(width: 14),
            Expanded(
              child:
                  Text(title, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w400)),
            ),
            if (status != null) Text(status, style: TextStyle(color: Colors.grey.shade500, fontSize: 14)),
            const SizedBox(width: 10),
            FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12),
          ],
        ),
      ),
    );
  }

  Widget _buildConversationsCreatedCard(SyncProvider syncProvider) {
    if (!syncProvider.syncCompleted || syncProvider.syncedConversationsPointers.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Container(
        decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
        child: GestureDetector(
          onTap: () => routeToPage(context, const SyncedConversationsPage()),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Row(
              children: [
                SizedBox(width: 24, height: 24, child: _buildFaIcon(FontAwesomeIcons.circleCheck, color: Colors.green)),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    context.l10n.conversationsCreated(syncProvider.syncedConversationsPointers.length),
                    style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                  ),
                ),
                const Icon(Icons.chevron_right, color: Color(0xFF3C3C43), size: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSettingsCard() {
    final isPhoneStorageOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;

    return Container(
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
      child: Column(
        children: [
          Builder(
            builder: (context) {
              return _buildSettingsItem(
                icon: FontAwesomeIcons.mobile,
                title: context.l10n.storeAudioOnPhone,
                status: isPhoneStorageOn ? context.l10n.on : context.l10n.off,
                onTap: () {
                  Navigator.of(context)
                      .push(MaterialPageRoute(builder: (context) => const LocalStoragePage()))
                      .then((_) => setState(() {}));
                },
              );
            },
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43), indent: 52),
          Consumer<UserProvider>(
            builder: (context, userProvider, child) {
              final isCloudOn = userProvider.privateCloudSyncEnabled;
              return _buildSettingsItem(
                icon: FontAwesomeIcons.cloud,
                title: context.l10n.storeAudioOnCloud,
                status: isCloudOn ? context.l10n.on : context.l10n.off,
                onTap: () {
                  Navigator.of(context).push(MaterialPageRoute(builder: (context) => const PrivateCloudSyncPage()));
                },
              );
            },
          ),
        ],
      ),
    );
  }

  void _showCancelSyncDialog(BuildContext context, SyncProvider provider) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.cancelSync,
      message: context.l10n.cancelSyncMessage,
      confirmLabel: context.l10n.cancelSync,
      confirmColor: Colors.orange,
    );
    if (confirmed == true && context.mounted) {
      provider.cancelSync();
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(context.l10n.syncCancelled), backgroundColor: Colors.orange));
    }
  }

  void _showManageStorageSheet(BuildContext context, SyncProvider provider) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _ManageStorageSheet(
        provider: provider,
        onClearSynced: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await OmiConfirmDialog.show(
            context,
            title: context.l10n.deleteSyncedFiles,
            message: context.l10n.deleteSyncedFilesMessage,
            confirmLabel: context.l10n.clear,
            confirmColor: Colors.red,
          );
          if (confirmed == true && context.mounted) {
            await provider.deleteAllSyncedWals();
            if (context.mounted) {
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(SnackBar(content: Text(context.l10n.syncedFilesDeleted), backgroundColor: Colors.green));
            }
          }
        },
        onClearPending: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await OmiConfirmDialog.show(
            context,
            title: context.l10n.deletePendingFiles,
            message: context.l10n.deletePendingFilesWarning,
            confirmLabel: context.l10n.clear,
            confirmColor: Colors.red,
          );
          if (confirmed == true && context.mounted) {
            await provider.deleteAllPendingWals();
            if (context.mounted) {
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(SnackBar(content: Text(context.l10n.pendingFilesDeleted), backgroundColor: Colors.green));
            }
          }
        },
        onClearAll: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await OmiConfirmDialog.show(
            context,
            title: context.l10n.deleteAllFiles,
            message: context.l10n.deleteAllFilesWarning,
            confirmLabel: context.l10n.clearAll,
            confirmColor: Colors.red,
          );
          if (confirmed == true && context.mounted) {
            await provider.deleteAllSyncedWals();
            await provider.deleteAllPendingWals();
            if (context.mounted) {
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(SnackBar(content: Text(context.l10n.allFilesDeleted), backgroundColor: Colors.green));
            }
          }
        },
      ),
    );
  }

  void _handleSyncWals(BuildContext context, SyncProvider syncProvider) async {
    // Custom STT users: offline files are transcribed on Omi and count toward
    // the limit. Confirm before proceeding.
    if (!await confirmSyncForCustomStt(context)) return;
    if (!context.mounted) return;

    final sdCardWals = syncProvider.missingWals.where((wal) => wal.storage == WalStorage.sdcard).toList();

    if (sdCardWals.isNotEmpty) {
      _showSdCardWarningDialog(context, syncProvider, sdCardWals.length);
    } else {
      syncProvider.syncWals();
    }
  }

  String _formatErrorMessage(BuildContext context, String errorMessage) {
    if (errorMessage.startsWith('Exception: ')) {
      errorMessage = errorMessage.substring('Exception: '.length);
    }

    final lowerMessage = errorMessage.toLowerCase();
    if (lowerMessage.contains('timeout') || lowerMessage.contains('did not respond')) {
      return context.l10n.deviceNotResponding;
    }
    return errorMessage;
  }

  void _showSdCardWarningDialog(BuildContext context, SyncProvider syncProvider, int sdCardCount) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Row(
          children: [
            _buildFaIcon(FontAwesomeIcons.sdCard, size: 20, color: Colors.deepPurpleAccent),
            const SizedBox(width: 12),
            Text(context.l10n.sdCardProcessing, style: const TextStyle(color: Colors.white, fontSize: 18)),
          ],
        ),
        content: Text(
          context.l10n.sdCardProcessingMessage(sdCardCount),
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey.shade500)),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              syncProvider.syncWals();
            },
            child: Text(
              context.l10n.process,
              style: const TextStyle(color: Colors.deepPurpleAccent, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProcessCard(SyncProvider syncProvider) {
    final l = context.l10n;
    final s = syncProvider.syncState;

    if (syncProvider.syncError != null && syncProvider.failedWal == null) {
      return _buildSyncErrorCard(syncProvider);
    }

    final isActive = syncProvider.isSyncing;
    final uploaded = syncProvider.uploadedWals.length;
    final readyToSync = syncProvider.missingWals.length;
    final bool showSpinner = (isActive || uploaded > 0) && !syncProvider.isRateLimited;

    String title;
    String? subtitle;
    Color titleColor = Colors.white;
    Widget? action;

    if (isActive) {
      final speed = syncProvider.syncSpeedKBps;
      final speedStr = (speed != null && speed > 0) ? '${speed.toStringAsFixed(1)} KB/s' : null;
      switch (s.phase) {
        case SyncPhase.downloadingFromDevice:
          title = l.syncCardDownloadingTitle;
          subtitle = _progressLine(s, speedStr);
          action = _statusActionPill(l.cancel, Colors.redAccent, () => _showCancelSyncDialog(context, syncProvider));
          break;
        case SyncPhase.uploadingToCloud:
          title = l.syncCardUploadingTitle;
          subtitle = _progressLine(s, null);
          action = _statusActionPill(l.cancel, Colors.redAccent, () => _showCancelSyncDialog(context, syncProvider));
          break;
        case SyncPhase.processingOnServer:
          title = l.syncCardProcessing;
          subtitle = l.syncProcessingBackgroundHint;
          break;
        case SyncPhase.waitingForInternet:
          title = l.syncCardWaitingInternet;
          titleColor = Colors.orangeAccent;
          break;
        case SyncPhase.idle:
          title = l.syncCardUploadingTitle;
          subtitle = _progressLine(s, speedStr);
          if (syncProvider.isSdCardSyncing) {
            action = _statusActionPill(l.cancel, Colors.redAccent, () => _showCancelSyncDialog(context, syncProvider));
          }
          break;
      }
    } else if (syncProvider.isRateLimited) {
      title =
          syncProvider.rateLimitReason == RateLimitReason.backendBusy ? l.syncCardBackendBusy : l.syncCardRateLimited;
      titleColor = Colors.orangeAccent;
    } else if (uploaded > 0) {
      title = l.syncCardProcessing;
      subtitle = l.syncProcessingBackgroundHint;
    } else if (readyToSync > 0) {
      title = l.syncCardReadyCount(readyToSync);
      action = _statusActionPill(l.sync, Colors.deepPurpleAccent, () {
        if (context.read<ConnectivityProvider>().isConnected) {
          _handleSyncWals(context, syncProvider);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(l.internetRequired),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          );
        }
      });
    } else {
      title = l.syncCardAllBackedUp;
      titleColor = Colors.grey.shade400;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          if (showSpinner) ...[
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent),
              ),
            ),
            const SizedBox(width: 12),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: TextStyle(color: titleColor, fontSize: 15, fontWeight: FontWeight.w500, height: 1.25),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 3),
                  Text(subtitle, style: TextStyle(color: Colors.grey.shade500, fontSize: 13)),
                ],
              ],
            ),
          ),
          if (action != null) ...[const SizedBox(width: 10), action],
        ],
      ),
    );
  }

  String? _progressLine(SyncState s, String? speedStr) {
    final cur = s.currentFile ?? 0;
    final tot = s.totalFiles ?? 0;
    final parts = <String>[];
    if (tot > 0) parts.add(context.l10n.syncCardProgressOf(cur, tot));
    if (speedStr != null) parts.add(speedStr);
    return parts.isEmpty ? null : parts.join(' · ');
  }

  Widget _statusActionPill(String label, Color color, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(100)),
        child: Text(label, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w500)),
      ),
    );
  }

  Widget _buildSyncErrorCard(SyncProvider syncProvider) {
    final errorMessage = syncProvider.syncError!;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.red.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          const FaIcon(FontAwesomeIcons.circleExclamation, color: Colors.redAccent, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _formatErrorMessage(context, errorMessage),
              style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          _statusActionPill(context.l10n.retry, Colors.redAccent, () => syncProvider.retrySync()),
        ],
      ),
    );
  }

  Widget _buildStatusChips(SyncProvider syncProvider) {
    Widget chip(WalStatusFilter filter, String label, int count) {
      final selected = syncProvider.statusFilter == filter;
      return Expanded(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => syncProvider.setStatusFilter(filter),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 2),
            padding: const EdgeInsets.symmetric(vertical: 8),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: selected ? Colors.white.withValues(alpha: 0.08) : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              count > 0 ? '$label  $count' : label,
              style: TextStyle(
                color: selected ? Colors.white : Colors.grey.shade500,
                fontSize: 13,
                fontWeight: selected ? FontWeight.w500 : FontWeight.w400,
              ),
            ),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(10)),
      child: Row(
        children: [
          chip(WalStatusFilter.pending, context.l10n.pending, syncProvider.pendingStatusCount),
          chip(WalStatusFilter.synced, context.l10n.synced, syncProvider.syncedStatusCount),
        ],
      ),
    );
  }

  Widget _buildEmptyFilterState(BuildContext context, WalStatusFilter filter) {
    final isPending = filter == WalStatusFilter.pending;
    return Container(
      margin: const EdgeInsets.all(20),
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
      child: Column(
        children: [
          _buildFaIcon(
            isPending ? FontAwesomeIcons.circleCheck : FontAwesomeIcons.clockRotateLeft,
            size: 24,
            color: isPending ? Colors.green : Colors.grey,
          ),
          const SizedBox(height: 16),
          Text(
            isPending ? context.l10n.noPendingRecordings : context.l10n.noProcessedRecordings,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
          ),
          if (isPending) ...[
            const SizedBox(height: 4),
            Text(context.l10n.allCaughtUp, style: TextStyle(color: Colors.grey.shade500, fontSize: 14)),
          ],
        ],
      ),
    );
  }

  Widget _buildPendingList(List<Wal> pendingWals) {
    // Group by source
    final phoneWals = <Wal>[];
    final sdCardWals = <Wal>[];
    final limitlessWals = <Wal>[];

    for (final wal in pendingWals) {
      if (wal.storage == WalStorage.sdcard || wal.originalStorage == WalStorage.sdcard) {
        sdCardWals.add(wal);
      } else if (wal.storage == WalStorage.flashPage || wal.originalStorage == WalStorage.flashPage) {
        limitlessWals.add(wal);
      } else {
        phoneWals.add(wal);
      }
    }

    // If only one source, skip the section headers
    final sourceCount =
        (phoneWals.isNotEmpty ? 1 : 0) + (sdCardWals.isNotEmpty ? 1 : 0) + (limitlessWals.isNotEmpty ? 1 : 0);
    if (sourceCount <= 1) {
      return OptimizedWalsListWidget(wals: pendingWals);
    }

    // Build a single flattened list with source headers interleaved
    final List<_PendingListItem> items = [];
    void addSection(String label, IconData icon, Color color, List<Wal> wals) {
      items.add(_PendingListItem.header(label, icon, color, wals.length));
      for (final wal in wals) {
        items.add(_PendingListItem.wal(wal));
      }
    }

    if (phoneWals.isNotEmpty) addSection(context.l10n.phone, FontAwesomeIcons.mobileScreen, Colors.grey, phoneWals);
    if (sdCardWals.isNotEmpty) {
      addSection(context.l10n.sdCard, FontAwesomeIcons.sdCard, Colors.deepPurpleAccent, sdCardWals);
    }
    if (limitlessWals.isNotEmpty) {
      addSection(context.l10n.limitless, FontAwesomeIcons.bolt, Colors.teal, limitlessWals);
    }

    return SliverList.builder(
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        if (item.isHeader) {
          return Padding(
            padding: EdgeInsets.fromLTRB(20, index == 0 ? 0 : 20, 20, 8),
            child: Row(
              children: [
                _buildFaIcon(item.icon!, size: 14, color: item.color!),
                const SizedBox(width: 8),
                Text(
                  item.label!,
                  style: TextStyle(color: item.color, fontSize: 13, fontWeight: FontWeight.w600),
                ),
                const SizedBox(width: 6),
                Text('${item.count}', style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
              ],
            ),
          );
        }
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
          child: WalListItem(
            wal: item.wal!,
            walIdx: index,
            date: DateTime.fromMillisecondsSinceEpoch(item.wal!.timerStart * 1000),
          ),
        );
      },
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(20),
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(16)),
            child: Center(child: _buildFaIcon(FontAwesomeIcons.microphone, size: 24)),
          ),
          const SizedBox(height: 20),
          Text(
            context.l10n.noRecordings,
            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.audioFromOmiWillAppearHere,
            style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, result) {
        // Sync result persists until next sync starts
      },
      child: Consumer<SyncProvider>(
        builder: (context, syncProvider, child) {
          return Scaffold(
            backgroundColor: const Color(0xFF0D0D0D),
            appBar: AppBar(
              backgroundColor: const Color(0xFF0D0D0D),
              elevation: 0,
              leading: IconButton(
                icon: const Padding(
                  padding: EdgeInsets.only(left: 2, top: 1),
                  child: FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
                ),
                onPressed: () => Navigator.of(context).pop(),
              ),
              title: Text(
                context.l10n.offlineSync,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              centerTitle: true,
              actions: [
                GestureDetector(
                  onTap: () {
                    HapticFeedback.mediumImpact();
                    _showManageStorageSheet(context, syncProvider);
                  },
                  child: Container(
                    width: 36,
                    height: 36,
                    margin: const EdgeInsets.only(right: 8),
                    decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
                    child: Center(
                      child: _buildFaIcon(FontAwesomeIcons.ellipsisVertical, size: 16, color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
            body: CustomScrollView(
              slivers: [
                // Settings + Process card + status chips
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 16),
                        _buildProcessCard(syncProvider),
                        const SizedBox(height: 16),
                        _buildConversationsCreatedCard(syncProvider),
                        _buildSettingsCard(),
                        const SizedBox(height: 16),
                        _buildStatusChips(syncProvider),
                        const SizedBox(height: 16),
                      ],
                    ),
                  ),
                ),
                // Recordings list
                Consumer<SyncProvider>(
                  builder: (context, syncProvider, child) {
                    if (syncProvider.isLoadingWals && syncProvider.allWals.isEmpty) {
                      return const SliverToBoxAdapter(
                        child: Center(
                          child: Padding(
                            padding: EdgeInsets.all(32),
                            child: CircularProgressIndicator(color: Colors.white),
                          ),
                        ),
                      );
                    }

                    if (syncProvider.allWals.isEmpty) {
                      return SliverToBoxAdapter(child: _buildEmptyState(context));
                    }

                    final wals = syncProvider.filteredByStatusWals;

                    if (wals.isEmpty) {
                      return SliverToBoxAdapter(child: _buildEmptyFilterState(context, syncProvider.statusFilter));
                    }

                    if (syncProvider.statusFilter == WalStatusFilter.pending) {
                      return _buildPendingList(wals);
                    }

                    return OptimizedWalsListWidget(wals: wals);
                  },
                ),
                const SliverToBoxAdapter(child: SizedBox(height: 100)),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// Groups already-sorted wals (newest first) by year/month/day/hour bucket.
/// The caller is responsible for passing a sorted input — keeping the sort
/// outside this function lets [OptimizedWalsListWidget] do it exactly once
/// per data change instead of on every Consumer rebuild. Previously this
/// also mutated the input via `.sort()`; that was a hidden side-effect on
/// the provider's filtered list and is now removed.
Map<DateTime, List<Wal>> _groupWalsByDate(List<Wal> sortedWals) {
  final groupedWals = <DateTime, List<Wal>>{};
  for (final wal in sortedWals) {
    final createdAt = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final date = DateTime(createdAt.year, createdAt.month, createdAt.day, createdAt.hour);
    groupedWals.putIfAbsent(date, () => <Wal>[]).add(wal);
  }
  return groupedWals;
}

/// Renders a (potentially very large) list of wals as a [SliverList.builder]
/// with sticky date-hour headers. The grouping/sort/flatten step is O(n log n);
/// caching it across rebuilds matters because [SyncProvider] fires
/// `notifyListeners()` many times per second during active sync. Without the
/// cache, every notification re-sorted and re-flattened the whole list (10–30ms
/// per rebuild at 50k items) even though the underlying data hadn't changed.
///
/// Invalidation strategy mirrors [SyncProvider.displaySortedWals]: a stamp
/// derived from the input list's identity and length detects fresh refreshes
/// (new list assigned by `refreshWals`) while ignoring in-place per-wal status
/// mutations that don't affect grouping (status flips don't change timerStart).
class OptimizedWalsListWidget extends StatefulWidget {
  final List<Wal> wals;
  const OptimizedWalsListWidget({super.key, required this.wals});

  @override
  State<OptimizedWalsListWidget> createState() => _OptimizedWalsListWidgetState();
}

class _OptimizedWalsListWidgetState extends State<OptimizedWalsListWidget> {
  List<ListItem>? _cache;
  int _cacheStamp = 0;

  int get _stamp => identityHashCode(widget.wals) ^ widget.wals.length;

  List<ListItem> _flatten() {
    final stamp = _stamp;
    final cached = _cache;
    if (cached != null && _cacheStamp == stamp) return cached;
    // Defensive copy before sorting so we never mutate the provider's
    // filtered list — sort is descending by timerStart (newest first).
    final sorted = List<Wal>.from(widget.wals)..sort((a, b) => b.timerStart.compareTo(a.timerStart));
    final groupedWals = _groupWalsByDate(sorted);
    final items = <ListItem>[];
    for (final entry in groupedWals.entries) {
      items.add(DateHeaderItem(entry.key));
      for (int i = 0; i < entry.value.length; i++) {
        items.add(WalItem(entry.value[i], i, entry.key));
      }
    }
    _cache = items;
    _cacheStamp = stamp;
    return items;
  }

  @override
  Widget build(BuildContext context) {
    final flattenedItems = _flatten();

    return SliverList.builder(
      itemCount: flattenedItems.length,
      itemBuilder: (context, index) {
        final item = flattenedItems[index];

        if (item is DateHeaderItem) {
          return Padding(
            padding: EdgeInsets.fromLTRB(20, index == 0 ? 0 : 24, 20, 8),
            child: Text(
              dateTimeFormat('MMM d, h a', item.date),
              style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w500),
            ),
          );
        } else if (item is WalItem) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
            child: WalListItem(wal: item.wal, walIdx: item.index, date: item.date),
          );
        }
        return const SizedBox.shrink();
      },
    );
  }
}

abstract class ListItem {}

class DateHeaderItem extends ListItem {
  final DateTime date;
  DateHeaderItem(this.date);
}

class WalItem extends ListItem {
  final Wal wal;
  final int index;
  final DateTime date;
  WalItem(this.wal, this.index, this.date);
}

class _PendingListItem {
  final bool isHeader;
  final String? label;
  final IconData? icon;
  final Color? color;
  final int? count;
  final Wal? wal;

  _PendingListItem.header(this.label, this.icon, this.color, this.count)
      : isHeader = true,
        wal = null;

  _PendingListItem.wal(this.wal)
      : isHeader = false,
        label = null,
        icon = null,
        color = null,
        count = null;
}

class _ManageStorageSheet extends StatelessWidget {
  final SyncProvider provider;
  final VoidCallback onClearSynced;
  final VoidCallback onClearPending;
  final VoidCallback onClearAll;

  const _ManageStorageSheet({
    required this.provider,
    required this.onClearSynced,
    required this.onClearPending,
    required this.onClearAll,
  });

  @override
  Widget build(BuildContext context) {
    final syncedCount = provider.syncedWals.length;
    final pendingCount = provider.pendingDeletableWals.length;
    final totalCount = syncedCount + pendingCount;

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Drag handle
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(color: Colors.grey.shade700, borderRadius: BorderRadius.circular(2)),
              ),
              const SizedBox(height: 20),
              // Title
              Text(
                context.l10n.manageStorage,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 24),
              // Synced row
              _StorageRow(
                icon: FontAwesomeIcons.circleCheck,
                iconColor: Colors.green,
                title: context.l10n.synced,
                subtitle: context.l10n.safelyBackedUp,
                count: syncedCount,
                onClear: syncedCount > 0 ? onClearSynced : null,
                clearLabel: context.l10n.clear,
              ),
              const SizedBox(height: 12),
              // Pending row
              _StorageRow(
                icon: FontAwesomeIcons.clockRotateLeft,
                iconColor: Colors.orange,
                title: context.l10n.pending,
                subtitle: context.l10n.notYetSynced,
                count: pendingCount,
                onClear: pendingCount > 0 ? onClearPending : null,
                clearLabel: context.l10n.clear,
                isWarning: true,
              ),
              if (totalCount > 0) ...[
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: TextButton(
                    onPressed: onClearAll,
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(color: Colors.red.withValues(alpha: 0.3)),
                      ),
                    ),
                    child: Text(
                      context.l10n.clearAll,
                      style: TextStyle(color: Colors.red.shade300, fontSize: 15, fontWeight: FontWeight.w500),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _StorageRow extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final int count;
  final VoidCallback? onClear;
  final String clearLabel;
  final bool isWarning;

  const _StorageRow({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.count,
    required this.onClear,
    required this.clearLabel,
    this.isWarning = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: iconColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Center(child: FaIcon(icon, size: 16, color: iconColor)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      title,
                      style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text('$count', style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(subtitle, style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
              ],
            ),
          ),
          if (onClear != null)
            GestureDetector(
              onTap: onClear,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: (isWarning ? Colors.orange : Colors.red).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Text(
                  clearLabel,
                  style: TextStyle(
                    color: isWarning ? Colors.orange.shade300 : Colors.red.shade300,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

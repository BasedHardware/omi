import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/sync/sync_card_progress_line.dart';
import 'package:omi/utils/sync_confirmation.dart';
import 'widgets/sync_error_card.dart';
import 'widgets/offline_sync_storage_sheet.dart';
import 'widgets/sync_list_header.dart';
import 'local_storage_page.dart';
import 'private_cloud_sync_page.dart';
import 'synced_conversations_page.dart';
import 'wal_item_detail/wal_item_detail_page.dart';

/// One recording on the legacy sync page. Consecutive rows under one date header read as one
/// outlined card: [isFirst] rounds and closes its top, [isLast] its bottom.
class WalListItem extends StatelessWidget {
  final DateTime date;
  final int walIdx;
  final Wal wal;
  final bool isFirst;
  final bool isLast;

  const WalListItem({
    super.key,
    required this.wal,
    required this.date,
    required this.walIdx,
    this.isFirst = true,
    this.isLast = true,
  });

  double _calcProgress(Wal wal) {
    if (!wal.isSyncing || wal.syncStartedAt == null) return 0.0;
    if (wal.storageTotalBytes <= 0) return 0.0;
    return (wal.storageOffset / wal.storageTotalBytes).clamp(0.0, 1.0);
  }

  String? _sourceLabel(BuildContext context) {
    if (wal.storage == WalStorage.sdcard) return context.l10n.sdCard;
    if (wal.originalStorage == WalStorage.sdcard) return context.l10n.fromSd;
    if (wal.storage == WalStorage.flashPage || wal.originalStorage == WalStorage.flashPage) {
      return context.l10n.limitless;
    }
    return null;
  }

  /// Subtitle colour (null: the row's tertiary default) and label. Black and white like the rest
  /// of Settings: amber for an automatic retry, red for failed and unrecoverable recordings.
  (Color?, String) _rowStatus(BuildContext context, bool hasError) {
    final l = context.l10n;
    final state = wal.syncDisplayState;
    if (state == WalSyncDisplayState.syncing) return (null, l.syncStatusBackingUp);
    if (hasError) return (OmiColors.danger, l.failedStatus);
    return switch (state) {
      WalSyncDisplayState.synced => (null, l.syncStatusConversationCreated),
      WalSyncDisplayState.uploaded => (null, l.syncStatusUploaded),
      WalSyncDisplayState.retrying => (OmiColors.warning, l.syncStatusRetrying),
      WalSyncDisplayState.failed => (OmiColors.danger, l.syncStatusFailed),
      WalSyncDisplayState.corrupted => (OmiColors.danger, l.syncStatusFileUnavailable),
      WalSyncDisplayState.outsideRecoveryWindow => (OmiColors.danger, l.syncStatusTooOld),
      WalSyncDisplayState.unsupportedAudio => (OmiColors.danger, l.syncStatusUnsupportedAudio),
      WalSyncDisplayState.uploadRejected => (OmiColors.danger, l.failedStatus),
      WalSyncDisplayState.waiting || WalSyncDisplayState.syncing => (null, l.syncStatusWaiting),
    };
  }

  /// The row's one control; null leaves the row's chevron.
  Widget? _trailing(BuildContext context, SyncProvider syncProvider, bool hasError) {
    final state = wal.syncDisplayState;
    if (state == WalSyncDisplayState.syncing) {
      return const OmiSpinner(size: OmiSpinnerSize.small);
    }
    if (hasError || state == WalSyncDisplayState.failed || state == WalSyncDisplayState.retrying) {
      return OmiButton.secondary(
        label: context.l10n.tryAgain,
        size: OmiButtonSize.compact,
        onPressed: () => syncProvider.syncWal(wal),
      );
    }
    // No upload can resolve these, so offer removal rather than a chevron that
    // leads to a detail page with nothing actionable on it.
    if (state == WalSyncDisplayState.corrupted ||
        state == WalSyncDisplayState.outsideRecoveryWindow ||
        state == WalSyncDisplayState.unsupportedAudio ||
        state == WalSyncDisplayState.uploadRejected) {
      return OmiButton.destructive(
        label: context.l10n.delete,
        size: OmiButtonSize.compact,
        onPressed: () async {
          final confirmed = await showOmiConfirm(
            context,
            title: context.l10n.deleteRecording,
            message: context.l10n.thisCannotBeUndone,
            confirmLabel: context.l10n.delete,
            destructive: true,
          );
          if (confirmed) await syncProvider.deleteWal(wal);
        },
      );
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final hasError = syncProvider.failedWal?.id == wal.id;
        final displayState = wal.syncDisplayState;
        final (statusColor, statusLabel) = _rowStatus(context, hasError);
        final timeStr = OmiDateFormat.of(context).time(DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000));
        final duration = OmiDuration.compact(wal.seconds, context.l10n);
        final source = _sourceLabel(context);
        final showBar = displayState == WalSyncDisplayState.syncing &&
            wal.status != WalStatus.synced &&
            wal.syncStartedAt != null &&
            wal.storage != WalStorage.flashPage;

        return OmiGroupedSlice(
          first: isFirst,
          last: isLast,
          child: Dismissible(
            key: Key(wal.id),
            direction:
                displayState == WalSyncDisplayState.syncing ? DismissDirection.none : DismissDirection.endToStart,
            confirmDismiss: (direction) {
              final uploading = wal.syncDisplayState == WalSyncDisplayState.uploaded;
              return showOmiConfirm(
                context,
                title: uploading ? context.l10n.deleteWhileProcessingTitle : context.l10n.deleteRecording,
                message: uploading ? context.l10n.deleteWhileProcessingMessage : context.l10n.thisCannotBeUndone,
                confirmLabel: context.l10n.delete,
                destructive: true,
              );
            },
            background: Container(
              alignment: Alignment.centerRight,
              padding: const EdgeInsets.only(right: OmiSpacing.lg),
              color: OmiColors.danger,
              child: OmiLineIcon(OmiLineGlyph.trash, size: 22, color: OmiColors.onAccent),
            ),
            onDismissed: (direction) {
              ServiceManager.instance().wal.getSyncs().deleteWal(wal);
            },
            child: Material(
              type: MaterialType.transparency,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  OmiSettingsRow(
                    title: source != null ? '$timeStr · $duration · $source' : '$timeStr · $duration',
                    subtitle: statusLabel,
                    subtitleColor: statusColor,
                    trailing: _trailing(context, syncProvider, hasError),
                    onTap: () => routeToPage(context, WalItemDetailPage(wal: wal)),
                  ),
                  if (showBar)
                    // The progress belongs to the row: tapping it opens the recording too.
                    GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => routeToPage(context, WalItemDetailPage(wal: wal)),
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: ClipRRect(
                                    borderRadius: OmiRadius.pillAll,
                                    child: LinearProgressIndicator(
                                      value: _calcProgress(wal),
                                      backgroundColor: OmiColors.surface3,
                                      color: OmiColors.textPrimary,
                                      minHeight: 3,
                                    ),
                                  ),
                                ),
                                if (wal.syncSpeedKBps != null && wal.syncSpeedKBps! > 0) ...[
                                  const SizedBox(width: OmiSpacing.sm),
                                  Text(
                                    '${wal.syncSpeedKBps!.toStringAsFixed(1)} KB/s',
                                    style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                                  ),
                                ],
                              ],
                            ),
                            if (wal.syncEtaSeconds != null && wal.syncEtaSeconds! > 0) ...[
                              const SizedBox(height: OmiSpacing.xxs),
                              Text(
                                context.l10n.etaLabel(OmiDuration.compact(wal.syncEtaSeconds!, context.l10n)),
                                style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                ],
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

  Widget _buildConversationsCreatedCard(SyncProvider syncProvider) {
    if (!syncProvider.syncCompleted || syncProvider.syncedConversationsPointers.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xl),
      child: OmiSettingsGroup(
        children: [
          OmiSettingsRow(
            leading: const OmiSettingsIconTile(FaIcon(FontAwesomeIcons.circleCheck)),
            title: context.l10n.conversationsCreated(syncProvider.syncedConversationsPointers.length),
            onTap: () => routeToPage(context, const SyncedConversationsPage()),
          ),
        ],
      ),
    );
  }

  Widget _buildSettingsCard() {
    final l = context.l10n;
    final isPhoneStorageOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;

    return Consumer<UserProvider>(
      builder: (context, userProvider, child) {
        return OmiSettingsGroup(
          header: l.storageSection,
          children: [
            OmiSettingsRow(
              leading: const OmiSettingsIconTile(FaIcon(FontAwesomeIcons.mobile)),
              title: l.storeAudioOnPhone,
              value: isPhoneStorageOn ? l.on : l.off,
              showChevron: true,
              onTap: () => routeToPage(context, const LocalStoragePage()).then((_) => setState(() {})),
            ),
            OmiSettingsRow(
              leading: const OmiSettingsIconTile(FaIcon(FontAwesomeIcons.cloud)),
              title: l.storeAudioOnCloud,
              value: userProvider.privateCloudSyncEnabled ? l.on : l.off,
              showChevron: true,
              onTap: () => routeToPage(context, const PrivateCloudSyncPage()),
            ),
          ],
        );
      },
    );
  }

  void _showCancelSyncDialog(BuildContext context, SyncProvider provider) async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.cancelSync,
      message: context.l10n.cancelSyncMessage,
      confirmLabel: context.l10n.cancelSync,
      destructive: true,
    );
    if (confirmed && context.mounted) {
      provider.cancelSync();
      OmiFeedback.info(context, context.l10n.syncCancelled);
    }
  }

  void _showManageStorageSheet(BuildContext context, SyncProvider provider) {
    showOmiSheet<void>(
      context: context,
      title: context.l10n.manageStorage,
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xs, OmiSpacing.xl, OmiSpacing.xl),
      builder: (sheetContext) => OfflineSyncStorageSheet(
        syncedCount: provider.syncedWals.length,
        pendingCount: provider.pendingDeletableWals.length,
        totalCount: provider.clearableWalsCount,
        onClearSynced: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await showOmiConfirm(
            context,
            title: context.l10n.deleteSyncedFiles,
            message: context.l10n.deleteSyncedFilesMessage,
            confirmLabel: context.l10n.clear,
            destructive: true,
          );
          if (confirmed && context.mounted) {
            await provider.deleteAllSyncedWals();
            if (context.mounted) {
              OmiFeedback.confirm(context, context.l10n.syncedFilesDeleted);
            }
          }
        },
        onClearPending: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await showOmiConfirm(
            context,
            title: context.l10n.deletePendingFiles,
            message: context.l10n.deletePendingFilesWarning,
            confirmLabel: context.l10n.clear,
            destructive: true,
          );
          if (confirmed && context.mounted) {
            await provider.deleteAllPendingWals();
            if (context.mounted) {
              OmiFeedback.confirm(context, context.l10n.pendingFilesDeleted);
            }
          }
        },
        onClearAll: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await showOmiConfirm(
            context,
            title: context.l10n.deleteAllFiles,
            message: context.l10n.deleteAllFilesWarning,
            confirmLabel: context.l10n.clearAll,
            destructive: true,
          );
          if (confirmed && context.mounted) {
            await provider.deleteAllClearableWals();
            if (context.mounted) {
              OmiFeedback.confirm(context, context.l10n.allFilesDeleted);
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
    if (SyncProvider.isPendingUploadError(errorMessage)) {
      return context.l10n.syncStatusFailed;
    }
    if (errorMessage.startsWith('Exception: ')) {
      errorMessage = errorMessage.substring('Exception: '.length);
    }

    final lowerMessage = errorMessage.toLowerCase();
    if (lowerMessage.contains('timeout') || lowerMessage.contains('did not respond')) {
      return context.l10n.deviceNotResponding;
    }
    return errorMessage;
  }

  void _showSdCardWarningDialog(BuildContext context, SyncProvider syncProvider, int sdCardCount) async {
    final process = await showOmiConfirm(
      context,
      title: context.l10n.sdCardProcessing,
      message: context.l10n.sdCardProcessingMessage(sdCardCount),
      confirmLabel: context.l10n.process,
    );
    if (process) syncProvider.syncWals();
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
    // Black and white like the rest of Settings; amber only when something is held up.
    var warning = false;
    var icon = FontAwesomeIcons.circleCheck;
    Widget? action;
    Widget cancelAction() => OmiButton.secondary(
          label: l.cancel,
          size: OmiButtonSize.compact,
          onPressed: () => _showCancelSyncDialog(context, syncProvider),
        );

    if (isActive) {
      final speed = syncProvider.syncSpeedKBps;
      final speedStr = (speed != null && speed > 0) ? '${speed.toStringAsFixed(1)} KB/s' : null;
      switch (s.phase) {
        case SyncPhase.downloadingFromDevice:
          title = l.syncCardDownloadingTitle;
          subtitle = _progressLine(s, speedStr);
          action = cancelAction();
          break;
        case SyncPhase.uploadingToCloud:
          title = l.syncCardUploadingTitle;
          subtitle = _progressLine(s, null);
          action = cancelAction();
          break;
        case SyncPhase.processingOnServer:
          title = l.syncCardProcessing;
          subtitle = l.syncProcessingBackgroundHint;
          break;
        case SyncPhase.waitingForInternet:
          title = l.syncCardWaitingInternet;
          warning = true;
          icon = FontAwesomeIcons.clock;
          break;
        case SyncPhase.idle:
          title = l.syncCardUploadingTitle;
          subtitle = _progressLine(s, speedStr);
          if (syncProvider.isSdCardSyncing) action = cancelAction();
          break;
      }
    } else if (syncProvider.isRateLimited) {
      title = syncCooldownTitle(syncProvider.rateLimitReason, l);
      warning = true;
      icon = FontAwesomeIcons.clock;
    } else if (uploaded > 0) {
      title = l.syncCardProcessing;
      final counts = syncProvider.offlineServerProcessingCounts;
      subtitle = SyncCardProgressLine.serverProcessingSubtitle(
            processed: counts.processed,
            total: counts.total,
            counterLabel: (p, t) => l.processingProgress(p, t),
          ) ??
          l.syncProcessingBackgroundHint;
    } else if (readyToSync > 0) {
      title = l.syncCardReadyCount(readyToSync);
      icon = FontAwesomeIcons.cloudArrowUp;
      action = OmiButton(
        label: l.sync,
        size: OmiButtonSize.compact,
        onPressed: () {
          if (context.read<ConnectivityProvider>().isConnected) {
            _handleSyncWals(context, syncProvider);
          } else {
            OmiFeedback.error(context, l.internetRequired);
          }
        },
      );
    } else {
      title = l.syncCardAllBackedUp;
    }

    return OmiGroupedCard(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      child: Row(
        children: [
          OmiSettingsIconTile(
            showSpinner
                ? const OmiSpinner(size: OmiSpinnerSize.small)
                : FaIcon(icon, color: warning ? OmiColors.warning : null),
          ),
          const SizedBox(width: OmiSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: OmiType.body.copyWith(color: warning ? OmiColors.warning : OmiColors.textPrimary),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                  ),
                ],
              ],
            ),
          ),
          if (action != null) ...[const SizedBox(width: OmiSpacing.sm), action],
        ],
      ),
    );
  }

  String? _progressLine(SyncState s, String? speedStr) {
    return SyncCardProgressLine.subtitle(
      phase: s.phase,
      currentFile: s.currentFile,
      totalFiles: s.totalFiles,
      counterLabel: (processed, total) => context.l10n.syncCardProgressOf(processed, total),
      speedSuffix: speedStr,
    );
  }

  Widget _buildSyncErrorCard(SyncProvider syncProvider) {
    return SyncErrorCard(
      message: _formatErrorMessage(context, syncProvider.syncError!),
      onRetry: () => syncProvider.retrySync(),
    );
  }

  Widget _buildStatusChips(SyncProvider syncProvider) {
    String label(String name, int count) => count > 0 ? '$name $count' : name;
    return OmiSegmentedControl<WalStatusFilter>(
      value: syncProvider.statusFilter,
      segments: {
        WalStatusFilter.pending: label(context.l10n.pending, syncProvider.pendingStatusCount),
        WalStatusFilter.synced: label(context.l10n.synced, syncProvider.syncedStatusCount),
        WalStatusFilter.corrupted: label(context.l10n.failedStatus, syncProvider.corruptedStatusCount),
      },
      onChanged: syncProvider.setStatusFilter,
    );
  }

  Widget _buildEmptyFilterState(BuildContext context, WalStatusFilter filter) {
    final isPending = filter == WalStatusFilter.pending;
    final isCorrupted = filter == WalStatusFilter.corrupted;
    return OmiEmptyState(
      glyph: OmiLineIcon(isPending
          ? OmiLineGlyph.check
          : isCorrupted
              ? OmiLineGlyph.info
              : OmiLineGlyph.clock),
      title: isPending
          ? context.l10n.noPendingRecordings
          : isCorrupted
              ? context.l10n.syncStatusFileUnavailable
              : context.l10n.noProcessedRecordings,
      message: isPending ? context.l10n.allCaughtUp : null,
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
    void addSection(String label, List<Wal> wals) {
      items.add(_PendingListItem.header(label, wals.length));
      for (var i = 0; i < wals.length; i++) {
        items.add(_PendingListItem.wal(wals[i], isFirst: i == 0, isLast: i == wals.length - 1));
      }
    }

    if (phoneWals.isNotEmpty) addSection(context.l10n.phone, phoneWals);
    if (sdCardWals.isNotEmpty) addSection(context.l10n.sdCard, sdCardWals);
    if (limitlessWals.isNotEmpty) addSection(context.l10n.limitless, limitlessWals);

    return SliverList.builder(
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        if (item.isHeader) {
          return SyncListHeader(label: item.label!, count: item.count, first: index == 0);
        }
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
          child: WalListItem(
            wal: item.wal!,
            walIdx: index,
            date: DateTime.fromMillisecondsSinceEpoch(item.wal!.timerStart * 1000),
            isFirst: item.isFirst,
            isLast: item.isLast,
          ),
        );
      },
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return OmiEmptyState(
      glyph: const OmiLineIcon(OmiLineGlyph.microphone),
      title: context.l10n.noRecordings,
      message: context.l10n.audioFromOmiWillAppearHere,
    );
  }

  @override
  Widget build(BuildContext context) {
    // Sync result persists until the next sync starts.
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        return OmiGroupedPage(
          title: context.l10n.offlineSync,
          actions: [
            OmiIconButton.filled(
              icon: const OmiLineIcon(OmiLineGlyph.more, size: 20),
              label: context.l10n.manageStorage,
              onPressed: () {
                HapticFeedback.mediumImpact();
                _showManageStorageSheet(context, syncProvider);
              },
            ),
          ],
          body: CustomScrollView(
            slivers: [
              // Settings + Process card + status chips
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: OmiSpacing.sm),
                      _buildProcessCard(syncProvider),
                      const SizedBox(height: OmiSpacing.xl),
                      _buildConversationsCreatedCard(syncProvider),
                      _buildSettingsCard(),
                      const SizedBox(height: OmiSpacing.xl),
                      _buildStatusChips(syncProvider),
                      const SizedBox(height: OmiSpacing.lg),
                    ],
                  ),
                ),
              ),
              // Recordings list
              Consumer<SyncProvider>(
                builder: (context, syncProvider, child) {
                  if (syncProvider.isLoadingWals && syncProvider.allWals.isEmpty) {
                    return const SliverToBoxAdapter(child: OmiLoadingState());
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
              const SliverToBoxAdapter(child: SizedBox(height: OmiSpacing.xxl)),
            ],
          ),
        );
      },
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
          final dates = OmiDateFormat.of(context);
          return SyncListHeader(label: '${dates.dayHeader(item.date)} · ${dates.time(item.date)}', first: index == 0);
        } else if (item is WalItem) {
          final isLast = index + 1 >= flattenedItems.length || flattenedItems[index + 1] is DateHeaderItem;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: WalListItem(
              wal: item.wal,
              walIdx: item.index,
              date: item.date,
              isFirst: item.index == 0,
              isLast: isLast,
            ),
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
  final int? count;
  final Wal? wal;
  final bool isFirst;
  final bool isLast;

  _PendingListItem.header(this.label, this.count)
      : isHeader = true,
        wal = null,
        isFirst = false,
        isLast = false;

  _PendingListItem.wal(this.wal, {required this.isFirst, required this.isLast})
      : isHeader = false,
        label = null,
        count = null;
}

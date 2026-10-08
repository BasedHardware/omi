part of 'auto_sync_page.dart';

extension _NativeOfflineSyncPresentation on _AutoSyncPageState {
  ({
    String title,
    String? subtitle,
    Color color,
    VoidCallback? action,
    String? actionLabel,
    Color actionColor,
    bool spinner,
    bool downloading
  }) _offlineStatus(SyncProvider p, SyncState s) {
    final l = context.l10n;
    final attention = p.needsAttentionWalsCount;
    final uploaded = p.uploadedWals.length;
    final readyToBackUp = p.displaySortedWals
        .where(
          (w) =>
              w.syncDisplayState == WalSyncDisplayState.waiting || w.syncDisplayState == WalSyncDisplayState.retrying,
        )
        .length;
    final hasAnyRecording = p.allWals.isNotEmpty;

    final isActive = s.isSyncing || s.isFetchingConversations;
    final bool showSpinner = (isActive || uploaded > 0) && !p.isRateLimited;

    String title;
    String? progressText;
    Color titleColor = OmiColors.textPrimary;
    VoidCallback? onAction;
    String? actionLabel;
    Color actionColor = OmiColors.accent;

    if (isActive) {
      switch (s.phase) {
        case SyncPhase.downloadingFromDevice:
          title = l.syncCardDownloadingTitle;
          // Percent and speed live on [DeviceDownloadMeter], not the file-count line.
          // A ring download has no file index, so the old subtitle stayed blank.
          break;
        case SyncPhase.waitingForInternet:
          title = l.syncCardWaitingInternet;
          titleColor = Colors.orangeAccent;
          break;
        case SyncPhase.uploadingToCloud:
          title = l.syncCardUploadingTitle;
          progressText = SyncCardProgressLine.subtitle(
            phase: s.phase,
            currentFile: s.currentFile,
            totalFiles: s.totalFiles,
            counterLabel: (processed, total) => l.syncCardProgressOf(processed, total),
          );
          break;
        case SyncPhase.processingOnServer:
          title = l.syncCardProcessing;
          break;
        default:
          title = s.isFetchingConversations ? l.syncCardProcessing : l.syncCardUploadingTitle;
      }
      actionLabel = l.cancel;
      actionColor = Colors.redAccent;
      onAction = () => _confirmCancel(context, p);
    } else if (p.isRateLimited) {
      title = syncCooldownTitle(p.rateLimitReason, l);
      titleColor = Colors.orangeAccent;
    } else if (uploaded > 0) {
      // Uploads finished, reconciler is resolving jobs in the background.
      title = l.syncCardProcessing;
      final counts = p.offlineServerProcessingCounts;
      progressText = SyncCardProgressLine.serverProcessingSubtitle(
            processed: counts.processed,
            total: counts.total,
            counterLabel: (processed, total) => l.processingProgress(processed, total),
          ) ??
          l.syncProcessingBackgroundHint;
    } else if (attention > 0) {
      title = l.syncCardNeedsAttention(attention);
      titleColor = Colors.orangeAccent;
      actionLabel = l.sync;
      onAction = () async {
        if (await confirmSyncForCustomStt(context) && context.mounted) p.syncWals();
      };
    } else if (readyToBackUp > 0) {
      title = l.syncCardReadyCount(readyToBackUp);
      actionLabel = l.sync;
      onAction = () async {
        if (await confirmSyncForCustomStt(context) && context.mounted) p.syncWals();
      };
    } else if (hasAnyRecording) {
      title = l.syncCardAllBackedUp;
      titleColor = OmiColors.active == OmiPalette.light ? OmiColors.textPrimary : Colors.grey.shade400;
    } else {
      // No recordings — same calm baseline; the card never pops in/out.
      title = l.syncCardAllBackedUp;
      titleColor = OmiColors.active == OmiPalette.light ? OmiColors.textPrimary : Colors.grey.shade400;
    }

    final downloading = isActive && s.phase == SyncPhase.downloadingFromDevice;

    return (
      title: title,
      subtitle: progressText,
      color: titleColor,
      action: onAction,
      actionLabel: actionLabel,
      actionColor: actionColor,
      spinner: showSpinner,
      downloading: downloading
    );
  }

  Widget _nativeOfflineSync(
      SyncProvider owner, UserProvider user, DeviceProvider device, List<Wal> wals, Widget classic) {
    if (!nativePresentationEnabled) return classic;
    final l = context.l10n;
    final s = owner.syncState;
    final status = _offlineStatus(owner, s);
    final ring = WalSyncs.isRingBufferFirmware(device.currentFirmwareVersion) ? device.ringStatus : null;
    final used = (ring?.usedBytes ?? 0).clamp(0, 1 << 53);
    final free = (ring?.freeBytes ?? 0).clamp(0, 1 << 53);
    final total = used + free;
    final fraction = total == 0 ? 0.0 : used / total;
    final percent = (s.progress.clamp(0.0, 1.0) * 100).round();
    final speed = s.speedKBps;
    final readout = s.progress > 0
        ? speed != null && speed > 0
            ? l.syncCardDownloadPercentSpeed(percent, speed < 10 ? speed.toStringAsFixed(1) : speed.toStringAsFixed(0))
            : l.syncCardDownloadPercent(percent)
        : l.loading;
    return Scaffold(
        body: IosNativeSurface(title: l.offlineSync, fallback: classic, toolbar: [
      NativeRow('offline_back', l.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      NativeRow('offline_info', l.howSyncingWorks, symbol: 'info.circle', action: (_) => _showInfoSheet(context)),
      if (owner.clearableWalsCount > 0)
        NativeRow('offline_manage', l.manageStorage,
            symbol: 'ellipsis', action: (_) => _showManageStorageSheet(context, owner)),
    ], sections: [
      NativeSection('offline_status', [
        NativeRow('offline_status_title', status.title, subtitle: status.subtitle ?? '', kind: 'label'),
        if (status.spinner) NativeRow('offline_busy', l.loading, kind: 'label', symbol: 'arrow.triangle.2.circlepath'),
        if (status.action != null)
          NativeRow('offline_status_action', status.actionLabel!,
              destructive: status.actionLabel == l.cancel, action: (_) => status.action!()),
        if (status.downloading)
          NativeRow('offline_download', readout,
              kind: s.progress > 0 ? 'progress' : 'label',
              value: s.progress > 0 ? s.progress.clamp(0.0, 1.0) : null,
              maximumValue: s.progress > 0 ? 1 : null),
        if (s.hasError) ...[
          NativeRow('offline_error',
              SyncProvider.isPendingUploadError(s.errorMessage) ? l.syncStatusFailed : s.errorMessage ?? l.syncFailed,
              kind: 'label', symbol: 'exclamationmark.circle'),
          NativeRow('offline_retry', l.retry, action: (_) => owner.retrySync()),
        ],
        if (owner.syncCompleted && owner.syncedConversationsPointers.isNotEmpty)
          NativeRow('offline_conversations', l.nConversationsCreated(owner.syncedConversationsPointers.length),
              kind: 'navigation', action: (_) => routeToPage(context, const SyncedConversationsPage())),
      ]),
      if (ring != null)
        NativeSection('offline_device_storage', [
          NativeRow('offline_device_storage_used', l.deviceStorageTitle,
              kind: 'progress',
              value: fraction,
              maximumValue: 1,
              subtitle:
                  '${l.deviceStoragePercentFull((fraction * 100).round())} · ${l.deviceStorageUsedOfTotal(WavBytesUtil.formatBytes(used, decimals: 0), WavBytesUtil.formatBytes(total, decimals: 0))} · ${l.deviceStorageFree(WavBytesUtil.formatBytes(free, decimals: 0))}'),
          if (fraction >= .95)
            NativeRow('offline_device_full', l.deviceStorageNearlyFull,
                kind: 'label', symbol: 'exclamationmark.triangle'),
        ]),
      NativeSection(
          'offline_storage',
          [
            NativeRow('offline_phone_storage', l.storeAudioOnPhone,
                kind: 'navigation',
                subtitle: SharedPreferencesUtil().unlimitedLocalStorageEnabled ? l.on : l.off, action: (_) async {
              await routeToPage(context, const LocalStoragePage());
              if (mounted) _updateNativeSync(() {});
            }),
            NativeRow('offline_cloud_storage', l.storeAudioOnCloud,
                kind: 'navigation',
                subtitle: user.privateCloudSyncEnabled ? l.on : l.off,
                action: (_) => routeToPage(context, const PrivateCloudSyncPage())),
            NativeRow('offline_retention', l.autoRemoveSyncedCopiesTitle,
                kind: 'toggle',
                value: SharedPreferencesUtil().autoRemoveSyncedCopies,
                subtitle: l.autoRemoveSyncedCopiesDescription(SharedPreferencesUtil().autoRemoveSyncedCopiesDays),
                action: (value) async {
              SharedPreferencesUtil().autoRemoveSyncedCopies = value as bool;
              if (value) await owner.applySyncedCopyRetention();
              if (mounted) _updateNativeSync(() {});
            }),
          ],
          title: l.storageSection),
      if (owner.allWals.isNotEmpty)
        NativeSection(
            'offline_recordings',
            [
              NativeRow('offline_filter', l.recordings,
                  kind: 'segmented',
                  value: _filter.name,
                  options: {
                    WalDisplayFilter.all.name: l.all,
                    WalDisplayFilter.pending.name: l.pending,
                    WalDisplayFilter.synced.name: l.synced
                  },
                  action: (value) => _updateNativeSync(() {
                        _filter = WalDisplayFilter.values.byName(value as String);
                        _nativeWalWindow = _AutoSyncPageState._nativeWalPage;
                      })),
              if (wals.isEmpty)
                NativeRow(
                    'offline_empty',
                    switch (_filter) {
                      WalDisplayFilter.synced => l.noSyncedRecordingsYet,
                      WalDisplayFilter.pending => l.noPendingRecordings,
                      _ => l.noRecordingsYet,
                    },
                    kind: 'label'),
              for (var i = 0; i < wals.length && i < _nativeWalWindow; i++) ..._nativeWalRows(owner, wals[i], i),
              // Reaching the end of the window projects the next page; nothing is loaded or synced.
              if (wals.length > _nativeWalWindow)
                NativeRow('offline_more', l.loading,
                    kind: 'label',
                    onVisible: (_) => _updateNativeSync(() => _nativeWalWindow += _AutoSyncPageState._nativeWalPage)),
            ],
            title: '${l.recordings} (${wals.length})'),
    ]));
  }

  List<NativeRow> _nativeWalRows(SyncProvider owner, Wal wal, int index) {
    final l = context.l10n;
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final dates = OmiDateFormat.of(context);
    final state = wal.syncDisplayState;
    final onDevice = wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;
    final label = state == WalSyncDisplayState.waiting && onDevice
        ? owner.syncState.phase == SyncPhase.downloadingFromDevice
            ? l.syncStatusDownloadingFromDevice
            : l.syncStatusOnDevice
        : _rowVisual(state).$3;
    final id = 'offline_wal:${wal.id}:$index';
    final progress = _rowDownloadFraction(wal);
    return [
      NativeRow(id,
          '${dates.dayHeader(date)} · ${dates.time(date)}${wal.seconds > 0 ? ' · ${OmiDuration.compact(wal.seconds, l)}' : ''}',
          kind: 'navigation',
          subtitle: label,
          options: {if (state != WalSyncDisplayState.syncing) 'delete': l.delete}, action: (value) async {
        if (value == 'delete') {
          final processing = state == WalSyncDisplayState.uploaded;
          final confirmed = await showOmiConfirm(context,
              title: processing ? l.deleteWhileProcessingTitle : l.deleteRecording,
              message: processing ? l.deleteWhileProcessingMessage : l.thisCannotBeUndone,
              confirmLabel: l.delete,
              destructive: true);
          if (confirmed && mounted) await owner.deleteWal(wal);
        } else if (owner.isSyncing && wal.storage == WalStorage.sdcard) {
          OmiFeedback.info(context, l.syncInProgress);
        } else {
          await routeToPage(context, WalItemDetailPage(wal: wal));
        }
      }),
      if (progress != null)
        NativeRow('$id:progress', label, kind: 'progress', value: progress.clamp(0.0, 1.0), maximumValue: 1),
      if (state == WalSyncDisplayState.failed || state == WalSyncDisplayState.retrying)
        NativeRow('$id:retry', l.tryAgain, action: (_) => owner.syncWal(wal)),
      if (_AutoSyncPageState._isUnsyncableState(state))
        NativeRow('$id:delete', l.delete, destructive: true, action: (_) => _confirmDeleteWal(wal)),
    ];
  }
}

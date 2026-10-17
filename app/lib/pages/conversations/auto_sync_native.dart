part of 'auto_sync_page.dart';

extension _NativeOfflineSyncPresentation on _AutoSyncPageState {
  /// The page as native sections. [status] is the status card the Flutter page draws, projected once
  /// per build; [toSyncSeconds] labels the To sync segment; [classic] is the complete Flutter page.
  Widget _nativeOfflineSync(
    SyncProvider owner,
    UserProvider user,
    DeviceProvider device,
    List<Wal> wals,
    _OfflineStatus status,
    int toSyncSeconds,
    Widget classic,
  ) {
    if (!nativePresentationEnabled) return classic;
    final l = context.l10n;
    final s = owner.syncState;
    final blocks = groupRecordingBlocks(wals);
    final ring = WalSyncs.isRingBufferFirmware(device.currentFirmwareVersion) ? device.ringStatus : null;
    final used = (ring?.usedBytes ?? 0).clamp(0, 1 << 53);
    final free = (ring?.freeBytes ?? 0).clamp(0, 1 << 53);
    final total = used + free;
    final fraction = total == 0 ? 0.0 : used / total;
    final barStep = status.barStep;
    // No toolbar actions, as on the Flutter app bar: "How syncing works" lives in Sync details and
    // Manage Storage in the Storage group.
    return Scaffold(
        body: IosNativeSurface(title: l.offlineSync, fallback: classic, toolbar: [
      NativeRow('offline_back', l.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
    ], sections: [
      NativeSection('offline_status', [
        NativeRow('offline_status_title', status.title, subtitle: status.subtitle ?? '', kind: 'label'),
        if (status.spinner) NativeRow('offline_busy', l.loading, kind: 'label', symbol: 'arrow.triangle.2.circlepath'),
        if (status.action != null)
          NativeRow('offline_status_action', status.actionLabel!,
              destructive: status.actionLabel == l.cancel, action: (_) => status.action!()),
        // One bar for the three steps, filling left to right like [SyncStepBar]: the active step names
        // the row, and a step with nothing measurable yet sits at the start of its third.
        if (barStep != null)
          NativeRow('offline_step', _syncStepLabel(barStep),
              kind: 'progress',
              value: (barStep.index + (status.barFraction?.clamp(0.0, 1.0) ?? 0)) / SyncStep.values.length,
              maximumValue: 1),
        if (s.hasError) ...[
          NativeRow('offline_error',
              SyncProvider.isPendingUploadError(s.errorMessage) ? l.syncStatusFailed : s.errorMessage ?? l.syncFailed,
              kind: 'label', symbol: 'exclamationmark.circle'),
          NativeRow('offline_retry', l.retry, action: (_) => owner.retrySync()),
        ],
        if (status.created > 0)
          NativeRow('offline_conversations', l.nConversationsCreated(status.created),
              kind: 'navigation', action: (_) => routeToPage(context, const SyncedConversationsPage())),
        // Upstream's Flutter sheet, presented over the native page; its explainer button opens the
        // native "How syncing works" modal.
        NativeRow('offline_details', l.syncDetailsTitle,
            kind: 'navigation',
            action: (_) => showSyncDetailsSheet(context, onHowSyncingWorks: () => _showInfoSheet(context))),
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
                subtitle: l.autoRemoveSyncedCopiesDays(SharedPreferencesUtil().autoRemoveSyncedCopiesDays),
                action: (value) async {
              SharedPreferencesUtil().autoRemoveSyncedCopies = value as bool;
              if (value) await owner.applySyncedCopyRetention();
              if (mounted) _updateNativeSync(() {});
            }),
            if (owner.clearableWalsCount > 0)
              NativeRow('offline_manage', l.manageStorage,
                  kind: 'navigation', action: (_) => _showManageStorageSheet(context, owner)),
          ],
          title: l.storageSection),
      if (owner.allWals.isNotEmpty)
        NativeSection(
            'offline_recordings',
            [
              // Two segments, as the Flutter chips: what still has to sync and what already has.
              NativeRow('offline_filter', l.recordings,
                  kind: 'segmented',
                  value: _filter.name,
                  options: {
                    WalDisplayFilter.pending.name: _pendingLabel(toSyncSeconds),
                    WalDisplayFilter.synced.name: l.synced,
                  },
                  action: (value) => _updateNativeSync(() {
                        _filter = WalDisplayFilter.values.byName(value as String);
                        _nativeWalWindow = _AutoSyncPageState._nativeWalPage;
                      })),
              if (wals.isEmpty)
                NativeRow('offline_empty',
                    _filter == WalDisplayFilter.synced ? l.noSyncedRecordingsYet : l.noPendingRecordings,
                    kind: 'label'),
              for (var i = 0; i < blocks.length && i < _nativeWalWindow; i++) ..._nativeBlockRows(owner, blocks[i], i),
              // Reaching the end of the window projects the next page; nothing is loaded or synced.
              if (blocks.length > _nativeWalWindow)
                NativeRow('offline_more', l.loading,
                    kind: 'label',
                    onVisible: (_) => _updateNativeSync(() => _nativeWalWindow += _AutoSyncPageState._nativeWalPage)),
            ],
            title: l.recordings),
    ]));
  }

  /// The step names [SyncStepBar] prints under its segments.
  String _syncStepLabel(SyncStep step) => switch (step) {
        SyncStep.download => context.l10n.syncStepLabelDownload,
        SyncStep.upload => context.l10n.syncStepLabelUpload,
        SyncStep.transcribe => context.l10n.syncStepLabelTranscribe,
      };

  List<NativeRow> _nativeBlockRows(SyncProvider owner, RecordingBlock block, int index) {
    if (block.wals.length == 1) return _nativeWalRows(owner, block.wals.single, index);
    final l = context.l10n;
    final id = 'offline_block:${block.oldest.id}:$index';
    return [
      NativeRow(id, _blockTitle(block),
          kind: 'navigation', subtitle: _rowLabel(block.representative).$2, action: (_) => _showBlockFiles(block)),
      if (block.state == WalSyncDisplayState.failed || block.state == WalSyncDisplayState.retrying)
        NativeRow('$id:retry', l.tryAgain, action: (_) async {
          for (final wal in block.wals) {
            if (wal.syncDisplayState == WalSyncDisplayState.failed ||
                wal.syncDisplayState == WalSyncDisplayState.retrying) {
              await owner.syncWal(wal);
            }
          }
        }),
      if (block.wals.every((wal) => _AutoSyncPageState._isUnsyncableState(wal.syncDisplayState)))
        NativeRow('$id:delete', l.delete, destructive: true, action: (_) => _confirmDeleteWals(block.wals)),
    ];
  }

  List<NativeRow> _nativeWalRows(SyncProvider owner, Wal wal, int index) {
    final l = context.l10n;
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final dates = OmiDateFormat.of(context);
    final state = wal.syncDisplayState;
    final label = _rowLabel(wal).$2;
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

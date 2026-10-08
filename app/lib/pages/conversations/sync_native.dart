part of 'sync_page.dart';

/// Recordings the native list projects at a time. Reaching the end of the window projects the next
/// page; this is presentation only and keeps snapshots small while an active sync notifies often.
const _syncWalPage = 200;

extension _NativeSyncPresentation on _SyncPageState {
  /// The legacy Offline Sync page as one native list. Status, storage, filter and recordings read the
  /// same provider state as [classic]; every command returns to [SyncProvider] and the existing pages
  /// and confirmations. Projecting status never starts a sync.
  Widget _nativeSync(SyncProvider owner, Widget classic) {
    if (!nativePresentationEnabled) return classic;
    return Consumer<UserProvider>(builder: (context, user, _) {
      final l = context.l10n;
      return Scaffold(
        body: IosNativeSurface(
          title: l.offlineSync,
          fallback: classic,
          toolbar: [
            NativeRow('sync_back', l.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
            NativeRow('sync_manage', l.manageStorage, symbol: 'ellipsis', action: (_) {
              HapticFeedback.mediumImpact();
              _showManageStorageSheet(context, owner);
            }),
          ],
          sections: [
            NativeSection('sync_status', _nativeSyncStatusRows(owner)),
            NativeSection(
                'sync_storage',
                [
                  NativeRow('sync_phone_storage', l.storeAudioOnPhone,
                      kind: 'navigation',
                      subtitle: SharedPreferencesUtil().unlimitedLocalStorageEnabled ? l.on : l.off, action: (_) async {
                    await routeToPage(context, const LocalStoragePage());
                    if (mounted) _updateNativeSync(() {});
                  }),
                  NativeRow('sync_cloud_storage', l.storeAudioOnCloud,
                      kind: 'navigation',
                      subtitle: user.privateCloudSyncEnabled ? l.on : l.off,
                      action: (_) => routeToPage(context, const PrivateCloudSyncPage())),
                ],
                title: l.storageSection),
            ..._nativeSyncRecordingSections(owner),
          ],
        ),
      );
    });
  }

  List<NativeRow> _nativeSyncStatusRows(SyncProvider owner) {
    final l = context.l10n;
    final rows = <NativeRow>[];
    // The same precedence as the original card: an unattributed sync error replaces the status.
    if (owner.syncError != null && owner.failedWal == null) {
      rows.addAll([
        NativeRow('sync_error', _formatErrorMessage(context, owner.syncError!),
            kind: 'label', symbol: 'exclamationmark.circle'),
        NativeRow('sync_retry', l.retry, action: (_) => owner.retrySync()),
      ]);
    } else {
      final status = _syncStatus(owner);
      rows.addAll([
        NativeRow('sync_status_title', status.title, kind: 'label', subtitle: status.subtitle ?? ''),
        if (status.spinner) NativeRow('sync_busy', l.loading, kind: 'label', symbol: 'arrow.triangle.2.circlepath'),
        if (status.action == _SyncStatusAction.sync)
          NativeRow('sync_start', l.sync, action: (_) => _onSyncPressed(context, owner)),
        if (status.action == _SyncStatusAction.cancel)
          NativeRow('sync_cancel', l.cancel, destructive: true, action: (_) => _showCancelSyncDialog(context, owner)),
      ]);
    }
    if (owner.syncCompleted && owner.syncedConversationsPointers.isNotEmpty) {
      rows.add(NativeRow('sync_conversations', l.conversationsCreated(owner.syncedConversationsPointers.length),
          kind: 'navigation', action: (_) => routeToPage(context, const SyncedConversationsPage())));
    }
    return rows;
  }

  List<NativeSection> _nativeSyncRecordingSections(SyncProvider owner) {
    final l = context.l10n;
    String chip(String label, int count) => count > 0 ? '$label  $count' : label;
    final filter = owner.statusFilter;
    final header = <NativeRow>[
      NativeRow('sync_filter', l.recordings, kind: 'segmented', value: filter.name, options: {
        WalStatusFilter.pending.name: chip(l.pending, owner.pendingStatusCount),
        WalStatusFilter.synced.name: chip(l.synced, owner.syncedStatusCount),
        WalStatusFilter.corrupted.name: chip(l.failedStatus, owner.corruptedStatusCount),
      }, action: (value) {
        _updateNativeSync(() => _nativeWalWindow = _syncWalPage);
        owner.setStatusFilter(WalStatusFilter.values.byName(value as String));
      }),
    ];
    if (owner.isLoadingWals && owner.allWals.isEmpty) {
      header.add(NativeRow('sync_loading', l.loading, kind: 'label'));
      return [NativeSection('sync_recordings', header)];
    }
    if (owner.allWals.isEmpty) {
      header.add(NativeRow('sync_empty', l.noRecordings,
          kind: 'label', subtitle: l.audioFromOmiWillAppearHere, symbol: 'mic'));
      return [NativeSection('sync_recordings', header)];
    }
    final wals = owner.filteredByStatusWals;
    if (wals.isEmpty) {
      header.add(switch (filter) {
        WalStatusFilter.pending => NativeRow('sync_empty', l.noPendingRecordings,
            kind: 'label', subtitle: l.allCaughtUp, symbol: 'checkmark.circle'),
        WalStatusFilter.corrupted =>
          NativeRow('sync_empty', l.syncStatusFileUnavailable, kind: 'label', symbol: 'exclamationmark.triangle'),
        WalStatusFilter.synced => NativeRow('sync_empty', l.noProcessedRecordings, kind: 'label', symbol: 'clock'),
      });
      return [NativeSection('sync_recordings', header)];
    }

    // The original list's grouping: pending recordings from more than one source are grouped by
    // source in provider order; everything else is newest first under date-hour headers.
    final groups = <(String, String, List<Wal>)>[];
    final bySource = _SyncPageState._walsBySource(wals);
    final sources = [
      ('phone', l.phone, bySource.phone),
      ('sd_card', l.sdCard, bySource.sdCard),
      ('limitless', l.limitless, bySource.limitless),
    ].where((source) => source.$3.isNotEmpty);
    if (filter == WalStatusFilter.pending && sources.length > 1) {
      for (final (id, label, members) in sources) {
        groups.add(('sync_source:$id', '$label · ${members.length}', members));
      }
    } else {
      final dates = OmiDateFormat.of(context);
      for (final entry in _groupWalsByDate(_nativeSortedWals(wals)).entries) {
        groups.add((
          'sync_hour:${entry.key.millisecondsSinceEpoch}',
          '${dates.dayHeader(entry.key)} · ${dates.time(entry.key)}',
          entry.value
        ));
      }
    }

    final sections = [NativeSection('sync_recordings', header)];
    var index = 0;
    for (final (id, title, members) in groups) {
      if (index >= _nativeWalWindow) break;
      final rows = <NativeRow>[];
      for (final wal in members) {
        if (index >= _nativeWalWindow) break;
        rows.addAll(_nativeSyncWalRows(owner, wal, index++));
      }
      sections.add(NativeSection(id, rows, title: title));
    }
    if (wals.length > _nativeWalWindow) {
      sections.add(NativeSection('sync_more_section', [
        NativeRow('sync_more', l.loading,
            kind: 'label', onVisible: (_) => _updateNativeSync(() => _nativeWalWindow += _syncWalPage)),
      ]));
    }
    return sections;
  }

  /// [wals] newest first, re-sorted only when the provider hands over a new list (its identity or
  /// length changed), like [OptimizedWalsListWidget]. Never sorts the provider's list in place.
  List<Wal> _nativeSortedWals(List<Wal> wals) {
    if (!identical(wals, _nativeSortSource) || wals.length != _nativeSortLength) {
      _nativeSortSource = wals;
      _nativeSortLength = wals.length;
      _nativeSorted = List<Wal>.from(wals)..sort((a, b) => b.timerStart.compareTo(a.timerStart));
    }
    return _nativeSorted;
  }

  List<NativeRow> _nativeSyncWalRows(SyncProvider owner, Wal wal, int index) {
    final l = context.l10n;
    final state = wal.syncDisplayState;
    final hasError = owner.failedWal?.id == wal.id;
    final syncing = state == WalSyncDisplayState.syncing;
    final source = WalListItem._sourceOf(context, wal);
    final time = OmiDateFormat.of(context).time(DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000));
    final duration = OmiDuration.compact(wal.seconds, l);
    // The recording id keeps a command from an older snapshot off a row that shifted position.
    final id = 'sync_wal:$index:${wal.id}';
    final rows = [
      NativeRow(id, source != null ? '$time · $duration · $source' : '$time · $duration',
          kind: 'navigation',
          subtitle: WalListItem._statusOf(context, wal, hasError).$2,
          options: {if (!syncing) 'delete': l.delete},
          swipeTrailing: syncing ? const [] : const ['delete'], action: (value) async {
        if (value == 'delete') {
          await _confirmNativeWalDelete(owner, wal, processing: wal.syncDisplayState == WalSyncDisplayState.uploaded);
        } else {
          await routeToPage(context, WalItemDetailPage(wal: wal));
        }
      }),
    ];
    if (WalListItem._showsProgress(wal)) {
      final fraction = WalListItem._calcProgress(wal);
      final speed = wal.syncSpeedKBps;
      final eta = wal.syncEtaSeconds;
      rows.add(NativeRow(
          '$id:progress',
          [
            '${(fraction * 100).round()}%',
            if (speed != null && speed > 0 && speed.isFinite) '${speed.toStringAsFixed(1)} KB/s',
            if (eta != null && eta > 0) l.etaLabel(OmiDuration.compact(eta, l)),
          ].join(' · '),
          kind: 'progress',
          value: fraction,
          maximumValue: 1));
    }
    if (hasError || state == WalSyncDisplayState.failed || state == WalSyncDisplayState.retrying) {
      rows.add(NativeRow('$id:retry', l.tryAgain, action: (_) => owner.syncWal(wal)));
    } else if (WalListItem._unsyncable(state)) {
      rows.add(NativeRow('$id:delete', l.delete,
          destructive: true, action: (_) => _confirmNativeWalDelete(owner, wal, processing: false)));
    }
    return rows;
  }

  /// The original swipe and Delete confirmations; a recording still processing on the server warns
  /// that its conversation may not appear.
  Future<void> _confirmNativeWalDelete(SyncProvider owner, Wal wal, {required bool processing}) async {
    final l = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: processing ? l.deleteWhileProcessingTitle : l.deleteRecording,
      message: processing ? l.deleteWhileProcessingMessage : l.thisCannotBeUndone,
      confirmLabel: l.delete,
      destructive: true,
    );
    if (confirmed && mounted) await owner.deleteWal(wal);
  }
}

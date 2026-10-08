part of 'wal_item_detail_page.dart';

/// The SwiftUI recording-file detail. [SyncProvider] (with its single audio player) stays the only
/// transfer, playback, share and delete owner; only labels, the transfer progress and waveform
/// levels cross the bridge, never a file path or audio. The classic page is the fallback.
extension _NativeWalDetailPresentation on _WalItemDetailPageState {
  Widget _nativeDetail(Widget classic) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      body: Consumer<SyncProvider>(
        builder: (context, syncProvider, child) {
          final l10n = context.l10n;
          final currentWal = syncProvider.getWalById(widget.wal.id) ?? widget.wal;
          final transferred =
              _needsTransfer && currentWal.storage != WalStorage.sdcard && currentWal.storage != WalStorage.flashPage;
          if (transferred) {
            // Like the classic page; the classic fallback is not built too, so it cannot pop again.
            _popOnceTransferred();
            return const OmiLoadingState();
          }
          final isTransferring = currentWal.isSyncing;
          return IosNativeSurface(
            title: l10n.recordingDetails,
            fallback: classic,
            toolbar: [
              NativeRow('wal_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
              NativeRow('wal_more', l10n.moreOptions, kind: 'menu', symbol: 'ellipsis', options: {
                'info': l10n.recordingInfo,
                if (_needsTransfer && !isTransferring) 'transfer': l10n.transferToPhone,
                if (!_needsTransfer) 'share': l10n.shareRecording,
                if (!isTransferring) 'delete': l10n.deleteRecording,
              }, action: (value) async {
                switch (value) {
                  case 'info':
                    await _showNativeFileDetails();
                  case 'transfer':
                    await _handleTransferToPhone();
                  case 'share':
                    await _handleShare(syncProvider);
                  case 'delete':
                    _showDeleteDialog(context);
                }
              }),
            ],
            sections: [
              _nativeHeader(),
              if (_needsTransfer)
                ..._nativeTransfer(syncProvider, currentWal, isTransferring)
              else
                ..._nativePlayback(syncProvider),
            ],
          );
        },
      ),
    );
  }

  /// The classic page pops once the WAL leaves device storage; the native page does too, exactly
  /// once, and only while this route is on top. The owner notifies before Transfer to Phone
  /// completes, so its success handler skips its own pop once this one is scheduled.
  void _popOnceTransferred() {
    if (_leavingTransferred) return;
    _leavingTransferred = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && ModalRoute.of(context)?.isCurrent != false) Navigator.of(context).pop();
    });
  }

  NativeSection _nativeHeader() {
    final l10n = context.l10n;
    final start = DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000);
    final dates = OmiDateFormat.of(context);
    final isFlashPage = widget.wal.storage == WalStorage.flashPage;
    return NativeSection('wal_header', [
      NativeRow('wal_date', dates.date(start), kind: 'label', subtitle: dates.time(start)),
      if (_needsTransfer)
        NativeRow('wal_storage',
            l10n.storedOnDevice(isFlashPage ? l10n.storageLocationLimitlessPendant : l10n.storageLocationSdCard),
            kind: 'label', symbol: isFlashPage ? 'memorychip' : 'sdcard')
      else
        NativeRow('wal_storage', l10n.privateAndSecureOnDevice, kind: 'label', symbol: 'lock.shield'),
    ]);
  }

  List<NativeSection> _nativeTransfer(SyncProvider syncProvider, Wal currentWal, bool isTransferring) {
    final l10n = context.l10n;
    final rawProgress = syncProvider.walsSyncedProgress;
    final progress = rawProgress.isFinite ? rawProgress.clamp(0.0, 1.0).toDouble() : 0.0;
    final speed = currentWal.syncSpeedKBps;
    final eta = currentWal.syncEtaSeconds;
    return [
      NativeSection('wal_transfer', [
        NativeRow('wal_transfer_status', isTransferring ? l10n.transferring : l10n.transferRequired,
            kind: 'label',
            symbol: isTransferring ? 'arrow.down.circle' : 'sdcard',
            subtitle: isTransferring ? l10n.downloadingAudioFromSdCard : l10n.transferRequiredDescription),
        if (isTransferring)
          NativeRow('wal_transfer_progress', l10n.transferring,
              kind: 'progress',
              value: progress,
              maximumValue: 1,
              subtitle: [
                '${(progress * 100).toInt()}%',
                if (speed != null && speed.isFinite && speed > 0) '${speed.toStringAsFixed(1)} KB/s',
                if (eta != null && eta > 0) l10n.etaLabel(_formatTransferEta(eta)),
              ].join(' · ')),
        if (isTransferring)
          NativeRow('wal_cancel_transfer', l10n.cancelTransfer,
              symbol: 'xmark', destructive: true, action: (_) => _handleCancelTransfer())
        else
          NativeRow('wal_transfer', l10n.transferToPhone,
              symbol: 'arrow.down.circle', action: (_) => _handleTransferToPhone()),
      ]),
    ];
  }

  List<NativeSection> _nativePlayback(SyncProvider syncProvider) {
    final l10n = context.l10n;
    final playback = _getPlaybackState(syncProvider);
    final isPlaying = syncProvider.isWalPlaying(widget.wal.id);
    final maximum = nativePlaybackMaximum(playback.totalDuration, widget.wal.seconds);
    final position = isPlaying ? playback.currentPosition : Duration.zero;
    final seconds = (position.inMilliseconds / 1000).clamp(0.0, maximum ?? 0.0).toDouble();
    final transport = playback.canPlayOrShare && isPlaying;
    return [
      NativeSection('wal_player', [
        if (_isProcessingWaveform) NativeRow('wal_waveform_loading', l10n.loadingYourRecording, kind: 'label'),
        if (maximum != null)
          NativeRow('wal_position', l10n.recordings,
              kind: 'slider',
              value: seconds,
              maximumValue: maximum,
              subtitle: '${_formatDuration(position)} / ${OmiDuration.offset(maximum.round())}',
              points: _isProcessingWaveform ? const [] : nativeWaveformPoints(_waveformData, maximum),
              enabled: transport,
              action: (value) => syncProvider.seekToPosition(Duration(milliseconds: ((value as num) * 1000).round()))),
      ]),
      NativeSection('wal_transport', [
        NativeRow('wal_back10', l10n.skipBack10Seconds,
            symbol: 'gobackward.10', enabled: transport, action: (_) => _handleSkipBackward(syncProvider)),
        NativeRow(
          'wal_play',
          isPlaying ? l10n.pause : l10n.play,
          symbol: isPlaying ? 'pause.fill' : 'play.fill',
          subtitle: playback.isProcessing ? l10n.processing : '',
          enabled: playback.canPlayOrShare && !playback.isProcessing,
          action: (_) => _handlePlayPause(syncProvider),
        ),
        NativeRow('wal_fwd10', l10n.skipForward10Seconds,
            symbol: 'goforward.10', enabled: transport, action: (_) => _handleSkipForward(syncProvider)),
      ]),
    ];
  }

  /// Recording info as a native sheet of labels, with the device artwork once its copy is ready;
  /// the Flutter dialog when it cannot be presented.
  Future<void> _showNativeFileDetails() async {
    final l10n = context.l10n;
    final wal = widget.wal;
    final result = await showIosNativeModal(context, title: l10n.recordingInfo, cancelId: 'close', actions: [
      NativeRow('close', l10n.close),
    ], sections: [
      NativeSection('wal_info', [
        NativeRow('wal_info_id', l10n.recordingIdLabel, kind: 'label', subtitle: wal.id),
        NativeRow('wal_info_date', l10n.dateTimeLabel,
            kind: 'label',
            subtitle: OmiDateFormat.of(context).dateTime(DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000))),
        NativeRow('wal_info_duration', l10n.durationLabel,
            kind: 'label', subtitle: OmiDuration.long(wal.seconds, l10n)),
        NativeRow('wal_info_format', l10n.audioFormatLabel, kind: 'label', subtitle: wal.codec.toFormattedString()),
        NativeRow('wal_info_storage', l10n.storageLocationLabel,
            kind: 'label', subtitle: _getStorageLocationLabel(wal.storage, context)),
        NativeRow('wal_info_size', l10n.estimatedSizeLabel, kind: 'label', subtitle: _estimateFileSize()),
        NativeRow('wal_info_model', l10n.deviceModelLabel,
            kind: 'label', subtitle: wal.deviceModel ?? l10n.unknownDevice, imageUri: _nativeDeviceImage),
        if (wal.device.isNotEmpty && wal.device != 'phone')
          NativeRow('wal_info_device', l10n.deviceIdLabel, kind: 'label', subtitle: wal.device),
        NativeRow('wal_info_status', l10n.statusLabel,
            kind: 'label', subtitle: wal.status == WalStatus.synced ? l10n.statusProcessed : l10n.statusUnprocessed),
      ]),
    ]);
    if (result == null && mounted) _showFileDetailsDialog(context);
  }
}

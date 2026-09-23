import 'dart:async';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:provider/provider.dart';
import 'package:omi/models/playback_state.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/widgets/waveform_section.dart';
import 'package:omi/ui/ui.dart';

class WalItemDetailPage extends StatefulWidget {
  final Wal wal;

  const WalItemDetailPage({super.key, required this.wal});

  @override
  State<WalItemDetailPage> createState() => _WalItemDetailPageState();
}

class _WalItemDetailPageState extends State<WalItemDetailPage> {
  List<double>? _waveformData;
  bool _isProcessingWaveform = false;
  SyncProvider? _syncProvider;

  /// Returns true if WAL is still on device storage (SD card or flash page) and needs transfer
  bool get _needsTransfer => widget.wal.storage == WalStorage.sdcard || widget.wal.storage == WalStorage.flashPage;

  @override
  void initState() {
    super.initState();
    if (!_needsTransfer) {
      _generateWaveform();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Save reference to SyncProvider to use safely in dispose()
    _syncProvider = context.read<SyncProvider>();
  }

  @override
  void dispose() {
    // Stop audio playback when exiting the detail page
    if (_syncProvider != null && _syncProvider!.isWalPlaying(widget.wal.id)) {
      _syncProvider!.toggleWalPlayback(widget.wal);
    }
    super.dispose();
  }

  Future<void> _generateWaveform() async {
    if (!mounted) return;

    setState(() {
      _isProcessingWaveform = true;
    });

    final syncProvider = context.read<SyncProvider>();
    final waveformData = await syncProvider.getWaveformForWal(widget.wal.id);

    if (mounted) {
      setState(() {
        _waveformData = waveformData;
        _isProcessingWaveform = false;
      });
    }
  }

  PlaybackState _getPlaybackState(SyncProvider syncProvider) {
    return PlaybackState(
      isPlaying: syncProvider.isWalPlaying(widget.wal.id),
      isProcessing: syncProvider.isProcessingAudio && syncProvider.currentPlayingWalId == widget.wal.id,
      canPlayOrShare: syncProvider.canPlayOrShareWal(widget.wal),
      isSynced: widget.wal.status == WalStatus.synced,
      hasError: syncProvider.failedWal?.id == widget.wal.id,
      currentPosition: syncProvider.currentPosition,
      totalDuration: syncProvider.totalDuration,
      playbackProgress: syncProvider.playbackProgress,
    );
  }

  void _showConfirm(String message) {
    if (mounted) OmiFeedback.confirm(context, message);
  }

  void _showError(String message) {
    if (mounted) OmiFeedback.error(context, message);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.recordingDetails),
        actions: [
          OmiIconButton(
            icon: const Icon(Icons.more_horiz),
            label: context.l10n.moreOptions,
            onPressed: () => _showOptionsMenu(context),
          ),
          const SizedBox(width: OmiSpacing.xxs),
        ],
      ),
      backgroundColor: OmiColors.surface0,
      body: _needsTransfer ? _buildDeviceTransferUI() : _buildPlaybackUI(),
    );
  }

  String _formatTransferEta(int seconds) => OmiDuration.compact(seconds, context.l10n);

  String _getStorageLocationLabel(WalStorage storage, BuildContext context) {
    switch (storage) {
      case WalStorage.sdcard:
        return context.l10n.storageLocationSdCard;
      case WalStorage.flashPage:
        return context.l10n.storageLocationLimitlessPendant;
      case WalStorage.disk:
        return context.l10n.storageLocationPhone;
      case WalStorage.mem:
        return context.l10n.storageLocationPhoneMemory;
    }
  }

  Widget _buildDeviceTransferUI() {
    final isFlashPage = widget.wal.storage == WalStorage.flashPage;
    final storageLabel =
        isFlashPage ? context.l10n.storageLocationLimitlessPendant : context.l10n.storageLocationSdCard;
    final storageIcon = isFlashPage ? Icons.memory : Icons.sd_card;
    final storageColor = isFlashPage ? Colors.teal : OmiColors.textSecondary;

    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final currentWal = syncProvider.getWalById(widget.wal.id) ?? widget.wal;
        final isTransferring = currentWal.isSyncing;
        final transferProgress = syncProvider.walsSyncedProgress;
        final transferSpeedKBps = currentWal.syncSpeedKBps;
        final transferEtaSeconds = currentWal.syncEtaSeconds;

        if (currentWal.storage != WalStorage.sdcard && currentWal.storage != WalStorage.flashPage) {
          // WAL has been transferred, pop back to refresh
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.of(context).pop();
            }
          });
          return const OmiLoadingState();
        }

        return Column(
          children: [
            // Title section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              child: Column(
                children: [
                  Text(
                    OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                    style: OmiType.title1,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    OmiDateFormat.of(context).time(DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                          color: Colors.grey.shade400,
                          fontSize: 16,
                          fontWeight: FontWeight.w400,
                        ),
                  ),
                  const SizedBox(height: 8),
                  // Storage notice
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: storageColor.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(storageIcon, color: storageColor, size: 14),
                        const SizedBox(width: 6),
                        Text(
                          context.l10n.storedOnDevice(storageLabel),
                          style: TextStyle(color: storageColor, fontSize: 12, fontWeight: FontWeight.w500),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Center content - Transfer UI
            Expanded(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 40),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // SD Card icon
                      Container(
                        width: 120,
                        height: 120,
                        decoration: const BoxDecoration(color: OmiColors.surface1, shape: BoxShape.circle),
                        child: Center(
                          child: Icon(
                            isTransferring ? Icons.downloading : Icons.sd_card,
                            size: 56,
                            color: OmiColors.textPrimary,
                          ),
                        ),
                      ),
                      const SizedBox(height: 32),

                      // Status text
                      Text(
                        isTransferring ? context.l10n.transferring : context.l10n.transferRequired,
                        style: Theme.of(
                          context,
                        ).textTheme.titleLarge!.copyWith(fontSize: 22, fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        isTransferring
                            ? context.l10n.downloadingAudioFromSdCard
                            : context.l10n.transferRequiredDescription,
                        style: Theme.of(
                          context,
                        ).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade400, fontSize: 14),
                        textAlign: TextAlign.center,
                      ),

                      // Progress indicator
                      if (isTransferring) ...[
                        const SizedBox(height: 32),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: transferProgress > 0 ? transferProgress : null,
                            backgroundColor: Colors.grey.shade800,
                            color: OmiColors.accent,
                            minHeight: 6,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              '${(transferProgress * 100).toInt()}%',
                              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, fontWeight: FontWeight.w500),
                            ),
                            if (transferSpeedKBps != null && transferSpeedKBps > 0) ...[
                              const SizedBox(width: 16),
                              Text(
                                '${transferSpeedKBps.toStringAsFixed(1)} KB/s',
                                style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
                              ),
                            ],
                          ],
                        ),
                        if (transferEtaSeconds != null && transferEtaSeconds > 0) ...[
                          const SizedBox(height: 8),
                          Text(
                            context.l10n.etaLabel(_formatTransferEta(transferEtaSeconds)),
                            style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                          ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
            ),

            // Transfer button
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 42),
              child: isTransferring
                  ? OmiButton.secondary(
                      label: context.l10n.cancelTransfer,
                      icon: Icons.close,
                      expand: true,
                      onPressed: _handleCancelTransfer,
                    )
                  : OmiButton(
                      label: context.l10n.transferToPhone,
                      icon: Icons.download,
                      expand: true,
                      onPressed: _handleTransferToPhone,
                    ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildPlaybackUI() {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final playbackState = _getPlaybackState(syncProvider);
        final isPlaying = syncProvider.isWalPlaying(widget.wal.id);

        return Column(
          children: [
            // Title section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              child: Column(
                children: [
                  Text(
                    OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                    style: OmiType.title1,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    OmiDateFormat.of(context).time(DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                          color: Colors.grey.shade400,
                          fontSize: 16,
                          fontWeight: FontWeight.w400,
                        ),
                  ),
                  const SizedBox(height: 8),
                  // Privacy notice
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.grey.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.security, color: Colors.grey.shade400, size: 14),
                        const SizedBox(width: 6),
                        Text(
                          context.l10n.privateAndSecureOnDevice,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w500),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Waveform section - dominant space
            Expanded(
              flex: 6,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: WaveformSection(
                  seconds: widget.wal.seconds,
                  waveformData: _waveformData,
                  isProcessingWaveform: _isProcessingWaveform,
                  playbackState: playbackState,
                  isPlaying: isPlaying,
                ),
              ),
            ),

            // Timer display
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Consumer<SyncProvider>(
                builder: (context, syncProvider, child) {
                  final currentPos = isPlaying ? playbackState.currentPosition : Duration.zero;
                  return Text(
                    _formatDuration(currentPos),
                    style: Theme.of(
                      context,
                    ).textTheme.titleLarge!.copyWith(fontSize: 48, fontWeight: FontWeight.w300, letterSpacing: 2),
                  );
                },
              ),
            ),

            // Controls section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _buildControlButton(
                    icon: FontAwesomeIcons.backward,
                    onPressed: playbackState.canPlayOrShare && isPlaying
                        ? () => _handleSkipBackward(context.read<SyncProvider>())
                        : null,
                    size: 60,
                  ),
                  _buildControlButton(
                    icon: playbackState.isProcessing
                        ? FontAwesomeIcons.hourglass
                        : (isPlaying ? FontAwesomeIcons.pause : FontAwesomeIcons.play),
                    size: 80,
                    backgroundColor: Theme.of(context).colorScheme.secondary,
                    iconColor: Colors.white,
                    onPressed: playbackState.canPlayOrShare && !playbackState.isProcessing
                        ? () => _handlePlayPause(context.read<SyncProvider>())
                        : null,
                  ),
                  _buildControlButton(
                    icon: FontAwesomeIcons.forward,
                    onPressed: playbackState.canPlayOrShare && isPlaying
                        ? () => _handleSkipForward(context.read<SyncProvider>())
                        : null,
                    size: 60,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 32),
          ],
        );
      },
    );
  }

  /// The playback position ("3:38", "1:02:05"); never drops the hours (tokens audit #20).
  String _formatDuration(Duration duration) => OmiDuration.offset(duration.inSeconds);

  Widget _buildControlButton({
    required FaIconData icon,
    VoidCallback? onPressed,
    double size = 48,
    Color? backgroundColor,
    Color? iconColor,
  }) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: backgroundColor ?? Theme.of(context).colorScheme.surface,
        shape: BoxShape.circle,
      ),
      child: IconButton(
        onPressed: onPressed,
        icon: FaIcon(icon, color: iconColor ?? Colors.white, size: size * 0.4),
      ),
    );
  }

  Future<void> _handleTransferToPhone() async {
    if (!mounted) return;

    try {
      final syncProvider = context.read<SyncProvider>();
      await syncProvider.transferWalToPhone(widget.wal);

      if (mounted) {
        _showConfirm(context.l10n.transferCompleteMessage);
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        _showError(context.l10n.transferFailedMessage(readableError(e)));
      }
    }
  }

  void _handleCancelTransfer() {
    final syncProvider = context.read<SyncProvider>();
    syncProvider.cancelSync();
    if (mounted) OmiFeedback.info(context, context.l10n.transferCancelled);
    // Pop back since the WAL state will change
    Navigator.of(context).pop();
  }

  Future<void> _handlePlayPause(SyncProvider syncProvider) async {
    await syncProvider.toggleWalPlayback(widget.wal);
  }

  Future<void> _handleSkipBackward(SyncProvider syncProvider) async {
    await syncProvider.skipBackward();
  }

  Future<void> _handleSkipForward(SyncProvider syncProvider) async {
    await syncProvider.skipForward();
  }

  void _showOptionsMenu(BuildContext context) {
    final syncProvider = context.read<SyncProvider>();
    final currentWal = syncProvider.getWalById(widget.wal.id) ?? widget.wal;
    final isTransferring = currentWal.isSyncing;

    showOmiSheet<void>(
      context: context,
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
      builder: (sheetContext) => OmiSettingsGroup(
        children: [
          OmiSettingsRow(
            leading: const Icon(Icons.info_outline),
            title: context.l10n.recordingInfo,
            showChevron: false,
            onTap: () {
              Navigator.pop(sheetContext);
              _showFileDetailsDialog(context);
            },
          ),
          if (_needsTransfer)
            OmiSettingsRow(
              leading: const Icon(Icons.download),
              title: isTransferring ? context.l10n.transferInProgress : context.l10n.transferToPhone,
              showChevron: false,
              onTap: isTransferring
                  ? null
                  : () {
                      Navigator.pop(sheetContext);
                      _handleTransferToPhone();
                    },
            )
          else
            OmiSettingsRow(
              leading: const Icon(Icons.ios_share_rounded),
              title: context.l10n.shareRecording,
              showChevron: false,
              onTap: () {
                Navigator.pop(sheetContext);
                _handleShare(context.read<SyncProvider>());
              },
            ),
          OmiSettingsRow(
            leading: const Icon(Icons.delete_outline),
            title: context.l10n.deleteRecording,
            isDestructive: !isTransferring,
            showChevron: false,
            onTap: isTransferring
                ? null
                : () {
                    Navigator.pop(sheetContext);
                    _showDeleteDialog(context);
                  },
          ),
        ],
      ),
    );
  }

  void _showDeleteDialog(BuildContext context) async {
    final uploading = widget.wal.syncDisplayState == WalSyncDisplayState.uploaded;
    final confirmed = await showOmiConfirm(
      context,
      title: uploading ? context.l10n.deleteWhileProcessingTitle : context.l10n.deleteRecording,
      message: uploading ? context.l10n.deleteWhileProcessingMessage : context.l10n.deleteRecordingConfirmation,
      confirmLabel: context.l10n.delete,
      destructive: true,
    );

    if (confirmed && context.mounted) {
      Navigator.of(context).pop(); // Go back to previous screen
      context.read<SyncProvider>().deleteWal(widget.wal);
    }
  }

  Future<void> _handleShare(SyncProvider syncProvider) async {
    try {
      await syncProvider.shareWalAsWav(widget.wal);
    } catch (e) {
      Logger.error('AudioPlayerUtils: Failed to share WAL audio: $e');
      if (mounted) {
        OmiFeedback.error(context, context.l10n.audioPlaybackFailed);
      }
    }
  }

  void _showFileDetailsDialog(BuildContext context) {
    final recordingDate = DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000);
    final estimatedSize = _estimateFileSize();

    showDialog<void>(
      context: context,
      builder: (dialogContext) => OmiAlertDialog(
        content: Material(
          type: MaterialType.transparency,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 16.0),
                  child: Image.asset(DeviceUtils.getDeviceImagePath(deviceName: widget.wal.deviceModel), height: 60),
                ),
              ),
              _buildDetailRow(context.l10n.recordingIdLabel, widget.wal.id),
              _buildDetailRow(context.l10n.dateTimeLabel, OmiDateFormat.of(context).dateTime(recordingDate)),
              _buildDetailRow(context.l10n.durationLabel, OmiDuration.long(widget.wal.seconds, context.l10n)),
              _buildDetailRow(context.l10n.audioFormatLabel, widget.wal.codec.toFormattedString()),
              _buildDetailRow(context.l10n.storageLocationLabel, _getStorageLocationLabel(widget.wal.storage, context)),
              _buildDetailRow(context.l10n.estimatedSizeLabel, estimatedSize),
              _buildDetailRow(context.l10n.deviceModelLabel, widget.wal.deviceModel ?? context.l10n.unknownDevice),
              if (widget.wal.device.isNotEmpty && widget.wal.device != "phone")
                _buildDetailRow(context.l10n.deviceIdLabel, widget.wal.device),
              _buildDetailRow(
                context.l10n.statusLabel,
                widget.wal.status == WalStatus.synced ? context.l10n.statusProcessed : context.l10n.statusUnprocessed,
              ),
            ],
          ),
        ),
        actions: [
          OmiDialogAction(
            label: context.l10n.close,
            isDefault: true,
            onPressed: () => Navigator.of(dialogContext).pop(),
          ),
        ],
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          const SizedBox(height: 2),
          Text(value, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    );
  }

  String _estimateFileSize() {
    final totalBytes = widget.wal.codec.estimatedRecordingBytes(
      seconds: widget.wal.seconds,
      sampleRate: widget.wal.sampleRate,
      channels: widget.wal.channel,
    );
    return _formatBytes(totalBytes);
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}

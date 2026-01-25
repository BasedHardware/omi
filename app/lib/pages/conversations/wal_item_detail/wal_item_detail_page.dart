import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/playback_state.dart';
import 'package:omi/pages/conversations/sync_widgets/fast_transfer_suggestion_dialog.dart';
import 'package:omi/pages/conversations/sync_widgets/location_permission_dialog.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices/wifi_sync_error.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/services/wifi/wifi_network_service.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/pages/conversations/sync_widgets/wifi_connection_sheet.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/waveform_section.dart';

class WalItemDetailPage extends StatefulWidget {
  final Wal wal;

  const WalItemDetailPage({super.key, required this.wal});

  @override
  State<WalItemDetailPage> createState() => _WalItemDetailPageState();
}

class _WalItemDetailPageState extends State<WalItemDetailPage> {
  List<double>? _waveformData;
  bool _isProcessingWaveform = false;
  bool _isSharing = false;
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

  void _showSnackBar(String message, [Color? backgroundColor]) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: backgroundColor,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        elevation: 0,
        automaticallyImplyLeading: true,
        title: Text(context.l10n.recordingDetails, style: Theme.of(context).textTheme.titleLarge),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.more_horiz, color: Colors.white),
            onPressed: () => _showOptionsMenu(context),
          ),
        ],
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: _needsTransfer ? _buildDeviceTransferUI() : _buildPlaybackUI(),
    );
  }

  String _formatTransferEta(int seconds) {
    if (seconds < 60) {
      return '${seconds}s';
    } else if (seconds < 3600) {
      final minutes = seconds ~/ 60;
      final secs = seconds % 60;
      return '${minutes}m ${secs}s';
    } else {
      final hours = seconds ~/ 3600;
      final minutes = (seconds % 3600) ~/ 60;
      return '${hours}h ${minutes}m';
    }
  }

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
    final storageColor = isFlashPage ? Colors.teal : Colors.deepPurpleAccent;

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
          return const Center(child: CircularProgressIndicator());
        }

        return Column(
          children: [
            // Title section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              child: Column(
                children: [
                  Text(
                    dateTimeFormat('dd MMM yyyy', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(
                          fontSize: 28,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    dateTimeFormat('H:mm', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
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
                      color: storageColor.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(storageIcon, color: storageColor, size: 14),
                        const SizedBox(width: 6),
                        Text(
                          context.l10n.storedOnDevice(storageLabel),
                          style: TextStyle(
                            color: storageColor,
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                          ),
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
                        decoration: BoxDecoration(
                          color: Colors.deepPurple.withOpacity(0.1),
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: Icon(
                            isTransferring ? Icons.downloading : Icons.sd_card,
                            size: 56,
                            color: Colors.deepPurpleAccent,
                          ),
                        ),
                      ),
                      const SizedBox(height: 32),

                      // Status text
                      Text(
                        isTransferring ? context.l10n.transferring : context.l10n.transferRequired,
                        style: Theme.of(context).textTheme.titleLarge!.copyWith(
                              fontSize: 22,
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        isTransferring
                            ? context.l10n.downloadingAudioFromSdCard
                            : context.l10n.transferRequiredDescription,
                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                              color: Colors.grey.shade400,
                              fontSize: 14,
                            ),
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
                            color: Colors.deepPurpleAccent,
                            minHeight: 6,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              '${(transferProgress * 100).toInt()}%',
                              style: TextStyle(
                                color: Colors.grey.shade400,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            if (transferSpeedKBps != null && transferSpeedKBps > 0) ...[
                              const SizedBox(width: 16),
                              Text(
                                '${transferSpeedKBps.toStringAsFixed(1)} KB/s',
                                style: TextStyle(
                                  color: Colors.grey.shade500,
                                  fontSize: 14,
                                ),
                              ),
                            ],
                          ],
                        ),
                        if (transferEtaSeconds != null && transferEtaSeconds > 0) ...[
                          const SizedBox(height: 8),
                          Text(
                            'ETA: ${_formatTransferEta(transferEtaSeconds)}',
                            style: TextStyle(
                              color: Colors.grey.shade500,
                              fontSize: 13,
                            ),
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
              child: SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton(
                  onPressed: isTransferring ? _handleCancelTransfer : _handleTransferToPhone,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: isTransferring ? Colors.orange : Colors.deepPurpleAccent,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        isTransferring ? Icons.close : Icons.download,
                        color: Colors.white,
                        size: 22,
                      ),
                      const SizedBox(width: 12),
                      Text(
                        isTransferring ? context.l10n.cancelTransfer : context.l10n.transferToPhone,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
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
                    dateTimeFormat('dd MMM yyyy', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(
                          fontSize: 28,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    dateTimeFormat('H:mm', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
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
                      color: Colors.grey.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.security, color: Colors.grey.shade400, size: 14),
                        const SizedBox(width: 6),
                        Text(
                          context.l10n.privateAndSecureOnDevice,
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                          ),
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
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(
                          fontSize: 48,
                          fontWeight: FontWeight.w300,
                          letterSpacing: 2,
                        ),
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
                    icon: Icons.replay_10,
                    onPressed: playbackState.canPlayOrShare && isPlaying
                        ? () => _handleSkipBackward(context.read<SyncProvider>())
                        : null,
                    size: 60,
                  ),
                  _buildControlButton(
                    icon: playbackState.isProcessing
                        ? Icons.hourglass_empty
                        : (isPlaying ? Icons.pause : Icons.play_arrow),
                    size: 80,
                    backgroundColor: Theme.of(context).colorScheme.secondary,
                    iconColor: Colors.white,
                    onPressed: playbackState.canPlayOrShare && !playbackState.isProcessing
                        ? () => _handlePlayPause(context.read<SyncProvider>())
                        : null,
                  ),
                  _buildControlButton(
                    icon: Icons.forward_10,
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

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);
    final milliseconds = (duration.inMilliseconds.remainder(1000) / 10).floor();
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')},${milliseconds.toString().padLeft(2, '0')}';
  }

  Widget _buildControlButton({
    required IconData icon,
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
        icon: Icon(
          icon,
          color: iconColor ?? Colors.white,
          size: size * 0.4,
        ),
      ),
    );
  }

  Future<void> _handleTransferToPhone() async {
    final preferredMethod = SharedPreferencesUtil().preferredSyncMethod;
    final wifiSupported = await ServiceManager.instance().wal.getSyncs().sdcard.isWifiSyncSupported();

    bool wifiHardwareAvailable = false;
    if (wifiSupported && widget.wal.storage == WalStorage.sdcard) {
      wifiHardwareAvailable = await _checkWifiHardwareAvailable();
      if (!wifiHardwareAvailable && preferredMethod == 'wifi') {
        SharedPreferencesUtil().preferredSyncMethod = 'ble';
        if (mounted) {
          _showSnackBar(context.l10n.deviceDoesNotSupportWifiSwitchingToBle, Colors.orange);
        }
      }
    }

    if (preferredMethod == 'ble' && wifiHardwareAvailable && widget.wal.storage == WalStorage.sdcard) {
      if (!mounted) return;
      final result = await FastTransferSuggestionDialog.show(context);
      if (result == null) return;

      if (result == 'switch') {
        // User wants to switch to Fast Transfer
        SharedPreferencesUtil().preferredSyncMethod = 'wifi';
        if (!mounted) return;
        _showSnackBar(context.l10n.switchedToFastTransfer, Colors.green);
      }
    }

    final currentMethod = SharedPreferencesUtil().preferredSyncMethod;
    if (Platform.isIOS && widget.wal.storage == WalStorage.sdcard) {
      if (currentMethod == 'wifi' && wifiHardwareAvailable) {
        if (!mounted) return;
        final hasPermission = await LocationPermissionHelper.checkAndRequest(context);
        if (!hasPermission) {
          return;
        }
      }
    }

    if (!mounted) return;

    try {
      final syncProvider = context.read<SyncProvider>();
      final currentMethod = SharedPreferencesUtil().preferredSyncMethod;

      // Show WiFi connection sheet if using WiFi for SD card transfer
      if (currentMethod == 'wifi' && wifiHardwareAvailable && widget.wal.storage == WalStorage.sdcard && mounted) {
        WifiConnectionListenerBridge? listener;

        final sheetController = await WifiConnectionSheet.show(
          context,
          deviceName: 'Omi',
          onCancel: () {
            syncProvider.cancelSync();
          },
          onRetry: () {
            if (listener != null) {
              syncProvider.transferWalToPhone(widget.wal, connectionListener: listener);
            }
          },
        );

        listener = WifiConnectionListenerBridge(sheetController);
        await syncProvider.transferWalToPhone(widget.wal, connectionListener: listener);
      } else {
        await syncProvider.transferWalToPhone(widget.wal);
      }

      if (mounted) {
        _showSnackBar(context.l10n.transferCompleteMessage, Colors.green);
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        _showSnackBar(context.l10n.transferFailedMessage(e.toString()), Colors.red);
      }
    }
  }

  Future<bool> _checkWifiHardwareAvailable() async {
    try {
      final connection = await ServiceManager.instance().device.ensureConnection(widget.wal.device);
      if (connection == null) {
        return true;
      }

      final ssid = WifiNetworkService.generateSsid(widget.wal.device);
      final password = WifiNetworkService.generatePassword(widget.wal.device);

      final result = await connection.setupWifiSync(ssid, password);

      if (!result.success && result.errorCode == WifiSyncErrorCode.wifiHardwareNotAvailable) {
        return false;
      }

      if (result.success) {
        await connection.stopWifiSync();
      }

      return true;
    } catch (e) {
      debugPrint('Error checking WiFi hardware: $e');
      return true;
    }
  }

  void _handleCancelTransfer() {
    final syncProvider = context.read<SyncProvider>();
    syncProvider.cancelSync();
    _showSnackBar(context.l10n.transferCancelled, Colors.orange);
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

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F1F25),
      builder: (sheetContext) => Container(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.info_outline, color: Colors.white),
              title: Text(context.l10n.recordingInfo, style: Theme.of(sheetContext).textTheme.bodyMedium),
              onTap: () {
                Navigator.pop(sheetContext);
                _showFileDetailsDialog(context);
              },
            ),
            if (_needsTransfer) ...[
              ListTile(
                leading: Icon(Icons.download, color: isTransferring ? Colors.grey : Colors.white),
                title: Text(
                  isTransferring ? context.l10n.transferInProgress : context.l10n.transferToPhone,
                  style: Theme.of(sheetContext).textTheme.bodyMedium!.copyWith(
                        color: isTransferring ? Colors.grey : Colors.white,
                      ),
                ),
                onTap: isTransferring
                    ? null
                    : () {
                        Navigator.pop(sheetContext);
                        _handleTransferToPhone();
                      },
              ),
            ] else ...[
              ListTile(
                leading: const Icon(Icons.share, color: Colors.white),
                title: Text(context.l10n.shareRecording, style: Theme.of(sheetContext).textTheme.bodyMedium),
                onTap: () {
                  Navigator.pop(sheetContext);
                  _handleShare(context.read<SyncProvider>());
                },
              ),
            ],
            ListTile(
              leading: Icon(Icons.delete, color: isTransferring ? Colors.grey : Colors.red),
              title: Text(
                context.l10n.deleteRecording,
                style: Theme.of(sheetContext).textTheme.bodyMedium!.copyWith(
                      color: isTransferring ? Colors.grey : Colors.red,
                    ),
              ),
              onTap: isTransferring
                  ? null
                  : () {
                      Navigator.pop(sheetContext);
                      _showDeleteDialog(context);
                    },
            ),
          ],
        ),
      ),
    );
  }

  void _showDeleteDialog(BuildContext context) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.deleteRecording,
      message: context.l10n.deleteRecordingConfirmation,
      confirmLabel: context.l10n.delete,
      confirmColor: Colors.red,
    );

    if (confirmed == true && mounted) {
      Navigator.of(context).pop(); // Go back to previous screen
      context.read<SyncProvider>().deleteWal(widget.wal);
    }
  }

  Future<void> _handleShare(SyncProvider syncProvider) async {
    setState(() => _isSharing = true);
    try {
      await syncProvider.shareWalAsWav(widget.wal);
    } finally {
      if (mounted) {
        setState(() => _isSharing = false);
      }
    }
  }

  void _showFileDetailsDialog(BuildContext context) {
    final theme = Theme.of(context);
    final recordingDate = DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000);
    final estimatedSize = _estimateFileSize();

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1A),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 16.0),
                  child: Image.asset(
                    DeviceUtils.getDeviceImagePathByModel(widget.wal.deviceModel),
                    height: 60,
                  ),
                ),
              ),
              _buildDetailRow(context.l10n.recordingIdLabel, widget.wal.id),
              _buildDetailRow(context.l10n.dateTimeLabel, dateTimeFormat('MMM dd, yyyy h:mm:ss a', recordingDate)),
              _buildDetailRow(context.l10n.durationLabel, secondsToHumanReadable(widget.wal.seconds, context)),
              _buildDetailRow(context.l10n.audioFormatLabel, widget.wal.codec.toFormattedString()),
              _buildDetailRow(context.l10n.storageLocationLabel, _getStorageLocationLabel(widget.wal.storage, context)),
              _buildDetailRow(context.l10n.estimatedSizeLabel, estimatedSize),
              _buildDetailRow(context.l10n.deviceModelLabel, widget.wal.deviceModel ?? context.l10n.unknownDevice),
              if (widget.wal.device.isNotEmpty && widget.wal.device != "phone")
                _buildDetailRow(context.l10n.deviceIdLabel, widget.wal.device),
              _buildDetailRow(
                  context.l10n.statusLabel,
                  widget.wal.status == WalStatus.synced
                      ? context.l10n.statusProcessed
                      : context.l10n.statusUnprocessed),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(context.l10n.close,
                style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.secondary)),
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
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium!.copyWith(color: Colors.grey.shade400),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }

  String _estimateFileSize() {
    // Estimate size based on codec, sample rate, channels, and duration
    int bytesPerSecond;
    switch (widget.wal.codec) {
      case BleAudioCodec.opus:
      case BleAudioCodec.opusFS320:
        bytesPerSecond = widget.wal.codec == BleAudioCodec.opusFS320 ? 40000 : 8000; // ~320kbps vs ~64kbps
        break;
      case BleAudioCodec.pcm16:
        bytesPerSecond = widget.wal.sampleRate * 2 * widget.wal.channel; // 16-bit samples
        break;
      case BleAudioCodec.pcm8:
        bytesPerSecond = widget.wal.sampleRate * 1 * widget.wal.channel; // 8-bit samples
        break;
      case BleAudioCodec.mulaw16:
      case BleAudioCodec.mulaw8:
        bytesPerSecond = widget.wal.sampleRate * 1 * widget.wal.channel; // μ-law is 8-bit encoded
        break;
      default:
        bytesPerSecond = 8000;
    }

    final totalBytes = bytesPerSecond * widget.wal.seconds;
    return _formatBytes(totalBytes);
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}

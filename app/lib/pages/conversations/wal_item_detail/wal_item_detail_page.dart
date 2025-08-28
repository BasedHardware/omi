import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';

import 'widgets/wal_detail_app_bar.dart';
import 'widgets/wal_waveform_section.dart';
import 'widgets/wal_controls_section.dart';
import 'widgets/wal_info_section.dart';
import 'models/playback_state.dart';

class WalItemDetailPage extends StatefulWidget {
  final Wal wal;

  const WalItemDetailPage({super.key, required this.wal});

  @override
  State<WalItemDetailPage> createState() => _WalItemDetailPageState();
}

class _WalItemDetailPageState extends State<WalItemDetailPage> {
  List<double>? _waveformData;
  bool _isProcessingWaveform = false;

  @override
  void initState() {
    super.initState();
    _generateWaveform();
  }

  @override
  void dispose() {
    super.dispose();
  }

  Future<void> _generateWaveform() async {
    setState(() {
      _isProcessingWaveform = true;
    });

    try {
      final syncProvider = context.read<SyncProvider>();
      final waveformData = await syncProvider.getWaveformForWal(widget.wal.id);
      if (mounted) {
        setState(() {
          _waveformData = waveformData;
          _isProcessingWaveform = false;
        });
      }
    } catch (e) {
      debugPrint('Error generating waveform: $e');
      if (mounted) {
        setState(() {
          _isProcessingWaveform = false;
        });
      }
    }
  }

  PlaybackState _getPlaybackState(SyncProvider syncProvider) {
    return PlaybackState(
      isPlaying: syncProvider.isWalPlaying(widget.wal.id),
      isProcessing: syncProvider.isProcessingAudio && syncProvider.currentPlayingWalId == widget.wal.id,
      isSharing: syncProvider.isWalSharing(widget.wal.id),
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
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: WalDetailAppBar(
        wal: widget.wal,
        onDelete: () {
          Navigator.of(context).pop();
          context.read<SyncProvider>().deleteWal(widget.wal);
        },
      ),
      body: Consumer<SyncProvider>(
        builder: (context, syncProvider, child) {
          final playbackState = _getPlaybackState(syncProvider);

          return Column(
            children: [
              WalWaveformSection(
                wal: widget.wal,
                waveformData: _waveformData,
                isProcessingWaveform: _isProcessingWaveform,
                playbackState: playbackState,
              ),
              WalControlsSection(
                wal: widget.wal,
                playbackState: playbackState,
                onShowSnackBar: _showSnackBar,
              ),
              WalInfoSection(
                wal: widget.wal,
                playbackState: playbackState,
                onShowSnackBar: _showSnackBar,
              ),
            ],
          );
        },
      ),
    );
  }
}

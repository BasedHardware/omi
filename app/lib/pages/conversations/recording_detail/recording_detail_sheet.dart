import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/models/playback_state.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/waveform_section.dart';

/// Floating bottom sheet for a batch/offline recording — playback (waveform +
/// transport), the primary "Sync now" (transcribe → conversation) action, and
/// share / details / delete. Replaces the old full-page detail screen.
Future<void> showRecordingDetailSheet(BuildContext context, LocalRecording recording) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _RecordingDetailSheet(recording: recording),
  );
}

class _RecordingDetailSheet extends StatefulWidget {
  final LocalRecording recording;

  const _RecordingDetailSheet({required this.recording});

  @override
  State<_RecordingDetailSheet> createState() => _RecordingDetailSheetState();
}

class _RecordingDetailSheetState extends State<_RecordingDetailSheet> {
  List<double>? _waveformData;
  bool _isProcessingWaveform = false;
  LocalRecordingsProvider? _provider;

  @override
  void initState() {
    super.initState();
    _generateWaveform();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _provider = context.read<LocalRecordingsProvider>();
  }

  @override
  void dispose() {
    if (_provider != null && _provider!.isPlaying(widget.recording)) {
      _provider!.togglePlayback(widget.recording);
    }
    super.dispose();
  }

  Future<void> _generateWaveform() async {
    if (!mounted) return;
    setState(() => _isProcessingWaveform = true);
    final data = await context.read<LocalRecordingsProvider>().getWaveform(widget.recording);
    if (mounted) {
      setState(() {
        _waveformData = data;
        _isProcessingWaveform = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        margin: const EdgeInsets.fromLTRB(8, 8, 8, 8),
        decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(28)),
        child: SafeArea(
          top: false,
          child: Consumer<LocalRecordingsProvider>(
            builder: (context, provider, child) {
              final rec = provider.getById(widget.recording.id) ?? widget.recording;
              final isPlaying = provider.isPlaying(rec);
              final playbackState = PlaybackState(
                isPlaying: isPlaying,
                isProcessing: provider.isProcessingAudio && isPlaying,
                canPlayOrShare: provider.canPlay(rec),
                isSynced: false,
                hasError: rec.state == LocalRecordingState.failed,
                currentPosition: provider.currentPosition,
                totalDuration: provider.totalDuration,
                playbackProgress: provider.playbackProgress,
              );
              final canPlay = playbackState.canPlayOrShare;

              return Padding(
                padding: const EdgeInsets.fromLTRB(20, 10, 20, 16),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 36,
                      height: 4,
                      decoration: BoxDecoration(color: const Color(0xFF3C3C43), borderRadius: BorderRadius.circular(2)),
                    ),
                    const SizedBox(height: 18),
                    Text(
                      dateTimeFormat('dd MMM yyyy', rec.startedAt),
                      style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      dateTimeFormat('h:mm a', rec.startedAt),
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                    const SizedBox(height: 18),
                    SizedBox(
                      height: 120,
                      child: WaveformSection(
                        seconds: rec.seconds,
                        waveformData: _waveformData,
                        isProcessingWaveform: _isProcessingWaveform,
                        playbackState: playbackState,
                        isPlaying: isPlaying,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      _formatPosition(isPlaying ? provider.currentPosition : Duration.zero),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 30,
                        fontWeight: FontWeight.w300,
                        letterSpacing: 1.5,
                        fontFeatures: [FontFeature.tabularFigures()],
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        IconButton(
                          iconSize: 30,
                          color: Colors.white,
                          disabledColor: Colors.grey.shade700,
                          onPressed: canPlay && isPlaying ? () => provider.skipBackward() : null,
                          icon: const Icon(Icons.replay_10),
                        ),
                        const SizedBox(width: 24),
                        GestureDetector(
                          onTap: canPlay && !playbackState.isProcessing ? () => provider.togglePlayback(rec) : null,
                          child: Container(
                            width: 72,
                            height: 72,
                            decoration: const BoxDecoration(color: Color(0xFF35343B), shape: BoxShape.circle),
                            child: Icon(
                              playbackState.isProcessing
                                  ? Icons.hourglass_empty
                                  : (isPlaying ? Icons.pause : Icons.play_arrow),
                              color: canPlay ? Colors.white : Colors.grey.shade600,
                              size: 34,
                            ),
                          ),
                        ),
                        const SizedBox(width: 24),
                        IconButton(
                          iconSize: 30,
                          color: Colors.white,
                          disabledColor: Colors.grey.shade700,
                          onPressed: canPlay && isPlaying ? () => provider.skipForward() : null,
                          icon: const Icon(Icons.forward_10),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      height: 52,
                      child: ElevatedButton(
                        onPressed: rec.isBusy ? null : () => _handleTranscribe(provider, rec),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          disabledBackgroundColor: const Color(0xFF35343B),
                          foregroundColor: Colors.black,
                          disabledForegroundColor: Colors.grey.shade500,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            if (rec.isBusy)
                              SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.grey.shade500),
                              )
                            else
                              const Icon(Icons.cloud_upload_outlined, size: 20),
                            const SizedBox(width: 10),
                            Text(
                              rec.isBusy ? context.l10n.syncStatusUploaded : context.l10n.syncNow,
                              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      children: [
                        _action(Icons.ios_share_rounded, context.l10n.shareRecording, const Color(0xFFC9CBCF),
                            () => provider.share(rec)),
                        _action(Icons.info_outline_rounded, context.l10n.recordingInfo, const Color(0xFFC9CBCF),
                            () => _showFileDetailsDialog(context, rec)),
                        _action(Icons.delete_outline_rounded, context.l10n.delete, Colors.redAccent,
                            rec.isBusy ? null : () => _confirmDelete(context, provider, rec)),
                      ],
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _action(IconData icon, String label, Color color, VoidCallback? onTap) {
    final c = onTap == null ? Colors.grey.shade700 : color;
    return Expanded(
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Column(
            children: [
              Icon(icon, color: c, size: 22),
              const SizedBox(height: 6),
              Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: c, fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }

  String _formatPosition(Duration duration) {
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);
    final centis = (duration.inMilliseconds.remainder(1000) / 10).floor();
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')},${centis.toString().padLeft(2, '0')}';
  }

  Future<void> _handleTranscribe(LocalRecordingsProvider provider, LocalRecording rec) async {
    final outcome = await provider.upload(rec);
    if (!mounted) return;
    switch (outcome) {
      case LocalUploadOutcome.rateLimited:
        AppSnackbar.showSnackbarError(context.l10n.fairUseBudgetExhausted, duration: const Duration(seconds: 4));
      case LocalUploadOutcome.failed:
        AppSnackbar.showSnackbarError(context.l10n.anErrorOccurredTryAgain);
      case LocalUploadOutcome.busy:
        break;
      case LocalUploadOutcome.started:
        Navigator.of(context).maybePop();
    }
  }

  void _confirmDelete(BuildContext context, LocalRecordingsProvider provider, LocalRecording rec) async {
    final navigator = Navigator.of(context);
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.deleteRecording,
      message: context.l10n.deleteRecordingConfirmation,
      confirmLabel: context.l10n.delete,
      confirmColor: Colors.red,
    );
    if (confirmed == true) {
      navigator.pop();
      provider.delete(rec);
    }
  }

  void _showFileDetailsDialog(BuildContext context, LocalRecording rec) {
    final theme = Theme.of(context);
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
              _detailRow(context.l10n.dateTimeLabel, dateTimeFormat('MMM dd, yyyy h:mm:ss a', rec.startedAt)),
              _detailRow(context.l10n.durationLabel, secondsToHumanReadable(rec.seconds, context)),
              _detailRow(context.l10n.audioFormatLabel, rec.codec.toFormattedString()),
              _detailRow(context.l10n.estimatedSizeLabel, _formatBytes(rec.sizeBytes)),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(context.l10n.close, style: theme.textTheme.labelMedium?.copyWith(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  Widget _detailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.labelMedium!.copyWith(color: Colors.grey.shade400)),
          const SizedBox(height: 2),
          Text(value, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    );
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}

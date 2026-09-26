import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/waveform_painter.dart';

/// Floating bottom sheet for a batch/offline recording — playback (waveform +
/// scrub + transport), the primary "Sync now" (transcribe → conversation)
/// action, and share / details / delete. Replaces the old full-page detail.
Future<void> showRecordingDetailSheet(BuildContext context, LocalRecording recording) {
  return showOmiSheet<void>(
    context: context,
    title: OmiDateFormat.of(context).date(recording.startedAt),
    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
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
  List<double>? _waveform;
  bool _loadingWaveform = false;
  Timer? _ticker;
  LocalRecordingsProvider? _provider;

  @override
  void initState() {
    super.initState();
    _loadWaveform();
    _ticker = Timer.periodic(const Duration(milliseconds: 200), (_) {
      if (mounted && (_provider?.isPlaying(widget.recording) ?? false)) setState(() {});
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _provider = context.read<LocalRecordingsProvider>();
  }

  @override
  void dispose() {
    _ticker?.cancel();
    if (_provider != null && _provider!.isPlaying(widget.recording)) {
      _provider!.togglePlayback(widget.recording);
    }
    super.dispose();
  }

  Future<void> _loadWaveform() async {
    if (!mounted) return;
    setState(() => _loadingWaveform = true);
    final data = await context.read<LocalRecordingsProvider>().getWaveform(widget.recording);
    if (!mounted) return;
    setState(() {
      _waveform = _normalize(data);
      _loadingWaveform = false;
    });
  }

  // Scale amplitudes so the loudest bar nearly fills the height — a quiet
  // recording still reads as a real waveform instead of a flat line.
  List<double>? _normalize(List<double>? data) {
    if (data == null || data.isEmpty) return data;
    final maxV = data.reduce(math.max);
    if (maxV <= 0) return data;
    final scale = 0.95 / maxV;
    return data.map((v) => (v * scale).clamp(0.0, 1.0)).toList();
  }

  /// A position in the recording ("3:38", "1:02:05"); never drops the hours (tokens audit #20).
  String _fmt(Duration d) => OmiDuration.offset(d.inSeconds);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<LocalRecordingsProvider>(
      builder: (context, provider, child) {
        final rec = provider.getById(widget.recording.id) ?? widget.recording;
        final isPlaying = provider.isPlaying(rec);
        final canPlay = provider.canPlay(rec);
        final total = provider.totalDuration.inMilliseconds > 0 && isPlaying
            ? provider.totalDuration
            : Duration(seconds: rec.seconds);
        final position = isPlaying ? provider.currentPosition : Duration.zero;
        final progress = isPlaying ? provider.playbackProgress.clamp(0.0, 1.0) : 0.0;

        return Stack(
          children: [
            SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          OmiDateFormat.of(context).time(rec.startedAt),
                          style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                        ),
                      ),
                      _buildMenu(context, provider, rec),
                    ],
                  ),
                  const SizedBox(height: OmiSpacing.lg),
                  SizedBox(height: 60, child: _buildWaveform(provider, rec, isPlaying, canPlay, total, progress)),
                  const SizedBox(height: 14),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(_fmt(position), style: _timeStyle),
                      Text(_fmt(total), style: _timeStyle),
                    ],
                  ),
                  const SizedBox(height: 28),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      IconButton(
                        iconSize: 28,
                        color: Colors.white,
                        disabledColor: OmiColors.textDisabled,
                        tooltip: l10n.skipBack10Seconds,
                        onPressed: canPlay && isPlaying ? () => provider.skipBackward() : null,
                        icon: const Icon(Icons.replay_10_rounded),
                      ),
                      const SizedBox(width: 28),
                      Semantics(
                        button: true,
                        enabled: canPlay,
                        label: isPlaying ? l10n.pause : l10n.play,
                        child: GestureDetector(
                          onTap: canPlay ? () => provider.togglePlayback(rec) : null,
                          child: Container(
                            width: 66,
                            height: 66,
                            decoration: BoxDecoration(
                              color: canPlay ? OmiColors.accent : OmiColors.surface2,
                              shape: BoxShape.circle,
                            ),
                            child: ExcludeSemantics(
                              child: Icon(
                                provider.isProcessingAudio && isPlaying
                                    ? Icons.hourglass_empty_rounded
                                    : (isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded),
                                color: canPlay ? OmiColors.onAccent : OmiColors.textDisabled,
                                size: 36,
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 28),
                      IconButton(
                        iconSize: 28,
                        color: Colors.white,
                        disabledColor: OmiColors.textDisabled,
                        tooltip: l10n.skipForward10Seconds,
                        onPressed: canPlay && isPlaying ? () => provider.skipForward() : null,
                        icon: const Icon(Icons.forward_10_rounded),
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  OmiButton.secondary(
                    label: rec.isBusy ? l10n.syncStatusUploaded : l10n.processNow,
                    icon: Icons.cloud_upload_outlined,
                    isLoading: rec.isBusy,
                    expand: true,
                    onPressed: rec.isBusy ? null : () => _handleTranscribe(provider, rec),
                  ),
                  const SizedBox(height: OmiSpacing.lg),
                ],
              ),
            ),
            if (provider.isPreparingShare) _preparingOverlay(context),
          ],
        );
      },
    );
  }

  static final TextStyle _timeStyle = OmiType.caption.copyWith(
    color: OmiColors.textTertiary,
    fontWeight: FontWeight.w500,
    fontFeatures: const [FontFeature.tabularFigures()],
  );

  Widget _buildWaveform(
    LocalRecordingsProvider provider,
    LocalRecording rec,
    bool isPlaying,
    bool canPlay,
    Duration total,
    double progress,
  ) {
    if (_loadingWaveform) {
      return const Center(child: OmiSpinner(size: OmiSpinnerSize.small));
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        void seek(double dx) {
          if (total.inMilliseconds <= 0) return;
          final p = (dx / constraints.maxWidth).clamp(0.0, 1.0);
          provider.seekTo(Duration(milliseconds: (p * total.inMilliseconds).round()));
        }

        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: isPlaying ? (d) => seek(d.localPosition.dx) : null,
          onHorizontalDragUpdate: isPlaying ? (d) => seek(d.localPosition.dx) : null,
          child: SizedBox(
            width: double.infinity,
            height: double.infinity,
            child: RepaintBoundary(
              child: CustomPaint(
                painter: WaveformPainter(isPlaying: isPlaying, waveformData: _waveform, playbackProgress: progress),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _preparingOverlay(BuildContext context) {
    return Positioned.fill(
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {},
        child: ColoredBox(
          color: OmiColors.surface1.withValues(alpha: 0.9),
          child: OmiLoadingState(label: context.l10n.preparingAudio),
        ),
      ),
    );
  }

  Widget _buildMenu(BuildContext context, LocalRecordingsProvider provider, LocalRecording rec) {
    return PopupMenuButton<String>(
      tooltip: context.l10n.moreOptions,
      icon: const Icon(Icons.more_horiz_rounded, color: OmiColors.textSecondary),
      color: OmiColors.surface2,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
      position: PopupMenuPosition.under,
      onSelected: (v) {
        switch (v) {
          case 'share':
            provider.share(rec);
          case 'info':
            _showFileDetailsDialog(context, rec);
          case 'delete':
            _confirmDelete(context, provider, rec);
        }
      },
      itemBuilder: (_) => [
        _menuItem('share', Icons.ios_share_rounded, context.l10n.shareRecording, Colors.white),
        _menuItem('info', Icons.info_outline_rounded, context.l10n.recordingInfo, Colors.white),
        if (!rec.isBusy) _menuItem('delete', Icons.delete_outline_rounded, context.l10n.delete, OmiColors.danger),
      ],
    );
  }

  PopupMenuItem<String> _menuItem(String value, IconData icon, String label, Color color) {
    return PopupMenuItem<String>(
      value: value,
      child: Row(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 12),
          Text(label, style: OmiType.subhead.copyWith(color: color)),
        ],
      ),
    );
  }

  Future<void> _handleTranscribe(LocalRecordingsProvider provider, LocalRecording rec) async {
    final outcome = await provider.upload(rec);
    if (!mounted) return;
    switch (outcome) {
      case LocalUploadOutcome.fairUseLimited:
        OmiFeedback.error(context, context.l10n.fairUseBudgetExhausted);
      case LocalUploadOutcome.backendBusy:
        OmiFeedback.error(context, context.l10n.msgUploadFileFailed);
      case LocalUploadOutcome.failed:
        OmiFeedback.error(context, context.l10n.anErrorOccurredTryAgain);
      case LocalUploadOutcome.busy:
        break;
      case LocalUploadOutcome.started:
        Navigator.of(context).maybePop();
    }
  }

  void _confirmDelete(BuildContext context, LocalRecordingsProvider provider, LocalRecording rec) async {
    final navigator = Navigator.of(context);
    // The local file may be the only copy: always confirm, never "Don't ask again" (§4).
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteRecording,
      message: context.l10n.deleteRecordingConfirmation,
      confirmLabel: context.l10n.delete,
      destructive: true,
    );
    if (confirmed) {
      navigator.pop();
      provider.delete(rec);
    }
  }

  void _showFileDetailsDialog(BuildContext context, LocalRecording rec) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => OmiAlertDialog(
        title: dialogContext.l10n.recordingInfo,
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _detailRow(context.l10n.dateTimeLabel, OmiDateFormat.of(context).dateTime(rec.startedAt)),
            _detailRow(context.l10n.durationLabel, OmiDuration.long(rec.seconds, context.l10n)),
            _detailRow(context.l10n.audioFormatLabel, rec.codec.toFormattedString()),
            _detailRow(context.l10n.estimatedSizeLabel, _formatBytes(rec.sizeBytes)),
          ],
        ),
        actions: [
          OmiDialogAction(
            label: dialogContext.l10n.close,
            isDefault: true,
            onPressed: () => Navigator.of(dialogContext).pop(),
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
          Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
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

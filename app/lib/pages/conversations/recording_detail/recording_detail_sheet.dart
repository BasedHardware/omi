import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/waveform_painter.dart';

/// Floating bottom sheet for a batch/offline recording — playback (waveform +
/// scrub + transport), the primary "Sync now" (transcribe → conversation)
/// action, and share / details / delete. Replaces the old full-page detail.
///
/// [nativeContentForTest] builds the native content inside the Flutter sheet, so a hermetic test
/// reaches the native wiring that only an iOS host with the flag would otherwise present.
Future<void> showRecordingDetailSheet(BuildContext context, LocalRecording recording,
    {@visibleForTesting bool nativeContentForTest = false}) {
  return showOmiSheet<void>(
    context: context,
    title: OmiDateFormat.of(context).date(recording.startedAt),
    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
    builder: (_) => _RecordingDetailSheet(recording: recording, native: nativeContentForTest),
    nativeBuilder: (_) => _RecordingDetailSheet(recording: recording, native: true),
  );
}

/// The most waveform bars a native playback slider carries.
const nativeWaveformLimit = 200;

/// A native playback slider's range in seconds: the longer of the player's and the file's
/// duration, or null when neither is a usable length (the slider is then omitted).
double? nativePlaybackMaximum(Duration player, int fileSeconds) {
  final maximum = math.max(player.inMilliseconds / 1000, fileSeconds.toDouble());
  return maximum.isFinite && maximum > 0 ? maximum : null;
}

/// At most [nativeWaveformLimit] bars over [seconds], each the loudest level of its span, scaled so
/// the loudest bar is 1. Non-finite levels count as silence; only these levels cross the bridge,
/// never the audio or its file.
List<Map<String, Object>> nativeWaveformPoints(List<double>? levels, double seconds) {
  if (levels == null || levels.isEmpty || !seconds.isFinite || seconds <= 0) return const [];
  final clean = [for (final level in levels) level.isFinite ? level.abs() : 0.0];
  final count = math.min(clean.length, nativeWaveformLimit);
  final bars = [
    for (var i = 0; i < count; i++)
      clean
          .sublist(i * clean.length ~/ count, math.max(i * clean.length ~/ count + 1, (i + 1) * clean.length ~/ count))
          .reduce(math.max),
  ];
  final peak = bars.reduce(math.max);
  return [
    for (var i = 0; i < count; i++)
      {
        'x': (i + 0.5) / count * seconds,
        'y': peak > 0 && peak.isFinite ? (bars[i] / peak).clamp(0.0, 1.0).toDouble() : 0.0,
        'label': '',
      },
  ];
}

class _RecordingDetailSheet extends StatefulWidget {
  final LocalRecording recording;

  /// Present the SwiftUI sheet, with the complete Flutter sheet as its fallback.
  final bool native;

  const _RecordingDetailSheet({required this.recording, this.native = false});

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

        final classic = Stack(
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
        if (!widget.native) return classic;
        return _nativeSheet(
          provider,
          rec,
          isPlaying: isPlaying,
          canPlay: canPlay,
          total: total,
          position: position,
          fallback: OmiSheetScaffold(
            title: OmiDateFormat.of(context).date(rec.startedAt),
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
            child: classic,
          ),
        );
      },
    );
  }

  /// The SwiftUI sheet: the same player, transport, process action and menu, all owned by
  /// [LocalRecordingsProvider]. While a share is being prepared every action is disabled, as the
  /// Flutter overlay blocks them.
  Widget _nativeSheet(
    LocalRecordingsProvider provider,
    LocalRecording rec, {
    required bool isPlaying,
    required bool canPlay,
    required Duration total,
    required Duration position,
    required Widget fallback,
  }) {
    final l10n = context.l10n;
    final preparing = provider.isPreparingShare;
    final maximum = nativePlaybackMaximum(isPlaying ? provider.totalDuration : Duration.zero, rec.seconds);
    final seconds = (position.inMilliseconds / 1000).clamp(0.0, maximum ?? 0.0).toDouble();
    final transport = canPlay && isPlaying && !preparing;
    return IosNativeSurface(
      title: OmiDateFormat.of(context).date(rec.startedAt),
      loading: preparing,
      loadingLabel: preparing ? l10n.preparingAudio : null,
      fallback: fallback,
      toolbar: [
        NativeRow('rec_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
        NativeRow('rec_more', l10n.moreOptions, kind: 'menu', symbol: 'ellipsis', enabled: !preparing, options: {
          'share': l10n.shareRecording,
          'info': l10n.recordingInfo,
          if (!rec.isBusy) 'delete': l10n.delete,
        }, action: (value) {
          switch (value) {
            case 'share':
              provider.share(rec);
            case 'info':
              _showNativeFileDetails(rec);
            case 'delete':
              _confirmDelete(context, provider, rec);
          }
        }),
      ],
      sections: [
        NativeSection('rec_player', [
          NativeRow('rec_time', OmiDateFormat.of(context).time(rec.startedAt), kind: 'label'),
          if (_loadingWaveform) NativeRow('rec_waveform_loading', l10n.loadingYourRecording, kind: 'label'),
          if (maximum != null)
            NativeRow('rec_position', l10n.recordings,
                kind: 'slider',
                value: seconds,
                maximumValue: maximum,
                subtitle: '${_fmt(position)} / ${OmiDuration.offset(maximum.round())}',
                points: _loadingWaveform ? const [] : nativeWaveformPoints(_waveform, maximum),
                enabled: transport,
                action: (value) => provider.seekTo(Duration(milliseconds: ((value as num) * 1000).round()))),
        ]),
        NativeSection('rec_transport', [
          NativeRow('rec_back10', l10n.skipBack10Seconds,
              symbol: 'gobackward.10', enabled: transport, action: (_) => provider.skipBackward()),
          NativeRow(
            'rec_play',
            isPlaying ? l10n.pause : l10n.play,
            symbol: isPlaying ? 'pause.fill' : 'play.fill',
            subtitle: provider.isProcessingAudio && isPlaying ? l10n.processing : '',
            enabled: canPlay && !preparing,
            action: (_) => provider.togglePlayback(rec),
          ),
          NativeRow('rec_fwd10', l10n.skipForward10Seconds,
              symbol: 'goforward.10', enabled: transport, action: (_) => provider.skipForward()),
        ]),
        NativeSection('rec_actions', [
          // The Flutter button shows its spinner while busy; the busy subtitle stands in for it.
          NativeRow('rec_process', rec.isBusy ? l10n.syncStatusUploaded : l10n.processNow,
              symbol: 'icloud.and.arrow.up',
              subtitle: rec.isBusy ? l10n.processing : '',
              enabled: !rec.isBusy && !preparing,
              action: (_) => _handleTranscribe(provider, rec)),
        ]),
      ],
    );
  }

  /// Recording info as a native sheet of labels; the Flutter dialog when it cannot be presented.
  Future<void> _showNativeFileDetails(LocalRecording rec) async {
    final l10n = context.l10n;
    final result = await showIosNativeModal(context, title: l10n.recordingInfo, cancelId: 'close', actions: [
      NativeRow('close', l10n.close),
    ], sections: [
      NativeSection('rec_info', [
        NativeRow('rec_info_date', l10n.dateTimeLabel,
            kind: 'label', subtitle: OmiDateFormat.of(context).dateTime(rec.startedAt)),
        NativeRow('rec_info_duration', l10n.durationLabel,
            kind: 'label', subtitle: OmiDuration.long(rec.seconds, l10n)),
        NativeRow('rec_info_format', l10n.audioFormatLabel, kind: 'label', subtitle: rec.codec.toFormattedString()),
        NativeRow('rec_info_size', l10n.estimatedSizeLabel, kind: 'label', subtitle: _formatBytes(rec.sizeBytes)),
      ]),
    ]);
    if (result == null && mounted) _showFileDetailsDialog(context, rec);
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
      icon: Icon(Icons.more_horiz_rounded, color: OmiColors.textSecondary),
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
        unawaited(AppReviewService().recordBadExperience(AppReviewBadExperience.captureFailure));
        OmiFeedback.error(context, context.l10n.msgUploadFileFailed);
      case LocalUploadOutcome.failed:
        unawaited(AppReviewService().recordBadExperience(AppReviewBadExperience.captureFailure));
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

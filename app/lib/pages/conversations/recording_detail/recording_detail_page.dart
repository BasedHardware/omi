import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/models/playback_state.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/waveform_section.dart';

/// Detail screen for a batch/offline-mode recording captured locally. Unlike the
/// WAL detail page it has no SD/flash transfer flow (recordings are always on the
/// phone) and adds a primary "transcribe" action that uploads the file and turns
/// it into a conversation. Backed entirely by [LocalRecordingsProvider].
class RecordingDetailPage extends StatefulWidget {
  final LocalRecording recording;

  const RecordingDetailPage({super.key, required this.recording});

  @override
  State<RecordingDetailPage> createState() => _RecordingDetailPageState();
}

class _RecordingDetailPageState extends State<RecordingDetailPage> {
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
    // Stop playback when leaving the page.
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
      body: Consumer<LocalRecordingsProvider>(
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

          return Column(
            children: [
              // Title section
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                child: Column(
                  children: [
                    Text(
                      dateTimeFormat('dd MMM yyyy', rec.startedAt),
                      style:
                          Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 28, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      dateTimeFormat('H:mm', rec.startedAt),
                      style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                            color: Colors.grey.shade400,
                            fontSize: 16,
                            fontWeight: FontWeight.w400,
                          ),
                    ),
                    const SizedBox(height: 8),
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

              // Waveform — dominant space
              Expanded(
                flex: 6,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: WaveformSection(
                    seconds: rec.seconds,
                    waveformData: _waveformData,
                    isProcessingWaveform: _isProcessingWaveform,
                    playbackState: playbackState,
                    isPlaying: isPlaying,
                  ),
                ),
              ),

              // Timer
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Text(
                  _formatPosition(isPlaying ? provider.currentPosition : Duration.zero),
                  style: Theme.of(context)
                      .textTheme
                      .titleLarge!
                      .copyWith(fontSize: 48, fontWeight: FontWeight.w300, letterSpacing: 2),
                ),
              ),

              // Transport controls
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    _buildControlButton(
                      icon: Icons.replay_10,
                      onPressed: playbackState.canPlayOrShare && isPlaying ? () => provider.skipBackward() : null,
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
                          ? () => provider.togglePlayback(rec)
                          : null,
                    ),
                    _buildControlButton(
                      icon: Icons.forward_10,
                      onPressed: playbackState.canPlayOrShare && isPlaying ? () => provider.skipForward() : null,
                      size: 60,
                    ),
                  ],
                ),
              ),

              // Primary action: transcribe (upload → conversation)
              Padding(
                padding: const EdgeInsets.fromLTRB(40, 12, 40, 32),
                child: SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: rec.isBusy ? null : () => _handleTranscribe(provider, rec),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.deepPurpleAccent,
                      disabledBackgroundColor: Colors.deepPurple.withValues(alpha: 0.3),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        if (rec.isBusy)
                          const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        else
                          const Icon(Icons.cloud_upload_outlined, color: Colors.white, size: 22),
                        const SizedBox(width: 12),
                        Text(
                          rec.isBusy ? context.l10n.syncStatusUploaded : context.l10n.syncNow,
                          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  String _formatPosition(Duration duration) {
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);
    final centis = (duration.inMilliseconds.remainder(1000) / 10).floor();
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')},${centis.toString().padLeft(2, '0')}';
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
        icon: Icon(icon, color: iconColor ?? Colors.white, size: size * 0.4),
      ),
    );
  }

  Future<void> _handleTranscribe(LocalRecordingsProvider provider, LocalRecording rec) async {
    await provider.upload(rec);
    if (mounted) Navigator.of(context).maybePop();
  }

  void _showOptionsMenu(BuildContext context) {
    final provider = context.read<LocalRecordingsProvider>();
    final rec = provider.getById(widget.recording.id) ?? widget.recording;

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
                _showFileDetailsDialog(context, rec);
              },
            ),
            ListTile(
              leading: const FaIcon(FontAwesomeIcons.share, color: Colors.white, size: 18),
              title: Text(context.l10n.shareRecording, style: Theme.of(sheetContext).textTheme.bodyMedium),
              onTap: () {
                Navigator.pop(sheetContext);
                provider.share(rec);
              },
            ),
            ListTile(
              leading: Icon(Icons.delete, color: rec.isBusy ? Colors.grey : Colors.red),
              title: Text(
                context.l10n.deleteRecording,
                style:
                    Theme.of(sheetContext).textTheme.bodyMedium!.copyWith(color: rec.isBusy ? Colors.grey : Colors.red),
              ),
              onTap: rec.isBusy
                  ? null
                  : () {
                      Navigator.pop(sheetContext);
                      _showDeleteDialog(context, provider, rec);
                    },
            ),
          ],
        ),
      ),
    );
  }

  void _showDeleteDialog(BuildContext context, LocalRecordingsProvider provider, LocalRecording rec) async {
    final navigator = Navigator.of(context);
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.deleteRecording,
      message: context.l10n.deleteRecordingConfirmation,
      confirmLabel: context.l10n.delete,
      confirmColor: Colors.red,
    );
    if (confirmed == true && mounted) {
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
              _buildDetailRow(context.l10n.dateTimeLabel, dateTimeFormat('MMM dd, yyyy h:mm:ss a', rec.startedAt)),
              _buildDetailRow(context.l10n.durationLabel, secondsToHumanReadable(rec.seconds, context)),
              _buildDetailRow(context.l10n.audioFormatLabel, rec.codec.toFormattedString()),
              _buildDetailRow(context.l10n.estimatedSizeLabel, _formatBytes(rec.sizeBytes)),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(
              context.l10n.close,
              style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.secondary),
            ),
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

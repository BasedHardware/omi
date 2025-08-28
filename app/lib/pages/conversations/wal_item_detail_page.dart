import 'dart:math';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

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
    // Clean up any resources if needed
    super.dispose();
  }

  Future<void> _generateWaveform() async {
    setState(() {
      _isProcessingWaveform = true;
    });

    try {
      final waveformData = await _extractWaveformFromWal(widget.wal);
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

  Future<List<double>> _extractWaveformFromWal(Wal wal) async {
    try {
      // Get audio file path
      String? audioFilePath = await _getAudioFilePath(wal);
      if (audioFilePath == null) {
        return _generateFallbackWaveform();
      }

      // Read and process audio data
      final file = File(audioFilePath);
      if (!file.existsSync()) {
        return _generateFallbackWaveform();
      }

      final audioData = await file.readAsBytes();
      List<double> samples = [];

      if (wal.codec.isOpusSupported()) {
        samples = await _extractSamplesFromOpus(audioData, wal);
      } else {
        samples = await _extractSamplesFromPcm(audioData, wal);
      }

      // Generate waveform from samples
      return _generateWaveformFromSamples(samples);
    } catch (e) {
      debugPrint('Error extracting waveform: $e');
      return _generateFallbackWaveform();
    }
  }

  Future<String?> _getAudioFilePath(Wal wal) async {
    // If WAL already has a file path, use it
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      final file = File(wal.filePath!);
      if (file.existsSync()) {
        return wal.filePath!;
      }
    }

    // If WAL has data in memory, create a temporary file
    if (wal.data.isNotEmpty) {
      return await _createTempFileFromMemoryData(wal);
    }

    return null;
  }

  Future<String?> _createTempFileFromMemoryData(Wal wal) async {
    try {
      final tempDir = Directory.systemTemp;
      final tempFilePath = '${tempDir.path}/temp_waveform_${wal.id}_${DateTime.now().millisecondsSinceEpoch}.bin';

      List<int> data = [];
      for (int i = 0; i < wal.data.length; i++) {
        var frame = wal.data[i].sublist(3); // Remove the 3-byte header

        // Format: <length>|<data> ; bytes: 4 | n
        final byteFrame = ByteData(frame.length);
        for (int j = 0; j < frame.length; j++) {
          byteFrame.setUint8(j, frame[j]);
        }
        data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
        data.addAll(byteFrame.buffer.asUint8List());
      }

      final file = File(tempFilePath);
      await file.writeAsBytes(data);
      return tempFilePath;
    } catch (e) {
      debugPrint('Error creating temp file from memory data: $e');
      return null;
    }
  }

  Future<List<double>> _extractSamplesFromOpus(Uint8List opusData, Wal wal) async {
    try {
      // Parse the custom format: <length>|<data> for each frame
      List<Uint8List> opusFrames = [];
      int offset = 0;

      while (offset < opusData.length - 4) {
        // Read frame length (4 bytes)
        final lengthBytes = opusData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;

        if (offset + length > opusData.length) break;

        // Read frame data
        final frameData = opusData.sublist(offset, offset + length);
        opusFrames.add(Uint8List.fromList(frameData));
        offset += length;
      }

      if (opusFrames.isEmpty) {
        return [];
      }

      // Initialize opus decoder
      final decoder = SimpleOpusDecoder(
        sampleRate: wal.sampleRate,
        channels: wal.channel,
      );

      // Decode frames and extract samples
      List<double> allSamples = [];
      for (final opusFrame in opusFrames) {
        try {
          final pcmFrame = decoder.decode(input: opusFrame);
          if (pcmFrame != null) {
            // Convert Int16List to double samples (normalize to -1.0 to 1.0)
            for (int i = 0; i < pcmFrame.length; i++) {
              allSamples.add(pcmFrame[i] / 32768.0);
            }
          }
        } catch (e) {
          debugPrint('Error decoding opus frame: $e');
          // Continue with other frames
        }
      }

      return allSamples;
    } catch (e) {
      debugPrint('Error extracting samples from opus: $e');
      return [];
    }
  }

  Future<List<double>> _extractSamplesFromPcm(Uint8List pcmData, Wal wal) async {
    try {
      // Parse the custom format: <length>|<data> for each frame
      List<Uint8List> pcmFrames = [];
      int offset = 0;

      while (offset < pcmData.length - 4) {
        // Read frame length (4 bytes)
        final lengthBytes = pcmData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;

        if (offset + length > pcmData.length) break;

        // Read frame data
        final frameData = pcmData.sublist(offset, offset + length);
        pcmFrames.add(Uint8List.fromList(frameData));
        offset += length;
      }

      if (pcmFrames.isEmpty) {
        return [];
      }

      // Combine all PCM frames
      final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
      final combinedPcm = Uint8List(totalLength);
      int writeOffset = 0;
      for (final frame in pcmFrames) {
        combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
        writeOffset += frame.length;
      }

      // Convert PCM bytes to samples
      List<double> samples = [];
      if (wal.codec == BleAudioCodec.pcm16) {
        // 16-bit PCM
        for (int i = 0; i < combinedPcm.length - 1; i += 2) {
          final sample = ByteData.sublistView(combinedPcm, i, i + 2).getInt16(0, Endian.little);
          samples.add(sample / 32768.0); // Normalize to -1.0 to 1.0
        }
      } else {
        // 8-bit PCM
        for (int i = 0; i < combinedPcm.length; i++) {
          final sample = combinedPcm[i] - 128; // Convert unsigned to signed
          samples.add(sample / 128.0); // Normalize to -1.0 to 1.0
        }
      }

      return samples;
    } catch (e) {
      debugPrint('Error extracting samples from PCM: $e');
      return [];
    }
  }

  List<double> _generateWaveformFromSamples(List<double> samples) {
    if (samples.isEmpty) {
      return _generateFallbackWaveform();
    }

    const int targetBars = 100; // Number of bars in waveform
    final int samplesPerBar = (samples.length / targetBars).ceil();

    List<double> waveformData = [];

    for (int i = 0; i < targetBars; i++) {
      final startIdx = i * samplesPerBar;
      final endIdx = math.min(startIdx + samplesPerBar, samples.length);

      if (startIdx >= samples.length) {
        waveformData.add(0.0);
        continue;
      }

      // Calculate RMS (Root Mean Square) for this segment
      double sum = 0.0;
      int count = 0;
      for (int j = startIdx; j < endIdx; j++) {
        sum += samples[j] * samples[j];
        count++;
      }

      final rms = count > 0 ? math.sqrt(sum / count) : 0.0;
      waveformData.add(rms);
    }

    // Normalize waveform data to 0.0-1.0 range
    if (waveformData.isNotEmpty) {
      final maxValue = waveformData.reduce(math.max);
      if (maxValue > 0) {
        waveformData = waveformData.map((value) => value / maxValue).toList();
      }
    }

    return waveformData;
  }

  List<double> _generateFallbackWaveform() {
    // Generate a fallback waveform using random data (similar to original)
    final random = Random(42); // Fixed seed for consistency
    return List.generate(100, (index) => random.nextDouble() * 0.7 + 0.1);
  }

  String _formatDuration(Duration duration) {
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);

    if (hours > 0) {
      return '${hours.toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
    } else {
      return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: _buildAppBar(context),
      body: Consumer<SyncProvider>(
        builder: (context, syncProvider, child) => _buildBody(context, syncProvider),
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    return AppBar(
      backgroundColor: Theme.of(context).colorScheme.primary,
      elevation: 0,
      leading: IconButton(
        icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
        onPressed: () => Navigator.of(context).pop(),
      ),
      actions: [
        PopupMenuButton<String>(
          onSelected: (value) async {
            final syncProvider = context.read<SyncProvider>();
            if (value == 'delete') {
              _showDeleteDialog(context, syncProvider);
            }
          },
          itemBuilder: (BuildContext context) => <PopupMenuEntry<String>>[
            const PopupMenuItem<String>(
              value: 'delete',
              child: ListTile(
                leading: Icon(Icons.delete, color: Colors.red),
                title: Text('Delete Audio File'),
              ),
            ),
          ],
          icon: const Icon(Icons.more_horiz, color: Colors.white),
        ),
      ],
    );
  }

  Widget _buildBody(BuildContext context, SyncProvider syncProvider) {
    final playbackState = _getPlaybackState(syncProvider);

    return Column(
      children: [
        _buildWaveformSection(context, syncProvider, playbackState),
        _buildControlsSection(context, syncProvider, playbackState),
        _buildInfoSection(context, syncProvider, playbackState),
      ],
    );
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

  Widget _buildWaveformSection(BuildContext context, SyncProvider syncProvider, PlaybackState state) {
    return Expanded(
      flex: 2,
      child: Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          children: [
            Expanded(
              child: _buildWaveformVisualization(context, syncProvider, state),
            ),
            const SizedBox(height: 16),
            _buildTimeIndicators(state),
          ],
        ),
      ),
    );
  }

  Widget _buildWaveformVisualization(BuildContext context, SyncProvider syncProvider, PlaybackState state) {
    if (_isProcessingWaveform) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(
              color: Colors.white70,
              strokeWidth: 2,
            ),
            SizedBox(height: 12),
            Text(
              'Analyzing audio...',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 12,
              ),
            ),
          ],
        ),
      );
    }

    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final currentState = _getPlaybackState(syncProvider);

        return LayoutBuilder(
          builder: (context, constraints) {
            return GestureDetector(
              onTapDown: (details) => _handleWaveformTap(
                details,
                constraints,
                syncProvider,
                currentState,
              ),
              child: Container(
                width: double.infinity,
                height: double.infinity,
                child: CustomPaint(
                  painter: WaveformPainter(
                    isPlaying: currentState.isPlaying,
                    waveformData: _waveformData,
                    playbackProgress: currentState.playbackProgress,
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  void _handleWaveformTap(
    TapDownDetails details,
    BoxConstraints constraints,
    SyncProvider syncProvider,
    PlaybackState state,
  ) {
    if (state.canPlayOrShare && syncProvider.totalDuration.inMilliseconds > 0 && state.isPlaying) {
      final localPosition = details.localPosition;
      final containerWidth = constraints.maxWidth;
      final progress = (localPosition.dx / containerWidth).clamp(0.0, 1.0);
      final seekPosition = Duration(
        milliseconds: (progress * syncProvider.totalDuration.inMilliseconds).round(),
      );
      syncProvider.seekToPosition(seekPosition);
    }
  }

  Widget _buildTimeIndicators(PlaybackState state) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final currentState = _getPlaybackState(syncProvider);
        final currentPos = currentState.isPlaying ? currentState.currentPosition : Duration.zero;
        final totalDur = currentState.isPlaying && currentState.totalDuration.inMilliseconds > 0
            ? currentState.totalDuration
            : Duration(seconds: widget.wal.seconds);

        return Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              _formatDuration(currentPos),
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
            ),
            Text(
              _formatDuration(totalDur),
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
            ),
          ],
        );
      },
    );
  }

  Widget _buildControlsSection(BuildContext context, SyncProvider syncProvider, PlaybackState state) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _buildControlButton(
            icon: Icons.replay_10,
            onPressed: state.canPlayOrShare && state.isPlaying ? () => _handleSkipBackward(syncProvider) : null,
          ),
          _buildControlButton(
            icon: state.isProcessing ? Icons.hourglass_empty : (state.isPlaying ? Icons.pause : Icons.play_arrow),
            size: 64,
            backgroundColor: Colors.white,
            iconColor: Colors.black,
            onPressed: state.canPlayOrShare && !state.isProcessing ? () => _handlePlayPause(syncProvider) : null,
          ),
          _buildControlButton(
            icon: Icons.forward_10,
            onPressed: state.canPlayOrShare && state.isPlaying ? () => _handleSkipForward(syncProvider) : null,
          ),
        ],
      ),
    );
  }

  Widget _buildInfoSection(BuildContext context, SyncProvider syncProvider, PlaybackState state) {
    return Expanded(
      flex: 1,
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildAudioInfo(state),
            const Spacer(),
            if (state.hasError && syncProvider.syncError != null) _buildErrorSection(syncProvider),
            _buildActionButtons(context, syncProvider, state),
          ],
        ),
      ),
    );
  }

  Widget _buildAudioInfo(PlaybackState state) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          dateTimeFormat('MMM dd, yyyy h:mm a', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          '${secondsToHumanReadable(widget.wal.seconds)} • ${widget.wal.codec.toFormattedString()}',
          style: TextStyle(
            color: Colors.grey.shade400,
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          children: [
            Icon(
              widget.wal.storage == WalStorage.sdcard ? Icons.sd_card : Icons.phone_android,
              color: widget.wal.storage == WalStorage.sdcard ? Colors.purple.shade300 : Colors.blue.shade300,
              size: 16,
            ),
            const SizedBox(width: 4),
            Text(
              widget.wal.deviceModel ?? "Phone Microphone",
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 12,
              ),
            ),
            if (state.isSynced) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.green.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: const Text(
                  'Processed ✅',
                  style: TextStyle(
                    color: Colors.green,
                    fontSize: 10,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }

  Widget _buildErrorSection(SyncProvider syncProvider) {
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: Colors.red.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.red.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Processing Error',
            style: TextStyle(color: Colors.red, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            syncProvider.syncError!,
            style: TextStyle(color: Colors.red.shade300, fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget _buildActionButtons(BuildContext context, SyncProvider syncProvider, PlaybackState state) {
    return Row(
      children: [
        if (state.canPlayOrShare)
          Expanded(
            child: ElevatedButton.icon(
              onPressed: state.isSharing ? null : () => _handleShare(syncProvider),
              icon: state.isSharing
                  ? const SizedBox(
                      width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.share, size: 18),
              label: Text(state.isSharing ? 'Sharing...' : 'Share'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.grey.shade700,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),
        if (state.canPlayOrShare) const SizedBox(width: 12),
        Expanded(
          child: ElevatedButton.icon(
            onPressed: () => _handleProcessAction(context, syncProvider, state),
            icon: Icon(
              state.hasError ? Icons.refresh : (state.isSynced ? Icons.refresh : Icons.cloud_upload),
              size: 18,
            ),
            label: Text(
              state.hasError ? 'Retry' : (state.isSynced ? 'Re-process' : 'Process'),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor:
                  state.hasError ? Colors.red.shade700 : (state.isSynced ? Colors.orange : Colors.deepPurple),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ],
    );
  }

  // Event handlers
  Future<void> _handlePlayPause(SyncProvider syncProvider) async {
    if (widget.wal.storage == WalStorage.sdcard) {
      _showSnackBar('Playback for SD card audio is not yet available.', Colors.orange);
      return;
    }

    try {
      await syncProvider.toggleWalPlayback(widget.wal);
    } catch (e) {
      _showSnackBar('Error playing audio: $e');
    }
  }

  Future<void> _handleSkipBackward(SyncProvider syncProvider) async {
    try {
      await syncProvider.skipBackward();
    } catch (e) {
      _showSnackBar('Error skipping backward: $e');
    }
  }

  Future<void> _handleSkipForward(SyncProvider syncProvider) async {
    try {
      await syncProvider.skipForward();
    } catch (e) {
      _showSnackBar('Error skipping forward: $e');
    }
  }

  Future<void> _handleShare(SyncProvider syncProvider) async {
    if (widget.wal.storage == WalStorage.sdcard) {
      _showSnackBar('Sharing for SD card audio is not yet available.', Colors.orange);
      return;
    }

    try {
      await syncProvider.shareWalAsWav(widget.wal);
    } catch (e) {
      _showSnackBar('Error sharing audio: $e');
    }
  }

  void _handleProcessAction(BuildContext context, SyncProvider syncProvider, PlaybackState state) {
    if (state.hasError) {
      syncProvider.retrySync();
    } else if (state.isSynced) {
      _showResyncDialog(context, syncProvider);
    } else {
      syncProvider.syncWal(widget.wal);
    }
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
        color: backgroundColor ?? Colors.grey.withOpacity(0.2),
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

  void _showDeleteDialog(BuildContext context, SyncProvider syncProvider) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text('Delete Audio File', style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Are you sure you want to delete this audio file? This action cannot be undone.',
              style: TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 12),
            Text(
              'File: ${secondsToHumanReadable(widget.wal.seconds)}',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
            Text(
              'Recorded: ${dateTimeFormat('MMM dd, h:mm a', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000))}',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop(); // Close dialog
              Navigator.of(context).pop(); // Close detail page
              syncProvider.deleteWal(widget.wal);
            },
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
  }

  void _showResyncDialog(BuildContext context, SyncProvider syncProvider) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text('Reprocess Audio File', style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'This will reprocess the audio file and may create a new conversation or update an existing one.',
              style: TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 12),
            Text(
              'File: ${secondsToHumanReadable(widget.wal.seconds)}',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
            Text(
              'Recorded: ${dateTimeFormat('MMM dd, h:mm a', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000))}',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              syncProvider.resyncWal(widget.wal);
            },
            child: const Text('Reprocess', style: TextStyle(color: Colors.orange)),
          ),
        ],
      ),
    );
  }
}

// Data classes for better state management
class PlaybackState {
  final bool isPlaying;
  final bool isProcessing;
  final bool isSharing;
  final bool canPlayOrShare;
  final bool isSynced;
  final bool hasError;
  final Duration currentPosition;
  final Duration totalDuration;
  final double playbackProgress;

  const PlaybackState({
    required this.isPlaying,
    required this.isProcessing,
    required this.isSharing,
    required this.canPlayOrShare,
    required this.isSynced,
    required this.hasError,
    required this.currentPosition,
    required this.totalDuration,
    required this.playbackProgress,
  });
}

class WaveformPainter extends CustomPainter {
  final bool isPlaying;
  final List<double>? waveformData;
  final double playbackProgress;

  const WaveformPainter({
    required this.isPlaying,
    this.waveformData,
    this.playbackProgress = 0.0,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.grey.shade600
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;

    final activePaint = Paint()
      ..color = Colors.white
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;

    final barWidth = 2.0;
    final spacing = 2.0;
    final barCount = (size.width / (barWidth + spacing)).floor();

    if (waveformData != null && waveformData!.isNotEmpty) {
      _paintRealWaveform(canvas, size, paint, activePaint, barWidth, spacing, barCount);
    } else {
      _paintFallbackWaveform(canvas, size, paint, activePaint, barWidth, spacing, barCount);
    }
  }

  void _paintRealWaveform(
    Canvas canvas,
    Size size,
    Paint paint,
    Paint activePaint,
    double barWidth,
    double spacing,
    int barCount,
  ) {
    final dataPointsPerBar = (waveformData!.length / barCount).ceil();

    for (int i = 0; i < barCount; i++) {
      final x = i * (barWidth + spacing);

      // Get average amplitude for this bar
      double amplitude = 0.0;
      int count = 0;
      for (int j = i * dataPointsPerBar; j < (i + 1) * dataPointsPerBar && j < waveformData!.length; j++) {
        amplitude += waveformData![j];
        count++;
      }
      if (count > 0) {
        amplitude /= count;
      }

      // Ensure minimum height for visibility
      amplitude = math.max(amplitude, 0.05);

      final height = amplitude * size.height * 0.8;
      final y = (size.height - height) / 2;

      final progressBarIndex = (barCount * playbackProgress).floor();
      final useActivePaint = isPlaying && i <= progressBarIndex;

      canvas.drawLine(
        Offset(x, y),
        Offset(x, y + height),
        useActivePaint ? activePaint : paint,
      );
    }
  }

  void _paintFallbackWaveform(
    Canvas canvas,
    Size size,
    Paint paint,
    Paint activePaint,
    double barWidth,
    double spacing,
    int barCount,
  ) {
    final random = Random(42); // Fixed seed for consistent waveform

    for (int i = 0; i < barCount; i++) {
      final x = i * (barWidth + spacing);
      final height = (random.nextDouble() * 0.7 + 0.1) * size.height;
      final y = (size.height - height) / 2;

      final progressBarIndex = (barCount * playbackProgress).floor();
      final useActivePaint = isPlaying && i <= progressBarIndex;

      canvas.drawLine(
        Offset(x, y),
        Offset(x, y + height),
        useActivePaint ? activePaint : paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) {
    return oldDelegate is WaveformPainter &&
        (oldDelegate.isPlaying != isPlaying ||
            oldDelegate.waveformData != waveformData ||
            oldDelegate.playbackProgress != playbackProgress);
  }
}

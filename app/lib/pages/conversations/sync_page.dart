import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/settings/widgets/appbar_with_banner.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:opus_dart/opus_dart.dart';
import 'dart:io';
import 'dart:typed_data';
import 'dart:convert';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'synced_conversations_page.dart';

class WalListItem extends StatefulWidget {
  final DateTime date;
  final int walIdx;
  final Wal wal;

  const WalListItem({
    super.key,
    required this.wal,
    required this.date,
    required this.walIdx,
  });

  @override
  State<WalListItem> createState() => _WalListItemState();
}

class _WalListItemState extends State<WalListItem> {
  bool _isPlaying = false;
  FlutterSoundPlayer? _audioPlayer;
  bool _isProcessing = false;
  bool _isSharing = false;

  @override
  void initState() {
    super.initState();
    _audioPlayer = FlutterSoundPlayer();
  }

  @override
  void dispose() {
    _audioPlayer?.closePlayer();
    super.dispose();
  }

  double calculateProgress(DateTime? startedAt, int eta) {
    if (startedAt == null) {
      return 0.0;
    }
    if (eta == 0) {
      return 0.01;
    }
    final elapsed = DateTime.now().difference(startedAt).inSeconds;
    final progress = elapsed / eta;
    return progress.clamp(0.0, 1.0);
  }

  Future<void> _togglePlayback() async {
    if (widget.wal.filePath == null || widget.wal.filePath!.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Audio file not available for playback'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    if (_isProcessing) return;

    if (_isPlaying) {
      // Stop playback
      await _audioPlayer?.stopPlayer();
      setState(() {
        _isPlaying = false;
      });
      return;
    }

    // Start playback
    setState(() {
      _isProcessing = true;
    });

    try {
      String? wavFilePath;

      // Check if it's an opus file that needs decoding
      if (widget.wal.codec.isOpusSupported()) {
        wavFilePath = await _decodeOpusToWav(widget.wal.filePath!);
      } else {
        // For PCM files, we can try to play directly or convert to WAV
        wavFilePath = await _convertPcmToWav(widget.wal.filePath!);
      }

      if (wavFilePath != null && mounted) {
        await _audioPlayer?.openPlayer();

        setState(() {
          _isPlaying = true;
          _isProcessing = false;
        });

        await _audioPlayer?.startPlayer(
          fromURI: wavFilePath,
          whenFinished: () {
            if (mounted) {
              setState(() {
                _isPlaying = false;
              });
            }
          },
        );
      }
    } catch (e) {
      debugPrint('Error playing audio: $e');
      if (mounted) {
        setState(() {
          _isProcessing = false;
          _isPlaying = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error playing audio: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<String?> _decodeOpusToWav(String opusFilePath, {bool forSharing = false}) async {
    try {
      final file = File(opusFilePath);
      if (!file.existsSync()) {
        throw Exception('Opus file not found');
      }

      // Read the opus file data
      final opusData = await file.readAsBytes();

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
        throw Exception('No opus frames found in file');
      }

      // Initialize opus decoder
      final decoder = SimpleOpusDecoder(
        sampleRate: widget.wal.sampleRate,
        channels: widget.wal.channel,
      );

      // Decode all frames
      List<Uint8List> pcmFrames = [];
      for (final opusFrame in opusFrames) {
        try {
          final pcmFrame = decoder.decode(input: opusFrame);
          if (pcmFrame != null) {
            // Convert Int16List to Uint8List
            final uint8Frame = Uint8List.fromList(pcmFrame.buffer.asUint8List());
            pcmFrames.add(uint8Frame);
          }
        } catch (e) {
          debugPrint('Error decoding opus frame: $e');
          // Continue with other frames
        }
      }

      if (pcmFrames.isEmpty) {
        throw Exception('No PCM data decoded');
      }

      // Combine all PCM frames
      final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
      final combinedPcm = Uint8List(totalLength);
      int writeOffset = 0;
      for (final frame in pcmFrames) {
        combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
        writeOffset += frame.length;
      }

      // Create WAV file
      final tempDir = await getTemporaryDirectory();
      final fileName = forSharing
          ? widget.wal.getFileName().replaceAll('.bin', '.wav')
          : 'decoded_${DateTime.now().millisecondsSinceEpoch}.wav';
      final wavFilePath = '${tempDir.path}/$fileName';

      final wavData = _createWavFile(
        pcmData: combinedPcm,
        sampleRate: widget.wal.sampleRate,
        channels: widget.wal.channel,
        bitsPerSample: 16,
      );

      await File(wavFilePath).writeAsBytes(wavData);
      return wavFilePath;
    } catch (e) {
      debugPrint('Error decoding opus to wav: $e');
      return null;
    }
  }

  Future<String?> _convertPcmToWav(String pcmFilePath, {bool forSharing = false}) async {
    try {
      final file = File(pcmFilePath);
      if (!file.existsSync()) {
        throw Exception('PCM file not found');
      }

      // Read the PCM file data (same custom format as opus)
      final pcmFileData = await file.readAsBytes();

      // Parse the custom format: <length>|<data> for each frame
      List<Uint8List> pcmFrames = [];
      int offset = 0;

      while (offset < pcmFileData.length - 4) {
        // Read frame length (4 bytes)
        final lengthBytes = pcmFileData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;

        if (offset + length > pcmFileData.length) break;

        // Read frame data
        final frameData = pcmFileData.sublist(offset, offset + length);
        pcmFrames.add(Uint8List.fromList(frameData));
        offset += length;
      }

      if (pcmFrames.isEmpty) {
        throw Exception('No PCM frames found in file');
      }

      // Combine all PCM frames
      final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
      final combinedPcm = Uint8List(totalLength);
      int writeOffset = 0;
      for (final frame in pcmFrames) {
        combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
        writeOffset += frame.length;
      }

      // Create WAV file
      final tempDir = await getTemporaryDirectory();
      final fileName = forSharing
          ? widget.wal.getFileName().replaceAll('.bin', '.wav')
          : 'converted_${DateTime.now().millisecondsSinceEpoch}.wav';
      final wavFilePath = '${tempDir.path}/$fileName';

      final bitsPerSample = widget.wal.codec == BleAudioCodec.pcm16 ? 16 : 8;
      final wavData = _createWavFile(
        pcmData: combinedPcm,
        sampleRate: widget.wal.sampleRate,
        channels: widget.wal.channel,
        bitsPerSample: bitsPerSample,
      );

      await File(wavFilePath).writeAsBytes(wavData);
      return wavFilePath;
    } catch (e) {
      debugPrint('Error converting PCM to wav: $e');
      return null;
    }
  }

  Future<void> _shareWalAsWav() async {
    if (widget.wal.filePath == null || widget.wal.filePath!.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Audio file not available for sharing'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    if (_isSharing) return;

    setState(() {
      _isSharing = true;
    });

    try {
      String? wavFilePath;

      // Check if it's an opus file that needs decoding
      if (widget.wal.codec.isOpusSupported()) {
        wavFilePath = await _decodeOpusToWav(widget.wal.filePath!, forSharing: true);
      } else {
        // For PCM files, convert to WAV
        wavFilePath = await _convertPcmToWav(widget.wal.filePath!, forSharing: true);
      }

      if (wavFilePath != null && mounted) {
        final result = await Share.shareXFiles(
          [XFile(wavFilePath)],
          text:
              'Omi Audio Recording - ${DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000).toString().split('.')[0]}',
        );

        if (result.status == ShareResultStatus.success) {
          debugPrint('Audio file shared successfully');
        }
      }
    } catch (e) {
      debugPrint('Error sharing audio: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error sharing audio: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isSharing = false;
        });
      }
    }
  }

  Uint8List _createWavFile({
    required Uint8List pcmData,
    required int sampleRate,
    required int channels,
    required int bitsPerSample,
  }) {
    const int wavHeaderSize = 44;
    final int frameSize = ((bitsPerSample + 7) ~/ 8) * channels;
    final int fileSize = wavHeaderSize + pcmData.length;

    final ByteData header = ByteData(wavHeaderSize);
    const Endian endian = Endian.little;

    // WAV header
    header.setUint32(4, fileSize - 8, endian); // File size - 8
    header.setUint32(16, 16, endian); // PCM format chunk size
    header.setUint16(20, 1, endian); // Audio format (PCM)
    header.setUint16(22, channels, endian); // Number of channels
    header.setUint32(24, sampleRate, endian); // Sample rate
    header.setUint32(28, sampleRate * frameSize, endian); // Byte rate
    header.setUint16(32, frameSize, endian); // Block align
    header.setUint16(34, bitsPerSample, endian); // Bits per sample
    header.setUint32(40, pcmData.length, endian); // Data chunk size

    final Uint8List headerBytes = header.buffer.asUint8List();
    headerBytes.setAll(0, ascii.encode('RIFF'));
    headerBytes.setAll(8, ascii.encode('WAVE'));
    headerBytes.setAll(12, ascii.encode('fmt '));
    headerBytes.setAll(36, ascii.encode('data'));

    // Combine header and PCM data
    final Uint8List wavFile = Uint8List(fileSize);
    wavFile.setAll(0, headerBytes);
    wavFile.setAll(wavHeaderSize, pcmData);

    return wavFile;
  }

  void _showResyncDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text('Resync Audio File', style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'This will resync the audio file and may create a new conversation or update an existing one.',
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
              _resyncWal(context);
            },
            child: const Text('Resync', style: TextStyle(color: Colors.orange)),
          ),
        ],
      ),
    );
  }

  void _resyncWal(BuildContext context) {
    context.read<ConversationProvider>().resyncWal(widget.wal);

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Resyncing audio file...'),
        backgroundColor: Colors.orange,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        // TODO
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
        child: Container(
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(16.0),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16.0),
            child: Dismissible(
              key: Key(widget.wal.id),
              direction: widget.wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
              background: Container(
                alignment: Alignment.centerRight,
                padding: const EdgeInsets.only(right: 20.0),
                color: Colors.red,
                child: const Icon(Icons.delete, color: Colors.white),
              ),
              onDismissed: (direction) {
                var wal = widget.wal;
                ServiceManager.instance().wal.getSyncs().deleteWal(wal);
              },
              child: Padding(
                padding: const EdgeInsetsDirectional.all(0),
                child: Column(
                  mainAxisSize: MainAxisSize.max,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ListTile(
                      leading: Padding(
                        padding: const EdgeInsets.only(top: 6.0),
                        child: Text(widget.wal.device == "phone" ? "📱" : "💾",
                            style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w500)),
                      ),
                      title: Row(
                        children: [
                          Expanded(
                            child: Text(
                              secondsToHumanReadable(widget.wal.seconds),
                              style: const TextStyle(color: Colors.white, fontSize: 16),
                            ),
                          ),
                          if (widget.wal.filePath != null && widget.wal.filePath!.isNotEmpty) ...[
                            IconButton(
                              onPressed: _isProcessing ? null : _togglePlayback,
                              icon: _isProcessing
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white70,
                                      ),
                                    )
                                  : Icon(
                                      _isPlaying ? Icons.pause_circle : Icons.play_circle,
                                      color: Colors.white70,
                                      size: 24,
                                    ),
                              tooltip: _isProcessing ? 'Processing...' : (_isPlaying ? 'Pause' : 'Play'),
                            ),
                            IconButton(
                              onPressed: _isSharing ? null : _shareWalAsWav,
                              icon: _isSharing
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white70,
                                      ),
                                    )
                                  : const Icon(
                                      Icons.share,
                                      color: Colors.white70,
                                      size: 20,
                                    ),
                              tooltip: _isSharing ? 'Sharing...' : 'Share as WAV',
                            ),
                          ],
                        ],
                      ),
                      subtitle: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            dateTimeFormat('h:mm a', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                            style: const TextStyle(color: Colors.grey, fontSize: 14),
                          ),
                          Text(
                            '${widget.wal.codec.toString().split('.').last.toUpperCase()} • ${widget.wal.sampleRate}Hz',
                            style: const TextStyle(color: Colors.grey, fontSize: 12),
                          ),
                          if (widget.wal.status == WalStatus.synced)
                            const Text(
                              'Synced ✅',
                              style: TextStyle(color: Colors.green, fontSize: 12),
                            ),
                        ],
                      ),
                      trailing: widget.wal.status == WalStatus.synced
                          ? Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Text(
                                  'Synced',
                                  style: TextStyle(color: Colors.green, fontSize: 14),
                                ),
                                const SizedBox(width: 8),
                                IconButton(
                                  onPressed: () => _showResyncDialog(context),
                                  icon: const Icon(
                                    Icons.refresh,
                                    color: Colors.white70,
                                    size: 20,
                                  ),
                                  tooltip: 'Resync',
                                ),
                              ],
                            )
                          : widget.wal.isSyncing && widget.wal.status != WalStatus.synced
                              ? Text(
                                  "${widget.wal.syncEtaSeconds != null ? "${widget.wal.syncEtaSeconds}s" : "Calculating"} ETA",
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                )
                              : TextButton(
                                  onPressed: () {
                                    context.read<ConversationProvider>().setSyncCompleted(false);
                                    context.read<ConversationProvider>().syncWal(widget.wal);
                                  },
                                  child: const Text('Sync', style: TextStyle(color: Colors.white))),
                    ),
                    if (widget.wal.isSyncing && widget.wal.status != WalStatus.synced)
                      LinearProgressIndicator(
                        value: calculateProgress(
                            widget.wal.syncStartedAt ?? DateTime.now(), widget.wal.syncEtaSeconds ?? 0),
                        backgroundColor: Colors.grey[800],
                        color: Colors.white,
                        minHeight: 4,
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class DateTimeListItem extends StatelessWidget {
  final bool isFirst;
  final DateTime date;

  const DateTimeListItem({super.key, required this.date, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(16, isFirst ? 0 : 20, 16, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            dateTimeFormat('MMM dd hh:00 a', date),
            style: const TextStyle(color: Colors.white, fontSize: 16),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Container(
              height: 1,
              color: Color(0xFF35343B),
            ),
          )
        ],
      ),
    );
  }
}

class SyncWalGroupWidget extends StatelessWidget {
  final List<Wal> wals;
  final DateTime date;
  final bool isFirst;
  const SyncWalGroupWidget({super.key, required this.wals, required this.date, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    if (wals.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DateTimeListItem(date: date, isFirst: isFirst),
          ...wals.map((wal) {
            return WalListItem(wal: wal, walIdx: wals.indexOf(wal), date: date);
          }),
          const SizedBox(height: 16),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }
  }
}

class SyncPage extends StatefulWidget {
  const SyncPage({super.key});

  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> with TickerProviderStateMixin {
  late AnimationController _hideFabAnimation;

  @override
  void initState() {
    _hideFabAnimation = AnimationController(vsync: this, duration: kThemeAnimationDuration, value: 1.0);
    super.initState();
  }

  Future<int> _getTotalWalSeconds() async {
    if (SharedPreferencesUtil().unlimitedLocalStorageEnabled) {
      // Include both missing and synced retained WALs
      final allWals = await context.read<ConversationProvider>().getAllWals();
      int totalSeconds = 0;
      for (var wal in allWals) {
        totalSeconds += wal.seconds;
      }
      return totalSeconds;
    } else {
      // Only missing WALs
      return context.read<ConversationProvider>().missingWalsInSeconds;
    }
  }

  Widget _buildStatItem(String label, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(color: Colors.grey, fontSize: 12),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }

  void _showDeleteSyncedDialog(BuildContext context, ConversationProvider provider) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text('Delete All Synced Files', style: TextStyle(color: Colors.white)),
        content: const Text(
          'This will permanently delete all synced audio files from your device. This action cannot be undone.',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () async {
              Navigator.of(context).pop();
              await provider.deleteAllSyncedWals();
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('All synced audio files have been deleted'),
                    backgroundColor: Colors.green,
                  ),
                );
              }
            },
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _hideFabAnimation.dispose();
    super.dispose();
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.depth == 0) {
      if (notification is UserScrollNotification) {
        final UserScrollNotification userScroll = notification;
        switch (userScroll.direction) {
          case ScrollDirection.forward:
            if (userScroll.metrics.maxScrollExtent != userScroll.metrics.minScrollExtent) {
              _hideFabAnimation.forward();
            }
            break;
          case ScrollDirection.reverse:
            if (userScroll.metrics.maxScrollExtent != userScroll.metrics.minScrollExtent) {
              _hideFabAnimation.reverse();
            }
            break;
          case ScrollDirection.idle:
            break;
        }
      }
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      onPopInvoked: (didPop) {
        var provider = Provider.of<ConversationProvider>(context, listen: false);
        provider.clearSyncResult();
      },
      child: Consumer<ConversationProvider>(builder: (context, conversationProvider, child) {
        return Scaffold(
          appBar: AppBarWithBanner(
            appBar: AppBar(
              title: const Text('Sync Conversations'),
              backgroundColor: Theme.of(context).colorScheme.primary,
            ),
            showAppBar: conversationProvider.isSyncing || conversationProvider.syncCompleted,
            child: Container(
              color: Colors.green,
              child: Center(
                child: Text(
                  conversationProvider.isSyncing
                      ? 'Syncing Conversations'
                      : conversationProvider.syncCompleted
                          ? 'Conversations Synced Successfully 🎉'
                          : '',
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              ),
            ),
          ),
          backgroundColor: Theme.of(context).colorScheme.primary,
          floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
          floatingActionButton: conversationProvider.isSyncing || conversationProvider.syncCompleted
              ? const SizedBox()
              : ScaleTransition(
                  scale: _hideFabAnimation,
                  child: Container(
                    margin: const EdgeInsets.fromLTRB(32, 16, 32, 0),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                    decoration: BoxDecoration(
                      border: const GradientBoxBorder(
                        gradient: LinearGradient(colors: [
                          Color.fromARGB(127, 208, 208, 208),
                          Color.fromARGB(127, 188, 99, 121),
                          Color.fromARGB(127, 86, 101, 182),
                          Color.fromARGB(127, 126, 190, 236)
                        ]),
                        width: 2,
                      ),
                      borderRadius: BorderRadius.circular(12),
                      color: Colors.black,
                    ),
                    child: TextButton(
                      onPressed: () async {
                        if (context.read<ConnectivityProvider>().isConnected) {
                          // _toggleAnimation();
                          await conversationProvider.syncWals();
                          // _toggleAnimation();
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Internet connection is required to sync memories'),
                              backgroundColor: Colors.red,
                            ),
                          );
                        }
                      },
                      child: const Text(
                        'Sync All',
                        style: TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ),
                  ),
                ),
          body: NotificationListener(
            onNotification: _handleScrollNotification,
            child: CustomScrollView(
              slivers: [
                SliverToBoxAdapter(
                  child: Column(
                    children: [
                      conversationProvider.isSyncing
                          ? Container(
                              padding: const EdgeInsets.all(12.0),
                              margin: const EdgeInsets.only(left: 16.0, right: 16.0, top: 12),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1F1F25),
                                borderRadius: BorderRadius.circular(16.0),
                              ),
                              child: const ListTile(
                                leading: Icon(
                                  Icons.warning,
                                  color: Colors.yellow,
                                ),
                                title: Text('Please do not close the app while sync is in progress'),
                              ),
                            )
                          : const SizedBox.shrink(),
                      const SizedBox(height: 30),
                      FutureBuilder<int>(
                        future: _getTotalWalSeconds(),
                        builder: (context, snapshot) {
                          int totalSeconds = snapshot.data ?? conversationProvider.missingWalsInSeconds;
                          return Text(
                            secondsToHumanReadable(totalSeconds),
                            style: const TextStyle(color: Colors.white, fontSize: 30),
                          );
                        },
                      ),
                      const SizedBox(height: 12),
                      Text(
                        SharedPreferencesUtil().unlimitedLocalStorageEnabled
                            ? 'to sync + stored locally'
                            : 'of conversations',
                        style: const TextStyle(color: Colors.white, fontSize: 18),
                      ),
                      const SizedBox(height: 20),
                      // WAL Stats Widget
                      FutureBuilder<WalStats>(
                        future: conversationProvider.getWalStats(),
                        builder: (context, snapshot) {
                          if (!snapshot.hasData) {
                            return const SizedBox.shrink();
                          }
                          final stats = snapshot.data!;
                          return Container(
                            margin: const EdgeInsets.symmetric(horizontal: 16),
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1F1F25),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Audio Files Statistics',
                                  style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                                ),
                                const SizedBox(height: 12),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    _buildStatItem('Total Files', '${stats.totalFiles}'),
                                    _buildStatItem('Total Size', stats.totalSizeFormatted),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    _buildStatItem('📱 Phone', '${stats.phoneFiles} (${stats.phoneSizeFormatted})'),
                                    _buildStatItem('💾 SD Card', '${stats.sdcardFiles} (${stats.sdcardSizeFormatted})'),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    _buildStatItem('✅ Synced', '${stats.syncedFiles}'),
                                    _buildStatItem('⏳ Pending', '${stats.missedFiles}'),
                                  ],
                                ),
                                if (stats.syncedFiles > 0) ...[
                                  const SizedBox(height: 12),
                                  SizedBox(
                                    width: double.infinity,
                                    child: ElevatedButton.icon(
                                      onPressed: () => _showDeleteSyncedDialog(context, conversationProvider),
                                      icon: const Icon(Icons.delete_sweep, size: 18),
                                      label: const Text('Delete All Synced Files'),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.red.shade700,
                                        foregroundColor: Colors.white,
                                      ),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          );
                        },
                      ),
                      const SizedBox(height: 20),
                      conversationProvider.isSyncing
                          ? conversationProvider.isFetchingConversations
                              ? const Padding(
                                  padding: EdgeInsets.all(8.0),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      SizedBox(
                                        height: 20,
                                        width: 20,
                                        child: CircularProgressIndicator(
                                          color: Colors.white,
                                        ),
                                      ),
                                      SizedBox(width: 12),
                                      Text(
                                        'Finalizing synced conversations',
                                        style: TextStyle(color: Colors.white, fontSize: 16),
                                        textAlign: TextAlign.center,
                                      ),
                                    ],
                                  ),
                                )
                              : const Padding(
                                  padding: EdgeInsets.all(8.0),
                                  child: Text(
                                    'Sync in Progress',
                                    style: TextStyle(color: Colors.white, fontSize: 16),
                                    textAlign: TextAlign.center,
                                  ),
                                )
                          : conversationProvider.syncCompleted &&
                                  conversationProvider.syncedConversationsPointers.isNotEmpty
                              ? Column(
                                  children: [
                                    const Text(
                                      'Conversations Synced Successfully 🎉',
                                      style: TextStyle(color: Colors.white, fontSize: 16),
                                    ),
                                    const SizedBox(
                                      height: 18,
                                    ),
                                    (conversationProvider.syncedConversationsPointers.isNotEmpty)
                                        ? Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                            decoration: BoxDecoration(
                                              border: const GradientBoxBorder(
                                                gradient: LinearGradient(colors: [
                                                  Color.fromARGB(127, 208, 208, 208),
                                                  Color.fromARGB(127, 188, 99, 121),
                                                  Color.fromARGB(127, 86, 101, 182),
                                                  Color.fromARGB(127, 126, 190, 236)
                                                ]),
                                                width: 2,
                                              ),
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                            child: TextButton(
                                              onPressed: () {
                                                routeToPage(context, const SyncedConversationsPage());
                                              },
                                              child: const Text(
                                                'View Synced Conversations',
                                                style: TextStyle(color: Colors.white, fontSize: 16),
                                              ),
                                            ),
                                          )
                                        : const SizedBox.shrink(),
                                  ],
                                )
                              : const SizedBox.shrink(),
                    ],
                  ),
                ),
                const SliverToBoxAdapter(child: SizedBox(height: 50)),
                Consumer<ConversationProvider>(
                  builder: (context, conversationProvider, child) {
                    return FutureBuilder<List<Wal>>(
                      future: conversationProvider.getAllWals(),
                      builder: (context, snapshot) {
                        if (snapshot.connectionState == ConnectionState.waiting) {
                          return const SliverToBoxAdapter(
                            child: Center(
                              child: CircularProgressIndicator(color: Colors.white),
                            ),
                          );
                        }

                        if (snapshot.hasError) {
                          return SliverToBoxAdapter(
                            child: Center(
                              child: Text(
                                'Error loading WAL files: ${snapshot.error}',
                                style: const TextStyle(color: Colors.red),
                              ),
                            ),
                          );
                        }

                        final allWals = snapshot.data ?? [];
                        if (allWals.isEmpty) {
                          return const SliverToBoxAdapter(
                            child: Center(
                              child: Padding(
                                padding: EdgeInsets.all(32.0),
                                child: Text(
                                  'No audio files found',
                                  style: TextStyle(color: Colors.grey, fontSize: 16),
                                ),
                              ),
                            ),
                          );
                        }

                        return WalsListWidget(wals: allWals);
                      },
                    );
                  },
                ),
                const SliverToBoxAdapter(child: SizedBox(height: 50)),
              ],
            ),
          ),
        );
      }),
    );
  }
}

Map<DateTime, List<Wal>> _groupWalsByDate(List<Wal> wals) {
  var groupedWals = <DateTime, List<Wal>>{};
  wals.sort((a, b) => b.timerStart.compareTo(a.timerStart));
  for (var wal in wals) {
    var createdAt = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    var date = DateTime(createdAt.year, createdAt.month, createdAt.day, createdAt.hour);
    if (!groupedWals.containsKey(date)) {
      groupedWals[date] = [];
    }
    groupedWals[date]?.add(wal);
  }
  for (final date in groupedWals.keys) {
    groupedWals[date]?.sort((a, b) => b.timerStart.compareTo(a.timerStart));
  }
  return groupedWals;
}

class WalsListWidget extends StatelessWidget {
  final List<Wal> wals;
  const WalsListWidget({super.key, required this.wals});

  @override
  Widget build(BuildContext context) {
    var groupedWals = _groupWalsByDate(wals);

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        childCount: groupedWals.keys.length,
        (context, index) {
          var date = groupedWals.keys.toList()[index];
          List<Wal> wals = groupedWals[date] ?? [];
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (index == 0) const SizedBox(height: 16),
              SyncWalGroupWidget(
                isFirst: index == 0,
                wals: wals,
                date: date,
              ),
            ],
          );
        },
      ),
    );
  }
}

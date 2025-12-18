import 'dart:async';

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';

class ConversationAudioPlayerWidget extends StatefulWidget {
  final ServerConversation conversation;
  final VoidCallback? onExpand;
  final VoidCallback? onCollapse;
  final bool isExpanded;

  const ConversationAudioPlayerWidget({
    super.key,
    required this.conversation,
    this.onExpand,
    this.onCollapse,
    this.isExpanded = false,
  });

  @override
  State<ConversationAudioPlayerWidget> createState() => _ConversationAudioPlayerWidgetState();
}

class _ConversationAudioPlayerWidgetState extends State<ConversationAudioPlayerWidget> {
  final AudioPlayer _audioPlayer = AudioPlayer();
  bool _isLoading = false;
  String? _errorMessage;
  double _playbackSpeed = 1.0;
  int _retryCount = 0;
  static const int _maxRetries = 3;

  // Total duration calculated from audio file metadata
  Duration _totalDuration = Duration.zero;
  // Cumulative durations for each track (used to calculate combined position)
  List<Duration> _trackStartOffsets = [];

  StreamSubscription<SequenceState?>? _sequenceSubscription;
  StreamSubscription<Object>? _errorSubscription;

  @override
  void initState() {
    super.initState();
    _calculateTotalDuration();
    _setupAudioPlayer();
  }

  @override
  void dispose() {
    _sequenceSubscription?.cancel();
    _errorSubscription?.cancel();
    _audioPlayer.dispose();
    super.dispose();
  }

  /// Calculate total duration from audio file metadata
  void _calculateTotalDuration() {
    double totalSeconds = 0;
    _trackStartOffsets = [];

    for (final audioFile in widget.conversation.audioFiles) {
      _trackStartOffsets.add(Duration(milliseconds: (totalSeconds * 1000).toInt()));
      totalSeconds += audioFile.duration;
    }

    _totalDuration = Duration(milliseconds: (totalSeconds * 1000).toInt());
    debugPrint('Total duration from metadata: $_totalDuration');
    debugPrint('Track offsets: $_trackStartOffsets');
  }

  /// Get combined position across all tracks
  Duration _getCombinedPosition(int? currentIndex, Duration trackPosition) {
    if (currentIndex == null || currentIndex >= _trackStartOffsets.length) {
      return trackPosition;
    }
    return _trackStartOffsets[currentIndex] + trackPosition;
  }

  Future<void> _setupAudioPlayer() async {
    if (!widget.conversation.hasAudio()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final headers = await getAudioHeaders();

      final audioFileIds = widget.conversation.audioFiles.map((af) => af.id).toList();
      final urls = getConversationAudioUrls(
        conversationId: widget.conversation.id,
        audioFileIds: audioFileIds,
        format: 'wav',
      );

      // Create concatenating audio source for gapless playback
      final playlist = ConcatenatingAudioSource(
        useLazyPreparation: true,
        children: urls.map((url) {
          return AudioSource.uri(
            Uri.parse(url),
            headers: headers,
          );
        }).toList(),
      );

      // Listen for playback errors
      _errorSubscription?.cancel();
      _errorSubscription = _audioPlayer.playbackEventStream.handleError((error) {
        debugPrint('Playback error: $error');
        if (mounted && _retryCount < _maxRetries) {
          _retryCount++;
          Future.delayed(const Duration(seconds: 1), () {
            if (mounted) _setupAudioPlayer();
          });
        } else if (mounted) {
          setState(() {
            _errorMessage = 'Playback error: ${error.toString()}';
          });
        }
      }).listen((_) {});

      await _audioPlayer.setAudioSource(
        playlist,
        preload: true,
      );

      _retryCount = 0;

      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    } catch (e, stackTrace) {
      debugPrint('Error setting up audio player: $e');
      debugPrint('Stack trace: $stackTrace');

      if (_retryCount < _maxRetries) {
        _retryCount++;
        await Future.delayed(Duration(seconds: _retryCount));
        if (mounted) {
          _setupAudioPlayer();
        }
        return;
      }

      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorMessage = 'Failed to load audio. Please try again.';
        });
      }
    }
  }

  Future<void> _retryLoad() async {
    _retryCount = 0;
    await _setupAudioPlayer();
  }

  Future<void> _togglePlayPause() async {
    if (_audioPlayer.playing) {
      await _audioPlayer.pause();
    } else {
      await _audioPlayer.play();
    }
  }

  Future<void> _setPlaybackSpeed(double speed) async {
    setState(() {
      _playbackSpeed = speed;
    });
    await _audioPlayer.setSpeed(speed);
  }

  /// Seek to a combined position across all tracks
  Future<void> _seekToCombinedPosition(Duration targetPosition) async {
    // Find which track this position falls into
    int targetIndex = 0;
    Duration positionInTrack = targetPosition;

    for (int i = 0; i < _trackStartOffsets.length; i++) {
      if (i == _trackStartOffsets.length - 1) {
        // Last track
        targetIndex = i;
        positionInTrack = targetPosition - _trackStartOffsets[i];
        break;
      } else if (targetPosition >= _trackStartOffsets[i] && targetPosition < _trackStartOffsets[i + 1]) {
        targetIndex = i;
        positionInTrack = targetPosition - _trackStartOffsets[i];
        break;
      }
    }

    await _audioPlayer.seek(positionInTrack, index: targetIndex);
  }

  String _formatDuration(Duration duration) {
    String twoDigits(int n) => n.toString().padLeft(2, '0');
    final minutes = twoDigits(duration.inMinutes.remainder(60));
    final seconds = twoDigits(duration.inSeconds.remainder(60));
    if (duration.inHours > 0) {
      return '${duration.inHours}:$minutes:$seconds';
    }
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.conversation.hasAudio()) {
      return const SizedBox.shrink();
    }

    if (widget.isExpanded) {
      return _buildExpandedPlayer();
    }

    return const SizedBox.shrink();
  }

  Widget _buildExpandedPlayer() {
    if (_isLoading) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: const Center(
          child: CircularProgressIndicator(color: Colors.deepPurpleAccent),
        ),
      );
    }

    if (_errorMessage != null) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 32),
            const SizedBox(height: 8),
            const Text(
              'Error loading audio',
              style: TextStyle(color: Colors.red),
            ),
            const SizedBox(height: 4),
            Text(
              _errorMessage!,
              style: const TextStyle(color: Colors.grey, fontSize: 12),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            TextButton.icon(
              onPressed: _retryLoad,
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Retry'),
              style: TextButton.styleFrom(
                foregroundColor: Colors.deepPurpleAccent,
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              _buildPlayPauseButton(),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Combined progress slider using total duration from metadata
                    StreamBuilder<int?>(
                      stream: _audioPlayer.currentIndexStream,
                      builder: (context, indexSnapshot) {
                        final currentIndex = indexSnapshot.data ?? 0;

                        return StreamBuilder<Duration>(
                          stream: _audioPlayer.positionStream,
                          builder: (context, positionSnapshot) {
                            final trackPosition = positionSnapshot.data ?? Duration.zero;
                            final combinedPosition = _getCombinedPosition(currentIndex, trackPosition);

                            return SliderTheme(
                              data: SliderTheme.of(context).copyWith(
                                trackHeight: 4,
                                thumbShape: const RoundSliderThumbShape(
                                  enabledThumbRadius: 6,
                                ),
                                overlayShape: const RoundSliderOverlayShape(
                                  overlayRadius: 14,
                                ),
                              ),
                              child: Slider(
                                value: combinedPosition.inMilliseconds.toDouble().clamp(
                                      0,
                                      _totalDuration.inMilliseconds.toDouble(),
                                    ),
                                max: _totalDuration.inMilliseconds.toDouble().clamp(1.0, double.infinity),
                                activeColor: Colors.deepPurpleAccent,
                                inactiveColor: Colors.grey.shade700,
                                onChanged: (value) {
                                  _seekToCombinedPosition(Duration(milliseconds: value.toInt()));
                                },
                              ),
                            );
                          },
                        );
                      },
                    ),
                    // Time display showing combined position / total duration
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8.0),
                      child: StreamBuilder<int?>(
                        stream: _audioPlayer.currentIndexStream,
                        builder: (context, indexSnapshot) {
                          final currentIndex = indexSnapshot.data ?? 0;

                          return StreamBuilder<Duration>(
                            stream: _audioPlayer.positionStream,
                            builder: (context, positionSnapshot) {
                              final trackPosition = positionSnapshot.data ?? Duration.zero;
                              final combinedPosition = _getCombinedPosition(currentIndex, trackPosition);

                              return Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(
                                    _formatDuration(combinedPosition),
                                    style: const TextStyle(
                                      color: Colors.grey,
                                      fontSize: 12,
                                    ),
                                  ),
                                  Text(
                                    _formatDuration(_totalDuration),
                                    style: const TextStyle(
                                      color: Colors.grey,
                                      fontSize: 12,
                                    ),
                                  ),
                                ],
                              );
                            },
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close, color: Colors.grey),
                onPressed: widget.onCollapse,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildSpeedButton(0.75),
              const SizedBox(width: 8),
              _buildSpeedButton(1.0),
              const SizedBox(width: 8),
              _buildSpeedButton(1.25),
              const SizedBox(width: 8),
              _buildSpeedButton(1.5),
              const SizedBox(width: 8),
              _buildSpeedButton(2.0),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPlayPauseButton() {
    return StreamBuilder<PlayerState>(
      stream: _audioPlayer.playerStateStream,
      builder: (context, snapshot) {
        final playerState = snapshot.data;
        final isPlaying = playerState?.playing ?? false;
        final processingState = playerState?.processingState ?? ProcessingState.idle;

        if (processingState == ProcessingState.loading || processingState == ProcessingState.buffering) {
          return Container(
            width: 48,
            height: 48,
            decoration: const BoxDecoration(
              color: Colors.deepPurpleAccent,
              shape: BoxShape.circle,
            ),
            child: const Center(
              child: SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  color: Colors.white,
                  strokeWidth: 2,
                ),
              ),
            ),
          );
        }

        return IconButton(
          onPressed: _togglePlayPause,
          icon: Icon(
            isPlaying ? Icons.pause : Icons.play_arrow,
            color: Colors.white,
            size: 32,
          ),
          style: IconButton.styleFrom(
            backgroundColor: Colors.deepPurpleAccent,
            shape: const CircleBorder(),
            fixedSize: const Size(48, 48),
          ),
        );
      },
    );
  }

  Widget _buildSpeedButton(double speed) {
    final isSelected = _playbackSpeed == speed;
    return InkWell(
      onTap: () => _setPlaybackSpeed(speed),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? Colors.deepPurpleAccent : const Color(0xFF35343B),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          '${speed}x',
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.grey,
            fontSize: 12,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:just_audio/just_audio.dart';
import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

class DesktopAudioPlayer extends StatefulWidget {
  final ServerConversation conversation;

  const DesktopAudioPlayer({
    super.key,
    required this.conversation,
  });

  @override
  State<DesktopAudioPlayer> createState() => _DesktopAudioPlayerState();
}

class _DesktopAudioPlayerState extends State<DesktopAudioPlayer> {
  AudioPlayer? _audioPlayer;
  bool _isAudioLoading = false;
  bool _isAudioInitialized = false;
  Duration _totalDuration = Duration.zero;
  List<Duration> _trackStartOffsets = [];

  @override
  void initState() {
    super.initState();
    _calculateTotalDuration();
  }

  @override
  void didUpdateWidget(DesktopAudioPlayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.conversation.id != oldWidget.conversation.id) {
      _calculateTotalDuration();
      _isAudioInitialized = false;
      _audioPlayer?.dispose();
      _audioPlayer = null;
    }
  }

  @override
  void dispose() {
    _audioPlayer?.dispose();
    super.dispose();
  }

  void _calculateTotalDuration() {
    double totalSeconds = 0;
    _trackStartOffsets = [];
    final files = List<AudioFile>.from(widget.conversation.audioFiles);
    files.sort((a, b) {
      final aTime = a.startedAt?.millisecondsSinceEpoch ?? 0;
      final bTime = b.startedAt?.millisecondsSinceEpoch ?? 0;
      return aTime.compareTo(bTime);
    });

    for (final audioFile in files) {
      _trackStartOffsets.add(Duration(milliseconds: (totalSeconds * 1000).toInt()));
      totalSeconds += audioFile.duration;
    }
    _totalDuration = Duration(milliseconds: (totalSeconds * 1000).toInt());
  }

  Duration _getCombinedPosition(int? currentIndex, Duration trackPosition) {
    if (currentIndex == null || currentIndex >= _trackStartOffsets.length) {
      return trackPosition;
    }
    return _trackStartOffsets[currentIndex] + trackPosition;
  }

  Future<void> _initAudioIfNeeded() async {
    if (!mounted) return;
    if (_isAudioInitialized || !widget.conversation.hasAudio()) {
      return;
    }

    setState(() {
      _isAudioLoading = true;
    });

    try {
      _audioPlayer = AudioPlayer();

      final signedUrlInfos = await getConversationAudioSignedUrls(widget.conversation.id);
      final sortedAudioFiles = List<AudioFile>.from(widget.conversation.audioFiles);
      sortedAudioFiles.sort((a, b) {
        final aTime = a.startedAt?.millisecondsSinceEpoch ?? 0;
        final bTime = b.startedAt?.millisecondsSinceEpoch ?? 0;
        return aTime.compareTo(bTime);
      });

      List<AudioSource> audioSources = [];
      Map<String, String>? fallbackHeaders;

      for (final audioFile in sortedAudioFiles) {
        final fileId = audioFile.id;
        final urlInfo = signedUrlInfos.firstWhere(
          (info) => info.id == fileId,
          orElse: () => AudioFileUrlInfo(id: fileId, status: 'pending', duration: 0),
        );

        if (urlInfo.isCached && urlInfo.signedUrl != null) {
          audioSources.add(AudioSource.uri(Uri.parse(urlInfo.signedUrl!)));
        } else {
          fallbackHeaders ??= await getAudioHeaders();
          final apiUrl = getAudioStreamUrl(
            conversationId: widget.conversation.id,
            audioFileId: fileId,
            format: 'wav',
          );
          audioSources.add(AudioSource.uri(Uri.parse(apiUrl), headers: fallbackHeaders));
        }
      }

      final playlist = ConcatenatingAudioSource(
        useLazyPreparation: true,
        children: audioSources,
      );

      await _audioPlayer!.setAudioSource(playlist, preload: true);
      _isAudioInitialized = true;
    } catch (e) {
      Logger.debug('Error initializing audio: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isAudioLoading = false;
        });
      }
    }
  }

  Future<void> _togglePlayPause() async {
    if (!_isAudioInitialized && !_isAudioLoading) {
      await _initAudioIfNeeded();
    }
    if (!mounted) return;
    if (_audioPlayer == null) return;

    if (_audioPlayer!.playing) {
      MixpanelManager().audioPlaybackPaused(
        conversationId: widget.conversation.id,
        positionSeconds: _audioPlayer!.position.inSeconds,
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );
      await _audioPlayer!.pause();
    } else {
      MixpanelManager().audioPlaybackStarted(
        conversationId: widget.conversation.id,
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );
      await _audioPlayer!.play();
    }
    if (mounted) setState(() {});
  }

  Future<void> _seekToCombinedPosition(Duration targetPosition) async {
    if (_audioPlayer == null) return;

    int targetIndex = 0;
    Duration positionInTrack = targetPosition;

    for (int i = 0; i < _trackStartOffsets.length; i++) {
      if (i == _trackStartOffsets.length - 1) {
        targetIndex = i;
        positionInTrack = targetPosition - _trackStartOffsets[i];
        break;
      } else if (targetPosition >= _trackStartOffsets[i] && targetPosition < _trackStartOffsets[i + 1]) {
        targetIndex = i;
        positionInTrack = targetPosition - _trackStartOffsets[i];
        break;
      }
    }

    if (positionInTrack.isNegative) {
      positionInTrack = Duration.zero;
    }

    MixpanelManager().audioPlaybackSeeked(
      conversationId: widget.conversation.id,
      toPositionSeconds: targetPosition.inSeconds,
    );

    await _audioPlayer!.seek(positionInTrack, index: targetIndex);
  }

  String _formatDurationRemaining(Duration position) {
    final remaining = _totalDuration - position;
    if (remaining.isNegative) return '0:00';
    final minutes = remaining.inMinutes.remainder(60);
    final seconds = remaining.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.conversation.hasAudio()) {
      return const SizedBox.shrink();
    }

    return Center(
      child: Container(
        height: 56,
        margin: const EdgeInsets.only(bottom: 24),
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: const Color(0xFF6B46C1),
          borderRadius: BorderRadius.circular(28),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              spreadRadius: 1,
              blurRadius: 5,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _buildPlayPauseButton(),
            const SizedBox(width: 8),
            _buildProgressBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildPlayPauseButton() {
    if (_isAudioLoading) {
      return const SizedBox(
        width: 32,
        height: 32,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      );
    }

    if (_audioPlayer == null) {
      return GestureDetector(
        onTap: _togglePlayPause,
        child: Container(
          width: 32,
          height: 32,
          decoration: const BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.play_arrow,
            color: Color(0xFF6B46C1),
            size: 20,
          ),
        ),
      );
    }

    return StreamBuilder<PlayerState>(
      stream: _audioPlayer!.playerStateStream,
      builder: (context, snapshot) {
        final playerState = snapshot.data;
        final isPlaying = playerState?.playing ?? false;
        final processingState = playerState?.processingState ?? ProcessingState.idle;

        if (processingState == ProcessingState.loading || processingState == ProcessingState.buffering) {
          return const SizedBox(
            width: 32,
            height: 32,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
            ),
          );
        }

        return GestureDetector(
          onTap: _togglePlayPause,
          child: Container(
            width: 32,
            height: 32,
            decoration: const BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
            ),
            child: Icon(
              isPlaying ? Icons.pause : Icons.play_arrow,
              color: const Color(0xFF6B46C1),
              size: 20,
            ),
          ),
        );
      },
    );
  }

  Widget _buildProgressBar() {
    const double progressBarWidth = 140.0; // Slightly wider for desktop

    if (_audioPlayer == null) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: progressBarWidth,
            height: 12,
            alignment: Alignment.center,
            child: Container(
              width: progressBarWidth,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Text(
            _formatDurationRemaining(Duration.zero),
            style: const TextStyle(color: Colors.white, fontSize: 12),
          ),
        ],
      );
    }

    return StreamBuilder<int?>(
      stream: _audioPlayer!.currentIndexStream,
      builder: (context, indexSnapshot) {
        final currentIndex = indexSnapshot.data ?? 0;
        return StreamBuilder<Duration>(
          stream: _audioPlayer!.positionStream,
          builder: (context, positionSnapshot) {
            final trackPosition = positionSnapshot.data ?? Duration.zero;
            final combinedPosition = _getCombinedPosition(currentIndex, trackPosition);
            final progress = _totalDuration.inMilliseconds > 0
                ? (combinedPosition.inMilliseconds / _totalDuration.inMilliseconds).clamp(0.0, 1.0)
                : 0.0;

            return Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                GestureDetector(
                  onTapDown: (details) {
                    final tapPosition = details.localPosition.dx;
                    final seekProgress = (tapPosition / progressBarWidth).clamp(0.0, 1.0);
                    final seekPosition = Duration(
                      milliseconds: (seekProgress * _totalDuration.inMilliseconds).toInt(),
                    );
                    _seekToCombinedPosition(seekPosition);
                  },
                  onHorizontalDragUpdate: (details) {
                    final tapPosition = details.localPosition.dx;
                    final seekProgress = (tapPosition / progressBarWidth).clamp(0.0, 1.0);
                    final seekPosition = Duration(
                      milliseconds: (seekProgress * _totalDuration.inMilliseconds).toInt(),
                    );
                    _seekToCombinedPosition(seekPosition);
                  },
                  child: Container(
                    width: progressBarWidth,
                    height: 20,
                    alignment: Alignment.center,
                    child: Container(
                      width: progressBarWidth,
                      height: 4,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.3),
                        borderRadius: BorderRadius.circular(2),
                      ),
                      child: FractionallySizedBox(
                        alignment: Alignment.centerLeft,
                        widthFactor: progress,
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(2),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _formatDurationRemaining(combinedPosition),
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

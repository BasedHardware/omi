import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:just_audio/just_audio.dart';
import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

enum ConversationBottomBarMode {
  recording, // During active recording (no summary icon)
  detail // For viewing completed conversations
}

enum ConversationTab { transcript, summary, actionItems }

class ConversationBottomBar extends StatefulWidget {
  final ConversationBottomBarMode mode;
  final ConversationTab selectedTab;
  final Function(ConversationTab) onTabSelected;
  final VoidCallback onStopPressed;
  final bool hasSegments;
  final bool hasActionItems;
  final ServerConversation? conversation;

  const ConversationBottomBar({
    super.key,
    required this.mode,
    required this.selectedTab,
    required this.onTabSelected,
    required this.onStopPressed,
    this.hasSegments = true,
    this.hasActionItems = true,
    this.conversation,
  });

  @override
  State<ConversationBottomBar> createState() => _ConversationBottomBarState();
}

class _ConversationBottomBarState extends State<ConversationBottomBar> {
  // Audio player for inline controls
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
  void didUpdateWidget(ConversationBottomBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.conversation?.id != oldWidget.conversation?.id) {
      _calculateTotalDuration();
    }
  }

  @override
  void dispose() {
    _audioPlayer?.dispose();
    super.dispose();
  }

  void _calculateTotalDuration() {
    if (widget.conversation == null) return;
    double totalSeconds = 0;
    _trackStartOffsets = [];
    for (final audioFile in widget.conversation!.audioFiles) {
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
    if (_isAudioInitialized || widget.conversation == null || !widget.conversation!.hasAudio()) {
      return;
    }

    setState(() {
      _isAudioLoading = true;
    });

    _calculateTotalDuration();

    try {
      _audioPlayer = AudioPlayer();

      final signedUrlInfos = await getConversationAudioSignedUrls(widget.conversation!.id);
      final audioFileIds = widget.conversation!.audioFiles.map((af) => af.id).toList();

      List<AudioSource> audioSources = [];
      Map<String, String>? fallbackHeaders;

      for (final fileId in audioFileIds) {
        // Find matching signed URL info
        final urlInfo = signedUrlInfos.firstWhere(
          (info) => info.id == fileId,
          orElse: () => AudioFileUrlInfo(id: fileId, status: 'pending', duration: 0),
        );

        if (urlInfo.isCached && urlInfo.signedUrl != null) {
          // Use signed URL directly
          audioSources.add(AudioSource.uri(Uri.parse(urlInfo.signedUrl!)));
        } else {
          // Fall back to API URL
          fallbackHeaders ??= await getAudioHeaders();
          final apiUrl = getAudioStreamUrl(
            conversationId: widget.conversation!.id,
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
      debugPrint('Error initializing audio: $e');
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

    final conversationId = widget.conversation?.id ?? '';

    if (_audioPlayer!.playing) {
      // Track pause
      final position = _audioPlayer!.position;
      final currentIndex = _audioPlayer!.currentIndex ?? 0;
      final combinedPosition = _getCombinedPosition(currentIndex, position);

      MixpanelManager().audioPlaybackPaused(
        conversationId: conversationId,
        positionSeconds: combinedPosition.inSeconds,
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );

      await _audioPlayer!.pause();
    } else {
      // Track play
      MixpanelManager().audioPlaybackStarted(
        conversationId: conversationId,
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );

      await _audioPlayer!.play();
    }
    if (mounted) setState(() {});
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
    if (!widget.hasSegments) {
      return const SizedBox();
    }

    return Center(
      child: _buildBottomBar(context),
    );
  }

  Widget _buildBottomBar(BuildContext context) {
    if (widget.mode == ConversationBottomBarMode.recording) {
      return _buildRecordingBar();
    }
    return _buildDetailBar(context);
  }

  Widget _buildRecordingBar() {
    return Material(
      elevation: 8,
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(28),
      child: Container(
        height: 56,
        width: 180,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: const Color(0xFF1A0B2E),
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
            _buildCircularButton(
              icon: FontAwesomeIcons.solidComments,
              isSelected: widget.selectedTab == ConversationTab.transcript,
              onTap: () => widget.onTabSelected(ConversationTab.transcript),
            ),
            const SizedBox(width: 8),
            _buildStopButton(),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailBar(BuildContext context) {
    final isTranscriptSelected = widget.selectedTab == ConversationTab.transcript;
    final isSummarySelected = widget.selectedTab == ConversationTab.summary;
    final hasAudio = widget.conversation?.hasAudio() ?? false;

    const double iconSize = 56.0;
    const double transcriptPillWidth = 195.0;
    const double summaryPillWidth = 140.0;

    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // Transcript: animated width expansion/collapse
        AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeInOut,
          width: (isTranscriptSelected && hasAudio) ? transcriptPillWidth : iconSize,
          height: iconSize,
          clipBehavior: Clip.hardEdge,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
          ),
          child: OverflowBox(
            maxWidth: transcriptPillWidth,
            alignment: Alignment.center,
            child: (isTranscriptSelected && hasAudio)
                ? _buildTranscriptPillContent()
                : _buildCircularButtonContent(
                    icon: FontAwesomeIcons.solidComments,
                    isSelected: isTranscriptSelected,
                    onTap: () => widget.onTabSelected(ConversationTab.transcript),
                  ),
          ),
        ),

        const SizedBox(width: 8),

        AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeInOut,
          width: isSummarySelected ? summaryPillWidth : iconSize,
          height: iconSize,
          clipBehavior: Clip.hardEdge,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
          ),
          child: OverflowBox(
            maxWidth: summaryPillWidth,
            alignment: Alignment.center,
            child: isSummarySelected
                ? _buildSummaryPillContent(context)
                : _buildCircularButtonContent(
                    icon: FontAwesomeIcons.solidFileLines,
                    isSelected: false,
                    onTap: () => widget.onTabSelected(ConversationTab.summary),
                  ),
          ),
        ),

        if (widget.hasActionItems) ...[
          const SizedBox(width: 8),
          _buildCircularButton(
            icon: FontAwesomeIcons.listCheck,
            isSelected: widget.selectedTab == ConversationTab.actionItems,
            onTap: () => widget.onTabSelected(ConversationTab.actionItems),
          ),
        ],
      ],
    );
  }

  Widget _buildTranscriptPillContent() {
    return Container(
      height: 56,
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
          // Play/Pause button
          _buildPlayPauseButton(),
          const SizedBox(width: 8),
          // Progress bar + time remaining
          Flexible(child: _buildProgressBar()),
        ],
      ),
    );
  }

  Widget _buildCircularButtonContent({
    required IconData icon,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Container(
      height: 56,
      width: 56,
      decoration: BoxDecoration(
        color: isSelected ? const Color(0xFF6B46C1) : const Color(0xFF2D1B4E),
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            spreadRadius: 1,
            blurRadius: 5,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        child: InkWell(
          borderRadius: BorderRadius.circular(28),
          onTap: () {
            HapticFeedback.mediumImpact();
            onTap();
          },
          child: Center(
            child: FaIcon(
              icon,
              color: isSelected ? Colors.white : Colors.grey.shade400,
              size: 22,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryPillContent(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, _) {
        final summarizedApp = provider.getSummarizedApp();
        final app = summarizedApp != null
            ? provider.appsList.firstWhereOrNull((element) => element.id == summarizedApp.appId)
            : null;

        return _buildSummaryPillInner(context, provider, app);
      },
    );
  }

  Widget _buildSummaryPillInner(BuildContext context, ConversationDetailProvider provider, App? app) {
    final isReprocessing = provider.loadingReprocessConversation;
    final reprocessingApp = provider.selectedAppForReprocessing;

    void handleTap() {
      HapticFeedback.mediumImpact();
      if (widget.selectedTab == ConversationTab.summary) {
        showModalBottomSheet(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (context) => const SummarizedAppsBottomSheet(),
        );
      } else {
        widget.onTabSelected(ConversationTab.summary);
      }
    }

    String displayName = 'Summary';
    if (isReprocessing && reprocessingApp != null) {
      displayName = reprocessingApp.name;
    } else if (app != null) {
      displayName = app.name;
    }

    if (displayName.length > 8) {
      displayName = '${displayName.substring(0, 8)}...';
    }

    String? appImageUrl;
    bool isLocalAsset = false;
    if (isReprocessing) {
      if (reprocessingApp != null) {
        appImageUrl = reprocessingApp.getImageUrl();
      } else {
        appImageUrl = Assets.images.herologo.path;
        isLocalAsset = true;
      }
    } else if (app != null) {
      appImageUrl = app.getImageUrl();
    }

    return Container(
      height: 56,
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
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(28),
        child: InkWell(
          borderRadius: BorderRadius.circular(28),
          onTap: handleTap,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // App icon or default icon
              _buildAppIcon(appImageUrl, isLocalAsset, isReprocessing),
              const SizedBox(width: 6),
              // App name
              Flexible(
                child: Text(
                  displayName,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              // Dropdown arrow
              const Icon(
                Icons.keyboard_arrow_down,
                color: Colors.white,
                size: 18,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPlayPauseButton() {
    // Show loading only when actively loading
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
    const double progressBarWidth = 90.0;

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
                // Progress bar with tap-to-seek
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
                    height: 20, // Larger hit area
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
                // Duration remaining
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

    // Ensure position is not negative
    if (positionInTrack.isNegative) {
      positionInTrack = Duration.zero;
    }

    // Track seek
    final conversationId = widget.conversation?.id ?? '';
    MixpanelManager().audioPlaybackSeeked(
      conversationId: conversationId,
      toPositionSeconds: targetPosition.inSeconds,
    );

    await _audioPlayer!.seek(positionInTrack, index: targetIndex);
  }

  Widget _buildCircularButton({
    Key? key,
    required IconData icon,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Material(
      key: key,
      elevation: 4,
      color: Colors.transparent,
      shape: const CircleBorder(),
      child: Container(
        height: 56,
        width: 56,
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF6B46C1) : const Color(0xFF2D1B4E),
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              spreadRadius: 1,
              blurRadius: 5,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          shape: const CircleBorder(),
          child: InkWell(
            borderRadius: BorderRadius.circular(28),
            onTap: () {
              HapticFeedback.mediumImpact();
              onTap();
            },
            child: Center(
              child: FaIcon(
                icon,
                color: isSelected ? Colors.white : Colors.grey.shade400,
                size: 22,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStopButton() {
    return Container(
      height: 40,
      width: 40,
      decoration: BoxDecoration(
        color: Colors.red,
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: Colors.red.withOpacity(0.4),
            spreadRadius: 1,
            blurRadius: 4,
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: widget.onStopPressed,
          child: const Icon(
            Icons.stop_rounded,
            color: Colors.white,
            size: 24,
          ),
        ),
      ),
    );
  }

  Widget _buildAppIcon(String? imageUrl, bool isLocalAsset, bool isLoading) {
    const double size = 28;

    if (isLoading) {
      return const SizedBox(
        width: size,
        height: size,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      );
    }

    if (imageUrl == null) {
      return SizedBox(
        width: size,
        height: size,
        child: SvgPicture.asset(
          Assets.images.aiMagic,
          colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
        ),
      );
    }

    if (isLocalAsset) {
      return Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(size / 2),
          image: DecorationImage(
            image: AssetImage(imageUrl),
            fit: BoxFit.cover,
          ),
        ),
      );
    }

    return CachedNetworkImage(
      imageUrl: imageUrl,
      imageBuilder: (context, imageProvider) {
        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            image: DecorationImage(
              image: imageProvider,
              fit: BoxFit.cover,
            ),
          ),
        );
      },
      errorWidget: (context, url, error) {
        return SizedBox(
          width: size,
          height: size,
          child: SvgPicture.asset(
            Assets.images.aiMagic,
            colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
          ),
        );
      },
      placeholder: (context, url) => const SizedBox(
        width: size,
        height: size,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      ),
    );
  }
}

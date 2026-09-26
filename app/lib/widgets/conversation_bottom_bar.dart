import 'dart:math' as math;
import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/audio/audio_timeline_mapper.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/ui/ui.dart';

enum ConversationBottomBarMode {
  recording, // During active recording (no summary icon)
  detail, // For viewing completed conversations
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
  final Function(Future<void> Function(double start, double end))? onSeekFunctionReady;
  final VoidCallback? onAudioInteraction;

  const ConversationBottomBar({
    super.key,
    required this.mode,
    required this.selectedTab,
    required this.onTabSelected,
    required this.onStopPressed,
    this.hasSegments = true,
    this.hasActionItems = true,
    this.conversation,
    this.onSeekFunctionReady,
    this.onAudioInteraction,
  });

  @override
  State<ConversationBottomBar> createState() => _ConversationBottomBarState();
}

class _ConversationBottomBarState extends State<ConversationBottomBar> {
  // Audio player for inline controls
  AudioPlayer? _audioPlayer;
  bool _isAudioLoading = false;
  bool _isAudioInitialized = false;
  Completer<void>? _initCompleter;
  Duration _totalDuration = Duration.zero;
  List<Duration> _trackStartOffsets = [];

  // Single conversation-level artifact mode: one dense MP3 (gaps collapsed),
  // wall-clock timeline mapped through the spans manifest. Fallback stays on
  // the per-part ConcatenatingAudioSource playlist.
  bool _singleArtifact = false;
  AudioTimelineMapper? _timelineMapper;
  StreamSubscription<Duration>? _segmentStopSubscription;

  /// Bumped on every segment seek / scrub so a stale end-handler cannot pause
  /// a newer tap's playback (#4471 cubic).
  int _segmentSeekGeneration = 0;

  List<AudioFile> _getSortedAudioFiles() {
    if (widget.conversation == null) return [];
    final files = List<AudioFile>.from(widget.conversation!.audioFiles);
    files.sort((a, b) {
      final aTime = a.startedAt?.millisecondsSinceEpoch ?? 0;
      final bTime = b.startedAt?.millisecondsSinceEpoch ?? 0;
      return aTime.compareTo(bTime);
    });
    return files;
  }

  @override
  void initState() {
    super.initState();
    _calculateTotalDuration();
    // Provide the seek function to parent widget
    widget.onSeekFunctionReady?.call(seekToTranscriptSegment);
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
    _segmentStopSubscription?.cancel();
    _audioPlayer?.dispose();
    super.dispose();
  }

  void _calculateTotalDuration() {
    if (widget.conversation == null) return;
    final stamp = widget.conversation!.conversationAudio;
    if (stamp != null && stamp.spans.isNotEmpty) {
      // Dense-artifact timeline: the total is the actual captured audio length
      // (the MP3 has inter-part gaps and lead-in silence collapsed out), so the
      // scrubber matches what the user can hear. Transcript-segment taps still
      // map their wall timestamp to the MP3 position via the spans manifest.
      _totalDuration = Duration(milliseconds: (stamp.capturedDuration * 1000).toInt());
      return;
    }
    double totalSeconds = 0;
    _trackStartOffsets = [];
    for (final audioFile in _getSortedAudioFiles()) {
      _trackStartOffsets.add(Duration(milliseconds: (totalSeconds * 1000).toInt()));
      totalSeconds += audioFile.duration;
    }
    _totalDuration = Duration(milliseconds: (totalSeconds * 1000).toInt());
  }

  Duration _getCombinedPosition(int? currentIndex, Duration trackPosition) {
    if (_singleArtifact) {
      // The dense MP3 plays linearly; position is the raw artifact time so it
      // advances 1:1 with playback against the captured-duration total.
      return trackPosition;
    }
    if (currentIndex == null || currentIndex >= _trackStartOffsets.length) {
      return trackPosition;
    }
    return _trackStartOffsets[currentIndex] + trackPosition;
  }

  /// Seek to a transcript segment and play until [segmentEndSeconds].
  ///
  /// Uses strict wall→artifact mapping (no gap-snap) so a segment whose start
  /// falls in a collapsed inter-part gap does not jump into a later span
  /// (#4471). Requires the dense conversation artifact + spans; the per-part
  /// playlist fallback is not used for segment taps.
  Future<void> seekToTranscriptSegment(double segmentStartSeconds, double segmentEndSeconds) async {
    widget.onAudioInteraction?.call();
    if (!_isAudioInitialized) {
      await _initAudioIfNeeded();
    }
    if (!mounted || _audioPlayer == null || !_isAudioInitialized) return;

    await _segmentStopSubscription?.cancel();
    _segmentStopSubscription = null;

    if (!_singleArtifact || _timelineMapper == null) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.audioPlaybackUnavailable);
      }
      return;
    }

    final filePosition = _timelineMapper!.wallToArtifactStrict(segmentStartSeconds);
    if (filePosition == null) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.audioPlaybackUnavailable);
      }
      return;
    }

    final stopAt = _timelineMapper!.wallToArtifactStrictInclusive(segmentEndSeconds);
    final stopSeconds = (stopAt != null && stopAt > filePosition) ? stopAt : filePosition;

    final targetPosition = Duration(milliseconds: (filePosition * 1000).clamp(0, double.infinity).toInt());
    final stopPosition = Duration(milliseconds: (stopSeconds * 1000).clamp(0, double.infinity).toInt());

    final conversationId = widget.conversation?.id ?? '';
    PlatformManager.instance.analytics.transcriptSegmentTapped(
      conversationId: conversationId,
      segmentStartSeconds: segmentStartSeconds,
      seekPositionSeconds: filePosition,
    );

    // Seek without bumping generation — we own the token for this segment stop.
    await _seekToCombinedPosition(targetPosition, invalidateSegmentStop: false);
    if (!mounted || _audioPlayer == null) return;
    final seekGeneration = ++_segmentSeekGeneration;

    _segmentStopSubscription = _audioPlayer!.positionStream.listen((position) async {
      if (seekGeneration != _segmentSeekGeneration) return;
      if (position < stopPosition) return;
      if (seekGeneration != _segmentSeekGeneration) return;
      await _segmentStopSubscription?.cancel();
      _segmentStopSubscription = null;
      if (seekGeneration != _segmentSeekGeneration) return;
      if (_audioPlayer != null && _audioPlayer!.playing) {
        await _audioPlayer!.pause();
        if (seekGeneration != _segmentSeekGeneration) return;
        if (mounted) setState(() {});
      }
    });

    if (!_audioPlayer!.playing) {
      PlatformManager.instance.analytics.audioPlaybackStarted(
        conversationId: conversationId,
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );
      await _audioPlayer!.play();
      if (seekGeneration != _segmentSeekGeneration) return;
      if (mounted) setState(() {});
    }
  }

  Future<void> _initAudioIfNeeded() async {
    if (!mounted) return;
    if (_isAudioInitialized || widget.conversation == null || !widget.conversation!.hasAudio()) {
      return;
    }

    // If a concurrent init is already in flight, wait for it instead of starting
    // a second one — otherwise both calls would create/init the same AudioPlayer
    // and trigger PlatformException "Platform player already exists".
    if (_initCompleter != null) {
      await _initCompleter!.future;
      return;
    }

    _initCompleter = Completer<void>();
    // Read before the awaits below: the messages for a load that fails.
    final l10n = context.l10n;

    setState(() {
      _isAudioLoading = true;
    });

    _calculateTotalDuration();

    try {
      _audioPlayer = AudioPlayer();

      // The backend builds playback artifacts asynchronously; poll while any
      // file is pending instead of streaming through the merge-in-request
      // endpoint that used to time out on long conversations.
      final deadline = DateTime.now().add(const Duration(seconds: 90));
      var urlsResponse = await getConversationAudioSignedUrls(widget.conversation!.id);
      while (urlsResponse.files.isEmpty || !urlsResponse.playbackReady) {
        if (!mounted) return;
        if (DateTime.now().isAfter(deadline)) {
          Logger.debug('Audio still pending after poll budget for ${widget.conversation!.id}');
          AnalyticsManager().audioPlaybackFailed(conversationId: widget.conversation!.id, reason: 'pending_timeout');
          await _dropFailedLoad(l10n.anErrorOccurredTryAgain);
          return;
        }
        await Future.delayed(Duration(milliseconds: urlsResponse.pollAfterMs ?? 3000));
        if (!mounted) return;
        urlsResponse = await getConversationAudioSignedUrls(widget.conversation!.id);
      }

      final conversationAudio = urlsResponse.conversationAudio;
      if (conversationAudio != null && conversationAudio.isCached && conversationAudio.spans.isNotEmpty) {
        // One dense MP3 for the whole conversation: no playlist, no track
        // offsets — position and seeks go through the spans mapper.
        _timelineMapper = AudioTimelineMapper(conversationAudio.spans);
        _singleArtifact = true;
        _totalDuration = Duration(milliseconds: (_timelineMapper!.capturedDuration * 1000).toInt());
        await _audioPlayer!.setAudioSource(AudioSource.uri(Uri.parse(conversationAudio.signedUrl!)), preload: true);
        _isAudioInitialized = true;
        return;
      }

      final sortedAudioFiles = _getSortedAudioFiles();
      List<AudioSource> audioSources = [];
      for (final audioFile in sortedAudioFiles) {
        final urlInfo = urlsResponse.files.where((info) => info.id == audioFile.id && info.isCached).firstOrNull;
        if (urlInfo?.signedUrl != null) {
          audioSources.add(AudioSource.uri(Uri.parse(urlInfo!.signedUrl!)));
        }
      }
      if (audioSources.isEmpty) {
        Logger.debug('No cached audio sources for ${widget.conversation!.id}');
        AnalyticsManager().audioPlaybackFailed(conversationId: widget.conversation!.id, reason: 'no_matching_sources');
        await _dropFailedLoad(l10n.audioPlaybackUnavailable);
        return;
      }

      final playlist = ConcatenatingAudioSource(useLazyPreparation: true, children: audioSources);

      await _audioPlayer!.setAudioSource(playlist, preload: true);
      _isAudioInitialized = true;
    } catch (e) {
      Logger.debug('Error initializing audio: $e');
      AnalyticsManager().audioPlaybackFailed(conversationId: widget.conversation?.id ?? '', reason: e.toString());
      // Before, a failed load was silent and Play then "played" an empty player.
      if (mounted) await _dropFailedLoad(l10n.audioPlaybackUnavailable);
    } finally {
      final completer = _initCompleter;
      _initCompleter = null;
      if (mounted) {
        setState(() {
          _isAudioLoading = false;
        });
      }
      completer?.complete();
    }
  }

  /// A load that failed leaves nothing to play: drop the player so the next tap loads again, and
  /// say why.
  Future<void> _dropFailedLoad(String message) async {
    final player = _audioPlayer;
    _audioPlayer = null;
    _isAudioInitialized = false;
    await player?.dispose();
    if (mounted) OmiFeedback.error(context, message);
  }

  Future<void> _togglePlayPause() async {
    widget.onAudioInteraction?.call();
    if (!_isAudioInitialized && !_isAudioLoading) {
      await _initAudioIfNeeded();
    }
    if (!mounted) return;
    // Nothing loaded (still loading, or the load failed and said so): never show Pause over silence.
    if (_audioPlayer == null || !_isAudioInitialized) return;

    final conversationId = widget.conversation?.id ?? '';

    if (_audioPlayer!.playing) {
      // Track pause
      final position = _audioPlayer!.position;
      final currentIndex = _audioPlayer!.currentIndex ?? 0;
      final combinedPosition = _getCombinedPosition(currentIndex, position);

      PlatformManager.instance.analytics.audioPlaybackPaused(
        conversationId: conversationId,
        positionSeconds: combinedPosition.inSeconds,
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );

      await _audioPlayer!.pause();
    } else {
      // Track play
      PlatformManager.instance.analytics.audioPlaybackStarted(
        conversationId: conversationId,
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );

      await _audioPlayer!.play();
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasSegments) {
      return const SizedBox();
    }

    return Center(child: _buildBottomBar(context));
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
      borderRadius: OmiRadius.pillAll,
      child: Container(
        height: 56,
        width: 180,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.pillAll,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.3),
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
              semanticLabel: context.l10n.transcript,
            ),
            const SizedBox(width: 8),
            _buildStopButton(),
          ],
        ),
      ),
    );
  }

  /// v2 Conversation: the recording as an inline card under the title — play, a waveform to tap
  /// or scrub (played bars in white), and position / length. Nothing without audio.
  ///
  /// When the saved audio covers much less than the conversation (the server stored only part of
  /// it, IMG_1160: a 5m 49s conversation with 3 s of audio), the card says so under the player
  /// instead of looking like a broken recording.
  Widget _buildDetailBar(BuildContext context) {
    final hasAudio = widget.conversation?.hasAudio() ?? false;
    if (!hasAudio) return const SizedBox.shrink();
    final conversationSeconds = widget.conversation!.getDurationInSeconds();
    final partial = conversationSeconds >= 30 &&
        _totalDuration > Duration.zero &&
        _totalDuration.inMilliseconds < conversationSeconds * 1000 * 0.5;
    return OmiCard(
      key: const Key('conversation_audio_card'),
      radius: 24,
      padding: const EdgeInsets.fromLTRB(12, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              _buildPlayPauseButton(diameter: 44),
              const SizedBox(width: 12),
              Expanded(child: _buildWaveformScrubber()),
            ],
          ),
          if (partial)
            Padding(
              key: const Key('conversation_audio_partial'),
              padding: const EdgeInsets.fromLTRB(4, 8, 0, 0),
              child: Text(
                context.l10n.audioPartiallySaved(
                  _clock(_totalDuration),
                  _clock(Duration(seconds: conversationSeconds)),
                ),
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
            ),
        ],
      ),
    );
  }

  /// The waveform strip (44 bars, 30 pt) and "0:12 / 0:30"; tap or drag it to seek.
  Widget _buildWaveformScrubber() {
    Widget strip(Duration position) {
      // Never a length shorter than what is playing ("0:03 / 0:02"): the audio file itself may run
      // a little past the saved-audio manifest.
      final fileLength = _singleArtifact ? _audioPlayer?.duration : null;
      var total = _totalDuration;
      if (fileLength != null && fileLength > total) total = fileLength;
      if (position > total) total = position;
      final progress =
          total.inMilliseconds > 0 ? (position.inMilliseconds / total.inMilliseconds).clamp(0.0, 1.0).toDouble() : 0.0;
      return Row(
        children: [
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final width = constraints.maxWidth;
                void seekAt(double dx) {
                  if (_audioPlayer == null || total.inMilliseconds <= 0 || width <= 0) return;
                  final p = (dx / width).clamp(0.0, 1.0);
                  _seekToCombinedPosition(Duration(milliseconds: (p * total.inMilliseconds).round()));
                }

                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTapDown: (d) => seekAt(d.localPosition.dx),
                  onHorizontalDragUpdate: (d) => seekAt(d.localPosition.dx),
                  child: SizedBox(
                    height: 30,
                    child: CustomPaint(painter: _ScrubStripPainter(progress: progress), size: Size(width, 30)),
                  ),
                );
              },
            ),
          ),
          const SizedBox(width: 12),
          Text(
            '${_clock(position)} / ${_clock(total)}',
            style: OmiType.footnote.copyWith(
              color: OmiColors.textSecondary,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      );
    }

    if (_audioPlayer == null) return strip(Duration.zero);
    return StreamBuilder<int?>(
      stream: _audioPlayer!.currentIndexStream,
      builder: (context, indexSnapshot) => StreamBuilder<Duration>(
        stream: _audioPlayer!.positionStream,
        builder: (context, positionSnapshot) =>
            strip(_getCombinedPosition(indexSnapshot.data ?? 0, positionSnapshot.data ?? Duration.zero)),
      ),
    );
  }

  static String _clock(Duration d) {
    final minutes = d.inMinutes;
    final seconds = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  /// Play/pause: a white circle ([diameter], in at least a 44pt target), labelled for screen readers.
  Widget _buildPlayPauseButton({double diameter = 32}) {
    Widget button(bool isPlaying) => OmiIconButton.filled(
          icon: Icon(isPlaying ? Icons.pause : Icons.play_arrow, size: 20),
          label: isPlaying ? context.l10n.pause : context.l10n.play,
          diameter: diameter,
          fillColor: OmiColors.accent,
          color: OmiColors.onAccent,
          onPressed: _togglePlayPause,
        );
    const loading =
        SizedBox.square(dimension: kOmiMinTapTarget, child: Center(child: OmiSpinner(size: OmiSpinnerSize.small)));

    if (_isAudioLoading) return loading;
    if (_audioPlayer == null) return button(false);

    return StreamBuilder<PlayerState>(
      stream: _audioPlayer!.playerStateStream,
      builder: (context, snapshot) {
        final playerState = snapshot.data;
        final processingState = playerState?.processingState ?? ProcessingState.idle;
        if (processingState == ProcessingState.loading || processingState == ProcessingState.buffering) {
          return loading;
        }
        return button(playerState?.playing ?? false);
      },
    );
  }

  Future<void> _seekToCombinedPosition(Duration targetPosition, {bool invalidateSegmentStop = true}) async {
    widget.onAudioInteraction?.call();
    if (_audioPlayer == null) return;

    // Scrubber seeks invalidate any in-flight segment end-handler.
    if (invalidateSegmentStop) {
      _segmentSeekGeneration++;
      await _segmentStopSubscription?.cancel();
      _segmentStopSubscription = null;
    }

    if (_singleArtifact) {
      // targetPosition is already artifact time (the scrubber runs on the dense
      // MP3; segment taps are mapped wall->artifact before they get here).
      PlatformManager.instance.analytics.audioPlaybackSeeked(
        conversationId: widget.conversation?.id ?? '',
        toPositionSeconds: targetPosition.inSeconds,
      );
      await _audioPlayer!.seek(targetPosition);
      return;
    }

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
    PlatformManager.instance.analytics.audioPlaybackSeeked(
      conversationId: conversationId,
      toPositionSeconds: targetPosition.inSeconds,
    );

    await _audioPlayer!.seek(positionInTrack, index: targetIndex);
  }

  Widget _buildCircularButton({
    Key? key,
    required FaIconData icon,
    required bool isSelected,
    required VoidCallback onTap,
    required String semanticLabel,
  }) {
    return Semantics(
      button: true,
      label: semanticLabel,
      excludeSemantics: true,
      onTap: () {
        OmiHaptics.medium();
        onTap();
      },
      child: Material(
        key: key,
        elevation: 4,
        color: Colors.transparent,
        shape: const CircleBorder(),
        child: Container(
          height: 56,
          width: 56,
          decoration: BoxDecoration(
            color: isSelected ? OmiColors.surface3 : OmiColors.surface1,
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.3),
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
              borderRadius: OmiRadius.pillAll,
              onTap: () {
                OmiHaptics.medium();
                onTap();
              },
              child: Center(
                  child: FaIcon(icon, color: isSelected ? OmiColors.textPrimary : OmiColors.textTertiary, size: 22)),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStopButton() {
    return OmiIconButton.filled(
      icon: const Icon(Icons.stop_rounded, size: 24),
      label: context.l10n.stopRecording,
      diameter: 40,
      fillColor: OmiColors.danger,
      color: OmiColors.textPrimary,
      onPressed: widget.onStopPressed,
    );
  }
}

/// The design's static waveform (lib.py `_hs`, seed 3, floor 0.18): played bars in white, the rest
/// at 26 % so the playhead reads at a glance.
class _ScrubStripPainter extends CustomPainter {
  _ScrubStripPainter({required this.progress});

  final double progress;
  static const int _bars = 44;
  static const double _gap = 2;

  static double _level(int i) {
    const seed = 3.0;
    const floor = 0.18;
    final a = (math.sin(i * 0.37 + seed) * math.sin(i * 0.113 + seed * 2.1)).abs();
    final b = math.sin(i * 1.7 + seed * 0.5).abs() * 0.35;
    return floor + (1 - floor) * math.min(1.0, a * 0.85 + b * 0.5);
  }

  @override
  void paint(Canvas canvas, Size size) {
    final barWidth = (size.width - _gap * (_bars - 1)) / _bars;
    if (barWidth <= 0) return;
    final played = Paint()..color = OmiColors.textPrimary;
    final rest = Paint()..color = OmiColors.textPrimary.withValues(alpha: 0.26);
    for (var i = 0; i < _bars; i++) {
      final h = math.max(4.0, size.height * _level(i));
      final x = i * (barWidth + _gap);
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(x, (size.height - h) / 2, barWidth, h),
        const Radius.circular(1),
      );
      canvas.drawRRect(rect, i / _bars < progress ? played : rest);
    }
  }

  @override
  bool shouldRepaint(_ScrubStripPainter old) => old.progress != progress;
}

import 'dart:async';
import 'dart:math' as math;

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/audio/audio_timeline_mapper.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/home_bottom_bar.dart' show kAskOmiGlyph;

enum ConversationBottomBarMode {
  recording, // During active recording (no summary icon)
  detail, // For viewing completed conversations
}

/// The conversation page's tabs, in no particular order (the page owns the order).
enum ConversationTab { transcript, summary }

/// Bars in the detail player's waveform.
const int _waveformBars = 36;

/// How much of each of [count] equal slices of the conversation someone was speaking, from 0 to 1,
/// read from the transcript's segment times. The detail player draws its waveform from these, so
/// the bars rise where people talked and drop to a dot through silence. All zero without segments.
List<double> speechLevels(List<TranscriptSegment> segments, int count) {
  if (count <= 0) return const [];
  if (segments.isEmpty) return List.filled(count, 0);
  final start = segments.map((segment) => segment.start).reduce(math.min);
  final span = segments.map((segment) => segment.end).reduce(math.max) - start;
  if (span <= 0) return List.filled(count, 1);
  final slice = span / count;
  final levels = List<double>.filled(count, 0);
  for (final segment in segments) {
    final from = segment.start - start;
    final to = segment.end - start;
    for (var i = (from / slice).floor().clamp(0, count - 1); i < count && i * slice < to; i++) {
      final overlap = math.min(to, (i + 1) * slice) - math.max(from, i * slice);
      if (overlap > 0) levels[i] += overlap / slice;
    }
  }
  return [for (final level in levels) level.clamp(0.0, 1.0)];
}

class ConversationBottomBar extends StatefulWidget {
  final ConversationBottomBarMode mode;
  final ConversationTab selectedTab;
  final Function(ConversationTab) onTabSelected;
  final VoidCallback onStopPressed;
  final bool hasSegments;
  final ServerConversation? conversation;
  final Function(Future<void> Function(double start, double end))? onSeekFunctionReady;
  final VoidCallback? onAudioInteraction;

  /// Opens Ask Omi about this conversation; the detail bar's Ask button and Ask Omi bar.
  final VoidCallback? onAskOmi;

  /// Reads the conversation's playback URLs; [getConversationAudioSignedUrls] unless a test fakes it.
  final Future<AudioUrlsResponse> Function(String conversationId)? fetchAudioUrls;

  const ConversationBottomBar({
    super.key,
    required this.mode,
    required this.selectedTab,
    required this.onTabSelected,
    required this.onStopPressed,
    this.hasSegments = true,
    this.conversation,
    this.onSeekFunctionReady,
    this.onAudioInteraction,
    this.onAskOmi,
    this.fetchAudioUrls,
  });

  @override
  State<ConversationBottomBar> createState() => _ConversationBottomBarState();
}

class _ConversationBottomBarState extends State<ConversationBottomBar> {
  // Audio player for inline controls, created once a playback plan resolves.
  AudioPlayer? _audioPlayer;
  bool _isAudioLoading = false;
  bool _isAudioInitialized = false;
  Completer<bool>? _initCompleter;
  Duration _totalDuration = Duration.zero;
  List<Duration> _trackStartOffsets = [];

  // Single conversation-level artifact mode: one dense MP3 (gaps collapsed),
  // wall-clock timeline mapped through the spans manifest. Fallback stays on
  // the per-part ConcatenatingAudioSource playlist.
  bool _singleArtifact = false;
  AudioTimelineMapper? _timelineMapper;
  StreamSubscription<Duration>? _segmentStopSubscription;
  StreamSubscription<PlaybackEvent>? _playbackErrorSubscription;

  /// Bumped on every segment seek / scrub so a stale end-handler cannot pause
  /// a newer tap's playback (#4471 cubic).
  int _segmentSeekGeneration = 0;

  List<AudioFile> _getSortedAudioFiles() {
    if (widget.conversation == null) return [];
    return ConversationPlaybackPlan.sortedFiles(widget.conversation!.audioFiles);
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
    _playbackErrorSubscription?.cancel();
    _audioPlayer?.dispose();
    super.dispose();
  }

  /// The length shown before playback starts, from the conversation alone. Replaced by the plan's
  /// length once the URLs resolve.
  void _calculateTotalDuration() {
    if (widget.conversation == null) return;
    _trackStartOffsets = [];
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
  /// Uses strict wall→playback mapping (no gap-snap) so a segment whose start
  /// falls in a collapsed inter-part gap does not jump into a later span
  /// (#4471). Works on the dense conversation artifact and on a part playlist
  /// whose parts carry their start times; otherwise playback is unavailable.
  Future<void> seekToTranscriptSegment(double segmentStartSeconds, double segmentEndSeconds) async {
    widget.onAudioInteraction?.call();
    if (!_isAudioInitialized && !await _initAudioIfNeeded()) return;
    if (!mounted || _audioPlayer == null) return;

    await _segmentStopSubscription?.cancel();
    _segmentStopSubscription = null;

    final mapper = _timelineMapper;
    final filePosition = mapper?.wallToArtifactStrict(segmentStartSeconds);
    if (mapper == null || filePosition == null) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.audioPlaybackUnavailable);
      }
      return;
    }

    final stopAt = mapper.wallToArtifactStrictInclusive(segmentEndSeconds);
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
      // A part playlist reports the position inside the current part.
      if (_getCombinedPosition(_audioPlayer?.currentIndex, position) < stopPosition) return;
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

  /// Resolves the conversation's audio and loads it into a new player. True when it can play; on
  /// any failure says so, leaves no player behind and lets the next tap try again.
  Future<bool> _initAudioIfNeeded() async {
    if (_isAudioInitialized) return true;
    if (!mounted || widget.conversation == null || !widget.conversation!.hasAudio()) return false;

    // If a concurrent init is already in flight, wait for it instead of starting
    // a second one — otherwise both calls would create/init an AudioPlayer
    // and trigger PlatformException "Platform player already exists".
    if (_initCompleter != null) return _initCompleter!.future;
    final completer = _initCompleter = Completer<bool>();
    setState(() => _isAudioLoading = true);

    var ready = false;
    try {
      ready = await _loadPlayback(widget.conversation!);
    } finally {
      _initCompleter = null;
      if (mounted) setState(() => _isAudioLoading = false);
      completer.complete(ready);
    }
    return ready;
  }

  Future<bool> _loadPlayback(ServerConversation conversation) async {
    final fetch = widget.fetchAudioUrls ?? getConversationAudioSignedUrls;
    void fail(String reason, {bool unavailable = false}) {
      Logger.debug('Audio playback failed for ${conversation.id}: $reason');
      AnalyticsManager().audioPlaybackFailed(conversationId: conversation.id, reason: reason);
      if (!mounted) return;
      final l10n = context.l10n;
      OmiFeedback.error(context, unavailable ? l10n.audioPlaybackUnavailable : l10n.anErrorOccurredTryAgain);
    }

    // The backend builds playback artifacts asynchronously; poll while any
    // file is pending instead of streaming through the merge-in-request
    // endpoint that used to time out on long conversations. No files at all
    // (no audio, a locked conversation, a failed request) is final: say so now.
    final deadline = DateTime.now().add(const Duration(seconds: 90));
    var urls = await fetch(conversation.id);
    while (urls.files.isNotEmpty && !urls.playbackReady) {
      if (!mounted) return false;
      if (DateTime.now().isAfter(deadline)) break;
      await Future.delayed(Duration(milliseconds: urls.pollAfterMs ?? 3000));
      if (!mounted) return false;
      urls = await fetch(conversation.id);
    }
    if (!mounted) return false;

    final plan = ConversationPlaybackPlan.resolve(
      urls,
      conversation.audioFiles,
      conversationStart: conversation.startedAt ?? conversation.createdAt,
    );
    if (plan.failure != null) {
      fail(plan.failure!, unavailable: plan.failure == ConversationPlaybackPlan.noPlayableParts);
      return false;
    }

    final player = AudioPlayer();
    try {
      await player.setAudioSource(
        plan.singleUrl != null
            ? AudioSource.uri(Uri.parse(plan.singleUrl!))
            : ConcatenatingAudioSource(
                useLazyPreparation: true,
                children: [for (final part in plan.parts) AudioSource.uri(Uri.parse(part.url))],
              ),
        preload: true,
      );
    } catch (e) {
      fail('load_failed: $e');
      unawaited(player.dispose());
      return false;
    }
    if (!mounted) {
      unawaited(player.dispose());
      return false;
    }

    _audioPlayer = player;
    _singleArtifact = plan.singleUrl != null;
    _timelineMapper = plan.mapper;
    _trackStartOffsets = plan.partOffsets;
    _totalDuration = plan.duration;
    _isAudioInitialized = true;
    // A part that fails mid-playlist (an expired URL, an unreadable file) surfaces here.
    _playbackErrorSubscription = player.playbackEventStream.listen(
      (_) {},
      onError: (Object e, StackTrace _) => fail('stream_error: $e'),
    );
    return true;
  }

  Future<void> _togglePlayPause() async {
    widget.onAudioInteraction?.call();
    if (!_isAudioInitialized && (_isAudioLoading || !await _initAudioIfNeeded())) return;
    if (!mounted || _audioPlayer == null) return;

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

  String _formatDurationRemaining(Duration position) {
    final remaining = _totalDuration - position;
    // OmiDuration.offset keeps the hours: 1h 5m remaining reads 1:05:00, not 5:00.
    return OmiDuration.offset(remaining.isNegative ? 0 : remaining.inSeconds);
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

  /// The detail page's one bar (v3): on Transcript the recording's waveform player with a round Ask
  /// button beside it; on Summary, or a conversation without audio, the Ask Omi bar alone. The
  /// summarizing app is picked from the ⋯ menu.
  Widget _buildDetailBar(BuildContext context) {
    final hasAudio = widget.conversation?.hasAudio() ?? false;
    final showPlayer = widget.selectedTab == ConversationTab.transcript && hasAudio;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      child: showPlayer
          ? Row(
              children: [
                Expanded(child: KeyedSubtree(key: const ValueKey('detail_audio_player'), child: _buildPlayer())),
                const SizedBox(width: 10),
                _buildAskButton(context),
              ],
            )
          : _buildAskBar(context),
    );
  }

  static BoxDecoration get _barDecoration => BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.pillAll,
        border: Border.all(color: OmiColors.border, width: 1),
      );

  void _askOmi() {
    HapticFeedback.mediumImpact();
    widget.onAskOmi?.call();
  }

  /// "Ask Omi", centred in a full-width 56 pt capsule.
  Widget _buildAskBar(BuildContext context) {
    final label = context.l10n.askOmi;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: Material(
        key: const ValueKey('detail_ask_omi'),
        color: Colors.transparent,
        child: Ink(
          height: 56,
          decoration: _barDecoration,
          child: InkWell(
            borderRadius: OmiRadius.pillAll,
            onTap: _askOmi,
            child: Center(child: Text(label, style: OmiType.headline)),
          ),
        ),
      ),
    );
  }

  /// The round Ask button beside the player: a 56 pt circle in the primary ink, as tall as the bar.
  Widget _buildAskButton(BuildContext context) {
    final label = context.l10n.askOmi;
    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        button: true,
        label: label,
        excludeSemantics: true,
        child: Material(
          key: const ValueKey('detail_ask_omi_round'),
          color: OmiColors.accent,
          shape: const CircleBorder(),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: _askOmi,
            child: SizedBox.square(
              dimension: 56,
              child: Center(child: FaIcon(kAskOmiGlyph, size: 20, color: OmiColors.onAccent)),
            ),
          ),
        ),
      ),
    );
  }

  /// Play/pause, the recording's waveform (tap or drag to seek) and the time left.
  Widget _buildPlayer() {
    return Container(
      height: 56,
      padding: const EdgeInsetsDirectional.only(start: 4, end: OmiSpacing.md),
      decoration: _barDecoration,
      child: Row(
        children: [
          _buildPlayPauseButton(),
          const SizedBox(width: 8),
          Expanded(child: _buildWaveform()),
        ],
      ),
    );
  }

  /// Play/pause: a 40 pt circle in the primary ink, labelled for screen readers.
  Widget _buildPlayPauseButton() {
    Widget button(bool isPlaying) => OmiIconButton.filled(
          icon: Icon(isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded, size: 22),
          label: isPlaying ? context.l10n.pause : context.l10n.play,
          diameter: 40,
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

  Widget _buildWaveform() {
    final levels = speechLevels(widget.conversation?.transcriptSegments ?? const [], _waveformBars);
    Widget waveform(double progress, Duration position, {ValueChanged<double>? onSeek}) {
      return Row(
        children: [
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                void seek(Offset local) => onSeek?.call((local.dx / constraints.maxWidth).clamp(0.0, 1.0));
                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTapDown: onSeek == null ? null : (details) => seek(details.localPosition),
                  onHorizontalDragUpdate: onSeek == null ? null : (details) => seek(details.localPosition),
                  child: SizedBox(
                    height: 44,
                    child: CustomPaint(
                      painter: _WaveformPainter(
                        levels: levels,
                        progress: progress,
                        played: OmiColors.textPrimary,
                        unplayed: OmiColors.textPrimary.withValues(alpha: 0.3),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(width: 10),
          Text(
            '-${_formatDurationRemaining(position)}',
            style: OmiType.footnote.copyWith(
              color: OmiColors.textTertiary,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      );
    }

    if (_audioPlayer == null) return waveform(0, Duration.zero);

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
            return waveform(
              progress,
              combinedPosition,
              onSeek: (fraction) => _seekToCombinedPosition(
                Duration(milliseconds: (fraction * _totalDuration.inMilliseconds).toInt()),
              ),
            );
          },
        );
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
        HapticFeedback.mediumImpact();
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
                HapticFeedback.mediumImpact();
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

/// How the detail player plays a conversation, decided from the playback URLs: the dense
/// conversation MP3 when it is ready, else a playlist of the parts that are, else nothing (with
/// [failure] saying why). Parts that cannot play are left out of the playlist, its offsets and its
/// length, so the time left and seeking match what is heard.
final class ConversationPlaybackPlan {
  const ConversationPlaybackPlan._({this.singleUrl, this.parts = const [], this.mapper, this.failure});

  /// [failure] when the conversation has no audio files, or the request failed or was refused.
  static const noAudioFiles = 'no_audio_files';

  /// [failure] when files exist but none can play (gone, or still being built when polling stopped).
  static const noPlayableParts = 'no_matching_sources';

  /// The dense conversation MP3.
  final String? singleUrl;

  /// The playable parts in time order, when there is no dense MP3.
  final List<({String url, double seconds})> parts;

  /// Wall-clock seconds (the transcript's timeline) to playback position, for transcript taps.
  /// Null when the parts cannot be placed in time.
  final AudioTimelineMapper? mapper;

  /// Why nothing can play; null when something can.
  final String? failure;

  /// Where each part starts in the playlist.
  List<Duration> get partOffsets {
    final offsets = <Duration>[];
    var seconds = 0.0;
    for (final part in parts) {
      offsets.add(Duration(milliseconds: (seconds * 1000).toInt()));
      seconds += part.seconds;
    }
    return offsets;
  }

  /// How long playback runs.
  Duration get duration {
    final seconds = singleUrl != null
        ? mapper?.capturedDuration ?? 0
        : parts.fold<double>(0, (total, part) => total + part.seconds);
    return Duration(milliseconds: (seconds * 1000).toInt());
  }

  /// The conversation's audio files in recording order.
  static List<AudioFile> sortedFiles(List<AudioFile> files) => List.of(files)
    ..sort((a, b) => (a.startedAt?.millisecondsSinceEpoch ?? 0).compareTo(b.startedAt?.millisecondsSinceEpoch ?? 0));

  static ConversationPlaybackPlan resolve(
    AudioUrlsResponse urls,
    List<AudioFile> files, {
    DateTime? conversationStart,
  }) {
    final dense = urls.conversationAudio;
    if (dense != null && dense.isCached && dense.spans.isNotEmpty) {
      return ConversationPlaybackPlan._(singleUrl: dense.signedUrl, mapper: AudioTimelineMapper(dense.spans));
    }
    if (urls.files.isEmpty) return const ConversationPlaybackPlan._(failure: noAudioFiles);

    final parts = <({String url, double seconds})>[];
    final spans = <ConversationAudioSpan>[];
    var placeable = conversationStart != null;
    var offset = 0.0;
    for (final file in sortedFiles(files)) {
      final info = urls.files.where((info) => info.id == file.id && info.isCached).firstOrNull;
      if (info == null) continue;
      final seconds = file.duration > 0 ? file.duration : info.duration;
      parts.add((url: info.signedUrl!, seconds: seconds));
      final startedAt = file.startedAt;
      if (placeable && startedAt != null && seconds > 0) {
        spans.add(ConversationAudioSpan(
          fileId: file.id,
          wallOffset: startedAt.difference(conversationStart!).inMilliseconds / 1000,
          artifactOffset: offset,
          len: seconds,
        ));
      } else {
        placeable = false;
      }
      offset += seconds;
    }
    if (parts.isEmpty) return const ConversationPlaybackPlan._(failure: noPlayableParts);
    return ConversationPlaybackPlan._(parts: parts, mapper: placeable ? AudioTimelineMapper(spans) : null);
  }
}

/// The player's waveform: one rounded bar per speech level, played bars in [played] up to
/// [progress] and the rest in [unplayed]. Silent slices keep a short bar so the track stays visible.
class _WaveformPainter extends CustomPainter {
  _WaveformPainter({required this.levels, required this.progress, required this.played, required this.unplayed});

  final List<double> levels;
  final double progress;
  final Color played;
  final Color unplayed;

  static const double _gap = 2;
  static const double _minHeight = 4;

  @override
  void paint(Canvas canvas, Size size) {
    if (levels.isEmpty) return;
    final barWidth = (size.width - _gap * (levels.length - 1)) / levels.length;
    if (barWidth <= 0) return;
    final maxHeight = size.height * 0.6;
    final paint = Paint();
    for (var i = 0; i < levels.length; i++) {
      // A fixed ripple per bar so speech reads as a voice rather than a block.
      final ripple = 0.55 + 0.45 * ((i * 7 + 3) % 11) / 10;
      final height = _minHeight + (maxHeight - _minHeight) * levels[i] * ripple;
      final left = i * (barWidth + _gap);
      paint.color = (i + 0.5) / levels.length <= progress ? played : unplayed;
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(left, (size.height - height) / 2, barWidth, height),
          Radius.circular(math.min(barWidth / 2, 1.5)),
        ),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_WaveformPainter oldDelegate) =>
      oldDelegate.progress != progress ||
      oldDelegate.levels != levels ||
      oldDelegate.played != played ||
      oldDelegate.unplayed != unplayed;
}

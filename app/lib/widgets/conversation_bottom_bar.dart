import 'dart:async';
import 'dart:math' as math;

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/audio/audio_timeline_mapper.dart';
import 'package:omi/utils/audio/conversation_playback_controller.dart';
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
/// [start]/[end] widen the drawn window beyond the first/last segment (the player spans wall 0 to
/// the end of the audio); they default to the segments' own bounds.
List<double> speechLevels(List<TranscriptSegment> segments, int count, {double? start, double? end}) {
  if (count <= 0) return const [];
  if (segments.isEmpty) return List.filled(count, 0);
  final base = start ?? segments.map((segment) => segment.start).reduce(math.min);
  final span = (end ?? segments.map((segment) => segment.end).reduce(math.max)) - base;
  if (span <= 0) return List.filled(count, 1);
  final slice = span / count;
  final levels = List<double>.filled(count, 0);
  for (final segment in segments) {
    final from = segment.start - base;
    final to = segment.end - base;
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
  final Future<ApiResult<AudioUrlsResponse>> Function(String conversationId)? fetchAudioUrls;

  /// The detail page's playback state: drives the transcript highlight/follow
  /// and records the reader's pending wall position across bar remounts.
  final ConversationPlaybackController? playbackController;

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
    this.playbackController,
  });

  @override
  State<ConversationBottomBar> createState() => _ConversationBottomBarState();
}

/// Why the detail player cannot play, shown as a persistent inline label with
/// a Try Again pill. Bounded reasons for analytics — never raw URLs or errors.
enum _AudioFailure { transport, unavailable, loadFailed, unmappable }

/// A failed /urls request carrying the classified [ApiProblem] so the bar can
/// tell "no audio" apart from "the request never returned".
class _UrlsRequestFailed implements Exception {
  const _UrlsRequestFailed(this.problem);
  final ApiProblem problem;
}

class _ConversationBottomBarState extends State<ConversationBottomBar> {
  // Audio player for inline controls, created once a playback plan resolves.
  AudioPlayer? _audioPlayer;
  bool _isAudioLoading = false;
  bool _isAudioInitialized = false;
  Completer<bool>? _initCompleter;

  /// Set by a timer 600 ms into a load so "Preparing Audio…" only appears for
  /// loads that take a beat — a bool, not a clock read, so fake pumps advance it.
  bool _showPreparingLabel = false;
  Timer? _loadLabelTimer;
  int _loadGeneration = 0;
  _AudioFailure? _failure;
  int _readyParts = 0;
  int _totalParts = 0;
  Duration _totalDuration = Duration.zero;
  List<Duration> _trackStartOffsets = [];

  // Single conversation-level artifact mode: one dense MP3 (gaps collapsed),
  // wall-clock timeline mapped through the spans manifest. Fallback stays on
  // the per-part ConcatenatingAudioSource playlist.
  bool _singleArtifact = false;
  AudioTimelineMapper? _timelineMapper;

  /// Wall-clock seconds spanned by the waveform: segment ends, the mapped
  /// wall duration and per-file ends, whichever runs longest.
  double _wallEndSeconds = 0;

  /// Wall ranges that cannot play (pending or unavailable parts, mapped
  /// gaps) as [0,1] fractions for the painter, plus parts with no timestamps
  /// that cannot be placed at all.
  List<(double, double)> _missingRanges = const [];
  bool _hasUnplaceableMissing = false;

  AudioUrlsResponse? _resolvedUrls;

  Object? _audioSourceSnapshot;

  static const _sourceEquality = DeepCollectionEquality();

  /// Latest combined artifact position in seconds; the waveform, remaining
  /// time and wall playhead read it without rebuilding on every tick.
  final ValueNotifier<double> _artifactPosition = ValueNotifier(0);
  StreamSubscription<Duration>? _positionSubscription;
  StreamSubscription<PlaybackEvent>? _playbackErrorSubscription;
  StreamSubscription<PlayerState>? _playerStateSubscription;

  /// Bumped on every seek so a stale stream reply or in-flight init cannot
  /// land an older position over a newer gesture.
  int _seekGeneration = 0;

  /// Completes when the current load is torn down; the poll loop races fetch
  /// and delay against it so a stale request cannot wait out the whole 90 s
  /// budget against a player that is already gone.
  Completer<void>? _loadCancel;

  /// Stable tear-off for attach/detach — a fresh `_seekWall` tear-off is equal
  /// but not guaranteed identical, which detach keys on.
  late final ConversationPlaybackSeekHandler _seekWallHandler = _seekWall;

  List<AudioFile> _getSortedAudioFiles() {
    if (widget.conversation == null) return [];
    return ConversationPlaybackPlan.sortedFiles(widget.conversation!.audioFiles);
  }

  @override
  void initState() {
    super.initState();
    _audioSourceSnapshot = _audioSourceFingerprint();
    _calculateTotalDuration();
    widget.playbackController?.attachSeekHandler(_seekWallHandler);
    // Provide the seek function to parent widget
    widget.onSeekFunctionReady?.call(seekToTranscriptSegment);
  }

  @override
  void didUpdateWidget(ConversationBottomBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.playbackController != oldWidget.playbackController) {
      oldWidget.playbackController?.detachSeekHandler(_seekWallHandler);
      widget.playbackController?.attachSeekHandler(_seekWallHandler);
    }
    if (widget.conversation?.id != oldWidget.conversation?.id) {
      _audioSourceSnapshot = _audioSourceFingerprint();
      _teardownPlayer(newConversation: true);
      _calculateTotalDuration();
      return;
    }
    final snapshot = _audioSourceFingerprint();
    final sourceChanged = !_sourceEquality.equals(snapshot, _audioSourceSnapshot);
    _audioSourceSnapshot = snapshot;
    if (sourceChanged) {
      _invalidateAudioSource();
    } else {
      _refreshWaveformMetadata();
    }
  }

  List<Object?> _audioSourceFingerprint() {
    final conversation = widget.conversation;
    if (conversation == null) return const [];
    final stamp = conversation.conversationAudio;
    return [
      (conversation.startedAt ?? conversation.createdAt).millisecondsSinceEpoch,
      for (final file in _getSortedAudioFiles())
        [
          file.id,
          file.provider,
          file.startedAt?.millisecondsSinceEpoch,
          file.duration,
          List<double>.of(file.chunkTimestamps),
        ],
      if (stamp != null)
        [
          stamp.duration,
          stamp.capturedDuration,
          for (final span in stamp.spans) (span.fileId, span.wallOffset, span.artifactOffset, span.len),
        ],
    ];
  }

  void _invalidateAudioSource() {
    _teardownPlayer(report: false, newConversation: true);
    _calculateTotalDuration();
    final controller = widget.playbackController;
    if (controller == null) return;
    final generation = _loadGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && generation == _loadGeneration) controller.playerDetached();
    });
  }

  void _refreshWaveformMetadata() {
    if (!_isAudioInitialized) {
      _calculateTotalDuration();
      return;
    }
    final metadata = _conversationMetadata(widget.conversation);
    final resolvedWallEnd = _timelineMapper?.wallDuration ?? _totalDuration.inMilliseconds / 1000;
    final wallEnd = math.max(metadata.wallEnd, resolvedWallEnd);
    if (wallEnd == _wallEndSeconds) return;
    _wallEndSeconds = wallEnd;
    final urls = _resolvedUrls;
    final conversation = widget.conversation;
    if (urls != null && conversation != null) _updateMissingRanges(urls, conversation);
  }

  @override
  void dispose() {
    widget.playbackController?.detachSeekHandler(_seekWallHandler);
    _teardownPlayer(report: false);
    widget.playbackController?.playerDetached(notify: false);
    _artifactPosition.dispose();
    super.dispose();
  }

  /// Drops the player and every subscription; the pending wall position lives
  /// in the page-owned controller and survives this (e.g. keyboard remount).
  /// Bumping [_loadGeneration] and [_seekGeneration] invalidates an in-flight
  /// load or seek: it must not adopt its player, complete a newer init's
  /// completer, or land an older position over a newer gesture. The old init
  /// completer resolves false so a waiting toggle/seek unwinds instead of
  /// hanging on a dead load. [report] is off for dispose — notifying the
  /// controller synchronously during widget teardown can reach listeners that
  /// are already gone. [newConversation] also clears the failure and missing
  /// ranges; a retry of the same conversation keeps its inline error until
  /// the fresh fetch answers.
  void _teardownPlayer({bool report = true, bool newConversation = false}) {
    _loadGeneration++;
    _seekGeneration++;
    _loadLabelTimer?.cancel();
    _loadCancel?.complete();
    _loadCancel = null;
    final staleInit = _initCompleter;
    _initCompleter = null;
    if (staleInit != null && !staleInit.isCompleted) staleInit.complete(false);
    _positionSubscription?.cancel();
    _positionSubscription = null;
    _playbackErrorSubscription?.cancel();
    _playbackErrorSubscription = null;
    _playerStateSubscription?.cancel();
    _playerStateSubscription = null;
    _audioPlayer?.dispose();
    _audioPlayer = null;
    _isAudioInitialized = false;
    _isAudioLoading = false;
    _showPreparingLabel = false;
    _timelineMapper = null;
    _singleArtifact = false;
    _artifactPosition.value = 0;
    _resolvedUrls = null;
    if (newConversation) {
      _failure = null;
      _missingRanges = [];
      _hasUnplaceableMissing = false;
      _readyParts = 0;
      _totalParts = 0;
    }
    if (report) {
      widget.playbackController?.playerDetached();
    }
  }

  /// The length shown before playback starts, from the conversation alone. Replaced by the plan's
  /// length once the URLs resolve.
  void _calculateTotalDuration() {
    final metadata = _conversationMetadata(widget.conversation);
    _trackStartOffsets = metadata.offsets;
    _totalDuration = metadata.total;
    _wallEndSeconds = metadata.wallEnd;
  }

  ({double wallEnd, Duration total, List<Duration> offsets}) _conversationMetadata(ServerConversation? conversation) {
    final offsets = <Duration>[];
    if (conversation == null) return (wallEnd: 0, total: Duration.zero, offsets: offsets);
    final segments = conversation.transcriptSegments;
    var wallEnd = segments.isEmpty ? 0.0 : segments.map((segment) => segment.end).reduce(math.max);
    final conversationStart = conversation.startedAt ?? conversation.createdAt;
    final sortedFiles = ConversationPlaybackPlan.sortedFiles(conversation.audioFiles);
    for (final file in sortedFiles) {
      final startedAt = file.startedAt;
      if (startedAt != null) {
        final fileWallEnd = startedAt.difference(conversationStart).inMilliseconds / 1000 + file.duration;
        if (fileWallEnd > wallEnd) wallEnd = fileWallEnd;
      }
    }
    final stamp = conversation.conversationAudio;
    if (stamp != null && stamp.spans.isNotEmpty) {
      // Dense-artifact timeline: the total is the actual captured audio length
      // (the MP3 has inter-part gaps and lead-in silence collapsed out), so the
      // scrubber matches what the user can hear. Transcript-segment taps still
      // map their wall timestamp to the MP3 position via the spans manifest.
      final mappedEnd = AudioTimelineMapper(stamp.spans).wallDuration;
      if (mappedEnd > wallEnd) wallEnd = mappedEnd;
      return (
        wallEnd: wallEnd,
        total: Duration(milliseconds: (stamp.capturedDuration * 1000).toInt()),
        offsets: offsets,
      );
    }
    double totalSeconds = 0;
    for (final audioFile in sortedFiles) {
      offsets.add(Duration(milliseconds: (totalSeconds * 1000).toInt()));
      totalSeconds += audioFile.duration;
    }
    return (wallEnd: wallEnd, total: Duration(milliseconds: (totalSeconds * 1000).toInt()), offsets: offsets);
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

  /// The seek handler the playback controller forwards wall-clock intents to.
  /// [strict] taps use the no-gap-snap map so a line in a collapsed gap does
  /// not jump into a later span (#4471); scrubs and reader repositions snap.
  Future<void> _seekWall(double wallSeconds, {required bool play, required bool strict}) async {
    widget.onAudioInteraction?.call();
    final generation = ++_seekGeneration;
    if (!_isAudioInitialized && !await _initAudioIfNeeded()) return;
    if (!mounted || _audioPlayer == null || generation != _seekGeneration) return;

    // A newer gesture may have landed while init was awaited: the
    // controller's latest pending point wins over this call's arguments.
    final controller = widget.playbackController;
    if (controller != null && controller.hasPending) {
      wallSeconds = controller.resumeWall ?? wallSeconds;
      strict = controller.pendingStrict;
    }
    final intent = controller?.intentGeneration;

    final mapper = _timelineMapper;
    if (mapper == null) {
      _setFailure(_AudioFailure.unmappable);
      return;
    }
    final artifact = strict ? mapper.wallToArtifactStrict(wallSeconds) : mapper.wallToArtifact(wallSeconds);
    if (artifact == null) {
      _setFailure(_AudioFailure.unmappable);
      return;
    }
    if (_failure == _AudioFailure.unmappable) setState(() => _failure = null);

    if (play && _audioPlayer!.processingState == ProcessingState.completed) {
      await _audioPlayer!.pause();
      if (!mounted || _audioPlayer == null || generation != _seekGeneration) return;
    }
    if (!await _seekToCombinedPosition(Duration(milliseconds: (artifact * 1000).clamp(0, double.infinity).toInt()))) {
      return;
    }
    if (!mounted || _audioPlayer == null || generation != _seekGeneration) return;
    if (controller != null && intent != controller.intentGeneration) return;
    controller?.clearPending();

    if (play && !_effectivePlaying) {
      PlatformManager.instance.analytics.audioPlaybackStarted(
        conversationId: widget.conversation?.id ?? '',
        durationSeconds: _totalDuration.inSeconds > 0 ? _totalDuration.inSeconds : null,
      );
      // play() resolves only once playback ends or is paused; don't await it.
      unawaited(
        _audioPlayer!.play().catchError((Object e) {
          Logger.debug('Audio playback failed to start: $e');
          _setFailure(_AudioFailure.loadFailed);
        }),
      );
      if (mounted) setState(() {});
    }
  }

  /// Seek to a transcript segment and play from there (unbounded).
  ///
  /// Uses strict wall→playback mapping (no gap-snap) so a segment whose start
  /// falls in a collapsed inter-part gap does not jump into a later span
  /// (#4471). Works on the dense conversation artifact and on a part playlist
  /// whose parts carry their start times; otherwise playback is unavailable.
  Future<void> seekToTranscriptSegment(double segmentStartSeconds, double segmentEndSeconds) async {
    final conversationId = widget.conversation?.id ?? '';
    final mapper = _timelineMapper;
    final mapped = mapper?.wallToArtifactStrict(segmentStartSeconds);
    PlatformManager.instance.analytics.transcriptSegmentTapped(
      conversationId: conversationId,
      segmentStartSeconds: segmentStartSeconds,
      seekPositionSeconds: mapped ?? segmentStartSeconds,
    );
    final controller = widget.playbackController;
    if (controller != null) {
      controller.seek(segmentStartSeconds, play: true, strict: true);
    } else {
      unawaited(_seekWall(segmentStartSeconds, play: true, strict: true));
    }
  }

  /// Resolves the conversation's audio and loads it into a new player. True when it can play; on
  /// any failure says so inline, leaves no player behind and lets the next tap try again.
  Future<bool> _initAudioIfNeeded() async {
    if (_isAudioInitialized) return true;
    if (!mounted || widget.conversation == null || !widget.conversation!.hasAudio()) return false;

    // If a concurrent init is already in flight, wait for it instead of starting
    // a second one — otherwise both calls would create/init an AudioPlayer
    // and trigger PlatformException "Platform player already exists".
    if (_initCompleter != null) return _initCompleter!.future;
    final completer = _initCompleter = Completer<bool>();
    // Captured at entry: a teardown bumps _loadGeneration mid-flight and the
    // stale poll/load must abort rather than adopt its player later.
    final generation = _loadGeneration;
    _loadCancel = Completer<void>();
    _loadLabelTimer?.cancel();
    // The "Preparing Audio…" label only shows for loads that take a beat.
    _loadLabelTimer = Timer(const Duration(milliseconds: 600), () {
      if (mounted && _isAudioLoading) setState(() => _showPreparingLabel = true);
    });
    setState(() => _isAudioLoading = true);

    var ready = false;
    try {
      ready = await _loadPlayback(widget.conversation!, generation);
    } finally {
      // A teardown detached this completer already; only the owner clears the
      // loading state so an obsolete load cannot dim a newer attempt's label.
      if (identical(_initCompleter, completer)) {
        _initCompleter = null;
        _loadLabelTimer?.cancel();
        if (mounted) {
          setState(() {
            _isAudioLoading = false;
            _showPreparingLabel = false;
          });
        }
        if (!completer.isCompleted) completer.complete(ready);
      }
    }
    return ready;
  }

  void _setFailure(_AudioFailure failure, {String? analyticsReason}) {
    Logger.debug('Audio playback failed for ${widget.conversation?.id}: ${failure.name}');
    AnalyticsManager().audioPlaybackFailed(
      conversationId: widget.conversation?.id ?? '',
      reason: analyticsReason ?? failure.name,
    );
    if (mounted) setState(() => _failure = failure);
  }

  /// Polls for playable URLs inside the shared 90 s budget; each fetch and
  /// delay is bounded by the time left and raced against teardown so disposal
  /// and deadlines always win. Returns the response, or null when the budget
  /// ran out, the load was superseded, or a request failed.
  Future<AudioUrlsResponse?> _pollPlaybackUrls(ServerConversation conversation, int generation) async {
    final fetch = widget.fetchAudioUrls ?? getConversationAudioSignedUrls;
    final deadline = DateTime.now().add(const Duration(seconds: 90));

    bool superseded() => generation != _loadGeneration || _loadCancel == null || _loadCancel!.isCompleted;

    Future<AudioUrlsResponse?> request() async {
      final remaining = deadline.difference(DateTime.now());
      if (remaining.isNegative || superseded()) return null;
      final cancel = _loadCancel!.future;
      final outcome = Completer<Object?>();
      final timer = Timer(remaining, () {
        if (!outcome.isCompleted) {
          outcome.completeError(const _UrlsRequestFailed(ApiProblem(ApiProblemKind.transport)));
        }
      });
      fetch(conversation.id).then<void>(
        (result) {
          if (!outcome.isCompleted) outcome.complete(result);
        },
        onError: (Object e, StackTrace s) {
          if (!outcome.isCompleted) outcome.completeError(e, s);
        },
      );
      cancel.then<void>((_) {
        if (!outcome.isCompleted) outcome.complete(null);
      });
      try {
        final result = await outcome.future;
        if (result is! ApiResult<AudioUrlsResponse>) return null;
        return switch (result) {
          ApiSuccess<AudioUrlsResponse>(:final data) => data,
          ApiFailure<AudioUrlsResponse>(:final problem) => throw _UrlsRequestFailed(problem),
        };
      } finally {
        timer.cancel();
      }
    }

    var urls = await request();
    while (urls != null && urls.files.isNotEmpty && !urls.playbackReady) {
      if (!mounted || superseded()) return null;
      _updateMissingRanges(urls, conversation);
      final remaining = deadline.difference(DateTime.now());
      if (remaining.isNegative) break;
      final cancel = _loadCancel!.future;
      final waited = Completer<void>();
      final timer = Timer(
        Duration(milliseconds: math.min(urls.pollAfterMs ?? 3000, remaining.inMilliseconds)),
        waited.complete,
      );
      cancel.then<void>((_) {
        if (!waited.isCompleted) waited.complete();
      });
      try {
        await waited.future;
      } finally {
        timer.cancel();
      }
      if (!mounted || superseded()) return null;
      urls = await request();
    }
    return urls;
  }

  Future<bool> _loadPlayback(ServerConversation conversation, int generation) async {
    // The backend builds playback artifacts asynchronously; poll while any
    // file is pending. A failed request is final for this attempt — the
    // inline error tells the reader which kind, and Try Again re-runs it.
    AudioUrlsResponse urls;
    try {
      final fetched = await _pollPlaybackUrls(conversation, generation);
      if (fetched == null) {
        if (!mounted || generation != _loadGeneration) return false;
        _setFailure(_AudioFailure.unavailable, analyticsReason: ConversationPlaybackPlan.noPlayableParts);
        return false;
      }
      urls = fetched;
    } on _UrlsRequestFailed catch (e) {
      if (!mounted || generation != _loadGeneration) return false;
      final kind = e.problem.kind;
      // Only "the request never returned" reads as Check Connection; server
      // and rate-limit answers are a load failure like any other.
      _setFailure(
        kind == ApiProblemKind.transport ? _AudioFailure.transport : _AudioFailure.loadFailed,
        analyticsReason: kind == ApiProblemKind.transport ? 'transport' : 'http_${e.problem.statusCode ?? kind.name}',
      );
      return false;
    }
    if (!mounted || generation != _loadGeneration || widget.conversation?.id != conversation.id) {
      return false;
    }

    final plan = ConversationPlaybackPlan.resolve(
      urls,
      conversation.audioFiles,
      conversationStart: conversation.startedAt ?? conversation.createdAt,
    );
    if (plan.failure != null) {
      // Both plan failures mean nothing can play — a genuinely empty answer is
      // unavailable audio, not a load error.
      _setFailure(_AudioFailure.unavailable, analyticsReason: plan.failure);
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
      Logger.debug('Audio load failed for ${conversation.id}: $e');
      if (mounted && generation == _loadGeneration) {
        _setFailure(_AudioFailure.loadFailed, analyticsReason: 'load_failed');
      }
      unawaited(player.dispose());
      return false;
    }
    if (!mounted || generation != _loadGeneration || widget.conversation?.id != conversation.id) {
      unawaited(player.dispose());
      return false;
    }

    _audioPlayer = player;
    _singleArtifact = plan.singleUrl != null;
    _timelineMapper = plan.mapper;
    _trackStartOffsets = plan.partOffsets;
    _totalDuration = plan.duration;
    // The waveform spans the resolved wall timeline: the mapped wall end, or
    // the playable parts' own length when nothing can be mapped — either can
    // run past the cached metadata's estimate.
    final resolvedWallEnd = plan.mapper?.wallDuration ?? plan.duration.inMilliseconds / 1000;
    if (resolvedWallEnd > _wallEndSeconds) _wallEndSeconds = resolvedWallEnd;
    _isAudioInitialized = true;
    _resolvedUrls = urls;
    // Only now, with the mapper adopted, do collapsed gaps have a wall range.
    _updateMissingRanges(urls, conversation);
    _attachPlayerListeners(player);
    widget.playbackController?.reportPlayback(
      wallSeconds: widget.playbackController!.wallPosition.value,
      playing: false,
      loaded: true,
      mapped: _timelineMapper != null,
    );
    return true;
  }

  /// One central subscription set feeding the waveform, remaining time and
  /// the shared controller — no nested stream ownership in build.
  void _attachPlayerListeners(AudioPlayer player) {
    _positionSubscription = player.positionStream.listen((position) {
      // A torn-down player's stream can still deliver: only the adopted
      // player may move the playhead or the controller.
      if (!identical(player, _audioPlayer)) return;
      final combined = _getCombinedPosition(player.currentIndex, position);
      _artifactPosition.value = combined.inMilliseconds / 1000;
      _reportWallPosition(combined);
    });
    _playerStateSubscription = player.playerStateStream.listen((state) {
      if (!identical(player, _audioPlayer)) return;
      // `completed` still reports playing in just_audio; only a genuinely
      // running track counts as playing for the controller and controls.
      final running = state.playing && state.processingState != ProcessingState.completed;
      _reportWallPosition(_getCombinedPosition(player.currentIndex, player.position), playing: running);
      if (mounted) setState(() {});
    });
    // A part that fails mid-playlist (an expired URL, an unreadable file) surfaces here.
    _playbackErrorSubscription = player.playbackEventStream.listen(
      (_) {},
      onError: (Object e, StackTrace _) {
        if (!identical(player, _audioPlayer)) return;
        Logger.debug('Audio stream error: $e');
        _setFailure(_AudioFailure.loadFailed, analyticsReason: 'stream_error');
      },
    );
  }

  void _reportWallPosition(Duration combined, {bool? playing}) {
    final controller = widget.playbackController;
    if (controller == null) return;
    final mapper = _timelineMapper;
    final wall =
        mapper != null ? mapper.artifactToWall(combined.inMilliseconds / 1000) : combined.inMilliseconds / 1000;
    controller.reportPlayback(
      wallSeconds: wall,
      playing: playing ?? _effectivePlaying,
      loaded: _isAudioInitialized,
      // Without a mapper the artifact position cannot claim a transcript
      // line: report it as unmapped instead of inventing a wall clock.
      mapped: mapper != null,
    );
  }

  /// The wall ranges the waveform dims: parts that cannot play yet (pending,
  /// unavailable) placed by their timestamps, plus the mapper's collapsed
  /// gaps. A part with no timestamp is unplaceable — reported separately,
  /// never given an invented range.
  void _updateMissingRanges(AudioUrlsResponse urls, ServerConversation conversation) {
    final conversationStart = conversation.startedAt ?? conversation.createdAt;
    final wallEnd = _wallEndSeconds > 0 ? _wallEndSeconds : 1.0;
    final missing = <(double, double)>[];
    var unplaceable = false;
    for (final file in _getSortedAudioFiles()) {
      final info = urls.files.where((candidate) => candidate.id == file.id).firstOrNull;
      final covered = info?.isCached == true || (urls.conversationAudio?.isCached ?? false);
      if (covered) continue;
      final startedAt = file.startedAt;
      if (startedAt == null) {
        unplaceable = true;
        continue;
      }
      final from = startedAt.difference(conversationStart).inMilliseconds / 1000;
      final to = from + (file.duration > 0 ? file.duration : (info?.duration ?? 0));
      missing.add(((from / wallEnd).clamp(0.0, 1.0), (to / wallEnd).clamp(0.0, 1.0)));
    }
    final mapper = _timelineMapper;
    if (mapper != null) {
      for (final (from, to) in mapper.gapRangesWall) {
        missing.add(((from / wallEnd).clamp(0.0, 1.0), (to / wallEnd).clamp(0.0, 1.0)));
      }
    }
    _missingRanges = missing;
    _hasUnplaceableMissing = unplaceable;
    _readyParts = urls.files.where((file) => file.isCached).length;
    _totalParts = urls.files.length;
  }

  /// Try Again after an inline failure: drop the failed player and re-run the
  /// whole resolve so init is never stuck "forever initialized".
  Future<void> _retryAudio() async {
    widget.onAudioInteraction?.call();
    setState(() => _failure = null);
    _teardownPlayer();
    await _initAudioIfNeeded();
  }

  /// just_audio keeps `playing` true through `completed`; the control state
  /// and follow logic need real, still-running playback.
  bool get _effectivePlaying =>
      _audioPlayer != null && _audioPlayer!.playing && _audioPlayer!.processingState != ProcessingState.completed;

  Future<void> _togglePlayPause() async {
    widget.onAudioInteraction?.call();
    if (!_isAudioInitialized && (_isAudioLoading || !await _initAudioIfNeeded())) return;
    if (!mounted || _audioPlayer == null) return;

    final conversationId = widget.conversation?.id ?? '';

    if (_effectivePlaying) {
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

      // The reader's point wins over the artifact's resting position: a line
      // tap maps strict, a scrub or scroll snaps into captured audio. Read it
      // after the awaited init so the newest gesture is the one applied, and
      // supersede any older in-flight seek.
      final controller = widget.playbackController;
      final completed = _audioPlayer!.processingState == ProcessingState.completed;
      if (completed) {
        // just_audio leaves playing:true at completed; pause() resets its
        // internal flag or the play() below returns before reaching the
        // platform.
        await _audioPlayer!.pause();
        if (!mounted || _audioPlayer == null) return;
      }
      // At the end of the track the paused point is the tail: restart takes a
      // fresh reader intent if one exists, otherwise the beginning.
      final resumeWall =
          completed ? (controller?.hasPending == true ? controller?.pendingWallSeconds : null) : controller?.resumeWall;
      if (resumeWall != null) {
        final generation = ++_seekGeneration;
        final intent = controller!.intentGeneration;
        final mapper = _timelineMapper;
        final strict = controller.pendingStrict;
        final artifact = mapper == null
            ? null
            : (strict ? mapper.wallToArtifactStrict(resumeWall) : mapper.wallToArtifact(resumeWall));
        if (artifact == null && mapper != null && strict) {
          _setFailure(_AudioFailure.unmappable);
          return;
        }
        if (artifact != null) {
          if (!await _seekToCombinedPosition(
            Duration(milliseconds: (artifact * 1000).clamp(0, double.infinity).toInt()),
          )) {
            return;
          }
          if (!mounted || _audioPlayer == null || generation != _seekGeneration) return;
          if (intent != controller.intentGeneration) return;
          controller.clearPending();
        }
      } else if (completed) {
        // Completed playback still reports playing: rewind before restarting.
        if (!await _seekToCombinedPosition(Duration.zero)) return;
        if (!mounted || _audioPlayer == null) return;
      }

      // Play always re-engages follow — even onto the same line the reader
      // scrolled away from.
      controller?.backToCurrent();

      // play() resolves only once playback ends or is paused; don't await it.
      unawaited(
        _audioPlayer!.play().catchError((Object e) {
          Logger.debug('Audio playback failed to start: $e');
          _setFailure(_AudioFailure.loadFailed);
        }),
      );
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
                Expanded(
                  child: KeyedSubtree(key: const ValueKey('detail_audio_player'), child: _buildPlayer()),
                ),
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
  /// Pills float above the bar: Back to Current while the reader owns the
  /// scroll, Try Again after an inline failure.
  Widget _buildPlayer() {
    final controller = widget.playbackController;
    final player = Container(
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
    if (controller == null && _failure == null) return player;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ListenableBuilder(
          listenable: controller ?? _artifactPosition,
          builder: (context, _) {
            final showBackToCurrent = controller != null &&
                !controller.isFollowing &&
                controller.followTargetSegmentId != null &&
                _isAudioInitialized;
            final showRetry = _failure != null && _failure != _AudioFailure.unmappable;
            if (!showBackToCurrent && !showRetry) return const SizedBox.shrink();
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (showBackToCurrent)
                    OmiButton.tertiary(
                      key: const Key('detail_audio_back_to_current'),
                      size: OmiButtonSize.compact,
                      label: context.l10n.playbackBackToCurrent,
                      onPressed: controller.backToCurrent,
                    ),
                  if (showBackToCurrent && showRetry) const SizedBox(width: 8),
                  if (showRetry)
                    OmiButton.tertiary(
                      key: const Key('detail_audio_retry'),
                      size: OmiButtonSize.compact,
                      label: context.l10n.tryAgain,
                      onPressed: _retryAudio,
                    ),
                ],
              ),
            );
          },
        ),
        player,
      ],
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
    const loading = SizedBox.square(
      dimension: kOmiMinTapTarget,
      child: Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
    );

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
        // `completed` still reports playing: present Play so a tap rewinds
        // and starts again.
        return button(playerState != null && playerState.playing && processingState != ProcessingState.completed);
      },
    );
  }

  /// The waveform runs on the transcript's wall clock: speech bars from
  /// segment times, the playhead from the mapped wall position, and missing
  /// parts dimmed in place. The remaining-time label stays on heard audio.
  Widget _buildWaveform() {
    final conversation = widget.conversation;
    final segments = conversation?.transcriptSegments ?? const <TranscriptSegment>[];
    var wallEnd = _wallEndSeconds;
    if (wallEnd <= 0 && segments.isNotEmpty) {
      wallEnd = segments.map((segment) => segment.end).reduce(math.max);
    }
    final levels = speechLevels(segments, _waveformBars, start: 0, end: wallEnd > 0 ? wallEnd : null);
    final controller = widget.playbackController;
    final l10n = context.l10n;

    final String? statusLabel = switch ((_failure, _showPreparingLabel)) {
      (_AudioFailure.transport, _) => l10n.playbackAudioNetworkFailed,
      (_AudioFailure.unavailable, _) || (_AudioFailure.unmappable, _) => l10n.playbackAudioUnavailable,
      (_AudioFailure.loadFailed, _) => l10n.playbackAudioLoadFailed,
      (null, true) => _readyParts < _totalParts
          ? '${l10n.playbackPreparingAudio} $_readyParts/$_totalParts'
          : l10n.playbackPreparingAudio,
      // Audio with no timestamps cannot be placed on the wall at all: say so
      // where the reader can see it rather than only flagging it for tests.
      _ when _hasUnplaceableMissing => l10n.playbackAudioUnavailable,
      _ => null,
    };

    void onSeekFraction(double fraction) {
      if (wallEnd <= 0) return;
      final wall = fraction * wallEnd;
      if (controller != null) {
        controller.seek(wall);
      } else {
        final mapper = _timelineMapper;
        final artifact = mapper != null ? mapper.wallToArtifact(wall) : wall;
        unawaited(_seekToCombinedPosition(Duration(milliseconds: (artifact * 1000).clamp(0, double.infinity).toInt())));
      }
    }

    return ValueListenableBuilder<double>(
      valueListenable: controller?.wallPosition ?? _artifactPosition,
      builder: (context, wallOrArtifact, _) {
        return ValueListenableBuilder<double>(
          valueListenable: _artifactPosition,
          builder: (context, artifactSeconds, __) {
            final wallSeconds = controller != null
                ? wallOrArtifact
                : (_timelineMapper?.artifactToWall(artifactSeconds) ?? artifactSeconds);
            // Loaded audio with no wall mapping cannot claim heard progress
            // on the transcript clock — draw no played bars rather than
            // inventing an alignment.
            final unmapped = _isAudioInitialized && _timelineMapper == null;
            final progress = !unmapped && wallEnd > 0 ? (wallSeconds / wallEnd).clamp(0.0, 1.0) : 0.0;
            final position = Duration(milliseconds: (artifactSeconds * 1000).toInt());
            return Row(
              children: [
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      void seek(Offset local) => onSeekFraction((local.dx / constraints.maxWidth).clamp(0.0, 1.0));
                      final canSeek = wallEnd > 0;
                      return GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTapDown: canSeek ? (details) => seek(details.localPosition) : null,
                        onHorizontalDragUpdate: canSeek ? (details) => seek(details.localPosition) : null,
                        child: SizedBox(
                          height: 44,
                          child: CustomPaint(
                            key: const Key('detail_audio_waveform'),
                            painter: _WaveformPainter(
                              levels: levels,
                              progress: progress,
                              played: OmiColors.textPrimary,
                              unplayed: OmiColors.textPrimary.withValues(alpha: 0.3),
                              dimmed: OmiColors.textPrimary.withValues(alpha: 0.1),
                              dimRanges: _missingRanges,
                              hasUnplaceableMissing: _hasUnplaceableMissing,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(width: 10),
                if (statusLabel != null)
                  Flexible(
                    child: Semantics(
                      liveRegion: true,
                      child: Text(
                        statusLabel,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                      ),
                    ),
                  )
                else
                  Text(
                    '-${_formatDurationRemaining(position)}',
                    style: OmiType.footnote.copyWith(
                      color: OmiColors.textTertiary,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
              ],
            );
          },
        );
      },
    );
  }

  Future<bool> _seekToCombinedPosition(Duration targetPosition) async {
    widget.onAudioInteraction?.call();
    final player = _audioPlayer;
    if (player == null) return false;

    try {
      if (_singleArtifact) {
        // targetPosition is already artifact time (the scrubber runs on the dense
        // MP3; segment taps are mapped wall->artifact before they get here).
        PlatformManager.instance.analytics.audioPlaybackSeeked(
          conversationId: widget.conversation?.id ?? '',
          toPositionSeconds: targetPosition.inSeconds,
        );
        await player.seek(targetPosition);
        return true;
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

      await player.seek(positionInTrack, index: targetIndex);
      return true;
    } catch (e) {
      Logger.debug('Audio seek failed for ${widget.conversation?.id}: $e');
      if (mounted && identical(player, _audioPlayer)) {
        _setFailure(_AudioFailure.loadFailed, analyticsReason: 'seek_failed');
      }
      return false;
    }
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
                child: FaIcon(icon, color: isSelected ? OmiColors.textPrimary : OmiColors.textTertiary, size: 22),
              ),
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
        spans.add(
          ConversationAudioSpan(
            fileId: file.id,
            wallOffset: startedAt.difference(conversationStart!).inMilliseconds / 1000,
            artifactOffset: offset,
            len: seconds,
          ),
        );
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
/// [progress] and the rest in [unplayed]. Silent slices keep a short bar so the track stays
/// visible. Bars inside a [dimRanges] wall fraction — a part that cannot play or a collapsed
/// gap — render in [dimmed] regardless of progress so missing audio reads as missing.
class _WaveformPainter extends CustomPainter {
  _WaveformPainter({
    required this.levels,
    required this.progress,
    required this.played,
    required this.unplayed,
    required this.dimmed,
    this.dimRanges = const [],
    this.hasUnplaceableMissing = false,
  });

  final List<double> levels;
  final double progress;
  final Color played;
  final Color unplayed;
  final Color dimmed;

  /// Wall fractions ([start, end] in 0..1) whose audio cannot play.
  final List<(double, double)> dimRanges;

  /// Audio exists that has no timestamps and cannot be placed on the wall at
  /// all — exposed to tests rather than painted as an invented range.
  final bool hasUnplaceableMissing;

  static const double _gap = 2;
  static const double _minHeight = 4;

  bool _isDimmed(double fraction) {
    for (final (from, to) in dimRanges) {
      if (fraction >= from && fraction < to) return true;
    }
    return false;
  }

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
      final fraction = (i + 0.5) / levels.length;
      paint.color = _isDimmed(fraction) ? dimmed : (fraction <= progress ? played : unplayed);
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
      oldDelegate.unplayed != unplayed ||
      oldDelegate.dimmed != dimmed ||
      oldDelegate.dimRanges != dimRanges ||
      oldDelegate.hasUnplaceableMissing != hasUnplaceableMissing;
}

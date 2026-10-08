import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/api/review.dart' as api;
import 'package:omi/backend/http/api/speaker_tag_prompts.dart' as speaker_api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/env/env.dart';
import 'package:omi/flavors.dart';
import 'package:omi/utils/logger.dart';

typedef ReviewItemsLoader = Future<ApiResult<ReviewItemsResponse>> Function();
typedef ReviewAnswerSender = Future<ApiResult<int>> Function(ReviewItem item, ReviewAnswer answer);
typedef ReviewClipLoader = Future<ApiResult<Uint8List>> Function(SpeakerItem speaker);
typedef ReleaseChannelReporter = Future<ApiResult<void>> Function(String channel);
typedef ReviewProjectsLoader = Future<ApiResult<List<EntityRef>>> Function();
typedef ConversationEntitiesLoader = Future<ApiResult<List<EntityRef>>> Function(String conversationId);

/// Plays [wav] for [itemId]; returns whether playback started.
typedef ReviewClipPlayer = Future<bool> Function(String itemId, Uint8List wav);

/// Whether the Review surface exists for this account. Unknown until the first load answers.
enum ReviewAvailability { unknown, on, off }

/// The few questions Omi needs the user to answer, shared by the Home entry card, the Review page,
/// and the same cards shown in context (a transcript, a person page).
///
/// Answers leave the list at once; a failed send puts the item back and reports false so the
/// caller can say so.
class ReviewProvider extends ChangeNotifier {
  ReviewProvider({
    ReviewItemsLoader? loadItems,
    ReviewAnswerSender? sendAnswer,
    ReviewClipLoader? loadClip,
    ReviewClipPlayer? playClip,
    ReviewProjectsLoader? loadProjects,
    ConversationEntitiesLoader? loadConversationEntities,
    bool Function()? isEligible,
    ReleaseChannelReporter? reportChannel,
    String Function()? releaseChannel,
  })  : _reportChannel = reportChannel ?? api.putReleaseChannel,
        _releaseChannel = releaseChannel ?? _defaultReleaseChannel,
        _isEligible = isEligible ?? _defaultEligible,
        _loadItems = loadItems ?? api.getReviewItems,
        _loadConversationEntities = loadConversationEntities ?? api.getConversationEntities,
        _loadProjects = loadProjects ?? api.getProjectEntities,
        _sendAnswer = sendAnswer ?? api.answerReviewItem,
        _loadClip = loadClip ?? _defaultLoadClip,
        _playClipOverride = playClip;

  final bool Function() _isEligible;
  final ReleaseChannelReporter _reportChannel;
  final String Function() _releaseChannel;
  bool _channelReported = false;
  final ReviewItemsLoader _loadItems;
  final ReviewAnswerSender _sendAnswer;
  final ReviewClipLoader _loadClip;
  final ReviewClipPlayer? _playClipOverride;
  final ReviewProjectsLoader _loadProjects;
  final ConversationEntitiesLoader _loadConversationEntities;

  /// Project names by id (project ids equal workstream ids), for grouping tasks by project.
  Map<String, EntityRef> projects = const {};

  ReviewAvailability availability = ReviewAvailability.unknown;
  List<ReviewItem> items = const [];
  int remainingToday = 0;
  bool loading = false;
  bool loadFailed = false;
  String? playingItemId;

  final Map<String, Uint8List> _clips = {};
  AudioPlayer? _player;
  int _playbackTicket = 0;
  bool _disposed = false;
  Future<void>? _inFlight;

  bool get isOn => availability == ReviewAvailability.on;

  /// The pending question about [entityId], if one is queued (shown inline on that entity's page).
  ReviewItem? questionAbout(String entityId) {
    for (final item in items) {
      final pair = item.samePerson;
      if (pair != null && (pair.left.entityId == entityId || pair.right.entityId == entityId)) return item;
    }
    return null;
  }

  /// The pending speaker question for [conversationId], if one is queued.
  ReviewItem? speakerQuestionIn(String conversationId) {
    for (final item in items) {
      if (item.speaker?.conversationId == conversationId) return item;
    }
    return null;
  }

  /// Reports this install's release channel once per session, for every build (a Store launch
  /// must clear an earlier TestFlight record). Failures are ignored; the next launch retries.
  Future<void> reportReleaseChannel() async {
    if (_channelReported) return;
    _channelReported = true;
    final result = await _reportChannel(_releaseChannel());
    if (result case ApiFailure(:final problem)) Logger.debug('release channel not recorded: $problem');
  }

  Future<void> load() => _inFlight ??= _load().whenComplete(() => _inFlight = null);

  /// The organizations and projects [conversationId] belongs to; empty while Review is off.
  Future<List<EntityRef>> conversationEntities(String conversationId) async {
    if (!isOn) return const [];
    return switch (await _loadConversationEntities(conversationId)) {
      ApiSuccess(:final data) => data,
      ApiFailure() => const [],
    };
  }

  Future<void> loadProjects() async {
    if (!isOn) return;
    if (await _loadProjects() case ApiSuccess(:final data)) {
      projects = {for (final project in data) project.entityId: project};
      _notify();
    }
  }

  Future<void> _load() async {
    // First release: TestFlight and dev builds only. Store builds never ask, whatever the server says.
    if (!_isEligible()) {
      availability = ReviewAvailability.off;
      _notify();
      return;
    }
    loading = true;
    _notify();
    switch (await _loadItems()) {
      case ApiSuccess(:final data):
        availability = ReviewAvailability.on;
        items = data.items;
        remainingToday = data.remainingToday < data.items.length ? data.items.length : data.remainingToday;
        loadFailed = false;
      case ApiFailure(:final problem):
        if (problem.kind == ApiProblemKind.notFound || problem.kind == ApiProblemKind.forbidden) {
          availability = ReviewAvailability.off;
          items = const [];
          remainingToday = 0;
        } else {
          loadFailed = true;
        }
        Logger.debug('review items unavailable: $problem');
    }
    loading = false;
    _notify();
  }

  /// Sends [answer]. The item leaves the list immediately and comes back if the send fails.
  Future<bool> answer(ReviewItem item, ReviewAnswer answer) async {
    final index = items.indexWhere((i) => i.itemId == item.itemId);
    if (index < 0) return false;
    if (playingItemId == item.itemId) await stopPlayback();
    final before = items;
    final beforeRemaining = remainingToday;
    items = [...items]..removeAt(index);
    remainingToday = remainingToday > 0 ? remainingToday - 1 : 0;
    _notify();
    switch (await _sendAnswer(item, answer)) {
      case ApiSuccess(:final data):
        remainingToday = data < items.length ? items.length : data;
        _notify();
        return true;
      case ApiFailure(:final problem):
        Logger.debug('review answer failed: $problem');
        if (!items.any((i) => i.itemId == item.itemId)) {
          items = before;
          remainingToday = beforeRemaining;
        }
        _notify();
        return false;
    }
  }

  Future<void> togglePlay(ReviewItem item) async {
    final speaker = item.speaker;
    if (_disposed || speaker == null) return;
    final ticket = ++_playbackTicket;
    if (playingItemId == item.itemId) {
      await stopPlayback();
      return;
    }
    playingItemId = item.itemId;
    _notify();
    var wav = _clips[item.itemId];
    if (wav == null) {
      switch (await _loadClip(speaker)) {
        case ApiSuccess(:final data):
          wav = data;
        case ApiFailure(:final problem):
          Logger.debug('review clip unavailable: $problem');
      }
    }
    if (_disposed || ticket != _playbackTicket) return;
    var played = false;
    if (wav != null && wav.isNotEmpty) {
      _clips[item.itemId] = wav;
      final playClip = _playClipOverride;
      played = playClip != null ? await playClip(item.itemId, wav) : await _playWithJustAudio(wav, ticket);
    }
    if (_disposed || ticket != _playbackTicket) return;
    // Playback has finished (or never started); either way the clip is no longer playing.
    if (playingItemId == item.itemId) playingItemId = null;
    if (!played) Logger.debug('review clip did not play');
    _notify();
  }

  Future<void> stopPlayback() async {
    _playbackTicket++;
    await _player?.stop();
    if (playingItemId != null) {
      playingItemId = null;
      _notify();
    }
  }

  Future<bool> _playWithJustAudio(Uint8List wav, int ticket) async {
    File? file;
    try {
      final directory = await getTemporaryDirectory();
      if (_disposed || ticket != _playbackTicket) return false;
      file = File('${directory.path}/review_clip_$ticket.wav');
      await file.writeAsBytes(wav, flush: true);
      final player = _player ??= AudioPlayer();
      await player.stop();
      if (_disposed || ticket != _playbackTicket) return false;
      await player.setFilePath(file.path);
      // Completes when playback stops, so the temporary file outlives the clip.
      await player.play();
      return true;
    } catch (error) {
      Logger.debug('review clip playback failed: ${error.runtimeType}');
      return false;
    } finally {
      if (file != null) {
        try {
          await file.delete();
        } catch (_) {}
      }
    }
  }

  static String _defaultReleaseChannel() =>
      Env.isTestFlight ? 'testflight' : (F.env == Environment.prod ? 'app_store' : 'dev');

  static bool _defaultEligible() => Env.isTestFlight || F.env == Environment.dev;

  static Future<ApiResult<Uint8List>> _defaultLoadClip(SpeakerItem speaker) => speaker_api.getSpeakerTagPromptClip(
        conversationId: speaker.conversationId,
        start: speaker.start,
        end: speaker.end,
      );

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _player?.dispose();
    super.dispose();
  }
}

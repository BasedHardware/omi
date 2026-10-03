import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart' show conversationLocalDayKey;
import 'package:omi/ui/ui.dart' show OmiColors, OmiPalette, OmiRadius;
import 'package:omi/utils/audio/audio_timeline_mapper.dart';
import 'package:omi/utils/audio/conversation_playback_controller.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/transcript.dart';

final _start = DateTime.utc(2026, 9, 24, 9, 39);

AudioFile _file(String id, {double duration = 60, int? startsAfterSeconds}) => AudioFile(
      id: id,
      uid: 'u',
      conversationId: 'c',
      chunkTimestamps: const [],
      duration: duration,
      startedAt: startsAfterSeconds == null ? null : _start.add(Duration(seconds: startsAfterSeconds)),
    );

AudioFileUrlInfo _url(String id, String status, {double duration = 60}) => AudioFileUrlInfo(
      id: id,
      status: status,
      signedUrl: status == 'cached' ? 'https://audio.test/$id.mp3' : null,
      contentType: status == 'cached' ? 'audio/mpeg' : null,
      duration: duration,
    );

TranscriptSegment _segment(
  String id,
  double start,
  double end, {
  bool isUser = false,
  int speakerId = 0,
  String? text,
}) {
  return TranscriptSegment(
    id: id,
    text: text ?? 'Words for $id',
    speaker: 'SPEAKER_0$speakerId',
    isUser: isUser,
    personId: null,
    start: start,
    end: end,
    translations: [],
  );
}

/// A dense artifact where artifact seconds equal wall seconds inside [spans].
AudioUrlsResponse _dense(List<ConversationAudioSpan> spans, {String fileStatus = 'pending'}) => AudioUrlsResponse(
      files: [_url('a', fileStatus)],
      conversationAudio: ConversationAudioUrlInfo(
        status: 'cached',
        signedUrl: 'https://audio.test/conversation.mp3',
        capturedDuration: spans.isEmpty ? 0 : spans.last.artifactEnd,
        spans: spans,
      ),
    );

/// Stands in for the native just_audio player: records seek/play/pause calls
/// and lets the test emit deterministic position/state events.
class _FakeAudioDevice {
  final calls = <String>[];
  MockStreamHandlerEventSink? events;
  MockStreamHandlerEventSink? data;
  // Long enough that emitted positions are never clamped short of the wall
  // spans under test.
  int durationMicros = 1200000000;
  bool playing = false;
  double positionSec = 0;
  bool failSeeks = false;

  void emit({bool? playing, double? positionSec, int processingState = 3, int? index, bool reportPlaying = true}) {
    if (positionSec != null) this.positionSec = positionSec;
    if (playing != null) this.playing = playing;
    // A stale playing=false arriving between play()'s optimistic mark and its
    // activation check silently cancels the platform play request — seeks only
    // report processing state, not a playing transition. speed 0 pins the
    // reported position: createPositionStream interpolates by real elapsed
    // time, which would drift the follow target mid-test.
    if (reportPlaying) data?.success({'playing': this.playing, 'speed': 0.0});
    events?.success({
      'processingState': processingState,
      'updateTime': DateTime.now().millisecondsSinceEpoch,
      'updatePosition': (this.positionSec * 1e6).toInt(),
      'bufferedPosition': (this.positionSec * 1e6).toInt(),
      'duration': durationMicros,
      'icyMetadata': null,
      'currentIndex': index,
    });
  }
}

void _fakeAudioPlatform(WidgetTester tester, _FakeAudioDevice fake) {
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(const MethodChannel('com.ryanheise.audio_session'), (call) async {
    if (call.method == 'setActive') return true;
    return null;
  });
  messenger.setMockMethodCallHandler(const MethodChannel('com.ryanheise.just_audio.methods'), (call) async {
    if (call.method != 'init') return <String, dynamic>{};
    final id = (call.arguments as Map)['id'] as String;
    messenger.setMockMethodCallHandler(MethodChannel('com.ryanheise.just_audio.methods.$id'), (call) async {
      switch (call.method) {
        case 'load':
          fake.calls.add('load');
          fake.playing = false;
          fake.emit(processingState: 3);
          return {'duration': fake.durationMicros};
        case 'seek':
          if (fake.failSeeks) {
            throw PlatformException(code: 'seek_failed', message: 'nope');
          }
          final args = call.arguments as Map;
          fake.positionSec = ((args['position'] as int?) ?? 0) / 1e6;
          fake.calls.add('seek:${fake.positionSec.toStringAsFixed(3)}:${args['index']}');
          fake.emit(reportPlaying: false);
          return <String, dynamic>{};
        case 'play':
          fake.calls.add('play');
          fake.emit(playing: true);
          return <String, dynamic>{};
        case 'pause':
          fake.calls.add('pause');
          fake.emit(playing: false);
          return <String, dynamic>{};
        default:
          return <String, dynamic>{};
      }
    });
    for (final stream in ['events', 'data']) {
      messenger.setMockStreamHandler(
        EventChannel('com.ryanheise.just_audio.$stream.$id'),
        MockStreamHandler.inline(
          onListen: (_, sink) {
            if (stream == 'events') {
              fake.events = sink;
            } else {
              fake.data = sink;
            }
          },
        ),
      );
    }
    return null;
  });
}

ServerConversation _conversation({List<TranscriptSegment>? segments, List<AudioFile>? audioFiles}) =>
    ServerConversation(
      id: 'conv-sync',
      createdAt: _start,
      startedAt: _start,
      structured: Structured('A call', ''),
      audioFiles: audioFiles ?? [_file('a', duration: 120, startsAfterSeconds: 0)],
      transcriptSegments: segments ?? const [],
    );

typedef _Fetch = Future<ApiResult<AudioUrlsResponse>> Function(String conversationId);

/// The detail-page composition: a page-owned [ConversationPlaybackController]
/// shared by a real [TranscriptWidget] (wired exactly like TranscriptWidgets)
/// and a real [ConversationBottomBar], with line taps forwarded the way
/// page.dart forwards them.
class _DetailHarness {
  _DetailHarness(this.controller);

  final ConversationPlaybackController controller;
  Future<void> Function(double start, double end)? seekToSegment;
}

class _UrlsEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://audio-urls.test/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<_DetailHarness> _pumpDetail(
  WidgetTester tester,
  ServerConversation conversation, {
  required _Fetch fetch,
  _FakeAudioDevice? fake,
  ConversationPlaybackController? controllerParam,
}) async {
  if (fake != null) _fakeAudioPlatform(tester, fake);
  final controller =
      controllerParam ?? (ConversationPlaybackController()..updateSegments(conversation.transcriptSegments));
  if (controllerParam == null) addTearDown(controller.dispose);
  final harness = _DetailHarness(controller);
  final provider = ConversationDetailProvider()
    ..selectedDate = conversationLocalDayKey(conversation.createdAt)
    ..setCachedConversation(conversation);
  addTearDown(provider.dispose);
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: ChangeNotifierProvider<ConversationDetailProvider>.value(
        value: provider,
        child: Scaffold(
          body: Column(
            children: [
              Expanded(
                child: ListenableBuilder(
                  listenable: controller,
                  builder: (context, _) {
                    controller.updateSegments(conversation.transcriptSegments);
                    return TranscriptWidget(
                      segments: conversation.transcriptSegments,
                      isConversationDetail: true,
                      followLatest: false,
                      horizontalMargin: false,
                      bottomMargin: 150,
                      currentSegmentId: controller.currentSegmentId,
                      followTargetSegmentId: controller.followTargetSegmentId,
                      followCurrentSegment:
                          controller.isFollowing && (controller.isPlaying || controller.followRequest > 0),
                      playbackFollowRequest: controller.followRequest,
                      onUserScroll: controller.suspendFollowing,
                      onTopVisibleSegmentChanged: controller.readerMovedTo,
                      onSegmentTap: (segment) => harness.seekToSegment?.call(segment.start, segment.end),
                    );
                  },
                ),
              ),
              ConversationBottomBar(
                mode: ConversationBottomBarMode.detail,
                selectedTab: ConversationTab.transcript,
                onTabSelected: (_) {},
                onStopPressed: () {},
                conversation: conversation,
                fetchAudioUrls: fetch,
                playbackController: controller,
                onSeekFunctionReady: (fn) => harness.seekToSegment = fn,
              ),
            ],
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  return harness;
}

/// Artifact seconds of every recorded `seek:<pos>:<index>` call — mapper
/// output is fractional, so assert with [closeTo], never string equality.
List<double> _seekArtifacts(List<String> calls) => [
      for (final c in calls)
        if (c.startsWith('seek:')) double.parse(c.substring(5, c.indexOf(':', 5))),
    ];

double _topOf(WidgetTester tester, Key key) => tester.getTopLeft(find.byKey(key)).dy;

double _viewportHeight(WidgetTester tester) => tester.getSize(find.byType(ListView)).height;

/// The rendered segment whose row top is closest to (but at or above) the
/// viewport's top edge — the same "top visible line" the transcript reports.
TranscriptSegment? _topVisibleSegment(WidgetTester tester, List<TranscriptSegment> segments) {
  final listTop = tester.getTopLeft(find.byType(ListView)).dy;
  final viewport = _viewportHeight(tester);
  TranscriptSegment? best;
  var bestTop = double.infinity;
  for (final seg in segments) {
    final f = find.byKey(ValueKey('transcript_seek_${seg.id}'));
    if (f.evaluate().isEmpty) continue;
    final rect = tester.getRect(f);
    if (rect.bottom - listTop <= 0 || rect.top - listTop >= viewport) continue;
    final top = rect.top - listTop;
    if (top < bestTop) {
      bestTop = top;
      best = seg;
    }
  }
  return best;
}

/// Platform-channel replies and event-channel emissions settle on the real
/// async queue, not the fake clock — flush both before asserting.
Future<void> _flushPlatform(WidgetTester tester, [int rounds = 6]) async {
  for (var i = 0; i < rounds; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pump();
  }
}

/// just_audio's position stream keeps a 150 ms periodic timer until the player
/// is disposed; unmount and let the next tick cancel it.
Future<void> _removeDetail(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump(const Duration(milliseconds: 200));
}

Finder _currentFill(Finder scope) => find.ancestor(
      of: scope,
      matching: find.byWidgetPredicate(
        (widget) =>
            widget is DecoratedBox &&
            widget.decoration is BoxDecoration &&
            (widget.decoration as BoxDecoration).color == OmiColors.surface2 &&
            (widget.decoration as BoxDecoration).borderRadius == OmiRadius.smAll,
      ),
    );

ServerConversation _snapshotConversation({required double audioSeconds, required double transcriptEnd}) =>
    _conversation(
      segments: [for (var end = 10.0; end <= transcriptEnd; end += 10) _segment('s${end.toInt()}', end - 10, end)],
      audioFiles: [_file('a', duration: audioSeconds, startsAfterSeconds: 0)],
    );

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    Env.init(_UrlsEnv());
  });

  testWidgets('audio still loading after ~600ms shows Preparing Audio inline', (tester) async {
    var fetches = 0;
    await _pumpDetail(
      tester,
      _conversation(segments: [_segment('s1', 0, 5)]),
      fetch: (_) async {
        fetches++;
        if (fetches == 1) {
          return ApiSuccess(AudioUrlsResponse(files: [_url('a', 'pending')], pollAfterMs: 60000));
        }
        // Never resolves: the request's own deadline timeout ends the poll.
        return Completer<ApiResult<AudioUrlsResponse>>().future;
      },
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 700));

    expect(find.textContaining('Preparing Audio'), findsOneWidget);

    // Let the pending poll and the request deadline run out so no timer is
    // left pending when the tree is torn down.
    await tester.pump(const Duration(seconds: 160));
    expect(fetches, 2);
  });

  testWidgets('a failed request leaves an inline error with Try Again, not a toast', (tester) async {
    var fetches = 0;
    await _pumpDetail(
      tester,
      _conversation(segments: [_segment('s1', 0, 5)]),
      fetch: (_) async {
        fetches++;
        return ApiSuccess(AudioUrlsResponse(files: []));
      },
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Audio Unavailable'), findsOneWidget);
    expect(
      find.byKey(const Key('detail_audio_retry')),
      findsOneWidget,
      reason: 'a persistent inline retry pill, not a vanishing SnackBar',
    );
    expect(find.byType(SnackBar), findsNothing, reason: 'audio errors are inline, not toasts');

    await tester.tap(find.byKey(const Key('detail_audio_retry')));
    await tester.pump();
    await tester.pump();
    expect(fetches, 2, reason: 'Try Again re-runs the whole resolve');
  });

  testWidgets('a transport failure reads Check Connection; a successful empty reads Audio Unavailable', (tester) async {
    var sends = 0;
    await _pumpDetail(
      tester,
      _conversation(segments: [_segment('s1', 0, 5)]),
      fetch: (id) => getConversationAudioSignedUrls(
        id,
        send: (_) async {
          sends++;
          if (sends == 1) throw const SocketException('unreachable');
          return http.Response('{"audio_files": [{"id": "b", "status": "unavailable"}]}', 200);
        },
      ),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Check Connection'), findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);
    expect(find.byKey(const Key('detail_audio_retry')), findsOneWidget);

    await tester.tap(find.byKey(const Key('detail_audio_retry')));
    await tester.pump();
    await tester.pump();
    expect(sends, 2);
    expect(find.text('Audio Unavailable'), findsOneWidget);
  });

  testWidgets('playback position marks and follows the current transcript line', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    expect(fake.calls, contains('play'));

    fake.emit(playing: true, positionSec: 35);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 500));

    final marker = find.byKey(const ValueKey('transcript_current_seg3'));
    expect(marker, findsOneWidget);
    expect(
      find.ancestor(
        of: marker,
        matching: find.byWidgetPredicate((w) => w is Semantics && w.properties.selected == true),
      ),
      findsOneWidget,
      reason: 'the current line is announced to assistive tech as selected',
    );
    expect(
      tester
          .widgetList<RichText>(find.descendant(of: marker, matching: find.byType(RichText)))
          .map((r) => r.text.style?.color)
          .where((c) => c == OmiColors.textPrimary),
      isNotEmpty,
      reason: 'the current line renders in primary ink, not the dimmed style',
    );
    final top = _topOf(tester, const ValueKey('transcript_current_seg3'));
    final listTop = tester.getTopLeft(find.byType(ListView)).dy;
    expect(
      top - listTop,
      moreOrLessEquals(_viewportHeight(tester) / 3, epsilon: 2),
      reason: 'the followed line sits one third down the viewport',
    );
    await _removeDetail(tester);
  });

  testWidgets('a waveform scrub before Play stores the point without fetching, then maps on Play', (tester) async {
    final fake = _FakeAudioDevice();
    var fetches = 0;
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async {
        fetches++;
        return ApiSuccess(
          _dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]),
        );
      },
    );

    // Scrub to ~wall 35 (inside seg3) on the 120 s wall track.
    final waveform = find.byKey(const Key('detail_audio_waveform'));
    final box = tester.getRect(waveform);
    await tester.tapAt(Offset(box.left + box.width * (35 / 120), box.center.dy));
    await tester.pump();
    await tester.pumpAndSettle(const Duration(milliseconds: 50));

    expect(fetches, 0, reason: 'a pre-Play scrub answers the gesture without loading audio');
    expect(find.byKey(const ValueKey('transcript_current_seg3')), findsOneWidget);
    final painter = tester.widget<CustomPaint>(find.byKey(const Key('detail_audio_waveform'))).painter as dynamic;
    expect(
      painter.progress,
      moreOrLessEquals(35 / 120, epsilon: 0.01),
      reason: 'the waveform tracks the scrubbed wall point before audio exists',
    );
    final scrubTop =
        _topOf(tester, const ValueKey('transcript_current_seg3')) - tester.getTopLeft(find.byType(ListView)).dy;
    expect(
      scrubTop,
      moreOrLessEquals(_viewportHeight(tester) / 3, epsilon: 2),
      reason: 'a pre-Play scrub still scrolls the target line into the reading zone',
    );

    // An idle reader drag while unloaded only moves the point; still no fetch.
    final scroll = tester.widget<ListView>(find.byType(ListView)).controller!;
    await tester.drag(find.byType(ListView), const Offset(0, -120));
    await tester.pumpAndSettle();
    expect(fetches, 0, reason: 'idle unloaded scrolling never fetches audio');
    final topSeg = _topVisibleSegment(tester, segments)!;
    final painterAfterDrag =
        tester.widget<CustomPaint>(find.byKey(const Key('detail_audio_waveform'))).painter as dynamic;
    expect(painterAfterDrag.progress, moreOrLessEquals(topSeg.start / 120, epsilon: 0.01));
    expect(topSeg.start, greaterThan(0), reason: 'the drag actually moved the read point');
    expect(scroll.offset, isNot(0));

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    await _flushPlatform(tester);

    expect(fetches, 1);
    expect(
      _seekArtifacts(fake.calls).last,
      closeTo(topSeg.start, 0.01),
      reason: 'Play applies the newest reader point, not the earlier scrub',
    );
    await _flushPlatform(tester);
    expect(fake.calls.last, 'play');
    await _removeDetail(tester);
  });

  testWidgets('tapping a transcript line seeks strict and plays on, past the segment end', (tester) async {
    final fake = _FakeAudioDevice();
    var fetches = 0;
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async {
        fetches++;
        return ApiSuccess(
          _dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]),
        );
      },
    );

    await tester.tap(find.byKey(const ValueKey('transcript_seek_seg2')));
    await _flushPlatform(tester);
    await _flushPlatform(tester);

    expect(fetches, 1, reason: 'the tap itself initializes the player');
    expect(_seekArtifacts(fake.calls), contains(closeTo(20, 0.01)));
    await _flushPlatform(tester);
    expect(fake.calls.where((c) => c == 'play'), hasLength(1));
    expect(find.byKey(const ValueKey('transcript_current_seg2')), findsOneWidget);

    // Rolling past the line's end does NOT pause; the next line takes over.
    fake.emit(playing: true, positionSec: 30);
    await _flushPlatform(tester);
    await tester.pump();
    expect(fake.calls, isNot(contains('pause')));
    expect(find.byKey(const ValueKey('transcript_current_seg3')), findsOneWidget);
    await _removeDetail(tester);
  });

  testWidgets('a reader drag during playback suspends follow until Back to Current', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 12; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 2);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 500));

    final scroll = tester.widget<ListView>(find.byType(ListView)).controller!;
    await tester.fling(find.byType(ListView), const Offset(0, -400), 800);
    await tester.pumpAndSettle();
    final offsetAfterDrag = scroll.offset;

    // Playback keeps going, but the reader owns the scroll: two later
    // positions in different segments land without yanking the list back.
    fake.calls.clear();
    fake.emit(playing: true, positionSec: 45);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 600));
    fake.emit(playing: true, positionSec: 105);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 600));

    expect(scroll.offset, offsetAfterDrag);
    expect(fake.calls, isNot(contains('pause')), reason: 'a reader gesture never pauses the playing audio');
    expect(
      fake.calls.where((c) => c.startsWith('seek:')),
      isEmpty,
      reason: 'a playing reader drag does not seek the player either',
    );
    expect(find.byKey(const Key('detail_audio_back_to_current')), findsOneWidget);

    await tester.tap(find.byKey(const Key('detail_audio_back_to_current')));
    await tester.pumpAndSettle();
    final top = _topOf(tester, const ValueKey('transcript_current_seg10'));
    final listTop = tester.getTopLeft(find.byType(ListView)).dy;
    expect(top - listTop, moreOrLessEquals(_viewportHeight(tester) / 3, epsilon: 2));
    await _removeDetail(tester);
  });

  testWidgets('a paused reader drag makes Play start at the new top line', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 12; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 2);
    await _flushPlatform(tester);
    await tester.tap(find.bySemanticsLabel('Pause'));
    await _flushPlatform(tester);

    await tester.drag(find.byType(ListView), const Offset(0, -150));
    await tester.pumpAndSettle();

    // The drag itself already seeked the loaded player to the rendered top
    // line — derive which line that is rather than hardcoding an index.
    final topSeg = _topVisibleSegment(tester, segments)!;
    expect(topSeg.start, greaterThan(0), reason: 'the drag moved the top line off the first row');
    expect(
      _seekArtifacts(fake.calls),
      contains(closeTo(topSeg.start, 0.01)),
      reason: 'a paused reader drag seeks to the actual rendered top line',
    );
    expect(fake.calls.last, isNot('play'));

    fake.calls.clear();
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    await _flushPlatform(tester);

    expect(
      _seekArtifacts(fake.calls),
      isNot(contains(closeTo(2, 0.01))),
      reason: 'Play resumes from the line the reader left, not the paused artifact spot',
    );
    expect(fake.calls.last, 'play');
    await _removeDetail(tester);
  });

  testWidgets('a far target is located by paging and lands at the top third', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [
      for (var i = 0; i < 500; i++)
        _segment('seg$i', i * 2.0, i * 2.0 + 1.5, speakerId: i % 4, text: 'Words for seg$i ' * (i % 12 + 1)),
    ];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 1000)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 800.5); // inside seg400
    await _flushPlatform(tester);
    await tester.pumpAndSettle(const Duration(milliseconds: 16));
    expect(find.byKey(const ValueKey('transcript_current_seg400')), findsOneWidget);
    final top = _topOf(tester, const ValueKey('transcript_current_seg400'));
    final listTop = tester.getTopLeft(find.byType(ListView)).dy;
    expect(
      top - listTop,
      moreOrLessEquals(_viewportHeight(tester) / 3, epsilon: 2),
      reason: 'a variable-height row top lands exactly a third down, not approximately',
    );
    await _removeDetail(tester);
  });

  testWidgets('collapsed gaps keep highlight and waveform on the wall clock', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [
      _segment('seg0', 0, 8),
      _segment('seg1', 30, 38),
      _segment('seg2', 360, 368),
      _segment('seg3', 390, 398),
    ];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async => ApiSuccess(
        _dense(const [
          ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 60),
          ConversationAudioSpan(fileId: 'b', wallOffset: 360, artifactOffset: 60, len: 60),
        ]),
      ),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);

    // Artifact 65 s is five minutes of wall time in — the collapsed gap never
    // existed on the player, but the transcript must still light up correctly.
    fake.emit(playing: true, positionSec: 65);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 600));

    final harness = tester.widget<TranscriptWidget>(find.byType(TranscriptWidget));
    expect(harness.currentSegmentId, 'seg2', reason: 'artifact 65 s maps to wall 365, inside seg2');
    expect(find.byKey(const ValueKey('transcript_current_seg2')), findsOneWidget);

    final painter = tester.widget<CustomPaint>(find.byKey(const Key('detail_audio_waveform'))).painter as dynamic;
    expect(
      painter.progress,
      moreOrLessEquals(365 / 420, epsilon: 0.01),
      reason: 'the waveform advances on the wall clock, not the artifact clock',
    );
    expect(
      (painter.dimRanges as List).cast<(double, double)>(),
      contains((60 / 420, 360 / 420)),
      reason: 'the collapsed five-minute gap renders as a dimmed band',
    );
    await _removeDetail(tester);
  });

  testWidgets('the newest scrub wins while a seek is still initializing', (tester) async {
    final fake = _FakeAudioDevice();
    final release = Completer<ApiResult<AudioUrlsResponse>>();
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) => release.future,
    );

    // Line tap kicks off initialization for a strict play-seek at wall 10;
    // a waveform scrub at wall 40 lands while the fetch is still in flight.
    await tester.tap(find.byKey(const ValueKey('transcript_seek_seg1')));
    await tester.pump();
    final waveform = find.byKey(const Key('detail_audio_waveform'));
    final box = tester.getRect(waveform);
    await tester.tapAt(Offset(box.left + box.width * (40 / 120), box.center.dy));
    await tester.pump();

    release.complete(
      ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );
    await _flushPlatform(tester);
    await _flushPlatform(tester);

    expect(fake.calls.where((c) => c == 'load'), hasLength(1), reason: 'one init for both intents');
    expect(
      _seekArtifacts(fake.calls),
      equals([closeTo(40, 0.01)]),
      reason: 'only the newest wall point is applied — the stale line tap never seeks',
    );
    await _flushPlatform(tester);
    expect(fake.calls.last, 'play', reason: 'the line tap still asked for playback');
    await _removeDetail(tester);
  });

  testWidgets('a reader drag cancels a locate in flight', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 500; i++) _segment('seg$i', i * 2.0, i * 2.0 + 1.5, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 1000)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 802);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 100)); // the locate is paging

    await tester.fling(find.byType(ListView), const Offset(0, 300), 800);
    await tester.pumpAndSettle(const Duration(seconds: 3));

    expect(
      find.byKey(const ValueKey('transcript_current_seg401')),
      findsNothing,
      reason: 'the cancelled locate never re-grabs the scroll to finish',
    );
    await _removeDetail(tester);
  });

  testWidgets('a paused reader drag replaces the resume point with the new top line start', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 12; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 23); // inside seg2 (20..28)
    await _flushPlatform(tester);
    await tester.tap(find.bySemanticsLabel('Pause'));
    await _flushPlatform(tester);
    fake.calls.clear();

    // A drag that reports a new top line snaps the paused point to that
    // line's start, not the artifact spot (23) it paused inside.
    await tester.drag(find.byType(ListView), const Offset(0, 25));
    await tester.pumpAndSettle();
    final topSeg = _topVisibleSegment(tester, segments)!;
    expect(
      _seekArtifacts(fake.calls),
      contains(closeTo(topSeg.start, 0.01)),
      reason: 'a reader gesture snaps the read point to the top line start',
    );

    fake.calls.clear();
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    await _flushPlatform(tester);
    expect(
      _seekArtifacts(fake.calls),
      isNot(contains(closeTo(23, 0.01))),
      reason: 'Play never resumes the stale in-line artifact position',
    );
    expect(fake.calls.last, 'play');
    await _removeDetail(tester);
  });

  testWidgets('remounting the bar keeps the wall point and Play resumes there', (tester) async {
    final fake = _FakeAudioDevice();
    final controller = ConversationPlaybackController();
    addTearDown(controller.dispose);
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    final conversation = _conversation(segments: segments);
    fetch(id) async =>
        ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]));

    await _pumpDetail(tester, conversation, fake: fake, fetch: fetch, controllerParam: controller);
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 35);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byKey(const ValueKey('transcript_current_seg3')), findsOneWidget);

    // Detach: the destroyed player must not leave stale loaded/playing state.
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    expect(controller.isLoaded, isFalse);
    expect(controller.isPlaying, isFalse);

    // Remount the same page-owned controller: Play resumes wall 35, not 0.
    await _pumpDetail(tester, conversation, fake: fake, fetch: fetch, controllerParam: controller);
    await tester.pump();
    fake.calls.clear();
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    await _flushPlatform(tester);
    expect(
      _seekArtifacts(fake.calls),
      contains(closeTo(35, 0.01)),
      reason: 'the detached bar preserved the wall point the player left',
    );
    expect(fake.calls.last, 'play');
    await _removeDetail(tester);
  });

  testWidgets('a completed stream presents Play and restarts from the beginning', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    final harness = await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, processingState: 4, positionSec: 120);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      harness.controller.isPlaying,
      isFalse,
      reason: 'just_audio keeps playing:true at completed — the controller must not',
    );
    expect(
      find.bySemanticsLabel('Play'),
      findsOneWidget,
      reason: 'the button reads Play at the end of the track, not Pause',
    );

    fake.calls.clear();
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    await _flushPlatform(tester);
    expect(
      _seekArtifacts(fake.calls),
      contains(closeTo(0, 0.01)),
      reason: 'restarting a completed track rewinds to the beginning',
    );
    expect(fake.calls.last, 'play');
    await _removeDetail(tester);
  });

  testWidgets('teardown during a pending poll leaves no stale timers or reports', (tester) async {
    final fake = _FakeAudioDevice();
    await _pumpDetail(
      tester,
      _conversation(segments: [_segment('s1', 0, 5)]),
      fake: fake,
      fetch: (_) => Completer<ApiResult<AudioUrlsResponse>>().future, // never resolves
    );
    await tester.tap(find.bySemanticsLabel('Play'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 700));
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();

    var fetches = 0;
    await _pumpDetail(
      tester,
      _conversation(segments: [_segment('s1', 0, 5)]),
      fake: fake,
      fetch: (_) async {
        fetches++;
        return ApiSuccess(AudioUrlsResponse(files: [_url('a', 'pending')], pollAfterMs: 60000));
      },
    );
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    expect(fetches, 1);
    // Teardown mid-delay: a leaked 60 s poll timer would still be pending at
    // test end and fail the harness — nothing here may flush it.
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    expect(fetches, 1, reason: 'the cancelled load must not keep polling');
  });

  testWidgets("a failed seek surfaces Couldn't Load Audio with Try Again", (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.calls.clear();
    fake.failSeeks = true;

    await tester.tap(find.byKey(const ValueKey('transcript_seek_seg2')));
    await _flushPlatform(tester);
    await _flushPlatform(tester);

    expect(find.text("Couldn't Load Audio"), findsOneWidget);
    expect(find.byKey(const Key('detail_audio_retry')), findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);
    expect(fake.calls.where((c) => c == 'play'), isEmpty, reason: 'playback must not start on a failed seek');
    await _removeDetail(tester);
  });

  testWidgets('a line tap after the track completed really plays from the tapped line', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, processingState: 4, positionSec: 120);
    await _flushPlatform(tester);
    fake.calls.clear();

    await tester.ensureVisible(find.byKey(const ValueKey('transcript_seek_seg2')));
    await tester.pumpAndSettle(const Duration(milliseconds: 50));
    fake.calls.clear();
    await tester.tap(find.byKey(const ValueKey('transcript_seek_seg2')));
    await _flushPlatform(tester);
    await _flushPlatform(tester);

    expect(_seekArtifacts(fake.calls), contains(closeTo(20, 0.01)));
    expect(
      fake.calls.last,
      'play',
      reason: 'the completed player\'s stale playing flag must not swallow the play request',
    );
    await _removeDetail(tester);
  });

  testWidgets('a missing part inside the span renders as a dimmed waveform range', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [
      _segment('seg0', 0, 8),
      _segment('seg1', 30, 38),
      _segment('seg2', 360, 368),
      _segment('seg3', 390, 398),
    ];
    await _pumpDetail(
      tester,
      _conversation(
        segments: segments,
        audioFiles: [
          _file('a', duration: 60, startsAfterSeconds: 0),
          _file('b', duration: 60, startsAfterSeconds: 360),
        ],
      ),
      fake: fake,
      fetch: (_) async => ApiSuccess(
        AudioUrlsResponse(files: [_url('a', 'cached', duration: 60), _url('b', 'unavailable', duration: 60)]),
      ),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    expect(fake.calls, contains('play'), reason: 'the cached part still plays');

    fake.emit(playing: true, positionSec: 32);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byKey(const ValueKey('transcript_current_seg1')), findsOneWidget);

    final painter = tester.widget<CustomPaint>(find.byKey(const Key('detail_audio_waveform'))).painter as dynamic;
    expect(
      (painter.dimRanges as List).cast<(double, double)>(),
      contains((360 / 420, 1.0)),
      reason: 'the unavailable part renders dimmed at its wall position',
    );
    expect(find.byType(SnackBar), findsNothing);
    await _removeDetail(tester);
  });

  testWidgets('audio without timestamps plays without inventing a transcript clock', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [for (var i = 0; i < 6; i++) _segment('seg$i', i * 10.0, i * 10.0 + 8, speakerId: i % 2)];
    final harness = await _pumpDetail(
      tester,
      _conversation(segments: segments, audioFiles: [_file('a', duration: 60)]),
      fake: fake,
      fetch: (_) async => ApiSuccess(AudioUrlsResponse(files: [_url('a', 'cached', duration: 60)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    expect(fake.calls, contains('play'), reason: 'unmapped audio still plays');

    fake.emit(playing: true, positionSec: 30);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 500));

    expect(
      harness.controller.currentSegmentId,
      isNull,
      reason: 'no mapper means no line can honestly claim the position',
    );
    expect(find.byKey(const ValueKey('transcript_current_seg3')), findsNothing);
    final painter = tester.widget<CustomPaint>(find.byKey(const Key('detail_audio_waveform'))).painter as dynamic;
    expect(painter.progress, 0, reason: 'the waveform must not imply speech is aligned to the heard audio');
    await _removeDetail(tester);
  });

  testWidgets('a same-id refresh expands the rendered remaining time before Play', (tester) async {
    final fake = _FakeAudioDevice();
    var fetches = 0;
    fetch(id) async {
      fetches++;
      return ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]));
    }

    final harness = await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 10, transcriptEnd: 10),
      fake: fake,
      fetch: fetch,
    );
    expect(find.text('-0:10'), findsOneWidget);

    await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 120, transcriptEnd: 120),
      fetch: fetch,
      controllerParam: harness.controller,
    );
    await tester.pump();

    expect(
      find.text('-2:00'),
      findsOneWidget,
      reason: 'the refreshed snapshot re-derives the cached duration for the same id',
    );
    expect(fetches, 0, reason: 'metadata alone never fetches playback URLs');
    await _removeDetail(tester);
  });

  testWidgets('a same-id refresh moves the waveform midpoint to the new wall end', (tester) async {
    final fake = _FakeAudioDevice();
    var fetches = 0;
    fetch(id) async {
      fetches++;
      return ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]));
    }

    final harness = await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 10, transcriptEnd: 10),
      fake: fake,
      fetch: fetch,
    );
    await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 120, transcriptEnd: 120),
      fetch: fetch,
      controllerParam: harness.controller,
    );
    await tester.pump();

    final box = tester.getRect(find.byKey(const Key('detail_audio_waveform')));
    await tester.tapAt(Offset(box.left + box.width / 2, box.center.dy));
    await tester.pump();

    expect(
      harness.controller.wallPosition.value,
      closeTo(60, 0.5),
      reason: 'the tap lands on the refreshed wall timeline',
    );
    expect(harness.controller.pendingWallSeconds, closeTo(60, 0.5));
    final painter = tester.widget<CustomPaint>(find.byKey(const Key('detail_audio_waveform'))).painter as dynamic;
    expect(painter.progress, moreOrLessEquals(0.5, epsilon: 0.01));
    expect(fetches, 0, reason: 'a pre-Play scrub still answers without loading audio');
    await _removeDetail(tester);
  });

  testWidgets('consecutive owner lines carry a migrating current fill', (tester) async {
    final previousPalette = OmiColors.active;
    addTearDown(() => OmiColors.active = previousPalette);
    for (final palette in [OmiPalette.dark, OmiPalette.light]) {
      OmiColors.active = palette;
      final fake = _FakeAudioDevice();
      final segments = [
        _segment('s0', 0, 8, isUser: true, speakerId: 1),
        _segment('s1', 10, 18, isUser: true, speakerId: 1),
        _segment('s2', 20, 28, speakerId: 2),
      ];
      await _pumpDetail(
        tester,
        _conversation(segments: segments),
        fake: fake,
        fetch: (_) async =>
            ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
      );

      await tester.tap(find.bySemanticsLabel('Play'));
      await _flushPlatform(tester);
      fake.emit(playing: true, positionSec: 5);
      await _flushPlatform(tester);
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byKey(const ValueKey('transcript_current_s0')), findsOneWidget);
      expect(
        _currentFill(find.byKey(const ValueKey('transcript_seek_s0'))),
        findsOneWidget,
        reason: 'the playing owner line paints its own background (${palette == OmiPalette.dark ? 'dark' : 'light'})',
      );
      expect(
        _currentFill(find.byKey(const ValueKey('transcript_seek_s1'))),
        findsNothing,
        reason: 'the adjacent inactive owner line keeps no fill',
      );
      expect(_currentFill(find.byKey(const ValueKey('transcript_seek_s2'))), findsNothing);

      fake.emit(playing: true, positionSec: 15);
      await _flushPlatform(tester);
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byKey(const ValueKey('transcript_current_s1')), findsOneWidget);
      expect(
        _currentFill(find.byKey(const ValueKey('transcript_seek_s1'))),
        findsOneWidget,
        reason: 'the fill migrates to the newly current owner line',
      );
      expect(
        _currentFill(find.byKey(const ValueKey('transcript_seek_s0'))),
        findsNothing,
        reason: 'the previous owner line clears its fill',
      );
      expect(
        find.ancestor(
          of: find.byKey(const ValueKey('transcript_current_s1')),
          matching: find.byWidgetPredicate((w) => w is Semantics && w.properties.selected == true),
        ),
        findsOneWidget,
        reason: 'the selected announcement survives the fill',
      );
      await _removeDetail(tester);
    }
  });

  testWidgets('consecutive non-owner lines carry a migrating current fill', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [
      _segment('s0', 0, 8, speakerId: 2),
      _segment('s1', 10, 18, speakerId: 2),
      _segment('s2', 20, 28, isUser: true, speakerId: 1),
    ];
    await _pumpDetail(
      tester,
      _conversation(segments: segments),
      fake: fake,
      fetch: (_) async =>
          ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)])),
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 5);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byKey(const ValueKey('transcript_current_s0')), findsOneWidget);
    expect(
      _currentFill(find.byKey(const ValueKey('transcript_seek_s0'))),
      findsOneWidget,
      reason: 'the playing non-owner line paints its own background',
    );
    expect(
      _currentFill(find.byKey(const ValueKey('transcript_seek_s1'))),
      findsNothing,
      reason: 'the adjacent inactive line keeps no fill',
    );

    fake.emit(playing: true, positionSec: 15);
    await _flushPlatform(tester);
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byKey(const ValueKey('transcript_current_s1')), findsOneWidget);
    expect(
      _currentFill(find.byKey(const ValueKey('transcript_seek_s1'))),
      findsOneWidget,
      reason: 'the fill migrates between same-speaker non-owner lines',
    );
    expect(_currentFill(find.byKey(const ValueKey('transcript_seek_s0'))), findsNothing);
    await _removeDetail(tester);
  });

  testWidgets('a same-id audio source change unloads; the next Play resolves anew and resumes', (tester) async {
    final fake = _FakeAudioDevice();
    var fetches = 0;
    fetch10(id) async {
      fetches++;
      return ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 10)]));
    }

    fetch120(id) async {
      fetches++;
      return ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]));
    }

    final harness = await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 10, transcriptEnd: 10),
      fake: fake,
      fetch: fetch10,
    );
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 4);
    await _flushPlatform(tester);
    expect(harness.controller.isPlaying, isTrue);

    await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 120, transcriptEnd: 120),
      fetch: fetch120,
      controllerParam: harness.controller,
    );
    await tester.pump();
    await tester.pump();

    expect(harness.controller.isLoaded, isFalse, reason: 'the plan built on old sources is discarded');
    expect(harness.controller.isPlaying, isFalse);
    expect(find.bySemanticsLabel('Play'), findsOneWidget, reason: 'no automatic resume on a source change');
    expect(fake.calls.where((c) => c == 'load'), hasLength(1));
    expect(fetches, 1);

    fake.calls.clear();
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    await _flushPlatform(tester);

    expect(fetches, 2, reason: 'Play re-resolves the new sources');
    expect(fake.calls.where((c) => c == 'load'), hasLength(1));
    expect(
      _seekArtifacts(fake.calls),
      contains(closeTo(4, 0.01)),
      reason: 'the preserved wall point resumes through the new mapping',
    );
    expect(fake.calls.last, 'play');
    await _removeDetail(tester);
  });

  testWidgets('a transcript-only refresh keeps the loaded player and extends the wall end', (tester) async {
    final fake = _FakeAudioDevice();
    var fetches = 0;
    fetch(id) async {
      fetches++;
      return ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 10)]));
    }

    final harness = await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 10, transcriptEnd: 10),
      fake: fake,
      fetch: fetch,
    );
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 4);
    await _flushPlatform(tester);
    fake.calls.clear();

    await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 10, transcriptEnd: 120),
      fetch: fetch,
      controllerParam: harness.controller,
    );
    await tester.pump();

    expect(harness.controller.isLoaded, isTrue);
    expect(harness.controller.isPlaying, isTrue);
    expect(fake.calls, isEmpty, reason: 'a transcript refresh issues no native load/pause/seek');
    expect(fetches, 1);

    final box = tester.getRect(find.byKey(const Key('detail_audio_waveform')));
    await tester.tapAt(Offset(box.left + box.width / 2, box.center.dy));
    await _flushPlatform(tester);
    expect(
      fake.calls.where((c) => c == 'load' || c == 'pause' || c == 'play'),
      isEmpty,
      reason: 'a scrub seeks but never reloads or restarts playback',
    );
    expect(
      _seekArtifacts(fake.calls),
      contains(closeTo(10, 0.01)),
      reason: 'midpoint of the refreshed 120 s wall snaps to the span end — the stale 10 s wall would seek 5',
    );
    final painter = tester.widget<CustomPaint>(find.byKey(const Key('detail_audio_waveform'))).painter as dynamic;
    expect(
      painter.progress,
      moreOrLessEquals(10 / 120, epsilon: 0.01),
      reason: 'the snapped playhead paints on the refreshed 120 s wall',
    );
    await _removeDetail(tester);
  });

  testWidgets('a value-equivalent audio refresh preserves the loaded partial playlist plan', (tester) async {
    final fake = _FakeAudioDevice();
    final segments = [
      _segment('seg0', 0, 8),
      _segment('seg1', 30, 38),
      _segment('seg2', 360, 368),
      _segment('seg3', 390, 398),
    ];
    urls() => ApiSuccess(
          AudioUrlsResponse(files: [_url('a', 'cached', duration: 60), _url('b', 'unavailable', duration: 60)]),
        );
    final harness = await _pumpDetail(
      tester,
      _conversation(
        segments: segments,
        audioFiles: [
          _file('a', duration: 60, startsAfterSeconds: 0),
          _file('b', duration: 60, startsAfterSeconds: 360),
        ],
      ),
      fake: fake,
      fetch: (_) async => urls(),
    );
    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    fake.emit(playing: true, positionSec: 30);
    await _flushPlatform(tester);
    await tester.pump();

    expect(find.text('-0:30'), findsOneWidget);
    fake.calls.clear();

    await _pumpDetail(
      tester,
      _conversation(
        segments: List.of(segments),
        audioFiles: [
          _file('a', duration: 60, startsAfterSeconds: 0),
          _file('b', duration: 60, startsAfterSeconds: 360),
        ],
      ),
      fetch: (_) async => urls(),
      controllerParam: harness.controller,
    );
    await tester.pump();

    expect(harness.controller.isLoaded, isTrue, reason: 'identical sources never invalidate the player');
    expect(harness.controller.isPlaying, isTrue);
    expect(
      find.text('-0:30'),
      findsOneWidget,
      reason: 'the adopted plan duration and part offsets are not clobbered by metadata',
    );
    expect(fake.calls.where((c) => c == 'load' || c == 'pause' || c == 'seek'), isEmpty);
    await _removeDetail(tester);
  });

  testWidgets('an in-flight load for superseded sources is rejected', (tester) async {
    final fake = _FakeAudioDevice();
    final release = Completer<ApiResult<AudioUrlsResponse>>();
    var fetches = 0;
    final harness = await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 10, transcriptEnd: 10),
      fake: fake,
      fetch: (_) {
        fetches++;
        return release.future;
      },
    );

    await tester.tap(find.bySemanticsLabel('Play'));
    await tester.pump();
    expect(fetches, 1);

    await _pumpDetail(
      tester,
      _snapshotConversation(audioSeconds: 120, transcriptEnd: 120),
      fetch: (_) async {
        fetches++;
        return ApiSuccess(
          _dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]),
        );
      },
      controllerParam: harness.controller,
    );
    await tester.pump();

    release.complete(
      ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 10)])),
    );
    await _flushPlatform(tester);

    expect(
      fake.calls.where((c) => c == 'load'),
      isEmpty,
      reason: 'the stale answer never loads a player for superseded sources',
    );
    expect(harness.controller.isLoaded, isFalse);
    expect(find.bySemanticsLabel('Play'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('Play'));
    await _flushPlatform(tester);
    await _flushPlatform(tester);
    expect(fetches, 2);
    expect(fake.calls.where((c) => c == 'load'), hasLength(1));
    expect(fake.calls.last, 'play');
    await _removeDetail(tester);
  });

  testWidgets('an in-place audio list mutation is detected on refresh', (tester) async {
    final fake = _FakeAudioDevice();
    var fetches = 0;
    fetch(id) async {
      fetches++;
      return ApiSuccess(_dense([const ConversationAudioSpan(fileId: 'a', wallOffset: 0, artifactOffset: 0, len: 120)]));
    }

    final files = [_file('a', duration: 10, startsAfterSeconds: 0)];
    final conversation = _conversation(segments: [_segment('s0', 0, 10)], audioFiles: files);
    final harness = await _pumpDetail(tester, conversation, fake: fake, fetch: fetch);
    expect(find.text('-0:10'), findsOneWidget);

    files.add(_file('b', duration: 110, startsAfterSeconds: 10));
    await _pumpDetail(tester, conversation, fetch: fetch, controllerParam: harness.controller);
    await tester.pump();

    expect(find.text('-2:00'), findsOneWidget, reason: 'mutating the list in place must still read as a new snapshot');
    expect(fetches, 0);
    await _removeDetail(tester);
  });
}

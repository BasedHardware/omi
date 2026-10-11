import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/audio/audio_timeline_mapper.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

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

/// Stands in for just_audio's native player: every player starts, and loading a source fails the
/// way AVPlayer reports an expired or refused URL (AVFoundationErrorDomain -11800).
void _fakeAudioPlatformThatCannotLoad(WidgetTester tester) {
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(const MethodChannel('com.ryanheise.just_audio.methods'), (call) async {
    if (call.method != 'init') return <String, dynamic>{};
    final id = (call.arguments as Map)['id'] as String;
    messenger.setMockMethodCallHandler(MethodChannel('com.ryanheise.just_audio.methods.$id'), (call) async {
      if (call.method == 'load')
        throw PlatformException(code: '-11800', message: 'The operation could not be completed');
      return <String, dynamic>{};
    });
    for (final stream in ['events', 'data']) {
      messenger.setMockStreamHandler(
        EventChannel('com.ryanheise.just_audio.$stream.$id'),
        MockStreamHandler.inline(onListen: (_, __) {}),
      );
    }
    return null;
  });
}

void main() {
  group('playback plan', () {
    test('the dense conversation MP3 wins when it is ready, whatever the parts say', () {
      final plan = ConversationPlaybackPlan.resolve(
        AudioUrlsResponse(
          files: [_url('a', 'pending')],
          conversationAudio: ConversationAudioUrlInfo(
            status: 'cached',
            signedUrl: 'https://audio.test/conversation.mp3',
            spans: const [ConversationAudioSpan(fileId: 'a', wallOffset: 5, artifactOffset: 0, len: 90)],
          ),
        ),
        [_file('a')],
        conversationStart: _start,
      );
      expect(plan.failure, isNull);
      expect(plan.singleUrl, 'https://audio.test/conversation.mp3');
      expect(plan.duration, const Duration(seconds: 90));
      expect(plan.mapper!.wallToArtifactStrict(10), 5);
    });

    test('a dense MP3 without spans falls back to the parts', () {
      final plan = ConversationPlaybackPlan.resolve(
        AudioUrlsResponse(
          files: [_url('a', 'cached')],
          conversationAudio: ConversationAudioUrlInfo(status: 'cached', signedUrl: 'https://audio.test/c.mp3'),
        ),
        [_file('a')],
      );
      expect(plan.singleUrl, isNull);
      expect(plan.parts.single.url, 'https://audio.test/a.mp3');
    });

    test('parts play in recording order and only the playable ones count toward offsets and length', () {
      final plan = ConversationPlaybackPlan.resolve(
        AudioUrlsResponse(files: [_url('late', 'cached'), _url('gone', 'unavailable'), _url('early', 'cached')]),
        [
          _file('late', duration: 40, startsAfterSeconds: 300),
          _file('gone', duration: 100, startsAfterSeconds: 120),
          _file('early', duration: 60, startsAfterSeconds: 0),
        ],
        conversationStart: _start,
      );
      expect(plan.failure, isNull);
      expect(plan.parts.map((part) => part.url), ['https://audio.test/early.mp3', 'https://audio.test/late.mp3']);
      expect(plan.partOffsets, [Duration.zero, const Duration(seconds: 60)]);
      expect(plan.duration, const Duration(seconds: 100), reason: 'the unavailable 100 s part is not heard');
    });

    test('transcript taps map onto a part playlist through each part’s start time', () {
      final plan = ConversationPlaybackPlan.resolve(
        AudioUrlsResponse(files: [_url('a', 'cached'), _url('b', 'cached')]),
        [_file('a', duration: 60, startsAfterSeconds: 0), _file('b', duration: 30, startsAfterSeconds: 600)],
        conversationStart: _start,
      );
      final mapper = plan.mapper!;
      expect(mapper.wallToArtifactStrict(15), 15, reason: '15 s into the first part');
      expect(mapper.wallToArtifactStrict(610), 70, reason: '10 s into the second part, which starts at 60 s');
      expect(mapper.wallToArtifactStrict(300), isNull, reason: 'nothing was recorded between the parts');
    });

    test('parts without start times still play, but transcript taps cannot be placed', () {
      final plan = ConversationPlaybackPlan.resolve(
          AudioUrlsResponse(files: [_url('a', 'cached')]),
          [
            _file('a'),
          ],
          conversationStart: _start);
      expect(plan.parts, hasLength(1));
      expect(plan.mapper, isNull);
    });

    test('a part with no recorded length takes the URL’s length', () {
      final plan = ConversationPlaybackPlan.resolve(
          AudioUrlsResponse(files: [_url('a', 'cached', duration: 42)]),
          [
            _file('a', duration: 0, startsAfterSeconds: 0),
          ],
          conversationStart: _start);
      expect(plan.duration, const Duration(seconds: 42));
    });

    test('no files means the request failed, was refused or there is no audio', () {
      final plan = ConversationPlaybackPlan.resolve(AudioUrlsResponse(files: []), [_file('a')]);
      expect(plan.failure, ConversationPlaybackPlan.noAudioFiles);
    });

    test('files that are all gone or still pending leave nothing to play', () {
      for (final status in ['unavailable', 'pending']) {
        final plan = ConversationPlaybackPlan.resolve(AudioUrlsResponse(files: [_url('a', status)]), [_file('a')]);
        expect(plan.failure, ConversationPlaybackPlan.noPlayableParts, reason: status);
      }
    });
  });

  group('play button', () {
    setUp(PlatformManager.initializeForLocalHarness);

    Future<ConversationDetailProvider> pumpBar(
      WidgetTester tester,
      Future<ApiResult<AudioUrlsResponse>> Function(String) fetch,
    ) async {
      final conversation = ServerConversation(
        id: 'conv-audio',
        createdAt: _start,
        startedAt: _start,
        structured: Structured('A call', ''),
        audioFiles: [_file('a', duration: 120, startsAfterSeconds: 0)],
      );
      final provider = ConversationDetailProvider()
        ..selectedDate = conversationLocalDayKey(conversation.createdAt)
        ..setCachedConversation(conversation);
      addTearDown(provider.dispose);
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: ChangeNotifierProvider<ConversationDetailProvider>.value(
            value: provider,
            child: Scaffold(
              body: ConversationBottomBar(
                mode: ConversationBottomBarMode.detail,
                selectedTab: ConversationTab.transcript,
                onTabSelected: (_) {},
                onStopPressed: () {},
                conversation: conversation,
                fetchAudioUrls: fetch,
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      return provider;
    }

    testWidgets('a refused or failed request says so at once instead of spinning, and the next tap retries', (
      tester,
    ) async {
      var fetches = 0;
      await pumpBar(tester, (_) async {
        fetches++;
        return ApiSuccess(AudioUrlsResponse(files: []));
      });

      await tester.tap(find.bySemanticsLabel('Play'));
      await tester.pump();
      await tester.pump();
      expect(fetches, 1, reason: 'no polling when there is nothing to wait for');
      expect(find.text('Audio Unavailable'), findsOneWidget);
      expect(find.bySemanticsLabel('Play'), findsOneWidget, reason: 'it never claims to be playing');

      await tester.tap(find.bySemanticsLabel('Play'));
      await tester.pump();
      expect(fetches, 2);
    });

    testWidgets('audio that is gone reads as unavailable', (tester) async {
      await pumpBar(tester, (_) async => ApiSuccess(AudioUrlsResponse(files: [_url('a', 'unavailable')])));

      await tester.tap(find.bySemanticsLabel('Play'));
      await tester.pump();
      await tester.pump();
      expect(find.text('Audio Unavailable'), findsOneWidget);
      expect(find.bySemanticsLabel('Play'), findsOneWidget);
    });

    testWidgets('waits while the audio is built, then reports a file that will not load and leaves Play', (
      tester,
    ) async {
      final responses = [
        AudioUrlsResponse(files: [_url('a', 'pending')], pollAfterMs: 10),
        AudioUrlsResponse(files: [_url('a', 'cached')]),
      ];
      var fetches = 0;
      _fakeAudioPlatformThatCannotLoad(tester);
      await pumpBar(tester, (_) async => ApiSuccess(responses[(fetches++).clamp(0, 1)]));

      await tester.tap(find.bySemanticsLabel('Play'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 20)); // the poll interval the backend asked for
      // just_audio settles a failed load through real platform-channel replies.
      for (var i = 0; i < 10 && find.byKey(const Key('detail_audio_retry')).evaluate().isEmpty; i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(fetches, 2, reason: 'polled once more while the part was pending');
      expect(find.text("Couldn't Load Audio"), findsOneWidget);
      expect(find.bySemanticsLabel('Play'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}

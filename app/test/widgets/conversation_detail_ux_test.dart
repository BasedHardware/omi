import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/capture_state_header.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversation_detail/widgets.dart' show conversationDurationLabel;
import 'package:omi/pages/conversation_detail/widgets/audio_download_progress_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/calendar_event_sheets.dart';
import 'package:omi/pages/conversation_detail/widgets/detail_search_bar.dart';
import 'package:omi/pages/conversation_detail/widgets/edit_segment_sheet.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/widgets/transcript.dart';

Widget _app(Widget home) {
  return MaterialApp(
    locale: const Locale('en'),
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: home,
  );
}

TranscriptSegment _segment(String id, {int speaker = 1, bool isUser = false, double start = 0, String? stt}) {
  return TranscriptSegment(
    id: id,
    text: 'Line $id',
    speaker: 'SPEAKER_0$speaker',
    isUser: isUser,
    personId: null,
    start: start,
    end: start + 1,
    translations: [],
    sttProvider: stt,
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('attendee names (hub #18)', () {
    test('an address shows its whole local part, a display name shows in full', () {
      expect(formatAttendeeName('john.doe@example.com'), 'john.doe');
      expect(formatAttendeeName('Ann Marie Lee'), 'Ann Marie Lee');
    });

    test('the label shows two names and counts the rest', () {
      expect(formatAttendeesLabel(['Ann Lee', 'bo@x.com', 'c@x.com', 'd@x.com']), 'Ann Lee, bo +2');
      expect(formatAttendeesLabel(['Ann Lee']), 'Ann Lee');
      expect(formatAttendeesLabel(const []), '');
    });
  });

  test('detail duration uses the list rule and the compact format (hub #15)', () {
    final conversation = ServerConversation(
      id: 'c',
      createdAt: DateTime(2026, 9, 23),
      structured: Structured('t', 'o'),
      transcriptSegments: [_segment('a', start: 0), _segment('b', start: 753)],
    );
    // Same seconds as the list row (getDurationInSeconds) and the same style (compact).
    expect(conversationDurationLabel(conversation), OmiDuration.compact(conversation.getDurationInSeconds()));
    expect(conversationDurationLabel(conversation), '12m');
  });

  test('getLastTranscript numbers speakers across the whole conversation', () {
    // Speaker 1 appears only before the 50-segment window; the window's speaker is still Speaker 2.
    final segments = [
      _segment('first', speaker: 1),
      for (var i = 0; i < 60; i++) _segment('s$i', speaker: 2, start: i + 1.0),
    ];
    final text = getLastTranscript(segments, includeTimestamps: false);
    expect(text, contains('Speaker 2'));
    expect(text, isNot(contains('Speaker 1:')));
  });

  testWidgets('transcript bubble: no provider name, start offset, labelled 44pt play', (tester) async {
    final segments = [_segment('a', start: 65, stt: 'deepgram')];
    await tester.pumpWidget(
      _app(
        Scaffold(
          body: TranscriptWidget(segments: segments, onSegmentTap: (_) {}, canDisplaySeconds: true),
        ),
      ),
    );
    await tester.pump();

    expect(find.textContaining('Deepgram'), findsNothing);
    expect(find.text('1:05'), findsOneWidget);
    final play = find.byTooltip('Play from here');
    expect(play, findsOneWidget);
    final size = tester.getSize(find.ancestor(of: play, matching: find.byType(OmiIconButton)));
    expect(size.width, greaterThanOrEqualTo(kOmiMinTapTarget));
    expect(size.height, greaterThanOrEqualTo(kOmiMinTapTarget));
  });

  testWidgets('capture state header names the state with the shared labels (hub #25)', (tester) async {
    for (final (state, label) in [
      (CaptureDisplayState.listening, 'Listening'),
      (CaptureDisplayState.paused, 'Paused'),
      (CaptureDisplayState.processing, 'Processing'),
    ]) {
      await tester.pumpWidget(_app(Scaffold(appBar: ConversationStateAppBar(state: state))));
      await tester.pump();
      expect(find.text(label), findsOneWidget);
      expect(find.byType(OmiBackButton), findsOneWidget);
    }
  });

  testWidgets('the transcription-outage sentence wraps in the header instead of clipping', (tester) async {
    // A phone-sized surface: the full sentence cannot fit one title line, so
    // the header must wrap it rather than ellipsize away the promise that
    // recording continues and will be processed later.
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
        _app(const Scaffold(appBar: ConversationStateAppBar(state: CaptureDisplayState.transcriptionUnavailable))));
    await tester.pump();

    final text = tester.widget<Text>(find.textContaining('recording continues on device'));
    expect(text.maxLines, greaterThan(1));
    expect(find.textContaining('will process later'), findsOneWidget);
    expect(tester.getSize(find.byType(ConversationStateAppBar)).height, kToolbarHeight);
  });

  testWidgets('search bar shows the position and disables arrows without results', (tester) async {
    final controller = TextEditingController(text: 'x');
    final focus = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focus.dispose);
    await tester.pumpWidget(
      _app(
        Scaffold(
          body: DetailSearchBar(
            controller: controller,
            focusNode: focus,
            query: 'x',
            currentIndex: 0,
            totalResults: 0,
            onChanged: (_) {},
            onPrevious: () {},
            onNext: () {},
            onCancel: () {},
          ),
        ),
      ),
    );
    expect(find.text('0/0'), findsOneWidget);
    final next = tester.widget<OmiIconButton>(
      find.ancestor(of: find.byTooltip('Next result'), matching: find.byType(OmiIconButton)),
    );
    expect(next.onPressed, isNull);
    expect(find.text('Cancel'), findsOneWidget);
  });

  group('audio download sheet (nav #14)', () {
    Future<(AudioDownloadSheetHandle, NavigatorState)> openOverPage(WidgetTester tester,
        {VoidCallback? onCancel}) async {
      late BuildContext pageContext;
      await tester.pumpWidget(
        _app(
          Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (context) {
                      pageContext = context;
                      return const Scaffold(body: Text('detail page'));
                    },
                  ),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      final handle = AudioDownloadSheetHandle.show(pageContext, onCancel: onCancel);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      return (handle, Navigator.of(pageContext));
    }

    testWidgets('a late close never pops the page underneath', (tester) async {
      final (handle, _) = await openOverPage(tester);
      handle.close();
      await tester.pump(const Duration(milliseconds: 500));
      expect(handle.isOpen, isFalse);
      handle.close();
      handle.close();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text('detail page'), findsOneWidget);
    });

    testWidgets('system back cancels the download and closes only the sheet', (tester) async {
      var cancelled = 0;
      final (handle, navigator) = await openOverPage(tester, onCancel: () => cancelled++);
      await navigator.maybePop();
      await tester.pump(const Duration(milliseconds: 500));
      expect(cancelled, 1);
      expect(handle.cancelled, isTrue);
      expect(find.text('detail page'), findsOneWidget);
    });

    testWidgets('offers Cancel while working', (tester) async {
      var cancelled = 0;
      final (handle, _) = await openOverPage(tester, onCancel: () => cancelled++);
      await tester.tap(find.text('Cancel'));
      await tester.pump(const Duration(milliseconds: 500));
      expect(cancelled, 1);
      expect(handle.isOpen, isFalse);
      expect(find.text('detail page'), findsOneWidget);
    });
  });

  group('edit segment sheet', () {
    Future<void> open(WidgetTester tester) async {
      await tester.pumpWidget(
        _app(
          Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => showEditSegmentBottomSheet(
                  context,
                  segment: _segment('a', isUser: true),
                  speakerName: 'You',
                  onSave: (_) {},
                ),
                child: const Text('edit'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('edit'));
      await tester.pumpAndSettle();
    }

    testWidgets('is titled with the speaker and closes cleanly when unchanged', (tester) async {
      await open(tester);
      expect(find.text('You'), findsOneWidget);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.byType(EditSegmentSheet), findsNothing);
    });

    testWidgets('asks before discarding an edit', (tester) async {
      await open(tester);
      await tester.enterText(find.byType(TextField), 'Changed words');
      await tester.pump();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.text('Keep Editing'), findsOneWidget);
      await tester.tap(find.text('Keep Editing'));
      await tester.pumpAndSettle();
      expect(find.byType(EditSegmentSheet), findsOneWidget);
    });
  });

  testWidgets('media viewer leaves by a trailing close button, never a back arrow (nav #11)', (tester) async {
    await tester.pumpWidget(
      _app(
        Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => MediaViewerPage.open(
                context,
                items: const [MediaViewerItem(imageUrl: 'https://example.invalid/a.png')],
                // A pre-existing caller flag that must not move the X to the leading edge.
              ),
              child: const Text('view'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('view'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byType(OmiCloseButton), findsOneWidget);
    expect(find.byType(BackButton), findsNothing);
    final appBar = tester.widget<AppBar>(find.byType(AppBar));
    expect(appBar.leading, isNull);
    expect(appBar.automaticallyImplyLeading, isFalse);
  });
}

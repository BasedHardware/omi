import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_markdown_widget.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:omi/widgets/conversation_photo_image.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _CountingSegments extends ListBase<TranscriptSegment> {
  _CountingSegments(int count)
      : _items = List.generate(
          count,
          (i) => TranscriptSegment(
            id: 'segment-$i',
            text: 'Line $i',
            speaker: 'SPEAKER_01',
            isUser: false,
            personId: null,
            start: i.toDouble(),
            end: i + 1.0,
            translations: const [],
          ),
        );

  final List<TranscriptSegment> _items;
  int reads = 0;
  @override
  int get length => _items.length;
  @override
  set length(int value) => _items.length = value;
  @override
  TranscriptSegment operator [](int index) {
    reads++;
    return _items[index];
  }

  @override
  void operator []=(int index, TranscriptSegment value) => _items[index] = value;
}

Widget _app(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('inline photo bytes are decoded once per retained photo', () async {
    final photo = ConversationPhoto(id: 'inline', base64: 'AQID', createdAt: DateTime(2026));
    final cache = ConversationPhotoBytesCache();
    final first = await cache.load(photo, 'c');
    var decodes = 1;
    for (var i = 0; i < 20; i++) {
      if (!identical(await cache.load(photo, 'c'), first)) decodes++;
    }
    // ignore: avoid_print
    print('DETAIL_METRIC retained_inline_photo_decodes=$decodes/21');
    expect(decodes, 1);
    final replaced = ConversationPhoto(id: 'inline', base64: 'BAUG', createdAt: DateTime(2026));
    expect(await cache.load(replaced, 'c'), [4, 5, 6]);
  });

  testWidgets('thumbnail requests display-sized image decode', (tester) async {
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetDevicePixelRatio);
    const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
    final photo = ConversationPhoto(id: 'inline', base64: png, createdAt: DateTime(2026));
    await tester.pumpWidget(_app(Center(
      child: SizedBox(width: 120, height: 90, child: ConversationPhotoImage(photo: photo)),
    )));
    await tester.pumpAndSettle();
    final image = tester.widget<Image>(find.byType(Image));
    final provider = image.image;
    final width = provider is ResizeImage ? provider.width : null;
    // ignore: avoid_print
    print('DETAIL_METRIC thumbnail_decode_width=$width logical_width=120 dpr=3');
    expect(width, 360);
  });

  for (final semanticsEnabled in [false, true]) {
    testWidgets('summary reparses on unchanged updates (semantics=$semanticsEnabled)', (tester) async {
      late StateSetter update;
      final content = List.generate(200, (i) => 'Block $i with **important** words.').join('\n\n');
      await tester.pumpWidget(_app(StatefulBuilder(builder: (context, setState) {
        update = setState;
        return CustomScrollView(slivers: [ConversationMarkdownSliver(content: content)]);
      })));
      await tester.pumpAndSettle();

      // flutter_markdown builds a fresh block widget tree whenever it parses.
      // Identity of the first AST block exposes actual reparses, independent
      // of host time, visible row count, and widget rebuild instrumentation.
      Widget firstParsedBlock() {
        final listFinder = find.descendant(
          of: find.byType(ConversationMarkdownSliver),
          matching: find.byType(SliverList),
        );
        final list = tester.widget<SliverList>(listFinder);
        final delegate = list.delegate as SliverChildBuilderDelegate;
        return (delegate.builder(tester.element(listFinder), 0)! as GestureDetector).child!;
      }

      var previous = firstParsedBlock();
      var reparses = 0;
      for (var i = 0; i < 20; i++) {
        update(() {});
        await tester.pump();
        final current = firstParsedBlock();
        if (!identical(current, previous)) reparses++;
        previous = current;
      }
      // ignore: avoid_print
      print('DETAIL_METRIC semantics=$semanticsEnabled unchanged_summary_reparses=$reparses/20 blocks=200');
      expect(find.byType(MarkdownBody), findsNothing);
      expect(reparses, 0);
    }, semanticsEnabled: semanticsEnabled);

    testWidgets('transcript scroll reads only mounted rows (semantics=$semanticsEnabled)', (tester) async {
      final segments = _CountingSegments(1200);
      var visibleReports = 0;
      var rowBuilds = 0;
      await tester.pumpWidget(_app(TranscriptWidget(
        segments: segments,
        isConversationDetail: true,
        scrollState: TranscriptScrollState(),
        onTopVisibleSegmentChanged: (_) => visibleReports++,
        segmentBuilder: (context, segment, index) {
          rowBuilds++;
          return SizedBox(height: 80, child: Text(segment.text));
        },
      )));
      await tester.pumpAndSettle();
      // ignore: avoid_print
      print('DETAIL_METRIC semantics=$semanticsEnabled initial_transcript_rows=$rowBuilds/1200');
      expect(rowBuilds, lessThan(30));
      segments.reads = 0;
      final gesture = await tester.startGesture(tester.getCenter(find.byType(ListView)));
      for (var i = 0; i < 10; i++) {
        await gesture.moveBy(const Offset(0, -12));
        await tester.pump(const Duration(milliseconds: 16));
      }
      final scrollReads = segments.reads;
      await gesture.up();
      await tester.pumpAndSettle();
      // ignore: avoid_print
      print(
          'DETAIL_METRIC semantics=$semanticsEnabled drag_segment_reads=$scrollReads visible_reports=$visibleReports');
      expect(visibleReports, greaterThan(0));
      expect(scrollReads, lessThan(1000), reason: '10 drag frames must not scan the entire 1200-line conversation');
    }, semanticsEnabled: semanticsEnabled);
  }
}

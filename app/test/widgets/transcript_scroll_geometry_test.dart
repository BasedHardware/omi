import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/widgets/transcript.dart';

class _LayoutProbe extends SingleChildRenderObjectWidget {
  const _LayoutProbe({required this.onLayout, required super.child});
  final VoidCallback onLayout;
  @override
  RenderObject createRenderObject(BuildContext context) => _RenderLayoutProbe(onLayout);
}

class _RenderLayoutProbe extends RenderProxyBox {
  _RenderLayoutProbe(this.onLayout);
  final VoidCallback onLayout;
  @override
  void performLayout() {
    onLayout();
    super.performLayout();
  }
}

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  for (final live in [false, true]) {
    testWidgets('${live ? 'live' : 'detail'} scroll geometry stays bounded from 120 to 1200 segments', (tester) async {
      final maxProbeCounts = <int>[];
      final firstLayouts = <int>[];
      for (final count in [120, 1200]) {
        final segments = List.generate(
            count,
            (index) => TranscriptSegment(
                  id: 'row-$index',
                  text: 'Line $index',
                  speaker: 'SPEAKER_00',
                  isUser: true,
                  personId: null,
                  translations: const [],
                  start: index.toDouble(),
                  end: index + 1.0,
                ));
        var probes = 0;
        var reveals = 0;
        var maxReveals = 0;
        var layouts = 0;
        var builds = 0;
        var maxProbes = 0;
        var updates = 0;
        var reports = 0;
        TranscriptSegment? reported;
        final scrollState = TranscriptScrollState();
        late ScrollController controller;
        await tester.pumpWidget(MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
              body: Align(
                  alignment: Alignment.topLeft,
                  child: SizedBox(
                    width: 320,
                    height: 320,
                    child: NotificationListener<ScrollUpdateNotification>(
                      onNotification: (_) {
                        updates++;
                        return false;
                      },
                      child: TranscriptWidget(
                        key: ValueKey('$live-$count'),
                        segments: segments,
                        isConversationDetail: !live,
                        followLatest: live,
                        scrollState: scrollState,
                        bottomMargin: 0,
                        leadingItemIds: const ['photo'],
                        leadingItems: const [SizedBox(height: 73)],
                        onScrollControllerReady: (value) => controller = value,
                        onScrollGeometryProbe: () => probes++,
                        onScrollRevealProbe: () => reveals++,
                        onTopVisibleSegmentChanged: (segment) {
                          reported = segment;
                          reports++;
                        },
                        segmentBuilder: (context, segment, index) {
                          builds++;
                          return _LayoutProbe(
                              onLayout: () => layouts++,
                              child: SizedBox(
                                key: ValueKey('content-${segment.id}'),
                                height: 48 + (index % 3) * 24,
                                child: Text(segment.text),
                              ));
                        },
                      ),
                    ),
                  ))),
        ));
        firstLayouts.add(layouts);
        expect(layouts, lessThan(30), reason: 'Opening lays out only a viewport/cache window');
        expect(builds, lessThan(30));
        expect(find.text('Line ${live ? count - 1 : 0}').hitTestable(), findsOneWidget);
        await tester.pumpAndSettle();
        final scrollable = find.descendant(of: find.byType(TranscriptWidget), matching: find.byType(Scrollable));
        final viewport = tester.getRect(scrollable);
        void checkReport() {
          final visible = segments.where((segment) {
            final row = find.byKey(ValueKey('content-${segment.id}'));
            if (row.evaluate().isEmpty) return false;
            final rect = tester.getRect(row);
            return rect.bottom > viewport.top && rect.top < viewport.bottom;
          }).toList();
          expect(visible, isNotEmpty);
          expect(reported?.id, visible.first.id, reason: 'Report the partially visible content at the top');
          expect(scrollState.anchorSegmentId, visible.first.id);
          expect(scrollState.anchorViewportOffset,
              closeTo(tester.getTopLeft(find.byKey(ValueKey('content-${visible.first.id}'))).dy - viewport.top, 0.01));
        }

        // Count all geometry inspections, including discovery and both capture
        // and report, rather than timing a benchmark or counting callbacks.
        final gesture = await tester.startGesture(viewport.center);
        await gesture.moveBy(Offset(0, live ? 30 : -30));
        await tester.pump(const Duration(milliseconds: 16));
        for (var step = 0; step < 12; step++) {
          probes = 0;
          reveals = 0;
          updates = 0;
          await gesture.moveBy(Offset(0, live ? 25 : -25));
          await tester.pump(const Duration(milliseconds: 16));
          expect(probes, greaterThan(0));
          expect(probes, lessThan(60));
          expect(reveals, inInclusiveRange(1, live ? 8 : 4));
          if (reveals > maxReveals) maxReveals = reveals;
          if (probes > maxProbes) maxProbes = probes;
          checkReport();
        }
        await gesture.up();
        await tester.pumpAndSettle();
        for (var fling = 0; fling < 6; fling++) {
          probes = 0;
          reveals = 0;
          updates = 0;
          await tester.fling(scrollable, Offset(0, live ? 240 : -240), 1500);
          expect(probes, lessThan(60 * (updates + 1)));
          expect(reveals, lessThanOrEqualTo((live ? 8 : 4) * (updates + 1)));
          for (var frame = 0; frame < 40; frame++) {
            probes = 0;
            reveals = 0;
            await tester.pump(const Duration(milliseconds: 16));
            expect(probes, lessThan(60));
            expect(reveals, lessThanOrEqualTo(live ? 8 : 4));
            if (reveals > maxReveals) maxReveals = reveals;
            if (probes > maxProbes) maxProbes = probes;
          }
          await tester.pumpAndSettle();
        }
        expect(reports, greaterThan(6));
        expect(controller.offset.abs(), greaterThan(300));
        maxProbeCounts.add(maxProbes);
        debugPrint(
            'SCROLL_GEOMETRY live=$live segments=$count first_layouts=${firstLayouts.last} max_probes=$maxProbes max_reveals=$maxReveals');
        await tester.pumpWidget(const SizedBox.shrink());
      }
      expect((maxProbeCounts.last - maxProbeCounts.first).abs(), lessThanOrEqualTo(4));
      expect((firstLayouts.last - firstLayouts.first).abs(), lessThanOrEqualTo(4));
    });
  }
}

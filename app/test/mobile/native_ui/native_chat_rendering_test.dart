import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_rich_text.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_tab.dart';

import 'native_test_host.dart';

const _markdown = '## Launch plan\n\n'
    'Read the [allowed guide](https://omi.me/allowed).\n\n'
    '1. Ship the **native** body\n   - Keep the owner\n\n'
    '> Links stay with Dart\n\n'
    '```dart\nfinal owner = "Dart";\n```\n\n'
    '| Owner | Status |\n| --- | --- |\n| Dart | Opens links |';

Map<String, Object> _block(String text) => {'kind': 'text', 'text': text, 'indent': 0, 'prefix': ''};

List<Map<String, Object>> _categories(int count, {String label = 'Day'}) => [
      for (var i = 0; i < count; i++) {'x': i, 'y': i * 2.0, 'label': '$label $i'},
    ];

Future<void> _dispatch(NativeRow row, Object? value) =>
    dispatchNativeAction(MethodCall('action', {'id': row.id, 'value': value}), isActive: () => true, rows: [row]);

void main() {
  group('rich AI message bodies', () {
    test('message_ai accepts the reader blocks of its own Markdown', () {
      final blocks = nativeRichText(_markdown);
      expect(blocks.map((block) => block['kind']), containsAll(['heading', 'text', 'quote', 'code', 'table']));
      final row = NativeRow('reply', 'Launch plan',
          kind: 'message_ai', blocks: blocks, options: nativeRichTextLinks(_markdown), action: (_) {});
      expect(row.valid, true);
      expect(row.projection['blocks'], blocks);
      expect(row.projection['options'], [
        {'id': 'https://omi.me/allowed', 'title': 'https://omi.me/allowed'}
      ]);
    });

    test('literal text with blocks, more than 2,000 blocks and blocks on other kinds are invalid', () {
      final blocks = nativeRichText(_markdown);
      expect(NativeRow('reply', 'Plan', kind: 'message_ai', plainText: true, blocks: blocks).valid, false);
      expect(NativeRow('reply', 'Plan', kind: 'message_ai', blocks: List.filled(2000, _block('Line'))).valid, true);
      expect(NativeRow('reply', 'Plan', kind: 'message_ai', blocks: List.filled(2001, _block('Line'))).valid, false);
      // The reader keeps its current limits.
      expect(NativeRow('note', 'Note', kind: 'rich_text', blocks: List.filled(2001, _block('Line'))).valid, true);
      for (final kind in ['message_user', 'label', 'button']) {
        expect(NativeRow('row', 'Row', kind: kind, blocks: blocks).valid, false, reason: kind);
      }
      expect(
          const NativeRow('reply', 'Plan', kind: 'message_ai', blocks: [
            {'kind': 'script', 'text': 'alert(1)', 'indent': 0, 'prefix': ''}
          ]).valid,
          false);
    });

    test('a link reaches the owner only when it is one of the options', () async {
      final values = <Object?>[];
      final row = NativeRow('reply', 'Launch plan',
          kind: 'message_ai',
          blocks: nativeRichText(_markdown),
          options: nativeRichTextLinks(_markdown),
          action: values.add);
      expect(row.accepts('https://omi.me/allowed'), true);
      expect(row.accepts(null), true, reason: 'The trailing action (for example retry) sends no value');
      for (final value in ['https://example.com/blocked', 'https://omi.me/allowed/other', '', true]) {
        expect(row.accepts(value), false);
        await expectLater(_dispatch(row, value), throwsA(isA<PlatformException>()));
      }
      await _dispatch(row, 'https://omi.me/allowed');
      await _dispatch(row, null);
      expect(values, ['https://omi.me/allowed', null]);

      // Without a whitelist every link is refused.
      final plain =
          NativeRow('plain', 'Plan', kind: 'message_ai', blocks: nativeRichText(_markdown), action: values.add);
      await expectLater(_dispatch(plain, 'https://omi.me/allowed'), throwsA(isA<PlatformException>()));
      expect(values, hasLength(2));
    });

    test('summary links open only through their own whitelist and the Dart owner', () async {
      final opened = <Uri>[];
      final rows =
          nativeSummaryContentRows('Intro with [docs](https://omi.me/docs).\n\n- Second block', open: (url) async {
        opened.add(url);
        return true;
      });
      expect(rows.map((row) => row.id), ['detail_summary_content', 'detail_summary_content:1']);
      for (final row in rows) {
        expect(row.valid, true);
        expect(row.kind, 'rich_text');
        expect(row.options, {'https://omi.me/docs': 'https://omi.me/docs'});
        expect(row.projection['enabled'], true);
      }
      await expectLater(_dispatch(rows.first, 'https://example.com'), throwsA(isA<PlatformException>()));
      await _dispatch(rows.last, 'https://omi.me/docs');
      expect(opened, [Uri.parse('https://omi.me/docs')]);

      // Only web links leave the app, and the URL as written matches the whitelist too.
      final mixed = nativeSummaryContentRows('[call](tel:123) and [site](https://Example.com/a)', open: (url) async {
        opened.add(url);
        return true;
      }).single;
      expect(mixed.accepts('https://Example.com/a'), true);
      await _dispatch(mixed, 'tel:123');
      await _dispatch(mixed, 'https://Example.com/a');
      expect(opened.map((url) => url.scheme), ['https', 'https']);
      expect(opened.last.host, 'example.com');

      // A summary without links keeps its rows passive: no whitelist and no owner action.
      final plain = nativeSummaryContentRows('Plain summary').single;
      expect(plain.options, isEmpty);
      expect(plain.projection['enabled'], false);
    });
  });

  group('categorical charts', () {
    test('chartStyle is valid only as line or bar on a chart', () {
      for (final style in ['line', 'bar']) {
        final row = NativeRow('chart', 'Messages', kind: 'chart', chartStyle: style, points: _categories(12));
        expect(row.valid, true);
        expect(row.projection['chartStyle'], style);
        expect(NativeRow('chart', 'Messages', kind: 'chart', chartStyle: style, points: _categories(1)).valid, true);
      }
      expect(NativeRow('chart', 'Messages', kind: 'chart', chartStyle: 'pie', points: _categories(3)).valid, false);
      expect(NativeRow('chart', 'Messages', kind: 'chart', chartStyle: '', points: _categories(3)).valid, false);
      for (final kind in ['label', 'waveform', 'message_ai']) {
        expect(NativeRow('row', 'Row', kind: kind, chartStyle: 'bar', points: _categories(3)).valid, false,
            reason: kind);
      }
    });

    test('points must be index-ordered categories with finite values and short labels', () {
      NativeRow chart(List<Map<String, Object>> points) =>
          NativeRow('chart', 'Messages', kind: 'chart', chartStyle: 'bar', points: points);
      expect(chart(const []).valid, false);
      expect(chart(_categories(10000)).valid, true);
      expect(chart(_categories(10001)).valid, false);
      for (final points in [
        [
          {'x': 1, 'y': 1, 'label': 'Day 1'}
        ],
        [
          {'x': 1, 'y': 1, 'label': 'Day 1'},
          {'x': 0, 'y': 1, 'label': 'Day 0'}
        ],
        [
          {'x': 0, 'y': 1, 'label': 'Day 0'},
          {'x': 2, 'y': 1, 'label': 'Day 2'}
        ],
        [
          {'x': 0.5, 'y': 1, 'label': 'Half'}
        ],
        [
          {'x': 0, 'y': double.nan, 'label': 'Day 0'}
        ],
        [
          {'x': 0, 'y': double.infinity, 'label': 'Day 0'}
        ],
        [
          {'x': 0, 'y': 1}
        ],
        [
          {'x': 0, 'y': 1, 'label': 'a' * 65}
        ],
      ]) {
        expect(chart(points).valid, false, reason: '$points');
      }
      expect(
          chart([
            {'x': 0.0, 'y': 1, 'label': 'a' * 64},
            {'x': 1, 'y': -3.5, 'label': '👩‍👩‍👧' * 64},
          ]).valid,
          true,
          reason: 'Doubles at the index are accepted, and labels count characters like Swift');
    });

    test('nativeChartLabel shortens long labels instead of invalidating the chart', () {
      expect(nativeChartLabel('Monday'), 'Monday');
      expect(nativeChartLabel('a' * 64), 'a' * 64);
      final long = nativeChartLabel('a' * 200);
      expect(long.characters.length, 64);
      expect(long, '${'a' * 63}…');
      final emoji = nativeChartLabel('👩‍👩‍👧' * 70);
      expect(emoji.characters.length, 64);
      expect(emoji, '${'👩‍👩‍👧' * 63}…');
      expect(
          NativeRow('chart', 'Messages', kind: 'chart', chartStyle: 'line', points: [
            {'x': 0, 'y': 1, 'label': nativeChartLabel('a' * 500)}
          ]).valid,
          true);
    });

    test('the Usage chart without chartStyle keeps its existing rules', () {
      // Usage skips future buckets (x gaps) and its labels are not capped.
      final usage = NativeRow('usage_chart', 'Words', kind: 'chart', points: [
        {'x': 0.0, 'y': 3.0, 'label': 'Mon'},
        {'x': 3.0, 'y': 0.0, 'label': 'a' * 65},
      ]);
      expect(usage.valid, true);
      expect(usage.projection['chartStyle'], isNull);
      expect(const NativeRow('usage_chart', 'Words', kind: 'chart').valid, true);
      expect(
          const NativeRow('usage_chart', 'Words', kind: 'chart', points: [
            {'x': 0, 'y': 1, 'label': 'Mon'},
            {'x': 0, 'y': 2, 'label': 'Tue'},
          ]).valid,
          false);
    });
  });

  group('native host', () {
    testWidgets('a rich message and a categorical chart cross the channel; links stay whitelisted', (tester) async {
      final host = NativeTestHost.install();
      final values = <Object?>[];
      await tester.pumpWidget(NativeTestHost.app(IosNativeSurface(
          title: 'Ask Omi',
          fallback: const Text('classic chat'),
          chat: const NativeChat(draft: '', placeholder: 'Ask Omi', actions: []),
          sections: [
            NativeSection('chat_messages', [
              NativeRow('reply', 'Launch plan',
                  kind: 'message_ai',
                  blocks: nativeRichText(_markdown),
                  options: nativeRichTextLinks(_markdown),
                  action: values.add),
              NativeRow('chart', 'Messages', kind: 'chart', chartStyle: 'bar', points: _categories(3)),
            ]),
          ])));
      await NativeTestHost.settle(tester);
      expect(find.text('classic chat'), findsNothing);
      final view = host.created.single;
      final update = host.calls.lastWhere((call) => call.$1 == view && call.$2.method == 'update').$2;
      final rows = ((update.arguments as Map)['sections'] as List).single['rows'] as List;
      expect((rows.first as Map)['blocks'], isNotEmpty);
      expect((rows.last as Map)['chartStyle'], 'bar');

      final refused = await host.sendFromNative(
          view, const MethodCall('action', {'id': 'reply', 'value': 'https://example.com/blocked'}));
      expect(() => const StandardMethodCodec().decodeEnvelope(refused!), throwsA(isA<PlatformException>()));
      expect(values, isEmpty);
      await host.sendFromNative(view, const MethodCall('action', {'id': 'reply', 'value': 'https://omi.me/allowed'}));
      expect(values, ['https://omi.me/allowed']);
    });

    testWidgets('an invalid chart or rich message keeps the complete Flutter surface', (tester) async {
      NativeTestHost.install();
      for (final row in [
        NativeRow('chart', 'Messages', kind: 'chart', chartStyle: 'bar', points: _categories(3, label: 'a' * 64)),
        NativeRow('reply', 'Plan', kind: 'message_ai', plainText: true, blocks: nativeRichText(_markdown)),
      ]) {
        await tester.pumpWidget(NativeTestHost.app(IosNativeSurface(
            key: UniqueKey(),
            title: row.id,
            fallback: const Text('complete flutter surface'),
            sections: [
              NativeSection('rows', [row])
            ])));
        await NativeTestHost.settle(tester);
        expect(find.text('complete flutter surface'), findsOneWidget, reason: row.id);
        expect(find.byType(UiKitView), findsNothing);
      }
    });
  });
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_graph.dart';

import 'native_test_host.dart';

const _accent = '#1A2B3C';
const _fallback = 'complete flutter graph';

const _nodes = [
  NativeGraphNode('me', 'You', 'user', 0, 0, 0, true),
  NativeGraphNode('ada', 'Ada', 'person', -110, -150, 0),
  NativeGraphNode('paris', 'Paris', 'place', 120, -120, 300),
  NativeGraphNode('omi', 'Omi', 'organization', 130, 140, -400),
];
const _edges = [
  NativeGraphEdge('me', 'ada', 'knows'),
  NativeGraphEdge('me', 'paris', 'visited'),
  NativeGraphEdge('ada', 'paris'),
];

NativeGraph _graph({
  List<NativeGraphNode> nodes = _nodes,
  List<NativeGraphEdge> edges = _edges,
  Set<String> highlighted = const {},
  double zoom = 1.0,
  bool interactive = true,
  String layout = 'fill',
  double? height,
  String accent = _accent,
}) =>
    NativeGraph(
        nodes: nodes,
        edges: edges,
        highlighted: highlighted,
        zoom: zoom,
        interactive: interactive,
        layout: layout,
        height: height,
        accent: accent);

NativeGraph _card({Set<String> highlighted = const {}, double? height = 140, bool interactive = false}) =>
    _graph(layout: 'card', height: height, interactive: interactive, highlighted: highlighted);

NativeRow _row(NativeGraph? graph,
        {String id = 'graph', Object? value = '', String kind = 'graph', NativeAction? action}) =>
    NativeRow(id, 'Memory Graph', kind: kind, value: value, graph: graph, action: action ?? (_) {});

Widget _surface(List<NativeRow> rows,
        {NativeSurfaceController? controller,
        NativeAction? search,
        NativeAction? onRefresh,
        NativeChat? chat,
        NativeReader? reader,
        List<NativeRow> toolbar = const []}) =>
    IosNativeSurface(
      title: 'Memory Graph',
      fallback: const Text(_fallback),
      controller: controller,
      search: search,
      onRefresh: onRefresh,
      chat: chat,
      reader: reader,
      toolbar: toolbar,
      sections: [NativeSection('graph', rows)],
    );

Future<bool> _rendersNatively(WidgetTester tester, Widget surface) async {
  NativeTestHost.install();
  await tester.pumpWidget(NativeTestHost.app(surface));
  await NativeTestHost.settle(tester);
  final native = find.byType(UiKitView).evaluate().isNotEmpty;
  expect(native, find.text(_fallback).evaluate().isEmpty, reason: 'Exactly one presentation renders');
  return native;
}

void main() {
  group('NativeGraph', () {
    test('a valid fill graph projects every field and sorted highlights', () {
      final graph = _graph(highlighted: {'paris', 'ada'}, zoom: 0.72);
      expect(graph.valid, isTrue);
      expect(graph.nodeIds, {'me', 'ada', 'paris', 'omi'});
      final projection = graph.projection;
      expect(projection['highlighted'], ['ada', 'paris']);
      expect(projection['zoom'], 0.72);
      expect(projection['interactive'], isTrue);
      expect(projection['layout'], 'fill');
      expect(projection['height'], isNull);
      expect(projection['placeholder'], isFalse);
      expect(projection['accent'], _accent);
      expect((projection['nodes'] as List).first,
          {'id': 'me', 'label': 'You', 'type': 'user', 'x': 0.0, 'y': 0.0, 'z': 0.0, 'fixed': true});
      expect((projection['edges'] as List).last, {'source': 'ada', 'target': 'paris', 'label': ''});
    });

    test('node and edge counts are bounded', () {
      expect(_graph(nodes: const [], edges: const []).valid, isFalse);
      final many = [for (var i = 0; i < 1025; i++) NativeGraphNode('n$i', '', 'concept', 0, 0, 0)];
      expect(_graph(nodes: many.take(1024).toList(), edges: const []).valid, isTrue);
      expect(_graph(nodes: many, edges: const []).valid, isFalse);
      final pairs = [
        for (var i = 0; i < 4097; i++) NativeGraphEdge('n${i % 64}', 'n${64 + i % 64}', 'edge $i'),
      ];
      expect(_graph(nodes: many.take(200).toList(), edges: pairs.take(4096).toList()).valid, isTrue);
      expect(_graph(nodes: many.take(200).toList(), edges: pairs).valid, isFalse);
      expect(NativeGraph.fits(1024, 4096), isTrue);
      expect(NativeGraph.fits(1025, 0), isFalse);
      expect(NativeGraph.fits(10, 4097), isFalse);
    });

    test('node ids are 1..256 units and unique', () {
      expect(_graph(nodes: [..._nodes, const NativeGraphNode('ada', 'Again', 'person', 1, 1, 1)]).valid, isFalse);
      expect(_graph(nodes: [..._nodes, const NativeGraphNode('', 'Empty', 'person', 1, 1, 1)]).valid, isFalse);
      expect(_graph(nodes: [..._nodes, NativeGraphNode('x' * 256, 'Long', 'person', 1, 1, 1)]).valid, isTrue);
      expect(_graph(nodes: [..._nodes, NativeGraphNode('x' * 257, 'Long', 'person', 1, 1, 1)]).valid, isFalse);
    });

    test('labels over the limits are rejected; the helpers truncate them instead', () {
      final long = 'a' * 300;
      expect(_graph(nodes: [..._nodes, NativeGraphNode('long', long, 'thing', 1, 1, 1)]).valid, isFalse);
      expect(
          _graph(nodes: [..._nodes, NativeGraphNode('long', nativeGraphLabel(long), 'thing', 1, 1, 1)]).valid, isTrue);
      expect(nativeGraphLabel(long).length, NativeGraph.maxLabelLength);
      expect(nativeGraphLabel(long), endsWith('…'));
      expect(nativeGraphLabel('Ada'), 'Ada');
      expect(_graph(edges: [..._edges, NativeGraphEdge('omi', 'me', long)]).valid, isFalse);
      expect(_graph(edges: [..._edges, NativeGraphEdge('omi', 'me', nativeGraphEdgeLabel(long))]).valid, isTrue);
      expect(nativeGraphEdgeLabel(long).length, NativeGraph.maxEdgeLabelLength);
      // A character is never split, so the result stays well-formed UTF-16.
      final emoji = nativeGraphEdgeLabel('👩‍👩‍👧' * 40);
      expect(emoji.length, lessThanOrEqualTo(NativeGraph.maxEdgeLabelLength));
      expect(emoji.characters.take(emoji.characters.length - 1).every((c) => c == '👩‍👩‍👧'), isTrue);
    });

    test('node types are the six renderer colours', () {
      for (final type in nativeGraphNodeTypes) {
        final node = NativeGraphNode('typed', 'Typed', type, 1, 1, 1);
        expect(_graph(nodes: [..._nodes, node]).valid, isTrue, reason: type);
      }
      expect(_graph(nodes: [..._nodes, const NativeGraphNode('typed', 'Typed', 'event', 1, 1, 1)]).valid, isFalse);
    });

    test('coordinates are finite and within 1e6', () {
      for (final value in [double.nan, double.infinity, double.negativeInfinity, 1e6 + 1, -1e6 - 1]) {
        expect(_graph(nodes: [..._nodes, NativeGraphNode('bad', '', 'thing', value, 0, 1)]).valid, isFalse);
        expect(_graph(nodes: [..._nodes, NativeGraphNode('bad', '', 'thing', 0, value, 1)]).valid, isFalse);
        expect(_graph(nodes: [..._nodes, NativeGraphNode('bad', '', 'thing', 1, 0, value)]).valid, isFalse);
      }
      expect(_graph(nodes: [..._nodes, const NativeGraphNode('edge', '', 'thing', 1e6, -1e6, 1e6)]).valid, isTrue);
    });

    test('at most one fixed node, a user at the origin', () {
      expect(_graph(nodes: [..._nodes, const NativeGraphNode('me2', 'You', 'user', 0, 0, 0, true)]).valid, isFalse);
      expect(
          _graph(nodes: const [NativeGraphNode('me', 'You', 'person', 0, 0, 0, true)], edges: const []).valid, isFalse);
      expect(
          _graph(nodes: const [NativeGraphNode('me', 'You', 'user', 0, 1, 0, true)], edges: const []).valid, isFalse);
      expect(_graph(nodes: const [NativeGraphNode('me', 'You', 'user', 4, 1, 0)], edges: const []).valid, isTrue);
    });

    test('edges join two different present nodes once per triple', () {
      expect(_graph(edges: [..._edges, const NativeGraphEdge('me', 'ghost')]).valid, isFalse);
      expect(_graph(edges: [..._edges, const NativeGraphEdge('ghost', 'me')]).valid, isFalse);
      expect(_graph(edges: [..._edges, const NativeGraphEdge('ada', 'ada', 'self')]).valid, isFalse);
      expect(_graph(edges: [..._edges, const NativeGraphEdge('me', 'ada', 'knows')]).valid, isFalse);
      // Another label, or the reverse direction, is a distinct edge.
      expect(_graph(edges: [..._edges, const NativeGraphEdge('me', 'ada', 'met')]).valid, isTrue);
      expect(_graph(edges: [..._edges, const NativeGraphEdge('ada', 'me', 'knows')]).valid, isTrue);
    });

    test('highlights are at most five current nodes', () {
      final nodes = [for (var i = 0; i < 6; i++) NativeGraphNode('n$i', '', 'concept', i.toDouble(), 0, 0)];
      expect(_graph(nodes: nodes, edges: const [], highlighted: {'n0', 'n1', 'n2', 'n3', 'n4'}).valid, isTrue);
      expect(_graph(nodes: nodes, edges: const [], highlighted: {'n0', 'n1', 'n2', 'n3', 'n4', 'n5'}).valid, isFalse);
      expect(_graph(highlighted: {'ada', 'ghost'}).valid, isFalse);
    });

    test('zoom is finite within 0.05...5', () {
      expect(_graph(zoom: 0.05).valid, isTrue);
      expect(_graph(zoom: 5).valid, isTrue);
      for (final zoom in [0.049, 5.01, double.nan, double.infinity]) {
        expect(_graph(zoom: zoom).valid, isFalse, reason: '$zoom');
      }
    });

    test('a card has a 100...600 height and no interaction; a fill graph has no height', () {
      expect(_card().valid, isTrue);
      expect(_card(height: 100).valid && _card(height: 600).valid, isTrue);
      for (final height in [null, 99.0, 601.0, double.nan]) {
        expect(_card(height: height).valid, isFalse, reason: '$height');
      }
      expect(_card(interactive: true).valid, isFalse);
      expect(_graph(height: 300).valid, isFalse);
      expect(_graph(layout: 'sheet').valid, isFalse);
    });

    test('the accent is # and six hex digits', () {
      for (final accent in ['#1a2b3c', '#ABCDEF', '#000000']) {
        expect(_graph(accent: accent).valid, isTrue, reason: accent);
      }
      for (final accent in ['1A2B3C', '#1A2B3', '#1A2B3CA', '#GGGGGG', '#1A2B3C\n', '']) {
        expect(_graph(accent: accent).valid, isFalse, reason: accent);
      }
    });

    test('a placeholder is empty, non-interactive and still honours its layout', () {
      const fill = NativeGraph.placeholder(accent: _accent);
      expect(fill.valid, isTrue);
      expect(fill.nodes, isEmpty);
      expect(fill.edges, isEmpty);
      expect(fill.highlighted, isEmpty);
      expect(fill.interactive, isFalse);
      expect(fill.projection['placeholder'], isTrue);
      expect(const NativeGraph.placeholder(layout: 'card', height: 140, accent: _accent).valid, isTrue);
      expect(const NativeGraph.placeholder(layout: 'card', accent: _accent).valid, isFalse);
      expect(const NativeGraph.placeholder(accent: 'purple').valid, isFalse);
    });
  });

  group('graph rows', () {
    test('kind graph holds exactly when a graph is present', () {
      expect(_row(_graph()).valid, isTrue);
      expect(_row(null).valid, isFalse);
      expect(_row(_graph(), kind: 'label', value: null).valid, isFalse);
      expect(_row(_graph(nodes: const [])).valid, isFalse, reason: 'An invalid graph invalidates its row');
      expect(_row(_graph()).projection['graph'], _graph().projection);
      expect(const NativeRow('plain', 'Plain').projection['graph'], isNull);
    });

    test('an interactive value is empty or a node id, and nothing is highlighted while empty', () {
      expect(_row(_graph(), value: 'ada').valid, isTrue);
      expect(_row(_graph(highlighted: {'ada', 'me'}), value: 'ada').valid, isTrue);
      expect(_row(_graph(highlighted: {'ada'}), value: '').valid, isFalse);
      expect(_row(_graph(), value: 'ghost').valid, isFalse);
      expect(_row(_graph(), value: null).valid, isFalse);
      expect(_row(_graph(), value: true).valid, isFalse);
    });

    test('a non-interactive graph has no value', () {
      expect(_row(_card(), value: null).valid, isTrue);
      expect(_row(_card(highlighted: {'ada'}), value: null).valid, isTrue);
      expect(_row(_card(), value: '').valid, isFalse);
      expect(_row(const NativeGraph.placeholder(accent: _accent), value: null).valid, isTrue);
      expect(_row(const NativeGraph.placeholder(accent: _accent), value: '').valid, isFalse);
    });

    test('accepts a node id or the background when interactive, and only null for a card', () {
      final interactive = _row(_graph());
      expect(interactive.accepts(''), isTrue);
      expect(interactive.accepts('paris'), isTrue);
      expect(interactive.accepts('ghost'), isFalse);
      expect(interactive.accepts(null), isFalse);
      expect(interactive.accepts(3), isFalse);
      final card = _row(_card(), value: null);
      expect(card.accepts(null), isTrue);
      expect(card.accepts(''), isFalse);
      expect(card.accepts('ada'), isFalse);
      final placeholder = _row(const NativeGraph.placeholder(accent: _accent), value: null);
      expect(placeholder.accepts(null), isTrue);
      expect(placeholder.accepts(''), isFalse);
    });

    test('commands reach the owner only with an accepted selection', () async {
      final selected = <Object?>[];
      final rows = [_row(_graph(), action: selected.add)];
      Future<void> send(Object? value) =>
          dispatchNativeAction(MethodCall('action', {'id': 'graph', 'value': value}), isActive: () => true, rows: rows);
      await send('ada');
      await send('');
      for (final value in ['ghost', null, 1]) {
        await expectLater(send(value), throwsA(isA<PlatformException>()));
      }
      expect(selected, ['ada', '']);
    });
  });

  group('graph surfaces', () {
    testWidgets('a fill graph renders with label and button rows around it', (tester) async {
      expect(
          await _rendersNatively(
              tester,
              _surface([
                const NativeRow('hint', 'Tap a node', kind: 'label'),
                _row(_graph()),
                NativeRow('retry', 'Try again', action: (_) {}),
              ], toolbar: [
                NativeRow('share', 'Share', symbol: 'square.and.arrow.up', action: (_) {}),
              ])),
          isTrue);
    });

    testWidgets('a second fill graph falls back', (tester) async {
      expect(await _rendersNatively(tester, _surface([_row(_graph()), _row(_graph(), id: 'second')])), isFalse);
    });

    testWidgets('a fill graph with another row kind falls back', (tester) async {
      expect(
          await _rendersNatively(
              tester,
              _surface([
                _row(_graph()),
                NativeRow('open', 'Open', kind: 'navigation', action: (_) {}),
              ])),
          isFalse);
    });

    testWidgets('a fill graph with a card graph falls back', (tester) async {
      expect(
          await _rendersNatively(tester, _surface([_row(_graph()), _row(_card(), id: 'card', value: null)])), isFalse);
    });

    testWidgets('a fill graph with search falls back', (tester) async {
      expect(await _rendersNatively(tester, _surface([_row(_graph())], search: (_) {})), isFalse);
    });

    testWidgets('a fill graph with refresh falls back', (tester) async {
      expect(await _rendersNatively(tester, _surface([_row(_graph())], onRefresh: (_) {})), isFalse);
    });

    testWidgets('a fill graph with chat falls back', (tester) async {
      const chat = NativeChat(draft: '', placeholder: 'Ask', actions: []);
      expect(await _rendersNatively(tester, _surface([_row(_graph())], chat: chat)), isFalse);
    });

    testWidgets('a fill graph with a reader falls back', (tester) async {
      expect(await _rendersNatively(tester, _surface([_row(_graph())], reader: const NativeReader())), isFalse);
    });

    testWidgets('a graph outside the sections falls back', (tester) async {
      expect(await _rendersNatively(tester, _surface([], toolbar: [_row(_card(), value: null)])), isFalse);
    });

    testWidgets('card graphs share an ordinary list with any rows', (tester) async {
      expect(
          await _rendersNatively(
              tester,
              _surface([
                _row(_card(), value: null),
                _row(const NativeGraph.placeholder(layout: 'card', height: 140, accent: _accent),
                    id: 'loading', value: null),
                NativeRow('open', 'Open', kind: 'navigation', action: (_) {}),
              ], search: (_) {})),
          isTrue);
    });

    testWidgets('an invalid graph sends the whole surface to Flutter', (tester) async {
      expect(await _rendersNatively(tester, _surface([_row(_graph(accent: 'violet'))])), isFalse);
    });

    testWidgets('a native modal refuses graph rows before presenting, as NativeModalPresenter does', (tester) async {
      NativeTestHost.install();
      const config = MethodChannel('com.omi.native_ui/config');
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      final calls = <MethodCall>[];
      messenger.setMockMethodCallHandler(config, (call) async {
        calls.add(call);
        return null;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(config, null));
      await tester.pumpWidget(NativeTestHost.app(const SizedBox(key: ValueKey('caller'))));
      final context = tester.element(find.byKey(const ValueKey('caller')));
      expect(
          await showIosNativeModal(context, title: 'Memory Graph', actions: const [
            NativeRow('cancel', 'Cancel', symbol: 'xmark'),
          ], sections: [
            NativeSection('graph', [_row(_card(), value: null)]),
          ]),
          isNull);
      expect(calls, isEmpty);
    });
  });

  group('row-scoped capture', () {
    testWidgets('only a current, valid, non-placeholder graph row reaches the host', (tester) async {
      final host = NativeTestHost.install(answer: (_, call) async {
        if (call.method == 'captureImage') return Uint8List.fromList([137, 80, 78, 71]);
        return null;
      });
      final controller = NativeSurfaceController();
      await tester.pumpWidget(NativeTestHost.app(_surface([
        const NativeRow('hint', 'Tap a node', kind: 'label'),
        _row(_graph()),
      ], controller: controller)));
      await NativeTestHost.settle(tester);
      final view = host.created.single;
      List<MethodCall> captures() => [
            for (final call in host.calls)
              if (call.$1 == view && call.$2.method == 'captureImage') call.$2
          ];

      expect(await controller.captureImage(target: 'hint'), isNull, reason: 'Not a graph row');
      expect(await controller.captureImage(target: 'ghost'), isNull, reason: 'Not a current row');
      expect(captures(), isEmpty);

      expect(await controller.captureImage(target: 'graph'), [137, 80, 78, 71]);
      expect(captures().single.arguments, {'target': 'graph'});

      // The whole-view capture keeps its original call.
      expect(await controller.captureImage(), [137, 80, 78, 71]);
      expect(captures().last.arguments, isNull);
    });

    testWidgets('a placeholder graph cannot be captured', (tester) async {
      final host = NativeTestHost.install(answer: (_, call) async {
        if (call.method == 'captureImage') return Uint8List.fromList([1]);
        return null;
      });
      final controller = NativeSurfaceController();
      await tester.pumpWidget(NativeTestHost.app(
          _surface([_row(const NativeGraph.placeholder(accent: _accent), value: null)], controller: controller)));
      await NativeTestHost.settle(tester);
      expect(await controller.captureImage(target: 'graph'), isNull);
      expect(host.calls.where((call) => call.$2.method == 'captureImage'), isEmpty);
    });

    testWidgets('an oversized capture is dropped', (tester) async {
      NativeTestHost.install(answer: (_, call) async {
        if (call.method == 'captureImage') return Uint8List(16 * 1024 * 1024 + 1);
        return null;
      });
      final controller = NativeSurfaceController();
      await tester.pumpWidget(NativeTestHost.app(_surface([_row(_graph())], controller: controller)));
      await NativeTestHost.settle(tester);
      expect(await controller.captureImage(target: 'graph'), isNull);
    });

    testWidgets('a capture the host refuses answers null instead of throwing', (tester) async {
      NativeTestHost.install(answer: (_, call) async {
        if (call.method == 'captureImage') throw PlatformException(code: 'capture_failed');
        return null;
      });
      final controller = NativeSurfaceController();
      await tester.pumpWidget(NativeTestHost.app(_surface([_row(_graph())], controller: controller)));
      await NativeTestHost.settle(tester);
      expect(await controller.captureImage(target: 'graph'), isNull);
      expect(await controller.captureImage(), isNull);
    });

    testWidgets('a capture on the Flutter fallback answers null', (tester) async {
      NativeTestHost.install();
      final controller = NativeSurfaceController();
      await tester.pumpWidget(
          NativeTestHost.app(_surface([_row(_graph()), _row(_graph(), id: 'second')], controller: controller)));
      await NativeTestHost.settle(tester);
      expect(find.text(_fallback), findsOneWidget);
      expect(await controller.captureImage(target: 'graph'), isNull);
    });
  });
}

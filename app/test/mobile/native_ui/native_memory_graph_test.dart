import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_graph.dart';
import 'package:omi/mobile/native_ui/native_navigation_chrome.dart';
import 'package:omi/pages/memories/widgets/memory_graph_controller.dart';
import 'package:omi/pages/memories/widgets/memory_graph_native.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

final _en = lookupAppLocalizations(const Locale('en'));

Map<String, dynamic> _fixture() => {
      'nodes': [
        {'id': 'ada', 'label': 'Ada', 'node_type': 'person'},
        {'id': 'paris', 'label': 'Paris', 'node_type': 'place'},
        {'id': 'omi', 'label': 'Omi', 'node_type': 'organization'},
      ],
      'edges': [
        {'source_id': 'ada', 'target_id': 'paris', 'label': 'visited'},
        {'source_id': 'ada', 'target_id': 'omi', 'label': 'works at'},
      ],
    };

MemoryGraphController _controller() {
  final controller = MemoryGraphController(loadGraph: () async => {}, localizations: () => _en, random: Random(3));
  addTearDown(controller.dispose);
  return controller;
}

/// The rows of the last snapshot published to [view], by id.
Map<String, Map> _published(NativeTestHost host, int view) {
  final update = host.calls.lastWhere((call) => call.$1 == view && call.$2.method == 'update').$2;
  final snapshot = update.arguments as Map;
  return {
    for (final row in [
      ...snapshot['toolbar'] as List,
      for (final section in snapshot['sections'] as List) ...(section as Map)['rows'] as List,
    ])
      (row as Map)['id'] as String: row,
  };
}

Map _snapshot(NativeTestHost host, int view) =>
    host.calls.lastWhere((call) => call.$1 == view && call.$2.method == 'update').$2.arguments as Map;

Future<void> _tap(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
  await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  await NativeTestHost.settle(tester);
}

class _TempDirectory extends PathProviderPlatform {
  _TempDirectory(this.path);
  final String path;

  @override
  Future<String?> getTemporaryPath() async => path;
}

/// A small opaque PNG, as the native renderer would return it.
Future<Uint8List> _png(int width, int height) async {
  final recorder = ui.PictureRecorder();
  Canvas(recorder).drawRect(Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()), Paint()..color = Colors.black);
  final image = await recorder.endRecording().toImage(width, height);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('projectNativeGraph', () {
    test('maps the fixed node to user and unknown types to concept, truncating labels', () {
      final graph = _controller();
      graph.populate({
        'nodes': [
          {'id': 'me', 'label': 'Me'},
          {'id': 'ada', 'label': 'A' * 300, 'node_type': 'person'},
          {'id': 'paris', 'label': 'Paris', 'node_type': 'place'},
          {'id': 'omi', 'label': 'Omi', 'node_type': 'organization'},
          {'id': 'cup', 'label': 'Cup', 'node_type': 'thing'},
          {'id': 'idea', 'label': 'Idea', 'node_type': 'concept'},
          {'id': 'odd', 'label': 'Odd', 'node_type': 'galaxy'},
        ],
        'edges': [
          {'source_id': 'me', 'target_id': 'ada', 'label': 'x' * 200},
        ],
      });

      final projection = projectNativeGraph(graph, layout: 'card', interactive: false, zoom: 0.6, height: 140)!;
      final types = {for (final node in projection.nodes) node.id: node.type};
      expect(types, {
        'me': 'user',
        'ada': 'person',
        'paris': 'place',
        'omi': 'organization',
        'cup': 'thing',
        'idea': 'concept',
        'odd': 'concept',
      });
      final me = projection.nodes.firstWhere((node) => node.id == 'me');
      expect([me.fixed, me.x, me.y, me.z], [true, 0, 0, 0]);
      expect(projection.nodes.firstWhere((node) => node.id == 'ada').label.length, NativeGraph.maxLabelLength);
      expect(projection.edges.single.label.length, NativeGraph.maxEdgeLabelLength);
      expect(projection.accent, matches(RegExp(r'^#[0-9A-F]{6}$')));
      expect(
          [projection.layout, projection.height, projection.zoom, projection.interactive], ['card', 140, 0.6, false]);
      expect(projection.valid, isTrue);
    });

    test('highlights only an interactive selection', () {
      final graph = _controller()..populate(_fixture());
      graph.select('ada');
      final interactive = projectNativeGraph(graph)!;
      expect(interactive.highlighted, {'ada', 'paris', 'omi'});
      expect(nativeGraphSelection(graph, interactive), 'ada');
      final card = projectNativeGraph(graph, layout: 'card', height: 140, interactive: false)!;
      expect(card.highlighted, isEmpty);
    });

    test('is null for an empty graph or one over the native limits', () {
      expect(projectNativeGraph(_controller()), isNull);
      final graph = _controller()
        ..populate({
          'nodes': [
            for (var i = 0; i < NativeGraph.maxNodes; i++) {'id': 'n$i', 'label': 'n$i'}
          ],
          'edges': const [],
        });
      expect(graph.simulation.nodes.length, NativeGraph.maxNodes + 1);
      expect(projectNativeGraph(graph), isNull);
    });
  });

  group('native graph page', () {
    testWidgets('projects loading, failure, empty and loaded states without flipping to classic', (tester) async {
      final host = NativeTestHost.install();
      var response = Completer<Map<String, dynamic>>();
      await tester
          .pumpWidget(NativeTestHost.app(MemoryGraphPage(trackOpenEvent: false, loadGraph: () => response.future)));
      await NativeTestHost.settle(tester);
      final view = host.created.single;

      var rows = _published(host, view);
      var snapshot = _snapshot(host, view);
      expect(snapshot['loading'], isTrue);
      expect(snapshot['refreshEnabled'], isFalse);
      expect((rows['memory_graph_canvas']!['graph'] as Map)['placeholder'], isTrue);
      expect(rows['memory_graph_share']!['enabled'], isFalse);
      expect(rows.keys, contains('memory_graph_back'));

      response.completeError(Exception('offline'));
      await NativeTestHost.settle(tester);
      rows = _published(host, view);
      snapshot = _snapshot(host, view);
      expect(
          [snapshot['loading'], snapshot['failed'], snapshot['error']], [false, true, _en.couldNotLoadKnowledgeGraph]);
      expect((rows['memory_graph_canvas']!['graph'] as Map)['placeholder'], isTrue);
      expect(rows['memory_graph_retry']!['title'], _en.tryAgain);

      response = Completer();
      // The retry stays pending natively until the reload finishes.
      final retry = _tap(tester, host, 'memory_graph_retry');
      response.complete({'nodes': const [], 'edges': const []});
      await retry;
      rows = _published(host, view);
      expect(rows.keys, containsAll(['memory_graph_empty_title', 'memory_graph_empty_message']));
      expect(rows.containsKey('memory_graph_canvas'), isFalse);

      response = Completer();
      // Reloading through the controller (the resume path) brings in the graph.
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      response.complete(_fixture());
      await NativeTestHost.settle(tester);
      rows = _published(host, view);
      final canvas = rows['memory_graph_canvas']!;
      final graph = canvas['graph'] as Map;
      expect([graph['placeholder'], graph['layout'], graph['interactive'], canvas['value']], [false, 'fill', true, '']);
      expect(rows['memory_graph_share']!['enabled'], isTrue);
      expect(host.created, [view], reason: 'one native view for every state');
      expect(find.byType(UiKitView), findsOneWidget);
    });

    testWidgets('a node tap republishes the selection and its highlights', (tester) async {
      final host = NativeTestHost.install();
      await tester
          .pumpWidget(NativeTestHost.app(MemoryGraphPage(trackOpenEvent: false, loadGraph: () async => _fixture())));
      await NativeTestHost.settle(tester);

      await _tap(tester, host, 'memory_graph_canvas', 'ada');
      var canvas = _published(host, host.created.last)['memory_graph_canvas']!;
      expect(canvas['value'], 'ada');
      expect((canvas['graph'] as Map)['highlighted'], ['ada', 'omi', 'paris']);

      await _tap(tester, host, 'memory_graph_canvas', '');
      canvas = _published(host, host.created.last)['memory_graph_canvas']!;
      expect(canvas['value'], '');
      expect((canvas['graph'] as Map)['highlighted'], isEmpty);
    });

    testWidgets('Share captures the graph row, watermarks it and shares a temporary file', (tester) async {
      final temp = Directory.systemTemp.createTempSync('memory_graph_share');
      addTearDown(() => temp.deleteSync(recursive: true));
      final previousPaths = PathProviderPlatform.instance;
      PathProviderPlatform.instance = _TempDirectory(temp.path);
      addTearDown(() => PathProviderPlatform.instance = previousPaths);
      final png = (await tester.runAsync(() => _png(600, 400)))!;
      final shared = <Map>[];
      final sharedBytes = <Uint8List>[];
      const shareChannel = MethodChannel('dev.fluttercommunity.plus/share');
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(shareChannel, (call) async {
        final arguments = call.arguments as Map;
        shared.add(arguments);
        sharedBytes.add(File((arguments['paths'] as List).single as String).readAsBytesSync());
        return 'dev.fluttercommunity.plus/share/success';
      });
      addTearDown(() => messenger.setMockMethodCallHandler(shareChannel, null));
      Uint8List? capture = png;
      final host = NativeTestHost.install(answer: (_, call) async => call.method == 'captureImage' ? capture : null);

      await tester
          .pumpWidget(NativeTestHost.app(MemoryGraphPage(trackOpenEvent: false, loadGraph: () async => _fixture())));
      await NativeTestHost.settle(tester);
      await tester.runAsync(() => _tap(tester, host, 'memory_graph_share'));
      await NativeTestHost.settle(tester);

      final captures = host.calls.where((call) => call.$2.method == 'captureImage').toList();
      expect(captures.single.$2.arguments, {'target': 'memory_graph_canvas'});
      expect(shared, hasLength(1));
      expect(shared.single['text'], _en.checkOutMyMemoryGraph);
      final bytes = sharedBytes.single;
      expect(bytes.sublist(1, 4), 'PNG'.codeUnits);
      expect(ByteData.sublistView(bytes).getUint32(16), 600, reason: 'the shared image keeps the captured size');
      final watermarked = (await tester.runAsync(() async {
        final codec = await ui.instantiateImageCodec(bytes);
        final image = (await codec.getNextFrame()).image;
        final pixels = (await image.toByteData())!;
        image.dispose();
        codec.dispose();
        // Any light pixel inside the "omi.me" band over the black capture is the watermark.
        for (var y = 140; y < 220; y++) {
          for (var x = 0; x < 600; x++) {
            if (pixels.getUint8((y * 600 + x) * 4) > 200) return true;
          }
        }
        return false;
      }))!;
      expect(watermarked, isTrue, reason: 'the watermark is drawn over the capture');
      expect(temp.listSync(), isEmpty, reason: 'the temporary file is removed after the sheet');

      capture = null;
      await tester.runAsync(() => _tap(tester, host, 'memory_graph_share'));
      await NativeTestHost.settle(tester);
      expect(host.calls.where((call) => call.$2.method == 'captureImage'), hasLength(2));
      expect(shared, hasLength(1), reason: 'no capture, no share');
    });
  });

  testWidgets('a full graph the native renderer cannot take keeps the classic page', (tester) async {
    NativeTestHost.install();
    Future<Map<String, dynamic>> huge() async => {
          'nodes': [
            for (var i = 0; i < NativeGraph.maxNodes; i++) {'id': 'n$i', 'label': 'n$i'}
          ],
          'edges': const [],
        };
    await tester.pumpWidget(NativeTestHost.app(MemoryGraphPage(trackOpenEvent: false, loadGraph: huge)));
    await NativeTestHost.settle(tester);
    expect(find.byType(UiKitView), findsNothing);
    expect(find.byType(AppBar), findsOneWidget);
  });

  group('onboarding knowledge graph step', () {
    Widget step(
            {required VoidCallback onContinue,
            required VoidCallback onBack,
            required Future<Map<String, dynamic>> Function() load}) =>
        NativeTestHost.app(Builder(
          builder: (context) => NativeNavigationChrome(
            sections: const [
              NativeSection(
                  'onboarding_progress', [NativeRow('onboarding_progress_label', 'Step 7 of 8', kind: 'label')]),
            ],
            toolbar: [NativeRow('onboarding_back', _en.back, symbol: 'chevron.left', action: (_) => onBack())],
            wrapFallback: (fallback) => NativeNavigationChrome(enabled: false, child: fallback),
            child: OnboardingKnowledgeGraphStep(onContinue: onContinue, loadGraph: load),
          ),
        ));

    testWidgets('projects every state with Continue and the navigation chrome', (tester) async {
      final host = NativeTestHost.install();
      var continued = 0, back = 0;
      var response = Completer<Map<String, dynamic>>();
      await tester.pumpWidget(step(onContinue: () => continued++, onBack: () => back++, load: () => response.future));
      await NativeTestHost.settle(tester);
      final view = host.created.single;

      var rows = _published(host, view);
      expect(_snapshot(host, view)['loading'], isFalse, reason: 'Continue stays reachable');
      expect(rows.keys, containsAll(['onboarding_back', 'onboarding_progress_label', 'onboarding_kg_description']));
      expect((rows['onboarding_kg_graph']!['graph'] as Map)['placeholder'], isTrue);
      expect(rows['onboarding_knowledge_graph_continue']!['enabled'], isTrue);

      response.completeError(Exception('offline'));
      await NativeTestHost.settle(tester);
      rows = _published(host, view);
      expect(_snapshot(host, view)['failed'], isFalse);
      expect(rows.keys,
          containsAll(['onboarding_kg_error', 'onboarding_kg_retry', 'onboarding_knowledge_graph_continue']));

      response = Completer();
      final retry = _tap(tester, host, 'onboarding_kg_retry');
      response.complete({'nodes': const [], 'edges': const []});
      await retry;
      rows = _published(host, view);
      expect(rows.keys, containsAll(['onboarding_kg_empty_title', 'onboarding_knowledge_graph_continue']));

      response = Completer();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      response.complete(_fixture());
      await NativeTestHost.settle(tester);
      rows = _published(host, view);
      final graph = rows['onboarding_kg_graph']!['graph'] as Map;
      expect([graph['placeholder'], graph['interactive'], graph['zoom']], [false, true, 0.72]);
      expect(rows.keys, contains('onboarding_knowledge_graph_continue'));

      await _tap(tester, host, 'onboarding_kg_graph', 'ada');
      expect(_published(host, view)['onboarding_kg_graph']!['value'], 'ada');

      await _tap(tester, host, 'onboarding_knowledge_graph_continue');
      expect(continued, 1);
      await _tap(tester, host, 'onboarding_back');
      expect(back, 1);
      expect(host.created, [view]);
    });

    testWidgets('a graph the native renderer cannot take restores the classic step and its chrome', (tester) async {
      NativeTestHost.install();
      Future<Map<String, dynamic>> huge() async => {
            'nodes': [
              for (var i = 0; i < NativeGraph.maxNodes; i++) {'id': 'n$i', 'label': 'n$i'}
            ],
            'edges': const [],
          };
      await tester.pumpWidget(step(onContinue: () {}, onBack: () {}, load: huge));
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsNothing);
      expect(find.byKey(const Key('onboarding_knowledge_graph_continue')), findsOneWidget);
      final chrome = tester.widget<NativeNavigationChrome>(find.byType(NativeNavigationChrome).last);
      expect(chrome.enabled, isFalse, reason: 'the classic step takes back its own navigation');
    });
  });
}

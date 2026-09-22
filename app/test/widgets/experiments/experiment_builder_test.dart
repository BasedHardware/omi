import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/experiment_service.dart';
import 'package:omi/widgets/experiments/experiment_builder.dart';

class Flags implements ExperimentFlagProvider {
  late Completer<ExperimentFlagSnapshot> response;
  @override
  Future<ExperimentFlagSnapshot> fetch(ExperimentContext context) {
    response = Completer<ExperimentFlagSnapshot>();
    return response.future;
  }
}

void main() {
  late Flags flags;
  late ExperimentService service;
  late ExperimentDefinition<bool> trial;
  late List<String> events;
  setUp(() {
    flags = Flags();
    events = [];
    trial = ExperimentDefinition(
        key: 'page-test',
        version: 1,
        variants: {'control': false, 'test': true},
        defaultVariant: 'control',
        namespaces: {'mobile-test'},
        surfaces: {'library'},
        expiresAt: DateTime.utc(2030));
    service = ExperimentService(provider: flags, definitions: [trial], emit: (event, _) => events.add(event))
      ..updateContext(const ExperimentContext(
          identityKey: 'test', analyticsEnabled: true, namespace: 'mobile-test', appBuild: 1000));
  });
  tearDown(() => service.dispose());
  Widget app({bool visible = true}) => MaterialApp(
      home: ExperimentBuilder<bool>(
          service: service,
          definition: trial,
          surface: 'library',
          visible: visible,
          loadingBuilder: (_) => const SizedBox(key: Key('loading')),
          builder: (context, alternative, child) => Scaffold(
              appBar: AppBar(title: Text(alternative ? 'Grid library' : 'List library')),
              body: Column(children: [
                const TextField(key: Key('search')),
                TextButton(
                    onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(builder: (_) => const Scaffold(body: Text('Conversation details')))),
                    child: const Text('Open conversation')),
                if (alternative)
                  Expanded(
                      child: GridView.count(
                          crossAxisCount: 2,
                          children: const [Card(child: Text('Project meeting')), Card(child: Text('Morning notes'))]))
                else
                  const Expanded(child: ListTile(title: Text('Conversation')))
              ]))));
  void assign(String variant) => flags.response.complete(ExperimentFlagSnapshot(
      identityKey: 'test',
      fetchedAt: DateTime.now(),
      values: {ExperimentService.enabledFlag: true, 'page-test': variant}));

  testWidgets('complete page variants preserve navigation and state across flag refresh', (tester) async {
    await tester.pumpWidget(app());
    expect(find.byKey(const Key('loading')), findsOneWidget);
    assign('test');
    await tester.pumpAndSettle();
    expect(find.text('Grid library'), findsOneWidget);
    expect(events.where((e) => e == 'experiment_exposed'), hasLength(1));
    await tester.enterText(find.byKey(const Key('search')), 'local input');
    service.applySnapshot(ExperimentFlagSnapshot(
        identityKey: 'test',
        fetchedAt: DateTime.now(),
        values: {ExperimentService.enabledFlag: true, 'page-test': 'control'}));
    await tester.pump();
    expect(find.text('Grid library'), findsOneWidget);
    expect(find.text('local input'), findsOneWidget);
    await tester.tap(find.text('Open conversation'));
    await tester.pumpAndSettle();
    expect(find.text('Conversation details'), findsOneWidget);
    Navigator.of(tester.element(find.text('Conversation details'))).pop();
    await tester.pumpAndSettle();
    expect(find.text('local input'), findsOneWidget);
    expect(events.where((e) => e == 'experiment_exposed'), hasLength(1));
    service.setKillSwitch(true);
    await tester.pumpAndSettle();
    expect(find.text('List library'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('hidden mounted surface is not exposed until visible', (tester) async {
    await tester.pumpWidget(app(visible: false));
    assign('control');
    await tester.pumpAndSettle();
    expect(events.where((e) => e == 'experiment_exposed'), isEmpty);
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();
    expect(events.where((e) => e == 'experiment_exposed'), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('disposing loading page before flags return never exposes', (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpWidget(const SizedBox());
    assign('test');
    await tester.pumpAndSettle();
    expect(events.where((e) => e == 'experiment_exposed'), isEmpty);
    expect(service.outcomeProperties(), isEmpty);
  });
}

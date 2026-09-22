import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/experiment_service.dart';

class FakeFlags implements ExperimentFlagProvider {
  final requests = <Completer<ExperimentFlagSnapshot>>[];
  @override
  Future<ExperimentFlagSnapshot> fetch(ExperimentContext context) {
    final request = Completer<ExperimentFlagSnapshot>();
    requests.add(request);
    return request.future;
  }
}

ExperimentDefinition<String> definition(
        {String key = 'test-ui', String? layer, Map<bool, String> booleanVariants = const {}}) =>
    ExperimentDefinition(
        key: key,
        version: 1,
        variants: {'control': 'original', 'test': 'alternative', 'holdout-7': 'original'},
        defaultVariant: 'control',
        namespaces: {'mobile-test'},
        surfaces: {'test-page'},
        expiresAt: DateTime.utc(2030),
        layer: layer,
        holdoutVariants: {'holdout-7'},
        booleanVariants: booleanVariants);
const contextA =
    ExperimentContext(identityKey: 'account-a', analyticsEnabled: true, namespace: 'mobile-test', appBuild: 1000);
const contextB =
    ExperimentContext(identityKey: 'account-b', analyticsEnabled: true, namespace: 'mobile-test', appBuild: 1000);

void main() {
  late DateTime now;
  late FakeFlags flags;
  late ExperimentDefinition<String> trial;
  late ExperimentService service;
  late List<(String, Map<String, Object>)> events;
  ExperimentFlagSnapshot snapshot({String identity = 'account-a', Map<String, Object>? values}) =>
      ExperimentFlagSnapshot(
          values: values ?? {ExperimentService.enabledFlag: true, 'test-ui': 'test'},
          fetchedAt: now,
          identityKey: identity);
  setUp(() {
    now = DateTime.utc(2026, 9, 22);
    flags = FakeFlags();
    trial = definition();
    events = [];
    service = ExperimentService(
        provider: flags,
        definitions: [trial],
        emit: (e, p) => events.add((e, p)),
        now: () => now,
        loadTimeout: const Duration(milliseconds: 20),
        allowQaOverrides: true)
      ..updateContext(contextA);
  });
  tearDown(() => service.dispose());

  test('assignment is separate from deduplicated exposure and lease scoped outcomes', () async {
    final pending = service.open(trial, surface: 'test-page');
    flags.requests.single.complete(snapshot());
    final lease = await pending;
    expect(lease.variant, 'alternative');
    expect(events.where((e) => e.$1 == 'experiment_assigned'), hasLength(1));
    expect(service.outcomeProperties(), isEmpty);
    lease.expose();
    lease.expose();
    expect(events.where((e) => e.$1 == 'experiment_exposed'), hasLength(1));
    expect(events.singleWhere((e) => e.$1 == 'experiment_exposed').$2[r'$feature/test-ui'], 'test');
    expect(events.where((e) => e.$1 == r'$feature_flag_called'), hasLength(1));
    expect(service.outcomeProperties(), {r'$feature/test-ui': 'test'});
    lease.dispose();
    expect(service.outcomeProperties(), isEmpty);
  });
  test('identity switch drops late A response without exposing B', () async {
    final a = service.open(trial, surface: 'test-page');
    service.updateContext(contextB);
    final b = service.open(trial, surface: 'test-page');
    flags.requests[0].complete(snapshot());
    flags.requests[1].complete(snapshot(identity: 'account-b'));
    final old = await a;
    final current = await b;
    expect(old.variant, 'original');
    old.expose();
    expect(service.outcomeProperties(), isEmpty);
    current.expose();
    expect(events.where((e) => e.$1 == 'experiment_exposed'), hasLength(1));
    old.dispose();
    current.dispose();
  });
  test('timeout commits default and late assignment never changes viewed surface', () async {
    final pending = service.open(trial, surface: 'test-page');
    final lease = await pending;
    flags.requests.single.complete(snapshot());
    await Future<void>.delayed(Duration.zero);
    lease.expose();
    expect(lease.variant, 'original');
    expect(events.where((e) => e.$1 == 'experiment_exposed'), isEmpty);
    lease.dispose();
  });
  test('remote kill revokes active UI and attribution; variant refresh is sticky', () async {
    service.applySnapshot(snapshot());
    final lease = await service.open(trial, surface: 'test-page');
    lease.expose();
    service.applySnapshot(snapshot(values: {ExperimentService.enabledFlag: true, 'test-ui': 'control'}));
    expect(lease.variant, 'alternative');
    service.applySnapshot(snapshot(values: {ExperimentService.enabledFlag: false, 'test-ui': 'test'}));
    expect(lease.variant, 'original');
    expect(service.outcomeProperties(), isEmpty);
    lease.dispose();
  });
  test('consent withdrawal revokes leases and prevents network calls', () async {
    service.applySnapshot(snapshot());
    final lease = await service.open(trial, surface: 'test-page');
    lease.expose();
    service.updateContext(const ExperimentContext(
        identityKey: 'account-a', analyticsEnabled: false, namespace: 'mobile-test', appBuild: 1000));
    final fallback = await service.open(trial, surface: 'test-page');
    expect(lease.variant, 'original');
    expect(flags.requests, isEmpty);
    expect(service.outcomeProperties(), isEmpty);
    lease.dispose();
    fallback.dispose();
  });
  test('missing, unknown, disabled and non-authoritative flags never count as control', () async {
    for (final values in <Map<String, Object>>[
      {},
      {ExperimentService.enabledFlag: true, 'test-ui': 'unknown'},
      {ExperimentService.enabledFlag: true, 'test-ui': false}
    ]) {
      service.applySnapshot(snapshot(values: values));
      final lease = await service.open(trial, surface: 'test-page');
      expect(lease.variant, 'original');
      lease.expose();
      lease.dispose();
    }
    expect(events.where((e) => e.$1 == 'experiment_exposed'), isEmpty);
  });
  test('cache expiry removes attribution, offline opens default but viewed UI remains', () async {
    service.applySnapshot(snapshot());
    final lease = await service.open(trial, surface: 'test-page');
    lease.expose();
    now = now.add(const Duration(minutes: 6));
    expect(service.outcomeProperties(), isEmpty);
    final fallback = await service.open(trial, surface: 'test-page');
    expect(lease.variant, 'alternative');
    expect(fallback.variant, 'original');
    lease.dispose();
    fallback.dispose();
  });
  test('QA assignment is isolated from analysis', () async {
    service.setQaOverride('test-ui', 'test');
    final lease = await service.open(trial, surface: 'test-page');
    lease.expose();
    expect(lease.variant, 'alternative');
    expect(events, isEmpty);
    expect(service.outcomeProperties(), isEmpty);
    lease.dispose();
  });
  test('server layer chooses exactly one trial and explicit holdout is attributed', () async {
    final first = definition(layer: 'discovery');
    final second = definition(key: 'second-ui', layer: 'discovery');
    final layered = ExperimentService(
        provider: flags, definitions: [first, second], emit: (e, p) => events.add((e, p)), now: () => now)
      ..updateContext(contextA)
      ..applySnapshot(snapshot(values: {
        ExperimentService.enabledFlag: true,
        'mobile-layer-discovery': 'test-ui',
        'test-ui': 'holdout-7',
        'second-ui': 'test'
      }));
    final chosen = await layered.open(first, surface: 'test-page');
    final excluded = await layered.open(second, surface: 'test-page');
    chosen.expose();
    excluded.expose();
    expect(chosen.properties['holdout'], true);
    expect(chosen.variant, 'original');
    expect(excluded.assigned, false);
    expect(layered.outcomeProperties(), {r'$feature/test-ui': 'holdout-7'});
    chosen.dispose();
    excluded.dispose();
    layered.dispose();
  });
  test('A to B to A cannot resurrect an earlier generation', () async {
    final oldRequest = service.open(trial, surface: 'test-page');
    service.updateContext(contextB);
    service.updateContext(contextA);
    flags.requests.single.complete(snapshot());
    final old = await oldRequest;
    old.expose();
    expect(old.assigned, false);
    expect(events.where((event) => event.$1 == 'experiment_exposed'), isEmpty);
    old.dispose();
  });
  test('untrusted or wrong-identity snapshots cannot enroll or expose', () async {
    for (final response in [
      ExperimentFlagSnapshot(
          values: {ExperimentService.enabledFlag: true, 'test-ui': 'test'},
          fetchedAt: now,
          identityKey: 'account-a',
          authoritative: false),
      snapshot(identity: 'account-b'),
      ExperimentFlagSnapshot(
          values: {ExperimentService.enabledFlag: true, 'test-ui': 'test'},
          fetchedAt: now.add(const Duration(minutes: 1)),
          identityKey: 'account-a'),
    ]) {
      final request = service.open(trial, surface: 'test-page');
      flags.requests.last.complete(response);
      final lease = await request;
      expect(lease.assigned, false);
      lease.expose();
      lease.dispose();
    }
    expect(events.where((event) => event.$1 == 'experiment_exposed'), isEmpty);
  });
  test('overlapping different variants omit ambiguous outcome attribution', () async {
    service.applySnapshot(snapshot());
    final first = await service.open(trial, surface: 'test-page');
    first.expose();
    service.applySnapshot(snapshot(values: {ExperimentService.enabledFlag: true, 'test-ui': 'control'}));
    final second = await service.open(trial, surface: 'test-page');
    second.expose();
    expect(first.variant, 'alternative');
    expect(second.variant, 'original');
    expect(service.outcomeProperties(), isEmpty);
    first.dispose();
    expect(service.outcomeProperties(), {r'$feature/test-ui': 'control'});
    second.dispose();
  });
  test('boolean false can be explicit assigned control', () async {
    final boolean = definition(booleanVariants: {true: 'test', false: 'control'});
    final other =
        ExperimentService(provider: flags, definitions: [boolean], emit: (e, p) => events.add((e, p)), now: () => now)
          ..updateContext(contextA)
          ..applySnapshot(snapshot(values: {ExperimentService.enabledFlag: true, 'test-ui': false}));
    final lease = await other.open(boolean, surface: 'test-page');
    lease.expose();
    expect(lease.assigned, true);
    expect(other.outcomeProperties(), {r'$feature/test-ui': 'control'});
    lease.dispose();
    other.dispose();
  });
}

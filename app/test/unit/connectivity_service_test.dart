import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/connectivity_service.dart';

void main() {
  late StreamController<List<ConnectivityResult>> interfaces;
  late StreamController<void> internet;
  late ConnectivityService service;
  late List<Completer<bool>> probes;
  late Future<List<ConnectivityResult>> Function() read;
  late List<bool> changes;

  Future<void> settle() => Future<void>.delayed(Duration.zero);

  setUp(() {
    interfaces = StreamController.broadcast(sync: true);
    internet = StreamController.broadcast(sync: true);
    probes = [];
    changes = [];
    read = () async => [ConnectivityResult.wifi];
    service = ConnectivityService.forTesting(
      readInterfaces: () => read(),
      interfaceChanges: interfaces.stream,
      refreshTicks: internet.stream,
      probeInternet: () {
        final probe = Completer<bool>();
        probes.add(probe);
        return probe.future;
      },
    );
    service.onConnectionChange.listen(changes.add);
  });

  tearDown(() async {
    service.dispose();
    for (final probe in probes) {
      if (!probe.isCompleted) probe.complete(false);
    }
    await settle();
    await interfaces.close();
    await internet.close();
  });

  Future<void> boot({bool online = true}) async {
    final initialized = service.init();
    await settle();
    probes.last.complete(online);
    await initialized;
    await settle();
  }

  test('concurrent initialization shares one interface read and probe', () async {
    var reads = 0;
    read = () async {
      reads++;
      return [ConnectivityResult.wifi];
    };
    final first = service.init();
    final second = service.init();
    expect(identical(first, second), isTrue);
    await settle();
    expect(reads, 1);
    expect(probes, hasLength(1));
    probes.single.complete(true);
    await Future.wait([first, second]);
    await service.init();
    expect(reads, 1);
  });

  test('handover during startup wins over an older interface snapshot', () async {
    final snapshot = Completer<List<ConnectivityResult>>();
    read = () => snapshot.future;
    final initialized = service.init();
    internet.add(null);
    expect(service.isConnected, isTrue, reason: 'wait for a known interface before probing');
    interfaces.add([ConnectivityResult.mobile]);
    await settle();
    expect(probes, hasLength(1));
    probes.single.complete(true);
    snapshot.complete([ConnectivityResult.none]);
    await initialized;
    await settle();
    expect(service.isConnected, isTrue);
    expect(changes, isEmpty);
  });

  test('old Wi-Fi failure cannot override the new cellular success', () async {
    await boot(online: false);
    interfaces.add([ConnectivityResult.wifi]);
    final wifi = probes.last;
    interfaces.add([ConnectivityResult.mobile]);
    final cellular = probes.last;
    cellular.complete(true);
    await settle();
    wifi.complete(false);
    await settle();
    expect(service.isConnected, isTrue);
    expect(changes, [false, true]);
  });

  test('interface loss invalidates pending success and periodic checks', () async {
    await boot();
    interfaces.add([ConnectivityResult.wifi]);
    final pending = probes.last;
    interfaces.add([ConnectivityResult.none]);
    internet.add(null);
    pending.complete(true);
    await settle();
    expect(service.isConnected, isFalse);
    expect(probes, hasLength(2), reason: 'do not probe without an interface');
    expect(changes, [false]);
  });

  test('periodic checks revalidate even without a checker status change', () async {
    await boot();
    internet.add(null);
    expect(service.isConnected, isTrue, reason: 'wait for the current probe');
    probes.last.complete(true);
    await settle();
    expect(service.isConnected, isTrue);
    expect(changes, isEmpty);
  });

  for (final interface in [ConnectivityResult.vpn, ConnectivityResult.bluetooth, ConnectivityResult.other]) {
    test('$interface requires reachability and can recover', () async {
      await boot(online: false);
      interfaces.add([interface]);
      probes.last.complete(false);
      await settle();
      expect(service.isConnected, isFalse);
      internet.add(null);
      probes.last.complete(true);
      await settle();
      expect(service.isConnected, isTrue);
    });
  }

  test('probe failure reports offline and the next event can recover', () async {
    final initialized = service.init();
    await settle();
    probes.last.completeError(StateError('fixture transport failure'));
    await initialized;
    expect(service.isConnected, isFalse);
    internet.add(null);
    probes.last.complete(true);
    await settle();
    expect(changes, [false, true]);
  });

  test('failed initial snapshot cleans subscriptions and allows retry', () async {
    read = () => Future.error(StateError('fixture interface failure'));
    await expectLater(service.init(), throwsStateError);
    expect(interfaces.hasListener, isFalse);
    expect(internet.hasListener, isFalse);
    read = () async => [ConnectivityResult.wifi];
    await boot();
    expect(probes, hasLength(1));
  });

  test('interface stream errors do not escape an observed snapshot failure', () async {
    final snapshot = Completer<List<ConnectivityResult>>();
    read = () => snapshot.future;
    final initialized = service.init();
    interfaces.addError(StateError('fixture event channel unavailable'));
    snapshot.completeError(StateError('fixture snapshot unavailable'));
    await expectLater(initialized, throwsStateError);
    expect(interfaces.hasListener, isFalse);
    expect(internet.hasListener, isFalse);
  });

  test('disposed service ignores pending checks', () async {
    final initialized = service.init();
    await settle();
    service.dispose();
    probes.last.complete(false);
    await initialized;
    expect(changes, isEmpty);
    await expectLater(service.init(), throwsStateError);
  });

  test('a wifi to cellular handover that never went offline is a network change', () async {
    var networkChanges = 0;
    service.onNetworkChange.listen((_) => networkChanges++);
    await boot();
    expect(networkChanges, 0, reason: 'the startup snapshot is not a change');

    interfaces.add([ConnectivityResult.mobile]);
    await settle();
    probes.last.complete(true);
    await settle();
    expect(networkChanges, 1);
    expect(changes, isEmpty, reason: 'online throughout, so onConnectionChange stays silent');

    interfaces.add([ConnectivityResult.mobile]);
    await settle();
    probes.last.complete(true);
    await settle();
    expect(networkChanges, 1, reason: 'the same interface set again is not a change');

    interfaces.add([ConnectivityResult.none]);
    await settle();
    expect(networkChanges, 1, reason: 'going offline is reported by onConnectionChange instead');
  });
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import 'native_test_host.dart';

const _fallback = 'complete flutter surface';

Widget _surface({String title = 'Tasks', String row = 'Review the native screens', Widget? nativeOwner}) =>
    IosNativeSurface(title: title, fallback: const Text(_fallback), nativeOwner: nativeOwner, sections: [
      NativeSection('tasks', [NativeRow('review', row, action: (_) {})])
    ]);

Future<Object?> _refuseUpdates(int viewId, MethodCall call) async {
  if (call.method == 'update') throw PlatformException(code: 'invalid_native_snapshot');
  return null;
}

void main() {
  testWidgets('a snapshot Swift refuses renders the fallback for good and invalidates the channel', (tester) async {
    final host = NativeTestHost.install(answer: _refuseUpdates);
    await tester.pumpWidget(NativeTestHost.app(_surface()));
    await NativeTestHost.settle(tester);
    expect(find.text(_fallback), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);
    final view = host.created.single;
    expect(host.methodsOf(view), ['update', 'invalidate']);
    expect(await host.sendFromNative(view, const MethodCall('action', {'id': 'review'})), isNull,
        reason: 'The refused view can no longer reach the Dart owner');

    // Later rebuilds, even with new content, never retry the refused renderer.
    await tester.pumpWidget(NativeTestHost.app(_surface(row: 'Review again')));
    await NativeTestHost.settle(tester);
    expect(find.text(_fallback), findsOneWidget);
    expect(host.created, [view]);
    expect(host.methodsOf(view), ['update', 'invalidate']);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a current view without a handler renders the fallback for good', (tester) async {
    final host = NativeTestHost.install(answer: (_, call) async {
      if (call.method == 'update') throw MissingPluginException();
      return null;
    });
    await tester.pumpWidget(NativeTestHost.app(_surface()));
    await NativeTestHost.settle(tester);
    expect(find.text(_fallback), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);
    final view = host.created.single;
    expect(host.methodsOf(view), ['update', 'invalidate']);

    host.answer = (_, __) async => null;
    await tester.pumpWidget(NativeTestHost.app(_surface(row: 'Review again')));
    await NativeTestHost.settle(tester);
    expect(find.text(_fallback), findsOneWidget);
    expect(host.created, [view]);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a replaced view losing its handler does not reject the current view', (tester) async {
    final firstUpdate = Completer<void>();
    late final NativeTestHost host;
    host = NativeTestHost.install(answer: (viewId, call) async {
      if (viewId == host.created.first && call.method == 'update') {
        await firstUpdate.future;
        throw MissingPluginException();
      }
      return null;
    });
    await tester.pumpWidget(NativeTestHost.app(_surface()));
    await NativeTestHost.settle(tester);
    final first = host.created.single;
    expect(host.methodsOf(first), ['update']);

    // Mounting a service owner rebuilds the platform view under the same State.
    await tester.pumpWidget(NativeTestHost.app(_surface(nativeOwner: const SizedBox())));
    await NativeTestHost.settle(tester);
    expect(host.created, hasLength(2));
    expect(host.disposed, [first]);
    firstUpdate.complete();
    await NativeTestHost.settle(tester);
    expect(find.byType(UiKitView), findsOneWidget);
    expect(find.text(_fallback), findsNothing);
    expect(host.methodsOf(host.created.last), contains('update'));
    expect(host.methodsOf(host.created.last), isNot(contains('invalidate')));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a parent swapping between classic and native trees never retries a refused surface', (tester) async {
    final host = NativeTestHost.install(answer: _refuseUpdates);
    var selecting = false;
    var title = 'Tasks';
    late StateSetter swap;
    await tester.pumpWidget(NativeTestHost.app(StatefulBuilder(builder: (context, setState) {
      swap = setState;
      return selecting ? const Text('classic selection') : _surface(title: title);
    })));
    await NativeTestHost.settle(tester);
    expect(find.text(_fallback), findsOneWidget);
    expect(host.created, hasLength(1));

    for (var round = 0; round < 3; round++) {
      swap(() => selecting = true);
      await NativeTestHost.settle(tester);
      expect(find.text('classic selection'), findsOneWidget);
      swap(() => selecting = false);
      await NativeTestHost.settle(tester);
      expect(find.text(_fallback), findsOneWidget, reason: 'A new State starts on the fallback');
    }
    expect(host.created, hasLength(1), reason: 'No native view is created for a refused surface again');

    // The route remembers only that surface: another one mounted in the route renders natively.
    host.answer = (_, __) async => null;
    swap(() => selecting = true);
    await NativeTestHost.settle(tester);
    swap(() {
      selecting = false;
      title = 'Memories';
    });
    await NativeTestHost.settle(tester);
    expect(find.byType(UiKitView), findsOneWidget);
    expect(host.created, hasLength(2));

    // The memory belongs to the route: a newly pushed route tries its renderer again.
    unawaited(
        Navigator.of(tester.element(find.byType(UiKitView))).push(MaterialPageRoute<void>(builder: (_) => _surface())));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(seconds: 1));
    expect(host.created, hasLength(3));
    expect(tester.takeException(), isNull);
  });

  testWidgets('the debug corrupt-snapshot seam publishes a version Swift does not accept', (tester) async {
    final host = NativeTestHost.install();
    IosNativeSurface.debugCorruptSnapshotForTest = true;
    addTearDown(() => IosNativeSurface.debugCorruptSnapshotForTest = false);
    await tester.pumpWidget(NativeTestHost.app(_surface()));
    await NativeTestHost.settle(tester);
    expect((tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map)['version'], 2);
    final update = host.calls.firstWhere((call) => call.$2.method == 'update').$2;
    expect((update.arguments as Map)['version'], 2);

    IosNativeSurface.debugCorruptSnapshotForTest = false;
    await tester.pumpWidget(NativeTestHost.app(_surface(row: 'Review again')));
    await NativeTestHost.settle(tester);
    final latest = host.calls.lastWhere((call) => call.$2.method == 'update').$2;
    expect((latest.arguments as Map)['version'], 1);
  });

  testWidgets('non-iOS or flag-off builds never create a native view', (tester) async {
    // With the flag (Android), the support check answers false off iOS, so the fallback renders.
    // The surface reads the signed-in owner first, so this test brings its own instead of an earlier one's.
    NativeTestHost.installOwner();
    await tester.pumpWidget(NativeTestHost.app(_surface()));
    await tester.pump();
    expect(find.text(_fallback), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);
  });
}

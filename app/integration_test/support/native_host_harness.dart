import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/ui.dart';

import '../visual_audit/fakes.dart';

/// Checks the mounted native surface against its real UIKit host and saves [screenshot].
typedef NativeHostCheck = Future<void> Function(WidgetTester tester, String screenshot);

/// Runs a native host suite on Simulator, with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
/// [register] declares the suite's cases. Each batch keeps its own target,
/// `integration_test/native_<batch>_host_test.dart`, whose `main` calls this.
void runNativeHostSuite(void Function(NativeHostCheck checkNativeHost) register) {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  register(_checkNativeHost);
}

/// Saves the integration plugin's UIKit screenshot. With NATIVE_UI_SCREENSHOT_PORT set, the test-only
/// driver first captures the Simulator display, so both show the same screen.
Future<List<int>> captureNativeHostScreenshot(String name) async {
  const port = int.fromEnvironment('NATIVE_UI_SCREENSHOT_PORT');
  if (port != 0) {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 15);
    try {
      final request = await client.getUrl(Uri.http('127.0.0.1:$port', '/capture', {'name': name}));
      final response = await request.close().timeout(const Duration(seconds: 20));
      expect(response.statusCode, 200, reason: 'The Simulator display capture must finish on this screen');
      await response.drain<void>();
    } finally {
      client.close(force: true);
    }
  }
  return IntegrationTestWidgetsFlutterBinding.instance.takeScreenshot(name);
}

Future<void> _checkNativeHost(WidgetTester tester, String screenshot) async {
  await tester.pump(const Duration(seconds: 2));
  await tester.pump(const Duration(seconds: 2));
  final native = find.byType(UiKitView);
  expect(native, findsOneWidget);
  expect(tester.getRect(native).height, greaterThan(550));
  // Platform-view creation is asynchronous on the first native route. Pumping
  // virtual frames alone does not wait for UIKit's real creation reply.
  int? id;
  final deadline = DateTime.now().add(const Duration(seconds: 10));
  while (id == null && DateTime.now().isBefore(deadline)) {
    await Future<void>.delayed(const Duration(milliseconds: 100));
    await tester.pump();
    id = nativeViewId(tester, native);
  }
  expect(id, isNotNull, reason: 'The real UIKit view must finish creating');
  await MethodChannel('com.omi.native_ui/surface/$id')
      .invokeMethod<void>('update', tester.widget<UiKitView>(native).creationParams);
  await Future<void>.delayed(const Duration(seconds: 2));
  await tester.pump();
  final received =
      await MethodChannel('com.omi.native_ui/surface/$id').invokeMapMethod<String, Object?>('debugPresentation');
  final projected = tester.widget<UiKitView>(native).creationParams as Map;
  expect((received!['toolbar'] as List).map((row) => row['id']), (projected['toolbar'] as List).map((row) => row['id']),
      reason: 'The UIKit owner must receive the current navigation projection');
  expect(tester.takeException(), isNull);
  expect(await captureNativeHostScreenshot(screenshot), isNotEmpty);
}

/// The platform view id of the UIKit view under [finder], once UIKit has created it.
int? nativeViewId(WidgetTester tester, Finder finder) {
  RenderUiKitView? view;
  void visit(RenderObject object) {
    if (object is RenderUiKitView) view = object;
    object.visitChildren(visit);
  }

  visit(tester.renderObject(finder));
  return view?.viewController.id;
}

/// The row [id] as the mounted native surfaces dispatch it: [IosNativeSurface.debugDispatchRows] lists
/// every row a surface's commands reach, including those its navigation chrome adds and its bottom bar.
/// When several surfaces project it, the last one in tree order (the topmost route) wins.
NativeRow nativeProjectedRow(WidgetTester tester, String id) {
  NativeRow? match;
  for (final surface in tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface, skipOffstage: false))) {
    for (final row in IosNativeSurface.debugDispatchRows(surface)) {
      if (row.id == id) match = row;
    }
  }
  if (match == null) throw TestFailure('No mounted native surface projects the row "$id"');
  return match;
}

/// A localized, themed app over the inert audit providers. Later [providers] replace earlier ones.
Widget nativeHostApp(Widget home,
        {List<SingleChildWidget> providers = const [], Brightness brightness = Brightness.dark}) =>
    MultiProvider(
        providers: [...defaultAuditProviders(), ...providers],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            theme: buildOmiTheme(brightness: brightness),
            home: home));

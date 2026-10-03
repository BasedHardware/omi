import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/ui.dart';

import 'journeys/support/hermetic_boot.dart';
import 'visual_audit/fakes.dart';

int nativeViewId(WidgetTester tester, Finder finder) {
  RenderUiKitView? view;
  void visit(RenderObject object) {
    if (object is RenderUiKitView) view = object;
    object.visitChildren(visit);
  }

  visit(tester.renderObject(finder));
  expect(view, isNotNull);
  return view!.viewController.id;
}

/// Exercises the actual Flutter platform view, UIKit containment and SwiftUI renderer.
/// Run on Simulator with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('native Home fills its Flutter host without splitting the scroll area', (tester) async {
    await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(MultiProvider(
      providers: defaultAuditProviders(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        theme: buildOmiTheme(brightness: Brightness.dark),
        home: Scaffold(
            body: IosNativeHome(
          requestInitialLoad: false,
          loadRecaps: () async => (
            ok: true,
            items: [
              DailySummary(
                id: 'host-recap',
                date: '2026-10-03',
                createdAt: DateTime.utc(2026, 10, 3),
                headline: 'A Busy Day of Shopping and Omi',
                overview: '',
                stats: DayStats(),
              )
            ]
          ),
          header: [
            NativeHomeAction('device', '53%', 'battery.75percent', () {}),
            NativeHomeAction('settings', 'Settings', 'gearshape', () {})
          ],
          footer: [
            NativeHomeAction('chat', 'Ask Omi', 'bubble.left', () {}),
            NativeHomeAction('tasks', 'Tasks', 'checklist', () {})
          ],
        )),
      ),
    ));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
    final native = find.byType(UiKitView);
    expect(native, findsOneWidget);
    final frame = tester.getRect(native);
    expect(frame.width, greaterThan(300));
    expect(frame.height, greaterThan(650));
    final viewId = nativeViewId(tester, native);
    await MethodChannel('com.omi.native_ui/home/$viewId')
        .invokeMethod<void>('update', tester.widget<UiKitView>(native).creationParams);
    expect(tester.takeException(), isNull);
    final screenshot = await binding.takeScreenshot('native-home-in-flutter-host');
    expect(screenshot, isNotEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });
  testWidgets('native form fills its Flutter host and detaches cleanly', (tester) async {
    await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(MultiProvider(
      providers: defaultAuditProviders(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: IosNativeSurface(
          title: 'Edit Task',
          fallback: const Text('Native renderer unavailable'),
          sections: [
            NativeSection('editor', [
              NativeRow('draft', 'Description', kind: 'text', value: 'Review the native iOS screens', action: (_) {}),
              NativeRow('complete', 'Completed', kind: 'toggle', value: false, action: (_) {}),
            ])
          ],
          toolbar: [NativeRow('save', 'Save', action: (_) {})],
        )),
      ),
    ));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
    final native = find.byType(UiKitView);
    expect(native, findsOneWidget);
    expect(tester.getRect(native).height, greaterThan(650));
    final viewId = nativeViewId(tester, native);
    // A rejected native factory must fail this check instead of passing as an empty UIView.
    await MethodChannel('com.omi.native_ui/surface/$viewId')
        .invokeMethod<void>('update', tester.widget<UiKitView>(native).creationParams);
    expect(tester.takeException(), isNull);
    // UIKit drawing continues independently of the Flutter test frame.
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pump();
    expect(await binding.takeScreenshot('native-form-in-flutter-host'), isNotEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}

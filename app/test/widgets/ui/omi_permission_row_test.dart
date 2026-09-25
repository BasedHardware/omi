import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/ui/components/omi_permission_row.dart';

Widget _app(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

class _FakeSource implements OnboardingPermissionsSource {
  final Map<OnboardingPermission, OmiPermissionStatus> statuses = {
    OnboardingPermission.location: OmiPermissionStatus.askable,
    OnboardingPermission.notifications: OmiPermissionStatus.blocked,
  };
  final List<OnboardingPermission> requested = [];

  @override
  List<OnboardingPermission> get permissions =>
      const [OnboardingPermission.location, OnboardingPermission.notifications];

  @override
  Future<OmiPermissionStatus> status(OnboardingPermission permission) async => statuses[permission]!;

  @override
  Future<void> request(OnboardingPermission permission) async {
    requested.add(permission);
    statuses[permission] = OmiPermissionStatus.granted;
  }
}

void main() {
  test('maps permission_handler statuses to what the reader can do', () {
    expect(OmiPermissionStatus.fromStatus(PermissionStatus.denied), OmiPermissionStatus.askable);
    expect(OmiPermissionStatus.fromStatus(PermissionStatus.granted), OmiPermissionStatus.granted);
    expect(OmiPermissionStatus.fromStatus(PermissionStatus.limited), OmiPermissionStatus.granted);
    expect(OmiPermissionStatus.fromStatus(PermissionStatus.permanentlyDenied), OmiPermissionStatus.blocked);
    expect(OmiPermissionStatus.fromStatus(PermissionStatus.restricted), OmiPermissionStatus.blocked);
  });

  testWidgets('an askable permission offers Allow, and only Allow prompts', (tester) async {
    var allowed = 0;
    await tester.pumpWidget(_app(OmiPermissionRow(
      title: 'Notifications',
      reason: 'So Omi can remind you.',
      status: OmiPermissionStatus.askable,
      onAllow: () => allowed++,
    )));
    expect(find.text('Allow'), findsOneWidget);
    expect(find.text('Open Settings'), findsNothing);
    await tester.tap(find.text('Allow'));
    expect(allowed, 1);
  });

  testWidgets('a FontAwesome leading glyph stands in for the Material icon', (tester) async {
    await tester.pumpWidget(_app(OmiPermissionRow(
      leading: const FaIcon(FontAwesomeIcons.solidBell),
      title: 'Notifications',
      reason: 'So Omi can remind you.',
      status: OmiPermissionStatus.askable,
      onAllow: () {},
    )));
    expect(find.byType(FaIcon), findsOneWidget);
    expect(tester.getSize(find.byType(FaIcon)).height, 22);
  });

  testWidgets('a granted permission shows Allowed and no action', (tester) async {
    await tester.pumpWidget(_app(OmiPermissionRow(
      title: 'Notifications',
      reason: 'So Omi can remind you.',
      status: OmiPermissionStatus.granted,
      onAllow: () => fail('must not prompt'),
    )));
    expect(find.text('Allowed'), findsOneWidget);
    expect(find.byType(TextButton), findsNothing);
  });

  testWidgets('a permission the system will not ask for again offers Open Settings', (tester) async {
    var opened = 0;
    await tester.pumpWidget(_app(OmiPermissionRow(
      title: 'Location',
      reason: 'So Omi can note where.',
      status: OmiPermissionStatus.blocked,
      onAllow: () => fail('must not prompt'),
      onOpenSettings: () => opened++,
    )));
    expect(find.text('Allow'), findsNothing);
    expect(find.textContaining('Turned off in Settings'), findsOneWidget);
    await tester.tap(find.text('Open Settings'));
    await tester.pump();
    expect(opened, 1);
  });

  testWidgets('onboarding: Continue never prompts; Allow prompts that one permission', (tester) async {
    final source = _FakeSource();
    var continued = 0;
    await tester.pumpWidget(_app(PermissionsWidget(goNext: () => continued++, source: source)));
    await tester.pumpAndSettle();

    // One row each; the blocked one offers Settings, not a prompt.
    expect(find.text('Allow'), findsOneWidget);
    expect(find.text('Open Settings'), findsOneWidget);

    await tester.tap(find.byKey(const Key('onboarding_permissions_continue')));
    await tester.pump();
    expect(continued, 1);
    expect(source.requested, isEmpty, reason: 'Continue moves on without firing any system prompt');

    await tester.tap(find.text('Allow'));
    await tester.pumpAndSettle();
    expect(source.requested, [OnboardingPermission.location]);
    expect(find.text('Allowed'), findsOneWidget);
  });
}

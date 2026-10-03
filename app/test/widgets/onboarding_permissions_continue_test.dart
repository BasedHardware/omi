import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/ui/components/omi_permission_row.dart';

class _FakeSource implements OnboardingPermissionsSource {
  _FakeSource(this.statuses, {this.failing = const {}});

  final Map<OnboardingPermission, OmiPermissionStatus> statuses;
  final Set<OnboardingPermission> failing;
  final List<OnboardingPermission> requested = [];

  @override
  List<OnboardingPermission> get permissions => statuses.keys.toList();

  @override
  Future<OmiPermissionStatus> status(OnboardingPermission permission) async => statuses[permission]!;

  @override
  Future<void> request(OnboardingPermission permission) async {
    requested.add(permission);
    if (failing.contains(permission)) throw Exception('platform error');
    statuses[permission] = OmiPermissionStatus.granted;
  }
}

Future<int> _tapContinue(WidgetTester tester, _FakeSource source) async {
  var nextCalls = 0;
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: PermissionsWidget(source: source, goNext: () => nextCalls++)),
    ),
  );
  await tester.pumpAndSettle();
  await tester.ensureVisible(find.byKey(const Key('onboarding_permissions_continue')));
  await tester.tap(find.byKey(const Key('onboarding_permissions_continue')));
  await tester.pumpAndSettle();
  return nextCalls;
}

void main() {
  testWidgets('Continue asks for every permission still missing, in row order, then moves on', (tester) async {
    final source = _FakeSource({
      OnboardingPermission.background: OmiPermissionStatus.granted,
      OnboardingPermission.location: OmiPermissionStatus.askable,
      OnboardingPermission.notifications: OmiPermissionStatus.askable,
    });

    expect(await _tapContinue(tester, source), 1);
    expect(source.requested, [OnboardingPermission.location, OnboardingPermission.notifications]);
  });

  testWidgets('Continue leaves blocked and service-off permissions to Settings', (tester) async {
    final source = _FakeSource({
      OnboardingPermission.location: OmiPermissionStatus.serviceOff,
      OnboardingPermission.notifications: OmiPermissionStatus.blocked,
    });

    expect(await _tapContinue(tester, source), 1);
    expect(source.requested, isEmpty);
  });

  testWidgets('a failed ask still asks the rest and moves on', (tester) async {
    final source = _FakeSource(
      {
        OnboardingPermission.location: OmiPermissionStatus.askable,
        OnboardingPermission.notifications: OmiPermissionStatus.askable,
      },
      failing: {OnboardingPermission.location},
    );

    expect(await _tapContinue(tester, source), 1);
    expect(source.requested, [OnboardingPermission.location, OnboardingPermission.notifications]);
  });
}

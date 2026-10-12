import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/permissions/permissions_widget.dart';
import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/components/omi_permission_row.dart';

/// [statuses] holds every permission's state, Bluetooth included; [permissions] lists only the
/// step's own cards, like the platform source (Bluetooth is added by the step when not allowed).
class _FakeSource implements OnboardingPermissionsSource {
  _FakeSource(this.statuses, {this.answers = const {}, this.failing = const {}});

  final Map<OnboardingPermission, OmiPermissionStatus> statuses;

  /// What the system prompt answers; granted when not listed.
  final Map<OnboardingPermission, OmiPermissionStatus> answers;
  final Set<OnboardingPermission> failing;
  final List<OnboardingPermission> requested = [];

  @override
  List<OnboardingPermission> get permissions =>
      statuses.keys.where((p) => p != OnboardingPermission.bluetooth).toList();

  @override
  Future<OmiPermissionStatus> status(OnboardingPermission permission) async =>
      statuses[permission] ?? OmiPermissionStatus.granted;

  @override
  Future<void> request(OnboardingPermission permission) async {
    requested.add(permission);
    if (failing.contains(permission)) throw Exception('platform error');
    statuses[permission] = answers[permission] ?? OmiPermissionStatus.granted;
  }
}

Future<List<int>> _pump(WidgetTester tester, _FakeSource source) async {
  final next = <int>[0];
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: PermissionsWidget(source: source, goNext: () => next[0]++)),
    ),
  );
  await tester.pumpAndSettle();
  return next;
}

bool _continueEnabled(WidgetTester tester) =>
    tester.widget<OmiButton>(find.byKey(const Key('onboarding_permissions_continue'))).onPressed != null;

Future<void> _toggle(WidgetTester tester, OnboardingPermission permission) async {
  final card = find.byKey(ValueKey('onboarding_permission_${permission.name}'));
  await tester.ensureVisible(card);
  await tester.tap(card);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Continue stays locked until every card is answered; each toggle asks only its own permission',
      (tester) async {
    final source = _FakeSource({
      OnboardingPermission.location: OmiPermissionStatus.askable,
      OnboardingPermission.notifications: OmiPermissionStatus.askable,
    });
    final next = await _pump(tester, source);

    expect(source.requested, isEmpty, reason: 'nothing prompts by itself');
    expect(_continueEnabled(tester), isFalse);

    await _toggle(tester, OnboardingPermission.location);
    expect(source.requested, [OnboardingPermission.location]);
    expect(_continueEnabled(tester), isFalse);

    await _toggle(tester, OnboardingPermission.notifications);
    expect(source.requested, [OnboardingPermission.location, OnboardingPermission.notifications]);
    expect(_continueEnabled(tester), isTrue);

    await tester.tap(find.byKey(const Key('onboarding_permissions_continue')));
    await tester.pumpAndSettle();
    expect(next[0], 1);
  });

  testWidgets('a "no" is an answer: the card shows it and the reader can still continue', (tester) async {
    final source = _FakeSource(
      {
        OnboardingPermission.location: OmiPermissionStatus.askable,
        OnboardingPermission.notifications: OmiPermissionStatus.askable,
      },
      answers: {
        OnboardingPermission.location: OmiPermissionStatus.askable,
        OnboardingPermission.notifications: OmiPermissionStatus.blocked,
      },
    );
    await _pump(tester, source);

    await _toggle(tester, OnboardingPermission.location);
    await _toggle(tester, OnboardingPermission.notifications);

    expect(find.text('Tap to fix'), findsOneWidget, reason: 'denied notifications say how to fix them');
    expect(_continueEnabled(tester), isTrue);
  });

  testWidgets('allowed and blocked permissions already count as answered', (tester) async {
    final source = _FakeSource({
      OnboardingPermission.location: OmiPermissionStatus.granted,
      OnboardingPermission.notifications: OmiPermissionStatus.blocked,
    });
    await _pump(tester, source);

    expect(_continueEnabled(tester), isTrue);
    expect(source.requested, isEmpty);
  });

  testWidgets('a failed ask still counts as answered', (tester) async {
    final source = _FakeSource(
      {OnboardingPermission.location: OmiPermissionStatus.askable},
      failing: {OnboardingPermission.location},
    );
    await _pump(tester, source);

    await _toggle(tester, OnboardingPermission.location);
    expect(_continueEnabled(tester), isTrue);
  });

  testWidgets('Bluetooth gets a card only when it is not allowed', (tester) async {
    final allowed = _FakeSource({
      OnboardingPermission.bluetooth: OmiPermissionStatus.granted,
      OnboardingPermission.location: OmiPermissionStatus.granted,
    });
    await _pump(tester, allowed);
    expect(find.byKey(const ValueKey('onboarding_permission_bluetooth')), findsNothing);
    await tester.pumpWidget(const SizedBox());

    final denied = _FakeSource({
      OnboardingPermission.bluetooth: OmiPermissionStatus.blocked,
      OnboardingPermission.location: OmiPermissionStatus.granted,
    });
    await _pump(tester, denied);
    expect(find.byKey(const ValueKey('onboarding_permission_bluetooth')), findsOneWidget);
    expect(find.text('Bluetooth permission is required to connect to your device.'), findsOneWidget);
  });
}

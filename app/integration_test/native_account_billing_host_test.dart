import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/widgets/cancel_subscription_sheet.dart';
import 'package:omi/providers/usage_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// No subscription request leaves the device; cancellation is only counted.
class _InertUsage extends UsageProvider {
  int cancellations = 0;

  @override
  Future<bool> cancelUserSubscription({String? reason, String? reasonDetails}) async {
    cancellations++;
    return false;
  }
}

/// Opens [flow] from a plain home route and walks it to its last step through the projected rows.
Future<void> _openLastStep(WidgetTester tester, Widget flow, String reasonRow) async {
  unawaited(Navigator.of(tester.element(find.text('home'))).push(MaterialPageRoute<void>(builder: (_) => flow)));
  await tester.pump(const Duration(seconds: 1));
  await nativeProjectedRow(tester, reasonRow).action!(null);
  await tester.pump(const Duration(milliseconds: 500));
  await nativeProjectedRow(tester, 'leave_continue').action!(null);
  await tester.pump(const Duration(seconds: 1));
  await nativeProjectedRow(tester, 'leave_skip').action!(null);
  await tester.pump(const Duration(seconds: 1));
}

/// Run on Simulator with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
void main() => runNativeHostSuite((checkNativeHost) {
      testWidgets('cancel subscription consequences are contained natively', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final usage = _InertUsage();
        addTearDown(usage.dispose);
        await tester.pumpWidget(nativeHostApp(const Scaffold(body: Center(child: Text('home'))),
            providers: [ChangeNotifierProvider<UsageProvider>.value(value: usage)]));
        await _openLastStep(tester, const CancelSubscriptionFlow(), 'cancel_reason:too_expensive');
        await checkNativeHost(tester, 'native-account-billing-flows-cancel-subscription-dark');
        expect(nativeProjectedRow(tester, 'cancel_confirm').destructive, true);
        expect(nativeProjectedRow(tester, 'leave_step').value, 3);
        expect(usage.cancellations, 0);
        expect(tester.takeException(), isNull);
      });

      testWidgets('delete account confirmation is contained natively', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        var requests = 0;
        await tester.pumpWidget(nativeHostApp(const Scaffold(body: Center(child: Text('home')))));
        await _openLastStep(tester, DeleteAccount(deleteAccountRequest: ({reason, reasonDetails}) async {
          requests++;
          return false;
        }), 'delete_reason:taking_break');
        await checkNativeHost(tester, 'native-account-billing-flows-delete-account-dark');
        expect(nativeProjectedRow(tester, 'delete_account').projection['enabled'], false);
        expect(nativeProjectedRow(tester, 'delete_confirm_word').maximumLength, 32);
        expect(requests, 0);
        expect(tester.takeException(), isNull);
      });
    });

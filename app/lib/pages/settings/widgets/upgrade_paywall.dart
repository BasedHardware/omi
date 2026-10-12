import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';

import 'package:omi/pages/settings/widgets/standalone_plans_sheet.dart';
import 'package:omi/services/superwall_pilot.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Shows the upgrade offer for one paywall placement and logs `Paywall Opened` with [source].
///
/// Free users go through the Superwall [placement] when the pilot is on; everyone else (and any
/// Superwall failure) gets the existing plans sheet over the current screen.
Future<void> openUpgradePaywall(
  BuildContext context, {
  required String placement,
  required String source,
  bool freeUser = true,
}) async {
  PlatformManager.instance.analytics.paywallOpened(source);
  if (freeUser && SuperwallPilot.instance.isEnabled) {
    final user = FirebaseAuth.instance.currentUser;
    if (user != null && !user.isAnonymous && await SuperwallPilot.instance.showPlacement(placement, user.uid)) return;
  }
  if (context.mounted) await showStandalonePlansSheet(context);
}

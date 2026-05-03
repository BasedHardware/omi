import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/onboarding/permissions/permissions_checker.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class MobileApp extends StatelessWidget {
  const MobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        if (authProvider.isSignedIn()) {
          // Returning users who haven't yet given consent under the new
          // model must see the consent screen before any AI processing
          // begins, even if the server says they completed onboarding
          // previously. OnboardingWrapper renders the consent step in
          // that case and routes them straight to home after Continue.
          if (!SharedPreferencesUtil().aiConsentGiven) {
            return const OnboardingWrapper();
          }
          if (SharedPreferencesUtil().onboardingCompleted) {
            if (!SharedPreferencesUtil().permissionsCompleted) {
              return const _PermissionsGate();
            }
            return const HomePageWrapper();
          } else {
            return const OnboardingWrapper();
          }
        } else {
          return const DeviceSelectionPage();
        }
      },
    );
  }
}

/// Checks if permissions are already granted. If so, marks as completed
/// and shows home. Otherwise shows the permissions interstitial.
class _PermissionsGate extends StatefulWidget {
  const _PermissionsGate();

  @override
  State<_PermissionsGate> createState() => _PermissionsGateState();
}

class _PermissionsGateState extends State<_PermissionsGate> {
  bool? _permissionsGranted;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final granted = await arePermissionsGranted();
    if (granted) {
      SharedPreferencesUtil().permissionsCompleted = true;
    }
    if (mounted) {
      setState(() => _permissionsGranted = granted);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_permissionsGranted == null) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(child: CircularProgressIndicator(color: Colors.white)),
      );
    }
    if (_permissionsGranted!) {
      return const HomePageWrapper();
    }
    MixpanelManager().permissionsInterstitialShown();
    return const PermissionsInterstitialPage();
  }
}

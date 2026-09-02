import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/permissions/permissions_checker.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/account_cutover/account_cutover_blocking_gate.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

class MobileApp extends StatefulWidget {
  const MobileApp({super.key, this.forceOnboardingRestart = false});

  // Debug-only: makes this instance show the onboarding flow from splash
  // regardless of sign-in / consent / completion state. Set by the debug
  // "restart onboarding" overlay in main.dart, which pushes a fresh
  // MobileApp — a full restart is required because completing onboarding
  // for real replaces every route (this one included) via
  // pushAndRemoveUntil, so there's no existing MobileApp instance left to
  // signal otherwise.
  final bool forceOnboardingRestart;

  @override
  State<MobileApp> createState() => _MobileAppState();
}

class _MobileAppState extends State<MobileApp> {
  int _lastPresentedSessionExpiration = 0;

  void _presentSessionExpiration(int generation) {
    if (generation <= _lastPresentedSessionExpiration) return;
    _lastPresentedSessionExpiration = generation;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      AppSnackbar.showSnackbarError(context.l10n.sessionExpiredSignInAgain);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        Widget content;
        if (widget.forceOnboardingRestart) {
          content = const OnboardingWrapper(forceStartAtSplash: true);
        } else if (authProvider.requiresReauthentication) {
          _presentSessionExpiration(authProvider.sessionExpirationGeneration);
          content = const OnboardingWrapper(forceAuthPage: true);
        } else if (authProvider.isSignedIn()) {
          // Cutover gate sits above onboarding and home so completed-onboarding
          // navigator replacements cannot bypass enforcement, and product
          // widgets are not constructed while blocked.
          content = AccountCutoverBlockingGate(
            productBuilder: (context) {
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
              }
              return const OnboardingWrapper();
            },
          );
        } else {
          content = const OnboardingWrapper();
        }

        return content;
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
    return const PermissionsInterstitialPage();
  }
}

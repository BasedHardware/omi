import 'package:flutter/material.dart';

import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Checks if critical permissions are granted. Returns true if all are granted.
///
/// The microphone is not part of this gate on purpose: it is asked when the reader first records
/// (docs/ux-contract.md §15), so a returning user is not held here for it.
Future<bool> arePermissionsGranted() async {
  final notification = await Permission.notification.isGranted;
  final location = await Permission.location.isGranted;
  return notification && location;
}

/// Interstitial shown when onboarding was completed (from backend) but permissions haven't been
/// granted on this device (fresh install). Same rows as the first-run step
/// ([OnboardingPermissionsPanel]); Continue goes home without prompting.
class PermissionsInterstitialPage extends StatefulWidget {
  const PermissionsInterstitialPage({super.key, this.source});

  final OnboardingPermissionsSource? source;

  @override
  State<PermissionsInterstitialPage> createState() => _PermissionsInterstitialPageState();
}

class _PermissionsInterstitialPageState extends State<PermissionsInterstitialPage> {
  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.permissionsInterstitialShown();
  }

  void _goHome(BuildContext context) {
    SharedPreferencesUtil().permissionsCompleted = true;
    Navigator.of(context).pushAndRemoveUntil(omiPageRoute(builder: (_) => const HomePageWrapper()), (route) => false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      body: Column(
        children: [
          // Omi logo in the top area, biased toward bottom
          Expanded(
            child: Align(
              alignment: const Alignment(0, 0.4),
              child: ExcludeSemantics(
                child: Image.asset(Assets.images.logoTransparent.path, width: 120, height: 120),
              ),
            ),
          ),
          Flexible(
            flex: 3,
            child: OnboardingCard(
              content: [
                Text(context.l10n.grantPermissions, style: OmiType.title1, textAlign: TextAlign.center),
                const SizedBox(height: OmiSpacing.xs),
                Text(
                  context.l10n.permissionsSetupDescription,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: OmiSpacing.xl),
                OnboardingPermissionsPanel(source: widget.source),
              ],
              footer: [
                const SizedBox(height: OmiSpacing.xs),
                OmiButton(
                  key: const Key('permissions_interstitial_continue'),
                  label: context.l10n.continueButton,
                  expand: true,
                  onPressed: () {
                    PlatformManager.instance.analytics.permissionsInterstitialCompleted();
                    _goHome(context);
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

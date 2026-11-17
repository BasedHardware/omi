import 'package:flutter/material.dart';

import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/pages/paywall/paywall_router.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';

/// Shown while a free plan's capture transcribes on this phone: it says transcription still works,
/// and opens the plans at the moment the difference from the cloud is felt.
bool showOnPhoneBanner({required bool transcribingOnPhone, required UsageProvider usage}) {
  final plan = usage.subscription?.subscription.plan;
  return transcribingOnPhone && usage.showSubscriptionUI && plan != null && !plan.isPaid && !plan.isUnknown;
}

class OnPhoneTranscriptionBanner extends StatelessWidget {
  const OnPhoneTranscriptionBanner({super.key, this.onUpgrade});

  /// Replaces the plans opener in tests.
  final VoidCallback? onUpgrade;

  static Future<void> _openPlans(BuildContext context) async {
    if (await PaywallRouter.openVariant(context, source: 'on_phone_banner')) return;
    if (!context.mounted) return;
    await showPlansSheetPrompt(context, source: 'on_phone_banner');
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
      child: Semantics(
        button: true,
        label: '${l10n.transcribingOnThisPhone}. ${l10n.getPro}',
        excludeSemantics: true,
        child: Material(
          color: OmiColors.surface1,
          borderRadius: BorderRadius.circular(OmiRadius.pill),
          child: InkWell(
            key: const Key('on_phone_banner'),
            borderRadius: BorderRadius.circular(OmiRadius.pill),
            onTap: onUpgrade ?? () => _openPlans(context),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 44),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
                child: Row(
                  children: [
                    Icon(onDevicePhoneIcon, size: 18, color: OmiColors.textSecondary),
                    const SizedBox(width: OmiSpacing.sm),
                    Expanded(child: Text(l10n.transcribingOnThisPhone, style: OmiType.subhead)),
                    Text(l10n.getPro, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
                    Icon(Icons.chevron_right, size: 18, color: OmiColors.textSecondary),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

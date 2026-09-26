import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class AiAppGeneratorBanner extends StatelessWidget {
  const AiAppGeneratorBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        OmiHaptics.light();

        // Track banner click
        PlatformManager.instance.analytics.track('AI App Generator Banner Clicked');

        routeToPage(context, const AiAppGeneratorPage());
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: OmiSpacing.md),
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border, width: 1),
        ),
        child: Row(
          children: [
            // Magic wand icon
            Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.mdAll),
              child: const Center(
                child: FaIcon(FontAwesomeIcons.wandMagicSparkles, color: OmiColors.textPrimary, size: 16),
              ),
            ),

            const SizedBox(width: OmiSpacing.sm),

            // Message
            Expanded(
              child: Text(
                context.l10n.aiAppGeneratorBannerTitle,
                style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
              ),
            ),

            // BETA badge
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: const BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
              child: Text(
                context.l10n.beta,
                style: OmiType.caption.copyWith(
                  color: OmiColors.textSecondary,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.5,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

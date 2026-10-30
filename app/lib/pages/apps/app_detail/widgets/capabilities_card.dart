import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';

class CapabilitiesCard extends StatelessWidget {
  final List<AppCapability> capabilities;

  const CapabilitiesCard({super.key, required this.capabilities});

  FaIconData _getCapabilityIcon(String id) {
    switch (id) {
      case 'chat':
        return FontAwesomeIcons.solidComment;
      case 'memories':
        return FontAwesomeIcons.solidFileLines;
      case 'external_integration':
        return FontAwesomeIcons.puzzlePiece;
      case 'persona':
        return FontAwesomeIcons.userAstronaut;
      case 'proactive_notification':
        return FontAwesomeIcons.solidBell;
      case 'push_to_talk':
        return FontAwesomeIcons.walkieTalkie;
      default:
        return FontAwesomeIcons.cubes;
    }
  }

  Color _getCapabilityColor(String id) {
    return OmiColors.textSecondary;
  }

  @override
  Widget build(BuildContext context) {
    if (capabilities.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16.0),
      margin: EdgeInsets.only(
        left: MediaQuery.of(context).size.width * 0.05,
        right: MediaQuery.of(context).size.width * 0.05,
        top: 12,
        bottom: 6,
      ),
      decoration: BoxDecoration(
        color: OmiColors.surface1.withValues(alpha: 0.8),
        borderRadius: OmiRadius.lgAll,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(context.l10n.capabilities, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: OmiSpacing.md),
          Wrap(
            spacing: OmiSpacing.sm,
            runSpacing: OmiSpacing.sm,
            children: capabilities.map((capability) {
              final color = _getCapabilityColor(capability.id);
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
                decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: OmiRadius.mdAll),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    FaIcon(_getCapabilityIcon(capability.id), size: 14, color: color),
                    const SizedBox(width: OmiSpacing.xs),
                    Text(
                      capability.getLocalizedTitle(context),
                      style: OmiType.footnote.copyWith(color: color, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ActionFieldsWidget extends StatelessWidget {
  const ActionFieldsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        // Only show if external integration is selected and actions are available
        if (!provider.isCapabilitySelectedById('external_integration') || provider.getActionTypes().isEmpty) {
          return const SizedBox.shrink();
        }

        return Column(
          children: [
            const SizedBox(height: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(left: 8.0, right: 8.0, bottom: 12.0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(context.l10n.scopes, style: OmiType.callout.copyWith(color: OmiColors.textSecondary)),
                      OmiIconButton(
                        icon:
                            const FaIcon(FontAwesomeIcons.solidCircleQuestion, color: OmiColors.textTertiary, size: 18),
                        label: context.l10n.docs,
                        onPressed: () {
                          launchUrl(Uri.parse('https://docs.omi.me/doc/developer/apps/Integrations'));
                        },
                      ),
                    ],
                  ),
                ),
                // List of action items - aligned with "Scopes" text
                Padding(
                  padding: const EdgeInsets.only(left: 8.0),
                  child: Column(
                    children: [
                      ...provider.getActionTypes().asMap().entries.map((entry) {
                        final index = entry.key;
                        final actionType = entry.value;
                        final isSelected = provider.actions.any((action) => action['action'] == actionType.id);
                        final isLast = index == provider.getActionTypes().length - 1;

                        return Column(
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 40,
                                  height: 40,
                                  decoration: const BoxDecoration(
                                    color: OmiColors.surface2,
                                    borderRadius: OmiRadius.mdAll,
                                  ),
                                  child: Center(
                                    child: FaIcon(
                                      _getIconForAction(actionType.id),
                                      color: Colors.grey.shade400,
                                      size: 16,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 14),
                                Expanded(
                                  child: Text(
                                    actionType.getLocalizedTitle(context),
                                    style: OmiType.callout,
                                  ),
                                ),
                                OmiSwitch(
                                  value: isSelected,
                                  onChanged: (value) {
                                    if (value) {
                                      provider.addSpecificAction(actionType.id);
                                    } else {
                                      provider.removeActionByType(actionType.id);
                                    }
                                  },
                                ),
                              ],
                            ),
                            if (!isLast)
                              Padding(
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                child: Divider(color: Colors.grey.shade800, height: 1),
                              ),
                          ],
                        );
                      }),
                    ],
                  ),
                ),
              ],
            ),
          ],
        );
      },
    );
  }

  FaIconData _getIconForAction(String actionId) {
    switch (actionId) {
      case 'create_conversation':
        return FontAwesomeIcons.solidComment;
      case 'create_facts':
        return FontAwesomeIcons.solidLightbulb;
      case 'read_conversations':
        return FontAwesomeIcons.solidComments;
      case 'read_memories':
        return FontAwesomeIcons.brain;
      case 'read_tasks':
        return FontAwesomeIcons.listCheck;
      default:
        return FontAwesomeIcons.puzzlePiece;
    }
  }
}

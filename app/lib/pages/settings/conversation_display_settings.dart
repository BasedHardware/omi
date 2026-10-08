import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ConversationDisplaySettings extends StatefulWidget {
  const ConversationDisplaySettings({super.key});

  @override
  State<ConversationDisplaySettings> createState() => _ConversationDisplaySettingsState();
}

class _ConversationDisplaySettingsState extends State<ConversationDisplaySettings> {
  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.conversationDisplaySettingsOpened();
  }

  Widget _buildThresholdSegments(ConversationProvider provider) {
    const thresholds = [60, 120, 180, 240, 300];

    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.md),
      child: Row(
        children: [
          for (final seconds in thresholds) ...[
            if (seconds != thresholds.first) const SizedBox(width: OmiSpacing.xs),
            Expanded(
              child: _ThresholdSegment(
                label: context.l10n.minLabel(seconds ~/ 60),
                selected: provider.shortConversationThreshold == seconds,
                onTap: () {
                  provider.setShortConversationThreshold(seconds);
                  PlatformManager.instance.analytics.shortConversationThresholdChanged(seconds);
                  setState(() {});
                },
              ),
            ),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final classic = Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.conversationDisplay)),
      body: Consumer<ConversationProvider>(
        builder: (context, provider, child) {
          return ListView(
            padding: const EdgeInsets.all(OmiSpacing.md),
            children: [
              OmiSettingsGroup(
                header: context.l10n.visibility,
                headerSubtitle: context.l10n.visibilitySubtitle,
                children: [
                  OmiSettingsRow.toggle(
                    leading: const FaIcon(FontAwesomeIcons.clock),
                    title: context.l10n.showShortConversations,
                    subtitle: context.l10n.showShortConversationsDesc,
                    value: provider.showShortConversations,
                    onChanged: (_) {
                      provider.toggleShortConversations();
                      PlatformManager.instance.analytics.showShortConversationsToggled(
                        provider.showShortConversations,
                      );
                    },
                  ),
                  OmiSettingsRow.toggle(
                    leading: const FaIcon(FontAwesomeIcons.trash),
                    title: context.l10n.showDiscardedConversations,
                    subtitle: context.l10n.showDiscardedConversationsDesc,
                    value: provider.showDiscardedConversations,
                    onChanged: (_) {
                      provider.toggleDiscardConversations();
                      PlatformManager.instance.analytics.showDiscardedConversationsToggled(
                        provider.showDiscardedConversations,
                      );
                    },
                  ),
                ],
              ),
              const SizedBox(height: OmiSpacing.xxl),
              OmiSettingsGroup(
                header: context.l10n.shortConversationThreshold,
                headerSubtitle: context.l10n.shortConversationThresholdSubtitle,
                children: [
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      OmiSettingsRow(
                        leading: const FaIcon(FontAwesomeIcons.clock),
                        title: context.l10n.durationThreshold,
                        subtitle: context.l10n.durationThresholdDesc,
                        value: context.l10n.minLabel(provider.shortConversationThreshold ~/ 60),
                      ),
                      _buildThresholdSegments(provider),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: OmiSpacing.xxl),
            ],
          );
        },
      ),
    );
    final provider = context.watch<ConversationProvider>();
    return IosNativeSurface(title: context.l10n.conversationDisplay, fallback: classic, toolbar: [
      NativeRow('display_back', context.l10n.back, symbol: 'chevron.left', action: (_) {
        Navigator.of(context).pop();
      })
    ], sections: [
      NativeSection(
          'visibility',
          [
            NativeRow('display_short', context.l10n.showShortConversations,
                subtitle: context.l10n.showShortConversationsDesc,
                kind: 'toggle',
                value: provider.showShortConversations, action: (_) {
              provider.toggleShortConversations();
              PlatformManager.instance.analytics.showShortConversationsToggled(provider.showShortConversations);
            }),
            NativeRow('display_discarded', context.l10n.showDiscardedConversations,
                subtitle: context.l10n.showDiscardedConversationsDesc,
                kind: 'toggle',
                value: provider.showDiscardedConversations, action: (_) {
              provider.toggleDiscardConversations();
              PlatformManager.instance.analytics.showDiscardedConversationsToggled(provider.showDiscardedConversations);
            }),
          ],
          title: context.l10n.visibility,
          footer: context.l10n.visibilitySubtitle),
      NativeSection(
          'threshold',
          [
            NativeRow('display_threshold', context.l10n.durationThreshold,
                subtitle: context.l10n.durationThresholdDesc,
                kind: 'choice',
                value: '${provider.shortConversationThreshold}',
                options: {
                  for (final seconds in [60, 120, 180, 240, 300]) '$seconds': context.l10n.minLabel(seconds ~/ 60)
                }, action: (value) {
              final seconds = int.parse(value as String);
              provider.setShortConversationThreshold(seconds);
              PlatformManager.instance.analytics.shortConversationThresholdChanged(seconds);
            })
          ],
          title: context.l10n.shortConversationThreshold,
          footer: context.l10n.shortConversationThresholdSubtitle),
    ]);
  }
}

/// One option of the short-conversation threshold picker: white when selected (INV-UI-1).
class _ThresholdSegment extends StatelessWidget {
  const _ThresholdSegment({required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected ? OmiColors.accent : OmiColors.surface2,
        borderRadius: OmiRadius.smAll,
        child: InkWell(
          borderRadius: OmiRadius.smAll,
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs, vertical: OmiSpacing.xs),
                child: Text(
                  label,
                  textAlign: TextAlign.center,
                  style: OmiType.footnote.copyWith(
                    color: selected ? OmiColors.onAccent : OmiColors.textSecondary,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

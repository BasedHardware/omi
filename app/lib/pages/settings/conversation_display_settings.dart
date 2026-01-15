import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
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
    MixpanelManager().conversationDisplaySettingsOpened();
  }

  Widget _buildSectionContainer({required List<Widget> children}) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: children,
      ),
    );
  }

  Widget _buildSectionHeader(String title, {String? subtitle}) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(
              subtitle,
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 14,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildToggleItem({
    required String title,
    required String description,
    required IconData icon,
    required bool value,
    required ValueChanged<bool>? onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFF2A2A2E),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Center(
              child: FaIcon(icon, color: Colors.grey.shade400, size: 16),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  description,
                  style: TextStyle(
                    color: Colors.grey.shade500,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Switch(
            value: value,
            onChanged: onChanged,
            activeColor: const Color(0xFF22C55E),
          ),
        ],
      ),
    );
  }

  Widget _buildThresholdSelector(ConversationProvider provider) {
    String getThresholdLabel(int seconds) {
      final minutes = seconds ~/ 60;
      return context.l10n.minLabel(minutes);
    }

    final thresholds = [
      (60, context.l10n.minLabel(1)),
      (120, context.l10n.minLabel(2)),
      (180, context.l10n.minLabel(3)),
      (240, context.l10n.minLabel(4)),
      (300, context.l10n.minLabel(5)),
    ];

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: const Color(0xFF2A2A2E),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Center(
                  child: FaIcon(
                    FontAwesomeIcons.clock,
                    color: Colors.grey.shade400,
                    size: 16,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.l10n.durationThreshold,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      context.l10n.durationThresholdDesc,
                      style: TextStyle(
                        color: Colors.grey.shade500,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFF2A2A2E),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  getThresholdLabel(provider.shortConversationThreshold),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Colors.white,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: thresholds.map((threshold) {
              final isSelected = provider.shortConversationThreshold == threshold.$1;
              return Expanded(
                child: GestureDetector(
                  onTap: () {
                    provider.setShortConversationThreshold(threshold.$1);
                    MixpanelManager().shortConversationThresholdChanged(threshold.$1);
                    setState(() {});
                  },
                  child: Container(
                    margin: EdgeInsets.only(
                      right: threshold != thresholds.last ? 8 : 0,
                    ),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    decoration: BoxDecoration(
                      color: isSelected ? const Color(0xFF22C55E).withValues(alpha: 0.2) : const Color(0xFF2A2A2E),
                      borderRadius: BorderRadius.circular(8),
                      border: isSelected ? Border.all(color: const Color(0xFF22C55E), width: 1) : null,
                    ),
                    child: Text(
                      threshold.$2,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                        color: isSelected ? Colors.white : Colors.grey.shade400,
                      ),
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        backgroundColor: const Color(0xFF000000),
        elevation: 0,
        leading: IconButton(
          icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          context.l10n.conversationDisplay,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
        ),
        centerTitle: true,
      ),
      body: Consumer<ConversationProvider>(
        builder: (context, provider, child) {
          return SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildSectionHeader(
                  context.l10n.visibility,
                  subtitle: context.l10n.visibilitySubtitle,
                ),
                _buildSectionContainer(
                  children: [
                    _buildToggleItem(
                      icon: FontAwesomeIcons.clock,
                      title: context.l10n.showShortConversations,
                      description: context.l10n.showShortConversationsDesc,
                      value: provider.showShortConversations,
                      onChanged: (_) {
                        provider.toggleShortConversations();
                        MixpanelManager().showShortConversationsToggled(provider.showShortConversations);
                      },
                    ),
                    const Divider(height: 1, color: Color(0xFF3C3C43)),
                    _buildToggleItem(
                      icon: FontAwesomeIcons.trash,
                      title: context.l10n.showDiscardedConversations,
                      description: context.l10n.showDiscardedConversationsDesc,
                      value: provider.showDiscardedConversations,
                      onChanged: (_) {
                        provider.toggleDiscardConversations();
                        MixpanelManager().showDiscardedConversationsToggled(provider.showDiscardedConversations);
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 32),
                _buildSectionHeader(
                  context.l10n.shortConversationThreshold,
                  subtitle: context.l10n.shortConversationThresholdSubtitle,
                ),
                _buildSectionContainer(
                  children: [
                    _buildThresholdSelector(provider),
                  ],
                ),
                const SizedBox(height: 32),
              ],
            ),
          );
        },
      ),
    );
  }
}

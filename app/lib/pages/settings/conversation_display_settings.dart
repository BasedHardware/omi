import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

class ConversationDisplaySettings extends StatefulWidget {
  const ConversationDisplaySettings({super.key});

  @override
  State<ConversationDisplaySettings> createState() => _ConversationDisplaySettingsState();
}

class _ConversationDisplaySettingsState extends State<ConversationDisplaySettings> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Conversation Display'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: Consumer<ConversationProvider>(
        builder: (context, provider, child) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _buildSectionHeader('Visibility'),
              const SizedBox(height: 12),
              _buildToggleCard(
                icon: Icons.timelapse,
                title: 'Show Short Conversations',
                subtitle: 'Display conversations shorter than the threshold below',
                value: provider.showShortConversations,
                onChanged: (_) => provider.toggleShortConversations(),
              ),
              const SizedBox(height: 12),
              _buildToggleCard(
                icon: Icons.delete_outline,
                title: 'Show Discarded Conversations',
                subtitle: 'Include conversations that were marked as discarded',
                value: provider.showDiscardedConversations,
                onChanged: (_) => provider.toggleDiscardConversations(),
              ),
              const SizedBox(height: 24),
              _buildSectionHeader('Short Conversation Threshold'),
              const SizedBox(height: 8),
              Text(
                'Conversations shorter than this duration will be hidden unless "Show Short Conversations" is enabled',
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey.shade500,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 16),
              _buildThresholdSelector(provider),
            ],
          );
        },
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0),
      child: Text(
        title,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 16,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _buildToggleCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return GestureDetector(
      onTap: () => onChanged(!value),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: value ? Colors.deepPurple : Colors.grey.shade800,
            width: 1,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: value ? Colors.deepPurple.withValues(alpha: 0.2) : Colors.grey.shade800,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(
                icon,
                size: 20,
                color: value ? Colors.deepPurple.shade200 : Colors.grey.shade400,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: value ? Colors.white : Colors.grey.shade300,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade500,
                      height: 1.3,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            _buildCustomToggle(value),
          ],
        ),
      ),
    );
  }

  Widget _buildCustomToggle(bool value) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      width: 48,
      height: 28,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: value ? Colors.deepPurple : Colors.grey.shade700,
      ),
      child: Stack(
        children: [
          AnimatedPositioned(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeInOut,
            left: value ? 22 : 2,
            top: 2,
            child: Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.2),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildThresholdSelector(ConversationProvider provider) {
    final thresholds = [
      (60, '1 min'),
      (120, '2 min'),
      (180, '3 min'),
      (240, '4 min'),
      (300, '5 min'),
    ];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.shade800, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(
                    Icons.timer_outlined,
                    size: 18,
                    color: Colors.grey.shade400,
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    'Duration Threshold',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                    ),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.deepPurple.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  _getThresholdLabel(provider.shortConversationThreshold),
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Colors.deepPurple.shade200,
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
                    setState(() {});
                  },
                  child: Container(
                    margin: EdgeInsets.only(
                      right: threshold != thresholds.last ? 8 : 0,
                    ),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    decoration: BoxDecoration(
                      color:
                          isSelected ? Colors.deepPurple.withValues(alpha: 0.3) : Colors.black.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(8),
                      border: isSelected ? Border.all(color: Colors.deepPurple, width: 1) : null,
                    ),
                    child: Column(
                      children: [
                        Text(
                          threshold.$2,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                            color: isSelected ? Colors.white : Colors.grey.shade400,
                          ),
                        ),
                      ],
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

  String _getThresholdLabel(int seconds) {
    final minutes = seconds ~/ 60;
    return '$minutes min';
  }
}

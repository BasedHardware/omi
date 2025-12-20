import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/pages/home/widgets/stats_detail_sheet.dart';

class StatsWidget extends StatelessWidget {
  const StatsWidget({super.key});

  // Calculate total words from all conversations
  int _calculateTotalWords(List<ServerConversation> conversations) {
    var totalWords = 0;
    for (final conversation in conversations) {
      for (final segment in conversation.transcriptSegments) {
        final text = segment.text.trim();
        if (text.isEmpty) continue;
        totalWords += text.split(RegExp(r'\s+')).length;
      }
    }
    return totalWords;
  }

  // Format large numbers (e.g., 1500 -> 1.5K)
  String _formatNumber(int number) {
    if (number >= 1000000) {
      return '${(number / 1000000).toStringAsFixed(1)}M';
    } else if (number >= 1000) {
      return '${(number / 1000).toStringAsFixed(1)}K';
    }
    return number.toString();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<ConversationProvider, MemoriesProvider>(
      builder: (context, conversationProvider, memoriesProvider, child) {
        final filteredConversations = conversationProvider.filteredConversations;
        final conversationsCount = filteredConversations.length;
        final memoriesCount = memoriesProvider.memories.length;
        final wordsCount = _calculateTotalWords(filteredConversations);

        return SizedBox(
          width: double.infinity,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                backgroundColor: Colors.transparent,
                builder: (_) => StatsDetailSheet(
                  conversations: filteredConversations,
                  memoriesCount: memoriesCount,
                  wordsCount: wordsCount,
                ),
              );
            },
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              padding: const EdgeInsets.only(left: 20, right: 5, top: 12, bottom: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(12),

              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                mainAxisSize: MainAxisSize.max,
                children: [
                  _buildStat(
                    count: conversationsCount,
                    label: 'Conversations',
                  ),
                  Container(
                    width: 1,
                    height: 24,
                    color: Colors.white24,
                  ),
                  _buildStat(
                    count: memoriesCount,
                    label: 'Memories',
                  ),
                  Container(
                    width: 1,
                    height: 24,
                    color: Colors.white24,
                  ),
                  _buildStat(
                    count: wordsCount,
                    label: 'Words',
                  ),
                  // const SizedBox(width: 8),
                  const Icon(
                    Icons.chevron_right,
                    color: Colors.white38,
                    size: 20,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildStat({
    required int count,
    required String label,
  }) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(
          _formatNumber(count),
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: const TextStyle(
            color: Colors.white70,
            fontSize: 10,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}



import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_badge.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_loading_badge.dart';

class DesktopSearchResultHeader extends StatelessWidget {
  const DesktopSearchResultHeader({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, provider, child) {
        var onSearches = provider.previousQuery.isNotEmpty;
        var isSearching = provider.isFetchingConversations;

        if (!onSearches) {
          return const SizedBox.shrink();
        }

        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 16),
          child: isSearching
              ? _buildSearchLoadingIndicator()
              : provider.totalSearchPages > 0
                  ? _buildSearchResults(provider)
                  : const SizedBox.shrink(),
        );
      },
    );
  }

  Widget _buildSearchLoadingIndicator() {
    return const OmiLoadingBadge(label: 'Searching...');
  }

  Widget _buildSearchResults(ConversationProvider provider) {
    return Row(
      children: [
        const Row(
          children: [
            OmiIconButton(
              icon: Icons.search_rounded,
              style: OmiIconButtonStyle.neutral,
              size: 24,
              iconSize: 12,
              borderRadius: 6,
              onPressed: null,
            ),
            SizedBox(width: 6),
            OmiBadge(
              label: 'Search results',
              fontSize: 12,
              color: ResponsiveHelper.textTertiary,
              borderRadius: 6,
              backgroundColor: ResponsiveHelper.backgroundSecondary,
            ),
          ],
        ),
        const SizedBox(width: 12),
        Text(
          '"${provider.previousQuery}"',
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: ResponsiveHelper.textSecondary,
            fontStyle: FontStyle.italic,
          ),
        ),
      ],
    );
  }
}

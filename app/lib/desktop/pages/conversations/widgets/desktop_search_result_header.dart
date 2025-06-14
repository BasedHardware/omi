import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

/// Premium minimal search result header for desktop
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
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(
                ResponsiveHelper.purplePrimary.withOpacity(0.8),
              ),
            ),
          ),
          const SizedBox(width: 8),
          const Text(
            'Searching...',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchResults(ConversationProvider provider) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
          ),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.search_rounded,
                size: 14,
                color: ResponsiveHelper.textTertiary,
              ),
              SizedBox(width: 6),
              Text(
                'Search results',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textTertiary,
                ),
              ),
            ],
          ),
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
